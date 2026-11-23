# Flink 为什么让快输入停下来，等慢输入的检查点标记

昨天的求和作业只有一条输入：边界标记前的金额进入快照，后面的金额在恢复时重读。现在把订单付款分散到 Kafka 的 P0、P1，由两个源子任务读取，再交给同一个算子计算总额。P0 很快，检查点标记已经到了，P1 的标记却还在路上。让快输入继续干活，看起来能少浪费一些时间；为什么 Flink 反而暂时停下它？今天只吃透这段等待如何守住恢复时的金额。

先补足系统位置。源子任务保存各自的读取位置，求和算子保存受管状态 `sum`，JobManager 中的协调器组织一轮检查点，TaskManager 执行任务，快照写到可靠存储。两个源经过按键分区的数据交换，把同一统计键送到一个求和子任务，因此它接收两条来自不同上游子任务的输入通道。即使业务代码只有一个求和入口，这些通道仍需要对齐。 [按键状态与交换后的多通道对齐](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/concepts/stateful-stream-processing/#barriers)

本文固定 Flink 2.1.0 的 DataStream 流模式，对照 2.1 系列文档，启用 exactly-once 对齐检查点，关闭非对齐检查点及自动切换，普通同步状态接口、HashMapStateBackend 与可靠文件系统检查点存储沿用昨天的条件。本例一次只进行一轮检查点，两个输入均未结束；不扩缩容、不执行外部副作用。下面是独立的双通道教学模型，初始总额为 0，C8 只是本例轮次编号，未运行集群或注入故障。

沿用 10、20、5 元，再加入 7、3 元。P0 的 100、101 在 C8 之前，102 在之后；P1 的 200 在之前，201 在之后。位置按“下一条应读取的 offset”书写，不与连接器内部的最后已读字段混用。两个源为 C8 固定的位置分别是 P0:102、P1:201。它们不是全局序号，102 与 201 也不需要相等；属于同一轮，表示两条流各自划定了前后边界。

```text
P0 通道：100:+10 → 101:+20 → C8 → 102:+5
P1 通道：200:+7  → C8      → 201:+3
```

选择这样一种到达时序：算子已经处理 P0 的前两笔，总额为 30，随后收到 P0 的 C8；P1 的 200 与后面的 C8 都尚未被它处理。正确的 C8 总额应为 `10+20+7=37`。P1 的 7 元虽然还在路上，源位置 201 已经声明它属于本轮之前；若恢复时从 201 继续，就不会再读 200，所以这 7 元必须已经由快照承接。

最自然的办法，是记住“P0 的标记到了”，但照常处理两边，等 P1 的标记也来再保存。于是算子先处理快通道的 102，把 30 变成 35；随后处理慢通道的 200，得到 42，再收到 P1 的 C8。若此时把 42 配上源位置 102、201，恢复会重读 5、3 元，变成 50。无故障地只算五笔，本该是 45。混进快照的那笔 5 元，被源边界又安排重读了一次。

图一把这个错误方案画出来。不要只看“两个标记都收齐了”，要找出 42 中哪笔钱并不属于 C8 应承接的输入集合。

![图一。教学反事实：P0 的 100:+10、101:+20 已计入总额 30，P0 的 C8 已到；P1 的 200:+7 及其后的 C8 尚未处理。若继续处理 P0 标记后的 102:+5，再处理 P1 标记前的 200:+7，等两个 C8 都到后保存总额 42，恢复从 P0:102、P1:201 重读 5、3，会得到 50，多算 5。横向箭头只表示各通道内部顺序，选择的跨通道先后是教学设定，不是 Flink 对齐协议的实际行为。](assets/figures/flink-alignment-mixed-cut.svg)

另一种简单做法，是第一个标记到来就保存 30，却不另存慢通道的在途记录。它又漏掉 7 元，恢复后只有 38。若干脆停下整个算子等待，慢通道标记前的 200 还没处理，等待反而妨碍边界向前推进。我们需要的不是全停或全不停，而是按通道区分：已经越过边界的先等，尚未走到边界的继续走。

这就是对齐。算子收到 P0 的 C8 后，暂停从 P0 通道向业务算子交付后续记录，102 的 5 元可以留在缓冲中，却不能修改 `sum`。P1 仍可推进，200 的 7 元被处理，总额变成 37。由于本例对齐模式中每条通道保持记录与标记的顺序，P1 的 C8 不会抢在 200 前面；它到达后，两个输入各自边界前的记录就都已进入状态，边界后的记录则都还没进入。

这个不变量可以脱离图复述：C8 的算子快照，恰好承接每条输入在各自 C8 标记之前的效果，不能少一条，也不能混入后面的效果。等齐标记提供的是“所有通道都已走到自己的边界”这份证据，并不要求它们同时到达，也不要求照片对应同一个全局时钟瞬间。

实现上，`SingleCheckpointBarrierHandler` 按检查点编号与通道身份收集标记，用已到通道集合和本轮目标通道数判断是否齐备。所选纯对齐路径的 `AbstractAlignedBarrierHandlerState.barrierReceived` 先登记暂停通道；未齐时进入收集状态，齐备才触发任务的检查点步骤。`ChannelState.blockChannel` 记录的是具体通道，并非把整个求和线程挂住。 [逐通道登记与齐备判断](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/io/checkpointing/SingleCheckpointBarrierHandler.java#L231-L278) · [对齐状态的处理规则](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/io/checkpointing/AbstractAlignedBarrierHandlerState.java#L53-L76) · [暂停与恢复的通道集合](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/io/checkpointing/ChannelState.java#L54-L78)

图二沿正确路径推进。请区分“输入边界已对齐”“本地稳定视图已固定”和“整轮可靠保存已完成”，它们不是同一时刻。

![图二。教学正确时序：先收到 P0 的 C8，总额为 30，暂停 P0 的后续交付，P1 继续。处理 P1 的 200:+7 后总额为 37，再收到 P1 的 C8，固定配套视图 P0:102、P1:201、sum=37。任务同步检查点步骤结束后恢复通道处理，实时状态可加 5、3 变为 45，C8 快照仍为 37。假设 C8 整轮完成、尚无更新的已完成检查点时任务故障，恢复 37 并重读 5、3，再得 45。向下箭头表示本例时间顺序，不是运行证据。](assets/figures/flink-alignment-recovery.svg)

两边齐备后，任务执行传播标记和固定稳定状态视图的同步步骤，然后解除暂停；后台继续保存快照，不必为了等远端写完而一直挡住 P0。2.1.0 的对齐状态代码在 `triggerGlobalCheckpoint` 返回后调用 `unblockAllChannels`，这里“触发”返回并不表示整轮已经完成，昨天核对过的异步报告与协调器完成登记仍要继续。 [触发与解除暂停的先后](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/io/checkpointing/AbstractAlignedBarrierHandlerState.java#L72-L76) · [任务同步阶段后安排异步保存](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/tasks/SubtaskCheckpointCoordinatorImpl.java#L283-L373)

实时状态接着加上 5、3，变成 45。假设 C8 已完整成功，尚无更新的已完成检查点时，执行任务的机器故障，协调器与可靠存储仍可用。恢复装载 37，源从 102、201 继续，重算两笔得到 45，下一位置分别变为 103、202。加法交换处理顺序不改变最终总额，本篇不承诺跨通道的中间输出顺序与故障前完全一致，也不把受管状态的恢复推广为外部输出只出现一次。

因此，这段等待省下的是为本轮另存相关在途通道数据的责任，成本则交给了交付延迟、网络缓冲和上游推进。暂停交付不是丢弃记录，也不意味着源立刻停止生产；可用缓冲仍可能承接一部分数据，持续等待会通过有限缓冲与流控把背压传向上游。官方网络设计说明了缓冲耗尽如何限制发送者；具体缓冲配置与监控字段需按当前版本核对。 [网络缓冲与背压的设计背景](https://flink.apache.org/2019/06/05/a-deep-dive-into-flinks-network-stack/)

如果 P1 的标记迟迟不来，快通道的后续记录就承担等待。实际还要区分第一张标记到达算子前的 start delay，与算子处理首个到最后一个标记之间的 alignment duration；两边都晚到但相差很小，对齐时间仍可能很短。异步存储耗时又是另一项。把这些等待混成“写快照慢”，可能优化错地方。若整轮因超时而取消，协议应解除本轮暂停、放弃 C8，不能把缺席标记当作已到并宣布成功。 [检查点指标的边界](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/ops/monitoring/checkpoint_monitoring/#history-tab) · [取消时解除暂停](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/io/checkpointing/AbstractAlignedBarrierHandlerState.java#L81-L84)

这也与早先的 Chandy–Lamport 快照形成具体比较：在本例第一个标记到达时先记录总额 30，再把另一通道随后到来、标记之前的 7 元另存为在途记录，也能保留恢复所需的整体关系；对齐方案则先把这 7 元吸收到算子状态，保存 37。共同目标是让输入边界与效果相容，区别在于等待处理还是保存通道数据。Flink 的非对齐检查点进一步把在途缓冲纳入恢复材料，减轻部分背压下的边界推进问题，同时增加保存与恢复的 I/O；若存储 I/O 已是瓶颈，额外保存通道数据未必划算；其捕获和重放协议需要另看实现。 [原快照算法的通道记录规则](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/12/Determining-Global-States-of-a-Distributed-System.pdf) · [Flink 非对齐的适用条件](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/ops/state/checkpointing_under_backpressure/#unaligned-checkpoints)

最后独立推演：如果 P1 的 7 元已计入，P1 的 C8 反而先到，应该暂停哪条通道，P0 的哪些记录仍可处理？若快输入不产生新的付款了，它的通道就能不再参与本轮吗？先画出每条流的标记前后，再判断状态应为多少，才能分清这段等待是在守住什么。
