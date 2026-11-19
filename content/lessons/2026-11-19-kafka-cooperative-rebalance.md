# Kafka 为什么先收回分区，再把它交给新消费者

通知服务的消费组 G 正在处理三条 Kafka 分区日志。A 负责 P0、P1，B 负责 P2，现在增加消费者 C，希望让三个人各处理一条。最自然的新分工是 A 留下 P0，B 留下 P2，C 接过 P1。问题并不在于怎样写出这张表，而在于表还没同时送达所有人时，谁可以开始工作。若 C 已经开始处理 P1，A 却还认为 P1 属于自己，一份看起来没有重复的目标表，仍可能对应两个重叠的处理者。

昨天讲了组成员与代次检查：超时后可以换人，过期请求不能继续提交进度。今天改看所有成员都健康、愿意配合的正常交接。我们想保住同一分区只有一个协议持有者，又希望无需迁移的 P0、P2 少做撤回和重新初始化。若每次组变化都把所有分区清空，安全关系容易解释，但稳定的工作也会被迫参与整轮拆卸。

这个简单方案就是 eager 重平衡的思路：成员先撤销所有持有分区，再加入新一轮分配。数据量小、分区状态很轻时，它是直接可用的办法。不过有状态的处理者可能维护缓存、聚合状态或恢复位置，撤回后重新接收同一分区，也可能触发额外收尾与初始化。为降低这类无谓变化，Kafka 的 cooperative 协议允许入组前保留已有分区，只对需要迁移的部分安排交接。 [两种撤回规则的源码契约](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/ConsumerPartitionAssignor.java#L246-L258)

本文固定 Java 客户端与 broker 4.1.0，使用 `subscribe` 管理的普通消费者组，`group.protocol=classic`，所有成员的 `partition.assignment.strategy` 都只配置 `org.apache.kafka.clients.consumer.CooperativeStickyAssignor`，关闭自动提交。组内没有失败、订阅变化或新的成员变化，应用按分区顺序处理，撤回回调能成功收尾。这里研究经典组的协作式分配器，不等同于 Kafka 新 `consumer` 协议，也不是 Kafka Streams 专用分配器。编号与时序均为教学模型，没有实际扩容或性能测量。 [分配器的适用接口](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/CooperativeStickyAssignor.html)

在经典组里，broker 上的组协调器协调成员入组与分工结果的传播，被选为组 leader 的消费者运行分配器。这个组 leader 不是保存消息的分区 leader。成员随订阅元数据上报当前持有的分区，分配器因而同时拥有两份信息：大家想订阅什么，以及此刻谁还持有什么。只看未来目标，无法安全解释迁移；必须把旧持有关系也当作分配输入。 [持有关系进入入组元数据](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java#L299-L318) · [组 leader 收集并运行分配](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java#L649-L691)

选择本例的期望分工为 A:{P0}、B:{P2}、C:{P1}。它只移动一条分区；真实算法选择哪一条，还取决于成员和订阅等输入，这里不声称某次运行必然得到这个具体编号。当前上报却仍为 A:{P0,P1}、B:{P2}、C:{}。P1 的新主人想要它，旧主人还报告持有它，这个交集就是需要先完成撤回的部分。

看图一。假如直接把目标作为本轮可执行分工，C 的新消息先到、A 的撤回消息后到，会发生什么？

![图一。教学反事实。当前持有为 A:{P0,P1}、B:{P2}、C:{}，期望分工为 A:{P0}、B:{P2}、C:{P1}。若立刻让 C 按目标开始，而 A 还未得知撤回，A 和 C 会同时认为自己持有 P1。箭头表示计划与消息送达顺序；最后一格不是 Kafka 协作式协议实际采用的分配。](assets/figures/kafka-cooperative-target.svg)

这里的洞察是，期望分工和本轮可以发布的分工不必相同。分配器先求目标，再把“要交给新人、却仍由别人持有”的分区从本轮结果中拿掉。于是第一轮返回 A:{P0}、B:{P2}、C:{}。C 暂时没有分区，这不是忘了给它工作，而是在保留一个交接缺口：P1 的新主人要等旧主人先退出。

4.1.0 的 `CooperativeStickyAssignor.assignPartitions` 先取得基础分配，找出正在转移的分区，再调用 `adjustAssignment`，从新主人的列表里删除这些分区。它没有通过覆盖 A 的本地变量来远程收回 P1，而是把安全的中间结果交给协议继续推进。 [期望分配与本轮调整](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/CooperativeStickyAssignor.java#L110-L130)

A 收到第一轮结果，把自己原有的 {P0,P1} 与新的 {P0} 相减，发现要撤回的只有 P1。客户端在更新持有集合之前调用 `onPartitionsRevoked({P1})`。假设 A 已完成 P1 的事件 100，回调停止继续为 P1 接受处理，完成相关收尾，并成功提交下一位置 101。P0 无需在这次回调里被一起清空。B 没有要撤回的分区，P2 也无需做同样的撤回操作。 [差集、撤回回调与重新入组](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java#L421-L447)

图二沿真实采用的教学路径推进。第一轮的 C 为什么可以为空，第二轮又凭什么把 P1 交给它？

![图二。教学交接时序。第一轮结果为 A:{P0}、B:{P2}、C:{}，P1 暂不交给 C。A 撤回 P1，成功保存下一位置 101，更新持有关系后请求重新入组。下一轮上报中 A 只持有 P0，B 持有 P2，C 为空，P1 已无人报告持有。第二轮在期望分工不变的条件下返回 A:{P0}、B:{P2}、C:{P1}，C 从保存位置 101 恢复。箭头表示时间，P0、P2 无需被撤回再分配。](assets/figures/kafka-cooperative-rounds.svg)

完成撤回后，A 的持有集合只剩 P0。客户端因为发生过撤回而请求重新入组，新的订阅元数据不再把 P1 列为 A 所有。假设第二轮期望分工不变，分配器这次看见 P1 已经没有旧持有者，便不再从 C 的结果中删除它。C 取得 P1，执行新增分区的回调，再按 G 保存的位置 101 恢复读取。至此，分工达到目标，迁移也有了明确的结束条件：旧持有关系已退出，新持有者才获分配。

先收回、后授予，牺牲的是 P1 在两轮之间的一段空档。它换掉了“所有分区先全部撤销”这个更大的条件。P0、P2 保留持有关系和相应本地状态，不意味着整个入组过程零等待，也不承诺每个时刻都在持续拉取：成员仍须参与组协议，代次也可能改变，消费线程可能等待协调。节省的主要是无必要的撤回、状态拆卸与重新建立，不能把这张机制图当作吞吐提升的测量。 [KIP-429 对增量交接与保留关系的设计](https://cwiki.apache.org/confluence/spaces/KAFKA/pages/103090108/KIP-429+Kafka+Consumer+Incremental+Rebalance+Protocol)

协议的不变量是，在这条正常协作路径中，仍被某成员报告持有的迁移分区，不能同时直接授予另一成员。若删掉第一轮对 C 的过滤，就回到图一的重叠；若 A 撤回后仍在下一轮报告 P1，分配器又缺少把它安全交出去的依据。因此，分配器、持有集合更新和下一轮上报必须互相配合。“少迁移”的目标也很重要：若目标每轮大幅翻转，就可能不断制造新的撤回，原本希望省掉的工作重新出现。

应用侧的完成边界同样不能省略。`onPartitionsRevoked` 是通知，不是能否接受新分工的投票。官方接口明确说，回调抛出异常不会否决分配变化，捕获异常后协议也不会自动反复重试这个回调。如果应用把 P1 交给了自己启动的后台线程，回调返回前却没有让它结束旧处理，更新客户端的持有集合不会替应用杀掉这个线程。旧任务仍可能操作数据库或发送短信。应用要把停止派工、必要收尾、可靠进度与异常处理接起来，不能把“调用过撤回回调”当成业务已交还资源的证据。 [回调的通知语义与异常边界](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/ConsumerRebalanceListener.java#L76-L94)

若 A 真正超时出局，也不能照搬图二，等待它完成一次正常撤回。分区可能已经交给别人，客户端以后观察到的是 `onPartitionsLost` 这类丢失通知，旧处理者未必还有提交资格。昨天的成员与代次校验继续承担拒绝旧提交的职责，外部效果仍需额外约束。正常合作交接减少不必要的中断，失联后的隔离处理过期执行者，两者面对的条件不同。 [正常撤回与已经丢失的区别](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/ConsumerRebalanceListener.java#L51-L66)

代价因此落在额外的协议轮次、持有元数据、分配器约束和应用回调管理上。本文的一次稳定迁移可用两轮说明，但持续成员变化、失败或目标调整时，不保证所有重平衡恰好两轮完成。迁移分区很少、状态重建代价较高时，这种局部交接更有吸引力；若所有分区都需要搬家，保留关系带来的收益会缩小。启用也需要全组兼容的配置，不能把某一个客户端换成协作式分配器，就默认整个组已经按这套约定运行。

Linux 的 RCU 可以提供一个结构上的对照：从共享结构移除一个对象的入口后，旧读者可能仍握着引用，不能立刻释放它；等待既有读侧临界区结束后，才能进入回收。共同点是把“安排改变”与“旧使用者已经退出”分开，为后一步建立证据。差异在于 RCU 允许多个读者并存，等待是为了安全释放内存；Kafka 这里安排的是独占分区的交接，通过成员元数据与协议轮次推进。两者都不能仅凭新结构已经写好，就跳过旧使用关系的结束条件。 [Linux RCU 的移除、等待与回收](https://docs.kernel.org/RCU/whatisRCU.html#rcu-overview)

留一个推演。若第二轮开始前 C 又退出，第一轮没交出去的 P1 一定还要交给 C 吗？若 A 的回调只发了取消信号就返回，后台处理 P1 的线程仍未结束，图二中哪个协议事实成立，哪个业务事实还没有成立？最后把初始状态改成 C 接到一条从未被别人持有的新分区，它是否也必须为了“撤回”额外等一轮？
