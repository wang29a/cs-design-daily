# Kafka 怎样把处理结果与消费进度一起提交

通知服务从 Kafka 读到订单 42 的付款事件，生成一条“待发送付款通知”的任务，再写回另一个 Kafka 主题。结果写成功后，服务还要保存消费进度。此时进程退出：任务已经存在，恢复位置却还停在付款事件之前。新进程重读这笔付款，又生成一份任务。昨天的事务读取保证不会交付中止的数据，今天继续追问：怎样把结果与“以后从哪里继续”接成一份可恢复的承诺？

先把场景固定在 Kafka Java 客户端与 broker 4.1.0。输入主题的分区叫 P0，付款事件在 offset 100；消费组 G 保存的下一位置是 100。服务只负责把这条输入转换成一条 Kafka 任务，输出到另一主题的 Q0，Q0 下一可写位置为 200。输入已可读，历史在恢复期间不会过期，没有其他输出插入。下面的编号与崩溃都是教学设定，没有运行集群或注入故障，真实短信发送不在本篇处理范围内。

最自然的顺序是先写结果，再保存 G 的位置 101。101 表示下次从输入 101 开始，已经处理的是 100；它与输出位置 200 属于两条日志。若在两步之间退出，Q0 已经有任务 200，G 仍是 100，恢复便会重做。先提交位置再写结果也不行：G 已是 101，任务尚未产生就退出，恢复会跳过付款。调整两次调用的先后，只是选择可能重复还是可能漏掉。 [先后提交的两个故障窗口](https://kafka.apache.org/41/design/design/#message-delivery-semantics)

看图一。两种顺序从同一状态分别出发，崩溃恰好发生在第一步完成之后。哪一份信息在冒充“这次转换已经完成”？

![图一。两条互斥的教学时序。输入 P0 的 100 是付款，G 的初始下一位置为 100。A 先把任务写到 Q0 的 200，再崩溃，G 仍为 100，恢复会重做并可能新增重复任务。B 先把 G 的下一位置提交为 101，再崩溃，Q0 尚无任务，恢复跳过输入 100。向下箭头表示每支内部的先后，不表示两支接续执行。](assets/figures/kafka-eos-split-commit.svg)

如果下游本来就按稳定事件标识去重，允许重做的方案完全有用，它把重复处理责任交给结果接收者。但普通追加日志不会因内容或 key 相同就自动覆盖。前天讲过的幂等生产者，识别的是同一批次的网络重试；新进程重读输入，再调用一次 `send`，属于新的应用发送，不能靠那份保证自动合并。

关键洞察是，消费组进度也保存在 Kafka 的内部主题里。它原本是另一项独立更新，现在可以成为同一笔事务里的数据：一边写输出任务，一边声明 G 对 P0 的下一位置为 101。两者共同提交或中止。系统不再试图让应用把两次独立成功排成完美顺序，而是把“做出了什么”与“据此可以略过哪些输入”交给同一个提交决定。 [结果与消费位置同属一笔事务](https://kafka.apache.org/41/design/design/#using-transactions)

具体接口是事务生产者的 `sendOffsetsToTransaction`。它把指定位置送给消费组协调器，并标为当前事务的一部分。调用返回只说明协调器已接收并确认请求，并不表示 G 已经提交 101。这个区别正是消除故障窗口的条件：若待提交的进度一到就立刻成为恢复位置，输出尚可中止时，输入就已经可能被跳过。 [4.1.0 API 对待提交位置的约定](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/KafkaProducer.java#L683-L709)

让 G 使用普通消费者组协议，本篇固定 `group.protocol=classic`，关闭 `enable.auto.commit`，并且不额外调用消费者的 `commitSync` 或 `commitAsync`。输入与输出的消费者都用 `read_committed`，处理者顺序处理 P0，一次只取这条输入。生产者配置稳定的 `transactional.id`，例如 `payment-task-worker-0`，先完成 `initTransactions`。这个标识由该逻辑工作者跨重启复用，同时运行的不同工作者不能共用它。处理与提交期间假设分区归属稳定，后面再讨论归属变化。

第一次处理记为事务 T1。消费者读到 P0 的 100，本地下一读取位置变为 101，但 G 保存的位置仍为 100。生产者开始 T1，把通知任务追加到 Q0 的 200，再用 `sendOffsetsToTransaction` 把 `{P0: 101}` 和 `consumer.groupMetadata()` 一起送入 T1。实际 API 还支持保存输入的 leader epoch 元数据，位置应从已完整处理的记录范围计算，不能把只处理了一部分的拉取批次全算进去。

组协调器怎样避免把 101 提前当真？4.1.0 的 `OffsetMetadataManager` 在重放事务位置记录时，把它放进 `pendingTransactionalOffsets`，与正式位置分开。结束标记到来后，COMMIT 分支才把待定值移入正式位置；ABORT 则撤掉待定值。这里保存的 101 是输入 P0 的恢复位置值，不是内部主题这条记录自身的 offset。 [事务位置的暂存路径](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/OffsetMetadataManager.java#L1164-L1177) · [按事务决定兑现位置](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/OffsetMetadataManager.java#L1203-L1247)

事务协调器与组协调器因此各有职责：前者推进事务决定及相关分区的结束处理，后者管理 G 的进度并参与同一事务。Q0 的任务则沿昨天的路径等待稳定边界，再由 `read_committed` 消费者筛选。参与日志可以在不同机器上，标记并非同时到达；本篇比较的是事务处理完成后可用于恢复的结果，不声称任意时刻跨分区读取都得到同一份数据库式快照。请求稳定位置时若仍有待定事务，组协调器也可以返回 `UNSTABLE_OFFSET_COMMIT`，让读取方等待结果。 [未决位置的稳定读取检查](https://github.com/apache/kafka/blob/4.1.0/group-coordinator/src/main/java/org/apache/kafka/coordinator/group/OffsetMetadataManager.java#L879-L908)

现在让进程在这两项写入都已被接收、但尚未请求提交 T1 时退出。图二沿一条完整恢复时序向下画：Q0 的 200 是否还会被下游当成任务？重新生成的任务又占哪个位置？

![图二。教学恢复时序，无其他 Q0 写入。T1 把任务写到 Q0 的 200，并暂存 G 对 P0 的下一位置 101，随后在请求提交前崩溃。新生产者以相同 transactional.id 初始化，使 T1 中止并完成相关处理；Q0 的 201 是 ABORT 标记，200 被稳定读取过滤，G 仍为 100。恢复后重读 P0 的 100，T2 把新任务写到 Q0 的 202，并把下一位置 101 纳入同一事务。T2 提交完成，203 为 COMMIT 标记，下游只交付任务 202，G 的恢复位置成为 101。箭头表示时间。](assets/figures/kafka-eos-recovery.svg)

新进程复用相同 `transactional.id`，完成 `initTransactions` 后再依据稳定的组位置恢复。这个初始化会处理前一实例留下的未完成事务；本例 T1 从未开始提交，因此被中止。假设 Q0 在 201 追加 ABORT，相关标记复制与事务处理都已完成，任务 200 虽还占日志位置，下游不会把它作为有效输出，G 的位置仍是 100。 [初始化如何处理前一实例的事务](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/KafkaProducer.java#L622-L631)

消费者于是重读付款 100，转换逻辑确实又执行一次。在新事务 T2 中，任务写到 Q0 的 202，下一输入位置 101 再次加入事务。提交 T2，假设 Q0 的 COMMIT 标记位于 203；待相关处理完成，G 的恢复位置为 101，下游只拿到有效任务 202。第一次尝试留下的 200 被过滤，两个控制标记也不作为任务交付。“只产生一次有效结果”不要求处理函数只调用一次，更不要求日志物理上只存在一份尝试。

如果只是中止事务而没有重启进程，本地消费者仍可能停在 101。生产者的 `abortTransaction` 不会替它执行 `seek`。程序必须在中止完成后，按仍持有的分区重新取得已提交位置并恢复读取；还要撤回本地未提交计算状态。否则，虽然 G 仍是 100，活着的进程却从 101 继续，之后甚至可能提交更远的位置，把 100 的结果永久略过。官方消息复制工具明确把中止与恢复消费位置接在一起。 [中止后的显式恢复](https://github.com/apache/kafka/blob/4.1.0/tools/src/main/java/org/apache/kafka/tools/TransactionalMessageCopier.java#L236-L245) · [两项操作的衔接](https://github.com/apache/kafka/blob/4.1.0/tools/src/main/java/org/apache/kafka/tools/TransactionalMessageCopier.java#L284-L290)

另一种故障不能混入图二：已经请求提交，成功回复却丢失。此时不能断言 T1 中止，再盲目重做。4.1.0 的 `commitTransaction` 契约要求提交超时后可重试同一提交；若不重试，只能关闭生产者，不能立刻改成中止。恢复初始化会等待已经开始的结束处理，若上一笔最终提交，恢复位置就是 101，应继续下一条。 [提交结果不确定时的 API 规则](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/KafkaProducer.java#L758-L764)

本篇不变量是，对于这个组按顺序确认处理的输入前缀，其应产生的输出与进度必须属于同一个事务结果。事务不能替应用证明业务确实做对了：漏调 `send` 却提交 101，仍会漏任务；把未完成的后续记录也计入进度，同样违反前提。归属改变也不能靠假设忽略，`consumer.groupMetadata()` 携带成员与代际信息，为位置提交提供比单独 group ID 更强的过期执行者检查。失去归属或被隔离后，应按错误契约停止旧处理并恢复，不能继续独立提交位置。 [成员信息与提交资格](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/KafkaProducer.java#L691-L697)

代价在于协调器状态、内部位置记录、结束标记、复制等待和故障后的恢复工作。长事务还会拖住昨天的稳定读取边界，批次越大，单次提交可分摊更多开销，但等待与失败后重做范围也越大。只需容忍重复、下游已有可靠幂等接口时，简单的处理后提交可能更合适。事务提供了可组织这些义务的边界，应用仍要维护归属、准确进度和错误分支。

这个思路也可以迁移到 PostgreSQL：在同一数据库事务里插入派生结果，再更新一行输入检查点，恢复时以该检查点决定重读位置。共同结构是把完成凭据当成数据，与结果一起提交。这个例子仍需独占或正确协调检查点的更新者，并兑现数据库自己的持久化条件；数据库事务不会自动更新 Kafka 的组位置。Kafka 则让分布在日志分区中的结果与内部位置记录参与其事务协议，两种机制的实现和读取隔离边界不同。 [PostgreSQL 事务的多步提交](https://www.postgresql.org/docs/18/tutorial-transactions.html)

最后改变输出目标：在 T1 中直接发送真实短信，然后中止 Kafka 事务。短信不会随着任务记录一起撤回。因此这篇保证止于受协调的 Kafka 记录与进度，外部接收者还需自己的幂等或提交合作。留一个推演：若图二恢复后错误地从本地 101 继续，再提交到 102，输入 100 的任务去哪了？若输出消费者改成 `read_uncommitted`，它会如何解释 Q0 的 200 与 202？分别找出被绕过的边界，才能判断“只处理一次”到底依赖谁。
