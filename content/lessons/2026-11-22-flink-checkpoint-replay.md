# Flink 已经处理过的消息，恢复时为什么还要再读

订单统计服务从 Kafka 读取付款金额，在内存中累计总额。它已经算到 35，机器却突然退出。重启后，系统把总额恢复成 30，又读了一遍最后那笔 5 元。处理函数确实重复执行了，为什么总额仍然正确？今天从这个看似倒退的恢复过程进入 Flink，理解一个输入位置怎样与一份计算状态共同成为恢复点。

Kafka 保存可重读的日志；Flink 在日志之上执行持续计算。应用把源、转换算子和末端输出组成数据流图，TaskManager 执行其中的任务，JobManager 协调调度与检查点。求和、窗口或关联需要记住已处理数据留下的状态，数据流连线里还可能有正在传输的记录。仅有原始消息仍在，并不能决定重启后应该从哪条读起，也不能告诉我们内存里的总额应该恢复多少。 [Flink 的执行部件与外部存储](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/deployment/overview/#overview-and-reference-architecture)

本篇固定 Flink 2.1.0 的 DataStream 流模式，设计说明对照 2.1 系列文档。显式启用 exactly-once 检查点，使用对齐模式、普通同步状态接口和 HashMapStateBackend，并配置可靠的文件系统检查点存储。教学中源与求和算子各一个子任务、分开执行，算子只有一条有序输入通道，不扩缩容、不使用异步外部调用；末端仅接收累计值，不执行付款等外部动作。下面只推演受管状态与源位置的恢复，没有运行 Flink 集群或测量性能。检查点默认关闭，需要应用启用；堆上工作状态也不等于已存入可靠存储。 [启用检查点的条件](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/fault-tolerance/checkpointing/#enabling-and-configuring-checkpointing) · [工作状态后端](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/ops/state/state_backends/#the-hashmapstatebackend)

设输入分区 P0 从 100 开始参与本例，100、101、102 的金额依次为 10、20、5 元，历史在恢复期间完整保留。所有记录进入同一个统计键，受管状态 `sum` 初始为 0，每处理一条就加上其金额，并向下游发出当前总额。为方便推演，本文把源位置统一写成“下一条应读取的 offset”：处理到 101，对应下一位置 102。这是教学记法，不把某个连接器内部字段或文档的最后已读位置与它混用。

最自然的办法，是隔几秒保存一次总额，再独立保存一次源位置。这在只有一个线程、能把两份信息可靠地一起固定和发布的小程序里完全可用；一旦保存各自发生，问题就出现了。若保存的是下一位置 102，却只有处理完 100 的总额 10，恢复会跳过 101 的 20 元，读完 102 只得 15。反过来，总额已含前两条的 30，源位置却还是 101，恢复重加 20、5，得到 55。两份文件各自正确，组合却没有共同解释。

把整个作业暂停，等所有在途数据处理完，再一起保存，也能建立这种解释。但暂停、排空和写完状态都要等最慢的部分；状态大时，前台等待可能很长。Flink 选择用随数据传播的边界，让各任务分别到达相容的位置，再把固定视图的持久化放到后台。无需每台机器同一时刻停住，但必须证明保存的状态恰好对应保存的输入前缀。

协调器发起检查点 C7。假设源已经向作业发出 100、101，还未发出 102，于是把本轮源位置固定为 102，并在后续数据前插入带 C7 编号的 barrier，即检查点边界标记。逻辑发送顺序为 `100 → 101 → C7 → 102`。C7 是 Flink 数据流内部的控制标记，不是往 Kafka 分区里追加一条业务消息。位置还必须对应向作业交付记录的边界，不能把源在网络缓冲里预取到哪里，直接当作算子已经接收并处理到哪里。 [边界标记与源位置](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/concepts/stateful-stream-processing/#barriers) · [源读者状态进入检查点](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/api/operators/SourceOperator.java#L595-L600)

看图一。源固定 102 时，求和算子未必已经处理完 101；为什么标记到达后，它仍能保存恰好为 30 的视图？

![图一。单输入教学模型：源已发出 100 的 10 元和 101 的 20 元，在两者之后、102 的 5 元之前插入 C7，并固定下一源位置 102。横向箭头表示有序数据流，C7 不越过前面的记录。求和算子处理完 100、101 后才收到 C7，在继续处理 102 前固定 sum=30。因此 C7 的两份状态为源位置 102、总额 30；固定视图仍不等于整轮检查点已经完成。](assets/figures/flink-checkpoint-cut.svg)

在本例的对齐模式中，同一通道保持这个顺序。C7 到达求和算子前，100、101 已经依次处理，总额变成 30；102 仍在标记之后。任务在处理后续记录前，为 C7 建立状态快照。这里的不变量是：快照包含边界前记录的全部效果，且不含边界后记录的效果。由于只有一个输入，不用等待其他通道的同轮标记；多输入时必须协调各条边界，不能只看先到的一条，这留给后续深入。

“先固定视图”不表示要先把整份状态写到远端，再让标记去下游。2.1.0 的 `SubtaskCheckpointCoordinatorImpl.checkpointState` 把标记广播、同步快照等步骤放在相对于记录处理不可插入的一步里，代码实际先广播标记，再准备状态快照，随后安排异步完成。关键在于 102 的处理不能插进这一步，把属于未来的 5 元混入 C7；下游也不必等上游远端写入结束才开始自己的检查点工作。 [标记、同步阶段与异步阶段的实际顺序](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/tasks/SubtaskCheckpointCoordinatorImpl.java#L283-L373)

之后实时计算可以继续。算子处理 102，总额变成 35，源也可能继续前进；后台仍在保存 C7 的 30。状态后端必须给异步写入者一个稳定视图，不能只保存指向可变对象的普通引用。所选堆状态实现使用支持异步快照的写时复制结构；这里需要知道的是旧视图受到保护，不把它简化成每次都立即复制整张表。 [堆状态快照入口](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/state/heap/CopyOnWriteStateTable.java#L28-L99)

但是，已经固定 30，仍不是可以恢复到 C7 的完成承诺。相关任务的异步快照要成功，向协调器报告保存结果与状态引用；协调器还要收齐本轮所需确认，完成检查点元数据并登记可恢复的检查点。只看到一份算子文件，或只看到末端收到标记，都不能跳过其余完成条件。源码的异步任务先结束快照，再报告；协调器检查本轮已完整确认，才进入完成路径。 [异步快照与报告](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/tasks/AsyncCheckpointRunnable.java#L112-L141) · [确认汇集与完成登记](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/CheckpointCoordinator.java#L1252-L1268)

图二选定一条故障时序：先让 C7 完整成功，实时总额已为 35，下一轮 C8 尚未完成便故障。恢复时该选哪份源位置，又该选哪个总额？

![图二。教学恢复时序：C7 固定下一源位置 102、sum=30；实时计算随后处理 102 的 5 元，sum=35，旧快照仍为 30。C7 完整成功后，在 C8 未完成时故障，恢复选取最新完成的 C7，重新载入 30，并从源位置 102 重读 5 元，得到 35。故障前那次 5 元的内存效果已经随工作状态撤回；下游累计值仍可能再次输出。向下箭头表示本例先后，不是运行追踪。](assets/figures/flink-checkpoint-replay.svg)

恢复选择最新完成的 C7，把总额恢复成 30，把源恢复到 102。先前处理 102 得到的那次 35 属于已丢弃的工作状态，不能与恢复后的状态相加；重读 102，再算 `30+5=35`，恰好补回检查点之后的效果。推演到这里，源的下一位置为 103，总额为 35，与无故障地处理三条记录相同。Flink 所说受管状态的 exactly-once，允许同一条输入物理上处理多次，要求恢复后的有效状态里只承接一次效果。 [重放与受管状态保证](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/learn-flink/fault_tolerance/#exactly-once-guarantees)

若 C7 还未完整完成就失败，应回到更早的已完成检查点，不能拿 C7 的源位置搭配旧一轮总额。若上传线程误读实时的 35，却仍配源位置 102，恢复重读 5 就变成 40。这两个反事实分别说明：边界一致与保存完成是两项义务，任何一项都不能用“有些数据已经写出”代替。还要把计算写进 Flink 管理的状态，普通全局变量不会因为开启检查点就自动进入这份协议。

代价是记录与状态之间的协调、固定旧视图的内存或磁盘成本、快照传输，以及失败后的加载与重算。更频繁地检查点通常缩短需要重放的范围，也增加保存工作；检查点持续很久或反复失败，真正可用的恢复点仍可能很旧。若输入历史提前过期，再完整的总额快照也补不出缺少的后续金额。能够从头重算、输入很小的任务，可以选择承担更大重算成本，少维护甚至不维护周期检查点；在线长寿命计算则需要一起评估保存成本和恢复预算。

这接回 Kafka“结果与消费位置共同提交”的设计：两者都要求恢复凭据与它声称已完成的效果成套成立。Kafka 事务把输出记录与组位置纳入同一提交决定；本篇 Flink 检查点把源状态与受管计算状态纳入同一恢复版本。Kafka 事务不会自动保存 Flink 的堆状态，Flink 状态回滚也不会撤回一个独立写出的外部结果。本例故障前后都可能向下游发出 35；若输出改为发短信或追加数据库行，还要由 sink 的事务、幂等或其他合作兑现端到端承诺。 [Kafka 的输出与位置事务](https://kafka.apache.org/41/design/design/#using-transactions) · [Flink 端到端保证的条件](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/learn-flink/fault_tolerance/#exactly-once-end-to-end)

最后独立改变条件：若 C7 只覆盖 100，恢复位置和总额各是多少，故障后要重读哪两条？若只恢复总额、不回退源，又会得到什么？下一次再加入第二条速度不同的输入，先到的 C7 为什么不能立刻替两条流决定总额边界？从“哪份状态包含了哪些输入”出发，就能继续推导等待、重放与在途数据的取舍。
