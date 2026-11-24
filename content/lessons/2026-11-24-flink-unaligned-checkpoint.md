# Flink 不等慢通道，怎样把在途数据也存进检查点

昨天，Flink 等两条输入的检查点标记到齐，才给求和状态拍照。快通道标记后的 5 元先等，慢通道标记前的 7 元先计入，快照因此保存 37。这个办法容易解释，但若标记前堆着大量待处理数据，标记也跟着等待，检查点迟迟无法推进。今天换一个问题：能否先保存当前的 30，让标记更早向下游走，同时保住还没计入的 7 元？

这个问题位于 Flink 的任务输入、网络缓冲与检查点存储之间。源子任务掌握 Kafka 分区的恢复位置，算子掌握已处理记录留下的状态，通道中还保存已经发出、尚未处理的数据。JobManager 的协调器收集整轮检查点，TaskManager 执行状态固定、缓冲捕获和异步保存。今天的新设计改变的是恢复材料的组成：不必先把所有在途记录都处理进算子状态，可以把一部分记录本身也保存下来。 [非对齐检查点的系统位置](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/concepts/stateful-stream-processing/#unaligned-checkpointing)

仍固定 Flink 2.1.0 的 DataStream 流模式，对照 2.1 系列文档。启用 exactly-once、非对齐检查点，对齐等待超时设为零，从一开始就走非对齐路径，最多一轮检查点并行。使用普通同步状态接口、HashMapStateBackend 和可靠文件系统存储。两个源经按键交换连接同一个求和子任务；不扩缩容、没有广播状态、事件时间定时器或外部副作用。配置选择可对照 `CheckpointOptions.forConfig`，不能把“非对齐”当作降低到 at-least-once 的另一种叫法。 [模式选择的实现](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/CheckpointOptions.java#L101-L119)

用与昨天相同的五笔金额，另开一份初始总额为 0 的教学模型，本轮编号 C9。P0 的 100、101 是 10、20 元，属于 C9 的源边界之前；102 的 5 元在之后。P1 的 200 是边界前的 7 元，201 的 3 元在之后。源快照按“下一读取位置”记为 P0:102、P1:201，输入历史在恢复期间完整保留。这只是逻辑位置记法，不是连接器状态文件的字段转储。

观察起点是：100、101 已被求和，总额为 30；P0 的 C9 首先被任务处理，P1 的 C9 尚未被它处理。为看清缓冲的责任，假设 P1 的 200 已在接收端缓冲里，但还没交给求和函数，其他通道没有待恢复的业务记录。真实积压可能包含很多缓冲，本例只画其中一条；所有编号、时序和金额都是教学设定，没有运行 Flink 或测量性能。

最自然的省等待办法，是收到第一张标记就保存 30，直接让所有输入继续。如果只保存这个数和两个源位置，恢复将从 102、201 开始，加上 5、3 后只有 38。7 元既没进入 30，又位于 P1 恢复位置之前，不会从源重新读到。仅仅取消等待，留下的是一个恢复缺口。继续处理到最后一张标记才保存，也可能像昨天那样把快通道的未来混进旧快照，问题并没有消失。

关键洞察是，这个缺口不必在拍照前靠计算填平。已经取得的记录还在通道里，可以让检查点同时保存“算子已经算出的 30”与“尚需补算的 7”。这样，源边界前应承接的 37 元，被拆成一份状态和一份待恢复输入。少等的条件，是明确记下被跳过的处理责任，而不是声称这笔处理已经完成。

图一观察同一个 7 元：它此时在哪里，为什么既不属于快照中的 30，也不该留给源位置 201 之后的读取来补？

![图一。教学模型：P0 的 100、101 已形成 sum=30，C9 的源位置为 P0:102、P1:201。P1 的 200:+7 已到接收缓冲但尚未计入求和，必须加入 C9 的通道状态。标记可以优先推进，7 元的恢复责任仍被保留。图中 C9 包含源位置、算子快照 30、P1 通道记录 200:+7；仅画这个缺口，其他通道无待恢复业务记录。箭头表示归属及捕获关系，不是运行追踪。](assets/figures/flink-unaligned-capture.svg)

Flink 的非对齐路径在首个标记到达时启动本地检查点，不再等所有通道先把旧记录处理完。标记作为可优先推进的事件，能够越过部分积压缓冲，但越过的记录要进入通道快照。2.1.0 的 `AlternatingWaitingForFirstBarrierUnaligned` 先初始化输入检查点，通知各输入开始捕获，再触发任务检查点；其标记通知路径可以把相应事件提升优先级。标记不必排队等每笔业务计算，数据的恢复归属却仍受协议保护。 [首个标记触发与输入捕获](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/io/checkpointing/AlternatingWaitingForFirstBarrierUnaligned.java#L49-L85)

捕获不能只看拍照后新到的网络数据，否则本例早已在输入队列里的 7 元仍会漏掉。`RemoteInputChannel.checkpointStarted` 会取得相关的在途缓冲，交给 `ChannelStatePersister.startPersisting`；已有缓冲进入写入队列，后续仍属于本轮范围的缓冲也由 `maybePersist` 接住。相应标记界定捕获的结束范围，避免把无穷未来都记进去。协议在这里操作带通道身份和序列边界的缓冲，本例写成一条业务记录，是为了看清金额归属。 [已有缓冲的捕获入口](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/consumer/RemoteInputChannel.java#L685-L710) · [已有缓冲、后续数据与边界](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/consumer/ChannelStatePersister.java#L71-L132)

真实数据还可能停在上游输出缓冲中，不能把接收队列当作在途数据的全部。Flink 为输入通道和输出分区都维护检查点状态；这个模型特意让那条 7 元已经位于接收端，并让其他待恢复记录为空，才可以只画一份输入通道数据。拓扑、缓冲位置或记录拆包方式改变时，不能直接照搬图中的文件数量与字节布局。

随后，实时作业可以继续处理 5、7、3，达到 45。C9 的算子视图仍固定为 30，通道快照仍承担那条 7 元，不能随着实时求和而把它从本轮恢复材料中随手删掉。不过，首个标记触发也不等于 C9 已完整成功：各通道的本轮捕获范围仍须收束，算子状态与通道状态都须保存成功，再由协调器完成整轮登记。`OperatorSnapshotFinalizer` 明确等待输入、输出通道状态的 future，而不是只等待受管状态文件。 [完整快照同时依赖通道状态](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/api/operators/OperatorSnapshotFinalizer.java#L50-L83)

图二选择 C9 已完整成功、尚无更新的已完成检查点时发生任务故障。恢复为何要重新装载那条 7 元，又为什么不用把 P1 的源位置退到 200？

![图二。教学恢复时序：C9 完整保存源位置 P0:102、P1:201，算子状态 30，以及 P1 通道记录 200:+7。实时作业已算到 45 后任务故障，丢弃实时工作状态，先载入 30，再重放通道中的 7 得到 37，然后从源位置重读 5、3，得到 45。7 由通道恢复，5、3 由源重读，不能漏掉或重复补入。向下箭头表示选定时序，不是性能或故障实验。](assets/figures/flink-unaligned-recovery.svg)

假设协调器和可靠存储仍可用，恢复加载 `sum=30`，还要恢复通道数据。选定先重放 P1 的 200，总额变成 37，再处理源位置 102、201 对应的 5、3，得到 45，后续位置为 P0:103、P1:202。`RecoveredInputChannel` 在转换为正常输入通道前要求恢复状态已经消费完；普通记录的接续不能绕过这段恢复数据。不同通道之间的交错顺序不要求复刻，本例加法的最终答案相同；每条通道内部的先后仍然重要。 [恢复数据与正常通道的衔接](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/consumer/RecoveredInputChannel.java#L106-L111) · [恢复队列的结束确认](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/io/network/partition/consumer/RecoveredInputChannel.java#L163-L180)

对本例求和算子，不变量现在变成：源边界前的每笔金额，要么效果已在算子快照中，要么通过保存的通道数据补回；边界后的金额由源重读。漏掉通道里的 7，最终只得 38；已经重放这 7 元，却又错误地从 P1:200 把它再读一次，就会得到 52。只恢复源位置和一个总额，已经不足以解释这一轮检查点。外部输出的事务或幂等责任也仍然存在，不能由这份状态恢复自动代办。

代价很具体：少等业务排空，换来缓冲保留、额外写入、检查点空间和恢复重放。背压导致大量数据在途时，它可能让检查点更早向下游推进，却不会提高慢算子本身的持续处理能力。若瓶颈正是检查点存储 I/O，额外写通道数据反而可能增加压力；若对齐原本很快，保存更多数据也未必值得。它还不能随时打断一条运行很久的用户函数，标记处理仍可能等这次调用返回，所以不能承诺任何背压下都立即完成检查点。 [适用条件与长记录处理限制](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/ops/state/checkpointing_under_backpressure/#unaligned-checkpoints)

这与早先的 Chandy–Lamport 快照共享“本地状态加通道状态”的结构：本地照片没包含的在途消息，仍可作为恢复材料。区别在于原教学协议依靠有序标记关闭消息清单，Flink 还要捕获已经排队的序列化缓冲，并处理标记优先推进后的边界与通道接续。共同目标是保住因果上的缺口，具体顺序证明不能直接互换。昨天的对齐得到 37，今天的算子快照是 30 加一份 7；这正显示设计改变的是完成责任放在哪里，而不只是删掉一段等待。 [Flink 对非对齐与原快照思想的说明](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/concepts/stateful-stream-processing/#unaligned-checkpointing)

最后先独立推演：若首个 C9 到来之前，7 元已经被求和，算子快照与这条通道的待恢复内容各应怎样变化？若积压从一条 7 元变成十万个缓冲，哪种等待可能变短，哪些保存与恢复成本会增加？从金额由谁承接开始判断，才能比较两种检查点在真实瓶颈下是否值得。
