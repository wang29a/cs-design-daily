# Flink 写出的文件，为什么要等检查点完成才算结果

前几天，Flink 故障后把总额从 35 恢复成 30，再重读最后的 5 元，仍能得到正确状态。但是，如果故障前那个 35 已经追加进下游文件，内存回滚并不会擦掉这一行。重放又写一次 35，下游就看见两份结果。今天把计算流水线补到末端，只吃透一个问题：怎样让文件发布与可恢复的计算边界配合起来？

这里的 sink 是流水线的输出端。求和算子把结果交给 FileSink 的 writer，writer 组织文件；独立的 committer 负责把待提交文件变成正式结果。JobManager 的检查点协调器完成整轮登记，TaskManager 执行写入、快照与提交。这个分工的价值在于：业务算子可以继续计算，文件也可以先写，却不必立刻让下游把它当成已经兑现的结果。

本篇固定 Flink 2.1.0 DataStream 流模式，启用 exactly-once 对齐检查点，最多一轮并行，使用同步受管状态与 HashMapStateBackend。FileSink 采用行编码、单 writer、单 bucket，显式选择 `OnCheckpointRollingPolicy`，每轮检查点关闭当前文件；关闭 compaction，不扩缩容。文件系统选 Flink 的本地实现，只推演原机任务进程故障：协调器仍在，检查点及输出磁盘保留，恢复任务可访问原路径，无其他程序改删文件。它不是整机丢盘后的恢复承诺，生产环境须另按部署选择共享存储。 [所选滚动策略](https://github.com/apache/flink/blob/release-2.1.0/flink-connectors/flink-file-sink-common/src/main/java/org/apache/flink/streaming/api/functions/sink/filesystem/rollingpolicies/OnCheckpointRollingPolicy.java#L27-L53)

源仍是未结束的 Kafka 输入，沿用单分区 P0：100、101、102 的金额为 10、20、5 元，`sum` 从 0 开始。每处理一笔，输出一行“输入编号，累计值”，依次是 `(100,10)`、`(101,30)`、`(102,35)`，不是把三行再相加。源位置按下一条读取的 offset 书写，输入历史完整保留。C10 划在 101 之后，应保存位置 102、总额 30。F10、F11 是教学文件代号，不是实际文件名；编号和故障时序均为推演，未运行 Flink、注入故障或测量性能。

最自然的办法是收到结果就追加到正式文件。只要接受重复并让下游可靠去重，这样做可以很实用；但仅启用检查点不会替它去重。反过来，先登记输入已处理、以后再补文件，登记后崩溃又可能漏行。把这两步调换，依然没有同时包含恢复位置、计算状态和输出责任的完成凭据。

关键洞察是把“写下字节”与“发布正式结果”分开。先把 `(100,10)`、`(101,30)` 写进尚未正式发布的 F10；到 C10 时关闭它，让内容稳定，并产生提交句柄 H10。H10 是可恢复提交句柄的教学代号，描述如何找到并提交这份具体文件，随后连同提交端的状态进入检查点。这样，未来即使不重读 100、101，也仍有足够材料补完它们的输出。检查点保存的是可恢复的提交责任，不必把文件正文再塞进算子总额里。

图一请观察：源已经准备从 102 恢复时，谁替前两条记录保留了尚未兑现的输出？

![图一。教学模型：处理 P0 的 100:+10、101:+20 后，sum=30，F10 写有两行 (100,10)、(101,30)。C10 到达 writer 时关闭 F10，使其成为 pending，并把提交句柄 H10 交给 committer。C10 保存下一源位置 102、算子状态 30、包含 H10 的提交端状态；整轮完成后才提交 F10，成为 finished。箭头表示先后与提交责任传递，不是运行追踪。F10、H10 是教学代号，pending 不代表出现了专用后缀。](assets/figures/flink-filesink-publication.svg)

实现中，`SinkWriterOperator.prepareSnapshotPreBarrier` 在传播本轮边界前刷新 writer 并发出 committables，即可提交对象。`FileWriterBucket.prepareCommit` 按所选策略关闭文件，再把 pending 文件的恢复句柄包装为这些对象。提交端收到的不是“请重新生成两行”，而是“请完成这份已经准备好的文件”。 [边界前准备提交对象](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/operators/sink/SinkWriterOperator.java#L188-L193) · [文件关闭与句柄交付](https://github.com/apache/flink/blob/release-2.1.0/flink-connectors/flink-connector-files/src/main/java/org/apache/flink/connector/file/sink/writer/FileWriterBucket.java#L194-L214)

文件有三种逻辑状态：正在写的 in-progress、已经关闭待提交的 pending、正式完成的 finished。pending 不保证改成一个叫 `.pending` 的文件名；物理暂存命名与逻辑状态不能混用。下游必须遵守 FileSink 的文件生命周期，只消费 finished 文件，不能把目录里所有可读字节都当结果。对于本地实现，暂存文件可以被主动找到并读取，这不是权限隔离。 [文件生命周期与读取约定](https://nightlies.apache.org/flink/flink-docs-release-2.1/docs/connectors/datastream/filesystem/#part-file-lifecycle)

`CommitterOperator.snapshotState` 把提交收集器的副本写入受管状态，保护本轮视图。相关任务快照可靠保存，协调器完成 C10 后，`notifyCheckpointComplete` 才推进相应范围的提交。两种完成仍有先后：C10 已是可恢复检查点，不等于 F10 此刻已经对读者正式可用；文件发布可能稍晚，还可能失败并触发恢复。 [提交材料的快照及完成通知](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/operators/sink/CommitterOperator.java#L144-L173)

现在安排故障：C10 已完整成功，但提交端还没执行 F10 的发布；实时求和已经处理 102 到达 35，另一个在写文件 F11 暂存了 `(102,35)`。任务进程退出。若恢复只载入位置 102 和总额 30，便永远不会重新产生前两行。正因为 C10 还保存 H10，恢复才知道必须完成 F10。

图二沿这条时序继续。另一个相邻故障窗口也请留意：若 F10 实际已经发布，进程却来不及记住成功，再调用提交会怎样？

![图二。教学恢复：C10 已可靠完成，保存位置 102、sum=30 和 H10；F10 尚未发布，实时状态已为 35，F11 在写 (102,35)，随后进程故障。恢复 C10，提交 H10 使原 F10 正式完成；F11 的旧尝试不作为 finished 结果消费。从 P0:102 重读 5，恢复总额为 35，写入新尝试 F11R；下一轮 C11 成功并提交后，该行正式可用。若 F10 在故障前已提交，恢复仍尝试同一 H10，本地实现发现暂存源已不存在而目标已存在，不创建第二个文件。箭头为选定教学时序。](assets/figures/flink-filesink-recovery.svg)

恢复时，提交算子的 `initializeState` 装载检查点里的收集器，并尽快提交不晚于恢复检查点的对象。因此即使完成通知还没送到，也能根据已完成的 C10 补交 H10。`FileCommitter` 使用 `recoverPendingFile(...).commitAfterRecovery()`，并非从业务输入重造 F10。完成通知不是唯一一次、绝不能丢的内存信号，持久保存的提交材料才让它可以被恢复接续。 [恢复时补交](https://github.com/apache/flink/blob/release-2.1.0/flink-runtime/src/main/java/org/apache/flink/streaming/runtime/operators/sink/CommitterOperator.java#L120-L140) · [FileSink 的实际提交调用](https://github.com/apache/flink/blob/release-2.1.0/flink-connectors/flink-connector-files/src/main/java/org/apache/flink/connector/file/sink/committer/FileCommitter.java#L55-L63)

若 F10 已经发布，恢复仍可能带着旧 H10 再试。接口要求恢复提交能够容忍先前已经成功的情况。本地实现检查原暂存路径与目标路径：暂存源还在便推进移动；源已不存在、正式目标已存在时，不再创建一份副本。这里重试的是同一文件的同一提交身份，不能换个新名字复制正文，再称它幂等。该判断依赖原文件未被外部改删，并非检查内容相同就自动去重。 [恢复提交的契约](https://github.com/apache/flink/blob/release-2.1.0/flink-core/src/main/java/org/apache/flink/core/fs/RecoverableFsDataOutputStream.java#L78-L88) · [本地文件的恢复提交分支](https://github.com/apache/flink/blob/release-2.1.0/flink-core/src/main/java/org/apache/flink/core/fs/local/LocalRecoverableFsDataOutputStream.java#L174-L203)

再恢复求和状态 30，从 102 重读 5，得到 35，写入新尝试 F11R。旧 F11 没有成为正式结果，读者不能消费它；恢复不保证所有遗留暂存字节立即消失。待下一轮 C11 完整成功并提交 F11R，正式文件合起来提供恰好三行，源下一位置为 103。若 C10 本来没完成，应恢复更早检查点并重做相应输入，不能拿未完成的 H10 单独宣布这批结果成立。

本例不变量是：略过的输入效果，既由检查点状态承接，也有已发布或可补交的文件输出；需要重读的输入，其旧尝试不能抢先成为正式结果。提前发布 F11，重放就可能重复 `(102,35)`；只保存 30 却丢掉 H10，恢复便可能缺前两行。它把两个独立更新间不可消除的瞬时窗口，改造成有持久凭据、可以补完并可重复尝试的步骤。

代价转移给了文件暂存、句柄持久化、提交重试和下游等待。所选策略每轮关闭文件，检查点频繁且流量小时容易形成小文件；检查点长期不能成功，正式输出也会迟迟不推进。多个 writer 的文件可以逐个完成，这不是整个目录的原子快照，更不能顺带保证读者消费文件后的短信只发一次。更换对象存储时，应重新核对可恢复写入、临时数据保留与提交语义，不能把本地移动分支直接套过去。 [恢复依赖存储材料仍在](https://github.com/apache/flink/blob/release-2.1.0/flink-core/src/main/java/org/apache/flink/core/fs/RecoverableWriter.java#L65-L81)

这与 Kafka 把输出和消费进度共同提交有相近结构：都让“以后可以跳过哪些输入”与其输出责任相容。差异在于 Kafka 把记录与组位置纳入同一事务；这里由 Flink 检查点保存源、计算和提交材料，文件系统再兑现发布，允许检查点先完成、文件稍后补交。它们共享恢复判断，具体事务与读取边界不同。 [Kafka 的输出与位置事务](https://kafka.apache.org/41/design/design/#using-transactions)

留两个独立推演：若 C10 完成通知丢失，但任务没有故障，后续 C11 完成时为什么不能只处理 C11 的新文件？若下游主动扫描并消费旧 F11 的暂存内容，即使最终目录只留下三行，外部业务还会发生什么？从“谁有权把哪份尝试当成正式结果”出发，才能判断 exactly-once 的边界真正落在哪里。
