# Flink 查询已经返回，为什么结果还要在队列里等

昨天，水位线让窗口知道哪些时间范围可以不再等。现在窗口前多了一道查询：每笔付款先去外部参考表补全标签，再交给窗口。如果第一笔查询很慢，后两笔很快，串行等待会浪费网络并发；若谁返回就立刻输出，又可能让水位线先走，把还在查询中的旧付款变成迟到。今天只吃透这个取舍：怎样放宽不必要的顺序，同时保住时间边界？

这里使用 Flink 的异步 I/O 算子。任务线程顺序调用用户的 `asyncInvoke`，异步客户端把请求发出去，函数尽快返回，任务才能继续接收输入；网络完成时，再通过 `ResultFuture` 递交结果。它不是 Flink 自动给每条记录开一个线程。若在 `asyncInvoke` 里调用阻塞查询，或马上等待 future，等待依然占着调用路径。低流量、外部调用本来很快时，同步做法简单且有价值；只有真正重叠了等待，异步才有意义。 [调用方式与阻塞陷阱](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/operators/asyncio/#caveats)

本篇固定 Flink 2.1.0 DataStream 流模式，对照 2.1 系列文档。启用 exactly-once 对齐检查点与可靠存储，恢复时拓扑和序列化配置不变。单个异步子任务、无扩缩容，使用 `AsyncDataStream.unorderedWait`，容量 4，超时 5 秒，不启用内建重试。参考表在教学期间不变，查询只读、无扣款等外部副作用，每笔产生一条保留标识、金额和原事件时间的结果。下游另开空的十秒滚动事件时间求和窗口，使用默认事件时间触发器，三笔都属于客户 9，零允许迟到。下面为源码支持的时序推演，没有运行集群、真实查询或测量吞吐。 [无序接口及无重试路径](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/datastream/AsyncDataStream.java#L115-L127)

输入依次是 A、B、W、C。A 在 t=8000 毫秒付款 20，B 在 t=9000 付款 3，W 是已经由上游合法产生的水位线 9999，C 在 t=12000 付款 5。时间仍相对一个十秒对齐起点书写；这是独立片段，不接着昨天的 40 累加。今天只讨论异步算子怎样保存已有 W 的前后关系，不重用昨天最大时间减乱序界的那份发射时序。补全后的结果记作 A′、B′、C′。

最自然的高并发方案，是发出三个查询，回调直接把结果交给下游，W 到达就原样转发。若 W 先到窗口，A′ 稍后才带着 8000 到达，窗口可能已过清理边界，20 元被当成迟到。这不是源真的晚发了 A，而是算子自己把进度承诺放到了未完成工作前面。另一端是严格保序：A′ 不出，B′ 就一直等。它能守住边界，但同一时间段内，求和并不需要 A′ 必须先于 B′。

关键洞察是用 W 划出不能跨越的边界，只在边界内部放宽顺序。队列逻辑上分成 `[A,B] → [W] → [C]`。第一段中谁先完成，谁可以先输出；整段既没有未完成请求，也没有已完成待输出结果之后，才轮到 W；W 输出后，才轮到下一段。无序因此有明确范围，并不是把事件流改成任意回调顺序。 [无序队列的分段不变量](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/queue/UnorderedStreamElementQueue.java#L42-L51)

图一观察已经返回的 C′：它明明不欠网络等待，为什么还没有输出资格？

![图一。教学队列：输入为 A(t=8000,+20)、B(t=9000,+3)、水位线 W=9999、C(t=12000,+5)，形成三个逻辑段：首段 A、B，中段 W，后段 C。容量为 4，三个记录条目加一个水位线条目占满队列。选定 C 最先返回，C′ 已完成但处在后段；首段 A、B 尚未完成，W 也不能输出。箭头表示段间输出资格，不是请求串行执行，三个外部查询已经发起。图为教学简化，不是运行追踪。](assets/figures/flink-asyncio-segments.svg)

实现中，记录条目绑定到所属 segment，完成后从未完成集合移入已完成队列。水位线自己是一个不必查询、已完成的条目，却被安排在独立段，后面再开新段。输出检查只看最前面的段；后段有结果并不意味着全队列可以越过前段输出。 [水位线建立分段](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/queue/UnorderedStreamElementQueue.java#L129-L164) · [完成集合与段是否排空](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/queue/UnorderedStreamElementQueue.java#L221-L245)

选择回调依次报告 C、B、A，均在超时前。C′ 先保留在后段；B 完成时，首段已有一个可输出项，于是 B′ 可以先离开，队列仍保留 A、W、C。最后 A 完成并输出，首段才排空；随后输出 W，再输出早已准备好的 C′。本例下游顺序为 `B′ → A′ → W → C′`。`StreamRecordQueueEntry` 输出时沿用原输入时间戳，因此先到的是 9000 的 3 元，再是 8000 的 20 元；二者都在 W 前，窗口仍能累计 23，W 触发旧窗口，C′ 的 5 元进入下一窗口。 [结果沿用输入时间戳](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/queue/StreamRecordQueueEntry.java#L60-L65)

图二把“回调先后”和“下游先后”分开。不要把其中任意一个完成时刻当作全部义务已经结束。

![图二。教学演化：三个查询的回调按 C、B、A 完成，C′ 先等在后段；B′ 可以从首段输出，旧窗口为 3，队列占用从 4 降为 3；A′ 输出后旧窗口为 23，首段排空，W=9999 才能输出并触发旧窗口；随后 C′ 输出，下一窗口为 5，队列排空。下游顺序是 B′、A′、W、C′，不是回调顺序 C、B、A。箭头表示选定教学先后；容量按输入条目计，水位线也占条目，不是性能测量。](assets/figures/flink-asyncio-emission.svg)

回调通常来自客户端线程，但不该自行修改算子队列并向下游发射。2.1.0 的 `ResultHandler.complete` 先用原子标志拦住重复完成，再把处理送进 mailbox，也就是任务线程可依次执行的待办。由那里填充结果、检查当前可输出项；需要继续输出时再安排后续待办。这样，外部完成可以并发到来，队列和输出仍沿算子受控路径推进。 [递交到 mailbox 与推进输出](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/AsyncWaitOperator.java#L620-L669)

容量约束也落在同一队列。`tryPut` 按条目计数，记录和水位线都会占位置。本例最初为 A、B、W、C 共 4 项：C′ 虽已查询完成，只要没有输出，位置就没释放。若继续来 D，暂时不能入队；插入路径会向 mailbox 让出执行机会，让已有回调及输出能够腾位，而不是占住线程死等。限制本算子继续接收，才会沿输入形成背压。它不是整个外部服务的全局并发配额，也不是字节硬上限，尤其真实请求若返回巨大结果集合，内存仍可能很大。 [条目计数与容量](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/queue/UnorderedStreamElementQueue.java#L75-L103) · [满队列时让出执行](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/AsyncWaitOperator.java#L333-L354)

还可以从图二中间分出一条恢复推演：B′ 已进入窗口，窗口状态为 3，A 未返回，C′ 已返回却未输出。假设这时完整完成检查点 C13，源恢复位置已越过 A、B、C。异步队列的快照仍保留 A、W、C；它保存的是这些输入元素，而非已经算好的 C′。若任务故障后从 C13 恢复，窗口恢复为 3，异步算子重放队列，重新查询 A 和 C，再遵守 W 的边界输出。最终旧窗口仍为 23，下一窗口为 5；段内完成顺序可以改变，不要求复刻先前的回调时序。 [队列输入进入检查点](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/AsyncWaitOperator.java#L291-L310) · [已完成但未输出也保存原输入](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/queue/UnorderedStreamElementQueue.java#L247-L257) · [恢复时重新调用处理](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/operators/async/AsyncWaitOperator.java#L225-L240)

这不承诺外部调用只发生一次。如果查询变成扣款，恢复重发就需要外部系统自己的幂等或事务合作；即使只读，参考表变化也可能让重查得到不同标签。今天固定稳定参考表，才可以把恢复答案说成相同。超时也不自动等于外部请求已取消：默认处理是以超时异常完成 result future，作业是否重启还取决于重启策略；自定义返回空集合则是改变业务输出，不能当作无代价的故障处理。 [默认超时行为](https://github.com/apache/flink/blob/release-2.1.0/flink-streaming-java/src/main/java/org/apache/flink/streaming/api/functions/async/AsyncFunction.java#L89-L98)

这种设计省下了等待期间无事可做的串行时间，把复杂性转交给结果缓存、分段输出、超时与恢复。慢 A 仍会挡住 W，并让已完成的 C′ 占位；水位线越密，能够自由乱序的片段也越碎。如果业务必须保留原输入顺序，可以选 `orderedWait`，代价是 B′ 也要等 A′。在小流量下，增加这些机制未必比同步查询划算；外部服务已饱和时，放大容量更不能凭空增加处理能力。 [两种输出模式的取舍](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/operators/asyncio/#order-of-results)

这也像早先的 Unix 管道收尾：所有写端关闭还不够，缓冲里的字节还得被读空，读者才得到 EOF。这里一段没有未完成请求还不够，已完成待输出结果也必须排空，W 才能通过。共同结构是把“生产已完成”和“消费者可跨过边界”分开；管道依据字节与端点生命周期，异步队列依据条目和事件时间边界，不能把二者当成同一种顺序保证。 [管道 EOF 的条件](https://man7.org/linux/man-pages/man7/pipe.7.html)

最后独立推演：若只把容量从 4 改成 3，原先“C 最先返回”的时序还能原样成立吗？若改用 `orderedWait`，同样的 C、B、A 回调顺序下，谁多承担了等待？先分清请求已发起、查询已完成、结果可输出三个状态，再判断某一种并发究竟释放了什么，又把成本留给了谁。
