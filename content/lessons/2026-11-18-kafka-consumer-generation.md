# Kafka 换了消费者，旧进程为什么不能再提交进度

订单 42 的付款事件在 Kafka 分区 P0 的 100，发货事件在 101。消费组 G 把 P0 分给进程 A，保存的下一读取位置仍是 100。A 处理完付款，准备把进度提交为 101，但请求迟迟没有到达。它随后长时间停顿，Kafka 把分区交给了 B。B 从 100 重读，处理完付款与发货，提交到 102。此时 A 的旧请求终于出现：协调器该接受 101，还是把它挡住？

前一讲把处理结果与恢复位置放进同一笔事务，保留了“处理者仍然有资格”的前提。今天专门拆开这项前提，先看普通进度提交。最自然的办法是只按组名和分区保存最后收到的值。这样实现简单，但网络到达顺序不代表工作资格的先后。旧请求若覆盖 B 的 102，恢复位置就倒退到 101，后续又可能重做发货。只认识“这是 G 的提交”，还不足以知道是谁、在哪一轮分工里提交。

另一个自然办法是通知 A：“你已经失去 P0，请停止。”正常退出和协作式交接确实有价值，却覆盖不了这个例子。A 可能停在垃圾回收、系统调度或断网期间，收不到通知；已经发出的请求也不会自动消失。若非要证明 A 已经彻底死亡再换人，系统又可能无限等下去。超时因此是一项推进服务的判断，不能被当成对远端进程死亡的证明。

本文固定 Kafka Java 客户端与 broker 4.1.0，使用 `subscribe` 参与的普通消费者组，显式设置 `group.protocol=classic`，不配置静态成员的 `group.instance.id`，关闭自动提交。例子假设协调器始终可用，P0 的数据与保存位置没有过期。A、B 是不透明 member ID 的教学简称，组代次 7、8 和消息时序也是教学设定，没有运行进程暂停或网络故障实验。这里没有使用手工 `assign` 模式，也不把经典组的规则推广成 Kafka 新消费者协议的完整实现。

Kafka 把组管理交给 broker 上的组协调器。它掌握 G 当前有哪些成员、处于哪一轮组代次，以及已提交位置；分配协议让参与者取得该轮分工。P0 的日志 leader 负责保存与提供记录，组协调器负责 G 的协作状态，两种职责可以在同一机器，也可以分开。换一个消费者不需要搬动 P0 的历史，只需新处理者取得分工，并从组位置恢复。 [消费者组、订阅与故障接管的接口背景](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html#consumergroups)

关键洞察是，把“我曾经取得工作”变成每次提交都要重新核对的资格。经典组维护 generation ID，下面称组代次。形成下一代时，协调器推进这个编号；客户端把 member ID 和当时的组代次一起放进提交请求。组名确定哪份协作状态，成员身份确定谁在发请求，代次确定它依据哪一轮分工。这不是消息 offset、生产者 epoch 或分区 leader epoch，它们分别编号不同的对象。 [组代次的推进](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/classic/ClassicGroup.java#L1287-L1302) · [提交请求携带的身份与代次](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java#L1300-L1358)

现在回到 A。第 7 代时，它对 P0 提交下一位置 101，请求已按这一代构造并发送，但被延迟。随后 A 的停顿使心跳中断，超过会话超时，协调器移除 A 并触发重新分配。假设下一次稳定分工是第 8 代，P0 归 B。B 以自己的成员身份与第 8 代提交 102，协调器接受并保存。数字 102 表示 100、101 这段已由本例 B 顺序处理完，下次从 102 开始。 [经典组会话超时与重新分配](https://kafka.apache.org/41/configuration/consumer-configs/#session.timeout.ms)

图一追踪的是同一份已经在途的旧请求。协调器把 P0 交给 B 后，A 所在操作系统是否仍保留那份进程内存，会改变请求的提交资格吗？

![图一。教学时序，向下箭头表示时间。G 第 7 代由 A 处理 P0，A 的下一位置 101 提交在途延迟。A 心跳中断超时后被移除，第 8 代 P0 交给 B；B 处理 100、101 后提交 102。旧请求携带成员 A、组代次 7 到达时，A 已不是当前成员，协调器返回 UNKNOWN_MEMBER_ID，G 对 P0 的保存位置仍为 102。](assets/figures/kafka-group-handoff.svg)

旧请求到达时，协调器面对的是当前第 8 代的状态，不会按 A 发出时的世界处理。4.1.0 的 `OffsetMetadataManager.commitOffset` 先调用组校验，再生成保存新位置的记录。对本例经典组，`ClassicGroup.validateMember` 找不到 A，返回 `UNKNOWN_MEMBER_ID`，请求不能把正式位置改回 101。这个结束条件与请求有没有成功传过网络不同：只有协调器按当前状态接受提交，才可能更新组位置。 [先校验、再处理位置更新](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/OffsetMetadataManager.java#L600-L625) · [成员不存在时的拒绝](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/classic/ClassicGroup.java#L797-L817)

如果只检查成员 ID，是否已经足够？改变一个条件：这次 A 没有被移除，而是其他成员离开引发换代。A、B 都参与了第 8 代，当前分工为 A 负责 P1、B 负责 P0，但一个按第 7 代构造的旧请求仍在途。身份可以延续，工作安排却已更新，过去那份请求不应借“我还在名单里”重新取得效力。

图二是独立分支，专门把成员检查设为通过。当前第 8 代同时认识 A、B，但到达的请求仍是第 7 代，下一位置仍为 101。这次会卡在哪一项条件？

![图二。独立教学分支。当前 G 为第 8 代，成员包括 A、B，分工为 A 负责 P1、B 负责 P0。旧请求仍携带 A、组代次 7 和 P0 下一位置 101。成员检查通过，代次检查发现 7 不等于 8，返回 ILLEGAL_GENERATION。箭头表示校验步骤，不表示参与新一代后替旧请求换证。](assets/figures/kafka-group-generation-check.svg)

`ClassicGroup.validateOffsetCommit` 在验证成员之后比较请求代次与当前代次，不同就返回 `ILLEGAL_GENERATION`。因此，成员检查阻止已经出局的执行者，代次检查阻止仍被认识的执行者使用过期请求。只有旧进程自己检查一次“我还在组里”是不够的：检查之后也可能换代，资格必须接到真正接受更改的入口上。 [成员与代次的连续校验](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/classic/ClassicGroup.java#L829-L869)

本篇的不变量由此可以说准：在所选经典组路径中，过期成员或过期代次的普通提交不能改变当前的组恢复位置。它并不是“位置数字永远只能变大”。单纯取两个数字的最大值，无法证明较大的值来自当前有资格的执行者，也无法表达应用有意重新定位后保存新位置的需求。位置说明做到哪里，成员与代次说明依据哪份协作资格；两类问题不能互相替代。

客户端也会预先阻止已经知道无资格的提交。`ConsumerCoordinator` 对自动分配的分区先取得稳定组代次，如果当前已不在有效组状态，会直接让提交失败。若请求已发出而服务端返回成员或代次错误，客户端再按自身状态处理重新入组与提交异常，应用常见的是 `CommitFailedException`。图一刻意观察已经在途的请求，并不是声称正常客户端恢复后一定还会主动发出旧提交。 [本地稳定代次检查](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java#L1302-L1326) · [旧提交响应的处理](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java#L1431-L1451)

失败以后，不能把同一批旧工作简单换上新代次再提交。应通过消费者协议确认现在持有哪些分区，按可靠的组位置和业务规则恢复，并处理旧任务的收尾。代次校验不检查每条业务是否已经完成，也不代替应用管理线程池里的旧任务。若后台线程处理缓慢，前台仍持续 `poll`，它甚至可能一直满足调用节奏，进度与资源管理还需应用自己保证。

这也解释了为什么心跳之外还有 `max.poll.interval.ms`：后台仍能发心跳，不代表主处理循环仍在推进。对本文动态成员，长时间不调用 `poll` 时客户端会主动离组，让其他处理者有机会接手。调大间隔可以容纳较慢批次，却可能延后重新分配；会话超时设得太短则更容易把暂时停顿变成换人。代次隔离没有消灭误判，它让系统可以在不确定旧进程是否死亡时继续推进，同时拒绝过期提交。 [心跳存活与处理推进的区别](https://kafka.apache.org/41/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html#failuredetection)

代价是协调器要维护成员、代次和组状态，客户端要参与重新分配、等待并恢复，故障窗口里的记录仍可能被重读。尤其要看清保护范围：A 恢复后若依据本地缓存直接发送短信，短信网关不会自动检查 Kafka 的组代次。Kafka 拒绝旧位置提交，不能收回已经发出的短信，也不是对进程的远程终止。昨天把结果与位置放进 Kafka 事务，正是把更多效果接入受协调的提交；外部效果仍需要接收端自己的幂等或资格校验。

etcd 的锁给出了一个具体的结构比较。锁与租约让调用者获得一个归属键，但进程暂停到租约过期后仍可能恢复。etcd Go 客户端 3.6.0 的 `Mutex.IsOwner()` 返回“这个键的创建修订号仍等于我取得时的修订号”的比较条件；把它放进同一个 etcd 事务的 `If`，再在 `Then` 中更新受保护的键，才把旧持有者的资格接到资源更新入口。Kafka 检查当前组成员与代次，etcd 检查锁归属键的当前状态，两者都不要求先证明旧进程已死。区别是 etcd 条件直接保护同一事务内的键更新，Kafka 这里保护组位置提交；两者都不能凭本地记忆自动隔离一个不参与检查的外部服务。 [etcd 锁的保护契约](https://etcd.io/docs/v3.6/dev-guide/api_concurrency_reference_v3/#service-lock) · [IsOwner 的实际比较条件](https://github.com/etcd-io/etcd/blob/v3.6.0/client/v3/concurrency/mutex.go#L144-L146)

留一个推演。图一若 A 的 101 在换代前已经被接受，B 接手应从哪里开始？再沿图二，假如只保留成员检查，哪个过期事实会被误当成当前资格？最后把提交改成“直接给短信网关发请求”，哪个部件必须新增判断，才能让同一套隔离思想真正覆盖这项效果？
