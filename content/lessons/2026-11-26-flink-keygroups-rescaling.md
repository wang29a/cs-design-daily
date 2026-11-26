# Flink 多开一个任务，旧的按键状态怎样找到新主人

付款统计已经能从检查点恢复，输出也有自己的提交协议。现在订单变多，两个求和任务忙不过来，准备扩成三个。客户 9 已累计付款 25 元，下一笔 3 元却可能被路由给新任务。新任务若只看到自己的空内存，会输出 3，而不是 28。今天不再讨论快照怎样完成，只看执行者数量改变后，数据怎样与旧状态重新相遇。

问题位于 `keyBy` 的分区交换与受管 keyed state 之间。keyed state 是每个业务键各有一份的状态，例如每位客户的累计金额；处理一条记录时，算子访问该键对应的状态。上游分区器决定记录送到哪个并行子任务，恢复系统决定每份旧状态装到哪里。两边必须遵守同一个归属规则，否则状态即使完整保存，也会被放到错误的地方。 [按键输入与状态共同分区](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/concepts/stateful-stream-processing/#keyed-state)

本篇固定 Flink 2.1.0 的 DataStream 流模式，普通同步状态接口、HashMapStateBackend、exactly-once 对齐检查点与可靠存储。源读取 Kafka 单分区 P0，按 Java `Integer` 客户号做 `keyBy`，每键维护一个名为 `sum` 的整数状态。求和算子显式设置最大并行度 M=8，当前并行度 P=2。通过停止并保存完整 canonical savepoint S12，再以 P=3 恢复；旧执行已经停止，算子 UID、状态名及序列化配置保持兼容，源并行度不变，输入历史保留，不讨论在线无停顿迁移、定时器或外部写入。输出只用于解释状态，昨天 FileSink 的保证不能省略其自身条件。 [通过保存点停止与恢复](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/ops/state/savepoints/#stopping-a-job-with-savepoint)

最自然的办法是 `hash(key) % P` 决定处理者，每个任务把自己的整张状态表存起来。并行度固定时，这种办法清楚且好用；但 P 从 2 改成 3，很多键的余数改变。如果旧任务 0 的文件仍整份交给新任务 0，路由已转向新任务的键就与旧状态分开。可以逐条读出旧键、重算新归属、重写新分片，这能做对，却把每次并行度变化都变成重新划分业务键空间。若状态本来很小或很少扩缩容，承担这份工作也未必不值得。

Flink 的洞察是先确定比执行任务更稳定的一层分片，再把这些分片交给当前任务。它叫键组 key group：M=8 表示始终有 g0 到 g7 八组，不表示现在启动八个任务。键先映射到组，组再映射到处理者。改变 P 时，只重新切分组的归属；键属于哪组及状态中的组身份仍然保留。组是重新分配 keyed state 的最小单位，组内仍保存各个键自己的状态，不能把同组客户的金额相加成一个总额。

在 2.1.0 的 `KeyGroupRangeAssignment` 中，令 H(k) 为 `MathUtils.murmurHash(k.hashCode())` 返回的非负整数，g 为组号，i 为任务索引。下面的除法取整数部分，所有索引从 0 开始，必须满足 `1 <= P <= M`。

```text
g = H(k) % M
i = floor(g * P / M)
```

第一步不含 P，正是稳定性的来源；第二步与恢复分配共用同一套规则。`KeyGroupStreamPartitioner.selectChannel` 直接调用这条分配路径，不是另写一份“差不多”的哈希。 [键、组与任务的两层映射](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/state/KeyGroupRangeAssignment.java#L50-L76) · [组的当前处理者](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/state/KeyGroupRangeAssignment.java#L124-L127) · [实际数据路由入口](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/partitioner/KeyGroupStreamPartitioner.java#L55-L66)

用三个整数键贯穿推演。依上述哈希规则，客户 3 的 H 为 847579505，落入 g1；客户 9 的 H 为 101886131，落入 g3；客户 1 的 H 为 68075478，落入 g6。金额和时序是教学设定，没有运行 Flink 或测量扩容性能。P0 的 100 是客户 3 付款 10，101 是客户 9 付款 20，102 是客户 1 付款 7，103 再给客户 9 加 5。S12 在这些记录之后固定下一源位置 104，三个 `sum` 分别为 10、25、7。 [哈希的整数运算定义](https://github.com/apache/flink/blob/release-2.1.0/flink-core/src/main/java/org/apache/flink/util/MathUtils.java#L137-L155)

图一请观察：客户 9 的 g3 没变，为什么它的状态却应该从旧任务 0 交给新任务 1？

![图一。教学映射：最大并行度 M=8 固定，客户 3、9、1 分别属于 g1、g3、g6，状态为 10、25、7。P=2 时旧任务 0 拥有 g0–g3，旧任务 1 拥有 g4–g7。P=3 时新任务 0 拥有 g0–g2，新任务 1 拥有 g3–g5，新任务 2 拥有 g6–g7。竖箭头表示同一键组的身份延续，变化的是任务边界；g3 与状态 25 转到新任务 1，g6 与状态 7 转到新任务 2。空组也仍有唯一归属，图不表示一组一个文件或实际迁移追踪。](assets/figures/flink-keygroups-assignment.svg)

P=2 时，`floor(g*2/8)` 把 g0–g3 分给旧 0，g4–g7 分给旧 1。P=3 时，g0–g2 属于新 0，g3–g5 属于新 1，g6–g7 属于新 2。例如 g3 的新处理者是 `floor(3*3/8)=1`，不能凭“组号 3”把它交给新 0。每个任务拿一段连续组号，组数不必相等，本例是 3、3、2；分段公式也由同一个类提供。 [连续组范围的计算](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/state/KeyGroupRangeAssignment.java#L93-L105)

恢复怎样使用这层分片？S12 不是只有“旧 0 一袋状态、旧 1 一袋状态”两个黑盒。状态句柄携带键组范围以及定位状态数据的元信息。`StateAssignmentOperation` 为新任务建立目标范围，再从旧句柄里提取与它相交的部分。新 1 要 g3–g5：它从旧 0 的 g0–g3 中接收 g3，从旧 1 的 g4–g7 中接收 g4–g5。本例 g4、g5 没有客户记录，仍不能把范围的分配规则省掉。 [按新范围重新分配状态](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/StateAssignmentOperation.java#L282-L330) · [提取范围交集](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/checkpoint/StateAssignmentOperation.java#L643-L658)

图二只放大新任务 1：同一段 g3–g5 的恢复归属，怎样接到 P0 的下一笔输入？

![图二。教学恢复：S12 已完成，源下一位置为 104。旧句柄 H0 覆盖 g0–g3，H1 覆盖 g4–g7；新任务 1 的目标范围为 g3–g5，取 H0 的 g3 与 H1 的 g4–g5，恢复客户 9 的 sum=25。随后输入 104 给客户 9 加 3，仍经 g3 路由到新任务 1，输出 28。若只把旧任务状态按相同任务索引装回，客户 9 的 25 留在新 0，而新 1 收到记录却无该键状态，就可能从零输出 3。箭头表示选取状态与后续记录的路由；句柄不是每组独立物理文件，图不是运行证据。](assets/figures/flink-keygroups-restore.svg)

范围求交不等于已经把每个键重写一遍。本篇保存点的 `KeyGroupsSavepointStateHandle.getIntersection` 可以构造引用同一底层数据、只保留相交组偏移的句柄。对于本篇 canonical 保存点，堆状态恢复走保存点恢复分支；底层 `FullSnapshotRestoreOperation` 按组偏移定位并读取组内容，再装载键与状态。这省去为决定新任务而重新哈希每个旧键的步骤，仍然需要读取、解码和恢复，不能称作零拷贝扩容，更不能把它推广为所有状态后端相同的文件布局。 [句柄交集仍引用底层数据](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/state/KeyGroupsSavepointStateHandle.java#L40-L48) · [按组定位保存点内容](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/runtime/state/restore/FullSnapshotRestoreOperation.java#L244-L262)

新执行恢复后，客户 3 的 10 在新 0，客户 9 的 25 在新 1，客户 1 的 7 在新 2。P0 从 104 继续：104 给客户 9 加 3，得到 28；105 给客户 1 加 2，得到 9；106 给客户 3 加 4，得到 14。推演终点是下一源位置 107，三份状态为客户 3→14、9→28、1→9。没有把所有客户凑成一份总额，也没有把源位置当成新的键组号。

这里的不变量是：每个组恰好分给一个新任务，同一个键的后续记录与它恢复出的状态必须落在该任务。只改路由不改状态，客户 9 就可能从零加出 3；让两份执行同时作为它的有效主人，又会产生独立演进的状态。这些是破坏协议的反事实，不是 Flink 正常恢复的行为；所引恢复代码还会核对组是否属于本任务。今天用停止旧作业再恢复的边界规避双重执行，不声称这套范围公式单独提供在线迁移协议。

稳定也有代价。M 决定分配粒度和并行度上限，不能在本例恢复时随意把 8 改成 16，假装只是多开任务；状态中的组身份和新哈希空间已经不同。设置更大的 M 留出扩容空间，却增加一些后端的内部结构与元数据成本。并且组数均匀不代表工作量均匀：若客户 9 占了绝大部分流量，它始终属于一个组、一个有效处理者，多开任务未必能拆掉这处热点。 [最大并行度的作用、成本与兼容约束](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/dev/datastream/execution/parallel/#setting-the-maximum-parallelism)

还要保留算子的稳定 UID、状态名和兼容的键与状态序列化规则；若新程序找不到原算子，或同一业务键改变了哈希含义，漂亮的组范围也无法替应用识别旧状态。保存点文档建议显式指定 UID，正因为任务实例索引可以变，而被恢复的逻辑算子身份不该跟着丢。 [保存点与算子身份](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/ops/state/savepoints/#assigning-operator-ids)

这接回 Kafka 的分区与消费者：稳定的分区承载数据身份，消费者数量变化时重新分配分区归属，不必把分区数改成消费者数。Flink 的键组也把逻辑分片与当前执行者分开。不过 Kafka 交接的是可重读日志分区及进度，Flink 此处还要恢复计算状态，并保证数据分区器采用同一新映射；消费者重平衡不能替它搬运 `sum`。这是结构上的比较，不是历史传承或正确性证明的直接移植。 [Kafka 的分区分配](https://kafka.apache.org/41/design/design/#the-consumer)

最后独立推演：M 仍为 8，若 P 从 3 缩成 2，客户 9 与客户 1 各回到哪里，新任务 1 要汇集哪些旧范围？若只有客户 9 一人持续变热，把 P 提到 8，究竟缓解了什么、又留下什么？先判断状态与输入归属，再谈“多加机器”，才不会把资源增加误当成自动获得正确扩展。
