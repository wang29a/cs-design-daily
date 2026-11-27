# Flink 数据会乱序，时间窗口什么时候该出结果

昨天，Flink 把客户的状态交给了新任务。现在仍统计客户 9，但业务改成“每十秒付款多少”：付款发生在第八秒，记录却可能到第十二秒才被处理。机器的时钟已经走过十秒，这笔钱还算不算上一段？若为等齐所有旧消息一直不出结果，无界数据流又没有一张“全部到达”的收据。今天只追这个矛盾：怎样有依据地结束一段时间，同时承认迟到仍然可能发生？

问题位于时间戳分配、输入进度汇合与窗口算子之间。事件时间来自业务记录的发生时间，处理时间来自执行机器的时钟；二者回答不同问题。源从业务字段提取事件时间，并生成随流传播的进度信息；窗口按事件时间归类付款，保存聚合状态，等待对应定时器触发。JobManager 的检查点负责恢复这些计算，与“这个窗口现在该不该输出”并不是同一项决定。 [事件时间与水位线的入口](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/event-time/generating_watermarks/)

本篇固定 Flink 2.1.0 的 DataStream 流模式，对照 2.1 系列文档。使用普通同步状态接口与 HashMapStateBackend；两个源子任务各读取 Kafka 的 P0、P1，一个分区一条输入通道，经 `keyBy` 把客户 9 送到同一个窗口子任务。使用十秒滚动事件时间窗口、增量求和、默认 `EventTimeTrigger`，`allowedLateness=0`，显式配置迟到侧输出，不加自定义触发器或清理器。两路始终 active，不启用空闲检测或水位线对齐。下面金额、到达顺序与周期回调位置均为教学设定，未运行 Flink 或测量延迟。

为避免日期遮住计算，t 表示相对一个十秒对齐固定起点的毫秒偏移。目标窗口是 `[0,10000)`：包含 t=0，不含 t=10000。记录写作 `(t,金额)`。先处理 P0 的 `(1000,10)`、`(8000,20)`，再处理 P1 的 `(7000,7)`，窗口总额为 37。随后 P0 已送来 `(12000,5)`，这 5 元属于下一个窗口；P1 的 `(9000,3)` 尚未到达当前算子。到达先后不是 t 的排序，Kafka 分区内位置有序也不等于业务时间戳有序。

最自然的办法，是机器时间跨过十秒就结算。这适合统计“本机这十秒实际处理了多少”，却改变了按发生时间统计的含义。另一种办法是看见 t=12000 就认定旧窗口结束：此时输出 37，稍后来到的 3 元就没被计入。即使某一路已经进入下个时间段，也不能替另一条慢输入宣布过去结束。若把全部输入无限缓存，答案或许更全，等待与状态空间却没有上界。

Flink 用水位线 watermark 把等待边界变成显式数据。W 的含义是：按所选策略，不再期待后续有 `t <= W` 的正常到达记录；窗口据此推进。这个声明不是对未来的预知。今天配置 `forBoundedOutOfOrderness(Duration.ofMillis(2000))`，采用有界乱序策略，每路记录已见最大时间 m，并假设后续不会出现比 `m-D` 更早的事件，D=2000 毫秒。生成器先更新 m，在周期回调时发出水位线；下面只列选定回调，省略没有改变结论的中间发射。

```text
每路水位线 Wi = mi - 2000 - 1
两路均 active 时，窗口输入进度 W = min(W0, W1)
```

减去最后的 1 毫秒，是为了仍然容纳恰好等于 `m-D` 的记录：m=12000 时，最早仍可正常期待 t=10000，于是声明已过界的只到 9999。2.1.0 的 `BoundedOutOfOrdernessWatermarks` 正是先取时间戳最大值，再在周期发射中减去乱序界和 1。这里的 2000 是事件时间差的假设，不是让每条记录在墙钟上睡两秒；没有新事件时，单靠周期回调也不会让 m 前进。 [假设与周期发射的实现](https://github.com/apache/flink/blob/release-2.1.0/flink-core/src/main/java/org/apache/flink/api/common/eventtime/BoundedOutOfOrdernessWatermarks.java#L28-L69)

图一观察两条不同的进度：P0 已给出 9999，为什么窗口仍然不该输出 37？

![图一。教学起点，时间单位为毫秒。客户 9 的目标窗口 [0,10000) 已收到 P0 的 1000:+10、8000:+20 及 P1 的 7000:+7，sum=37。P0 的 12000:+5 属于下一窗口，令 m0=12000、W0=9999；P1 此时 m1=7000、W1=4999。两路均 active，汇合水位线为 min(9999,4999)=4999，尚未达到目标窗口的触发时刻 9999。P1 的 9000:+3 尚未到达，不能被快输入替它宣告结束。箭头表示进度汇合，不是数据流排序或运行追踪。](assets/figures/flink-watermark-minimum.svg)

取最小值的理由很具体：整个输入可以宣告过去到哪里，只能到每一路都愿意跨过的位置。这不要求冻结 P0：快路可继续累积下一窗口，等待的是旧窗口触发，不是把整个任务挂起。`StatusWatermarkValve` 记录各输入进度，推进可参与汇合输入中的最小水位线，并且只向前输出。本例没有空闲退出及恢复追赶等状态变化，因而直接取两路最小值；不能把这条简式推广为忽略输入状态的任意场景。 [记录输入并尝试汇合](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/watermarkstatus/StatusWatermarkValve.java#L165-L184) · [单调推进最小水位线](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/watermarkstatus/StatusWatermarkValve.java#L273-L284)

慢路随后送来 `(9000,3)`，仍属于目标窗口，sum 变成 40；m1=9000，下一次发射 W1=6999，汇合进度也只到 6999。然后 P1 送来 `(12000,2)`，这 2 元进入下一窗口，与 P0 的 5 元合成 7。m1 到 12000，发射 W1=9999，此时两路水位线都是 9999，目标窗口终于有了触发依据。

为什么触发点是 9999，不是 10000？`TimeWindow.maxTimestamp()` 返回排他结束时间减 1，正是这个窗口最后一个可容纳的毫秒。默认 `EventTimeTrigger` 把事件时间定时器登记在此；内部定时器服务在水位线推进到该时刻时调用窗口触发逻辑。窗口输出 40，而不是等待机器时钟到一个同名时刻。 [窗口的最后时间戳](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/api/windowing/windows/TimeWindow.java#L80-L86) · [默认触发时刻](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/api/windowing/triggers/EventTimeTrigger.java#L37-L51) · [按水位线分派定时器](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/api/operators/InternalTimerServiceImpl.java#L328-L340)

图二继续追踪那份 40。输出之后，若 P1 又送来 t=6000 的 4 元，系统会撤回水位线重新计算吗？

![图二。教学演化：P1 的 9000:+3 使目标窗口 sum 从 37 变 40，W 从 4999 变 6999，仍不触发；P1 的 12000:+2 进入下一窗口，使该窗口已有 7，并令 W1=9999。两路进度汇合到 W=9999，触发目标窗口输出 40；allowedLateness=0，清理该窗口状态。此后 P1 的 6000:+4 迟到，进入配置的迟到侧输出，主输出不自动改成 44。水位线不后退，下一窗口仍保留 sum=7。箭头表示选定的教学先后，不是运行证据。](assets/figures/flink-watermark-window.svg)

在零允许迟到的配置下，窗口清理时刻也是 9999：触发后清理本窗口状态。迟到的 `(6000,4)` 所属窗口已经过期，`WindowOperator` 跳过该窗口，再把记录交给已配置的迟到侧输出；不配置侧输出时，这类记录被丢弃并计数。主结果不会自动从 40 改成 44，水位线也不倒退。推演终点是旧窗口已输出并清理，迟到侧输出收到 4 元，下一窗口状态为 7，作业本身仍未结束。 [触发输出与到期清理](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/operators/windowing/WindowOperator.java#L472-L487) · [跳过过期窗口及迟到去向](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/operators/windowing/WindowOperator.java#L405-L445)

这 4 元说明了证据边界：源曾见过 12000，不能在数学上证明以后永无 6000；它违反了本例选择的乱序界。水位线把有限等待组织成可执行策略，并未消灭迟到。应保持的不变量，是窗口使用的汇合进度不能越过任何仍参与的慢输入，而且事件归属始终按 t 判断。反事实若改用最大水位线，P0 的 9999 就会让窗口提前清理，随后那笔原本应正常计入的 3 元也可能被当作迟到。

代价转移给结果延迟、窗口状态保留和迟到处置。D 放大，通常多容纳乱序，却让时间进度更落后；它与 `allowedLateness` 不是同一个参数。后者增加时，窗口可在首次输出后继续保留状态，默认事件时间触发器还可能再次输出更新结果，下游便要理解更正而非把每次累计值相加。 [允许迟到与再次触发](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/operators/windows/#allowed-lateness)

若 P1 长期没数据，它的旧水位线可以拖住全局进度。空闲检测能够将它暂时排除，但超时说明的是一段处理时间内没有活动，不是业务历史已经完整；恢复输入若带来旧事件，仍须面对迟到策略。实际应先区分慢、空闲和背压，再决定是否接受这项取舍。水位线也不是检查点完成通知：窗口输出 40 不等于 40 已可靠持久化，恢复与外部提交仍承担前几天的责任。 [空闲输入的处理](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/event-time/generating_watermarks/#dealing-with-idle-sources)

这与 TCP 累积确认共享“用单调前沿约束后续动作”的结构：ACK=N 让发送端知道 N 之前的连续字节已收到，窗口水位线让算子决定哪些时间范围不再继续等。但 TCP 前沿依赖具体序号与已收齐字节，今天的有界乱序水位线依赖输入时间模式的假设，不能照搬成同样强的收齐证明。也正因此，迟到记录需要独立出口。 [TCP 累积确认的含义](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.4)

最后先独立推演：若 P1 最后只推进到 m1=11999，两路汇合水位线是多少，目标窗口会触发吗？若不改 D，而把允许迟到改成 2000，图二的 4 元到来时保留了什么状态、可能产生怎样的第二份输出？先找进度前沿和清理边界，再判断一种等待是否值得，才能说清“及时”与“完整”究竟由谁取舍。
