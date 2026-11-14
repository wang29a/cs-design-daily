# Kafka 的 leader 已经写下消息，为什么还不能报成功

订单 42 的付款事件已经送到 Kafka。分区 leader 把它追加到位置 100，随后机器失联。生产者先前若收到了成功，接手的机器却没有这条记录，这个成功到底承诺了什么？前两讲分别解释了历史如何重读、事件如何排进分区，今天继续追问一条分区日志在换 leader 后怎样延续。

最自然的办法是 leader 写完就回复，再让其他机器慢慢复制。Kafka 的 `acks=1` 提供的就是这种确认边界。配置该对照场景时同时关闭生产者幂等，以符合参数约束。它减少生产者等待，适合能够承受故障窗口内数据丢失的用途。假设副本 B、C 都还没拿到付款事件，A 就失联，接任者手中只有到 99 为止的历史。复制任务原本计划继续，也已经无法从 A 取到这次新增。选择更多副本，并不会自动推迟成功回复。 [生产者的 acks 契约](https://kafka.apache.org/41/configuration/producer-configs/#acks)

另一种方案是等所有指定副本都收到再报成功。这能扩大接任范围，但只要其中一台坏了，剩下的机器即使健康也会被拖住。Kafka 引入动态的同步副本集合 ISR，让确认所等待的复制进度，与故障后可以承接这条日志的副本范围相互配合。这个设计要一起回答“谁已经跟得上”和“现在至少要有多少份可依赖的副本”。 [复制日志与 ISR 的设计](https://kafka.apache.org/41/design/design/#replicated-logs-quorums-isrs-and-state-machines-oh-my)

本篇固定 Kafka 4.1.0，推演 P0 的三个副本 A、B、C，A 为 leader，生产者用 `acks=all`，主题用 `min.insync.replicas=2`。为了聚焦 ISR 的交接关系，选用 ELR 特性版本为 0、`unclean.leader.election.enable=false` 的配置。Kafka 4.1 新集群默认启用 ELR，会扩大安全选主的候选管理方式；这里明确采用它关闭时的路径。下面的编号、故障和消息时序都是教学设定。 [ELR 的版本与默认行为](https://kafka.apache.org/41/operations/eligible-leader-replicas/)

开始时 ISR 是 {A，B，C}，三个副本都已经有 0 至 99。每份日志的末尾位置记为 LEO，都是 100，表示下一条可以写到 100。leader 还维护共同的高水位 HW，初值也为 100。对本篇非事务记录，位置小于 HW 的记录已经跨过复制提交边界，可以交给普通消费者。这个提交边界与消费者组保存的恢复位置各有职责，消费者甚至可以还没开始读。

A 追加付款事件后，自己的 LEO 变成 101，但 B、C 的进度仍是 100。它们仍在 ISR 内，集合里的“同步”允许短暂落后，含义并非每时每刻内容完全相同。follower 向 leader 拉取日志，写入后再通过后续拉取报告自己的新位置，leader 才能据此更新它掌握的复制进度。图一保留 ISR 不变，看看 B 追上后够不够报成功。

![图一。稳定 ISR 为 A、B、C。A 追加位置 100 后，三个 LEO 为 101、100、100；leader 确认 B 追上后为 101、101、100；确认 C 也追上后为 101、101、101。前两步 HW 为 100，最后推进到 101，覆盖本次写入目标，acks=all 才可成功。箭头表示教学时序，进度按 leader 已获知的状态画出。](assets/figures/kafka-ack-frontier.svg)

B 追上以后已经有两份数据，但 C 还在 ISR 中，`acks=all` 仍需等它。这里的 2 是允许成功写入的最小 ISR 规模，当前集合有三台时，就要覆盖三台。等 leader 获知 C 也到 101，HW 才能推进到 101，位置 100 的付款事件进入共同前缀，生产者获得成功回复的条件才满足。leader 为这笔写入保存的目标是记录之后的位置 101，比较式是 `HW >= 101`。 [最小 ISR 与全部 ISR 的区别](https://kafka.apache.org/41/configuration/topic-configs/#min.insync.replicas)

源码把这笔等待接在共享前沿上。`DelayedProduce` 重查各分区的待确认目标，`Partition.checkEnoughReplicasReachOffset` 核对 HW 是否覆盖目标，并检查副本规模。多笔写入因而可以等待同一个 HW 推进，各自依据自己的目标结束。在同一个 leader 上用单调前沿表示已完成的日志前缀，省去了为每条记录各自维护完整确认集合的需要；前沿能够压缩状态，依赖的是副本按日志顺序复制。 [延迟写入的完成检查](https://github.com/apache/kafka/blob/4.1.0/core/src/main/scala/kafka/server/DelayedProduce.scala#L89-L116) · [目标位置与高水位的比较](https://github.com/apache/kafka/blob/4.1.0/core/src/main/scala/kafka/cluster/Partition.scala#L1080-L1124)

回到通知组 N。即使复制层的 HW 已到 101，N 也可能仍把自己的恢复位置记为 100，因为付款通知还没发完。反过来，生产者收到成功时，N 也可能尚未拉取这条事件。复制层的结束条件解决的是这条历史能否交给后续读取与接任者，通知是否送达和消费位置何时提交，还要沿前两讲的处理流程继续推进。

现在改动图一的时序。C 长时间停在 100，B 已到 101。如果永远等 C，就退回了“坏一台就不能继续”的方案。Kafka 会按追赶与存活状态调整 ISR，滞后副本的判定涉及 `replica.lag.time.max.ms`。图二假设 C 被判定掉队，ISR 变更已经生效，看看确认条件和故障交接怎样一起变化。

![图二。独立的故障分支。C 掉队后，ISR 生效为 A、B，两者 LEO 均为 101，达到最小规模 2，HW 可推进到 101 并成功确认。随后 A 失联，B 接任并保有付款事件 100。C 仍停在 100，尚无付款事件；只剩 B 同步时，后续新的 acks=all 写入达不到最小规模 2。箭头表示教学时序。](assets/figures/kafka-ack-handoff.svg)

集合变成 {A，B} 后，两者均已覆盖目标，规模又没有低于 2，HW 可以前进，写入可以成功。随后 A 失联，B 能承接付款事件。C 的旧日志仍缺这条记录，必须先追赶才能重新进入同步集合。如今若只有 B 在 ISR，新的 `acks=all` 写入会因最小副本数不足而失败。系统用一段写入不可用，避免继续给只在一台上存在的新数据作出同样的成功承诺。 [不足最小规模时的追加检查](https://github.com/apache/kafka/blob/4.1.0/core/src/main/scala/kafka/cluster/Partition.scala#L1361-L1379)

这条链要守住的不变量是，已经向生产者确认的共同前缀，必须能被允许接任的副本承接。如果只因为 C 还活着，就把它那份停在 100 的日志当作新权威，付款事件会从新历史里消失。在本文的配置下，缺少安全候选时应等待合格副本恢复。启用不干净选主则是在用可能丢失历史换取恢复服务的机会。副本集合的变更也是受协议协调的状态，不能由每次写入随意挑一个最快搭档，再让任意旧副本接任。 [故障后选主的取舍](https://kafka.apache.org/41/design/design/#unclean-leader-election-what-if-they-all-die)

这个设计把成本付在额外网络传输、重复存储、较慢 ISR 成员带来的等待，以及集合变化和故障交接的协调上。还要看清“写入日志”的物理边界。Kafka 不要求每次确认都先对每份日志做 fsync，文件追加可以先进入操作系统页缓存；复制成功的保证需要相应副本持续保有数据。多台机器同时掉电并丢失尚未刷盘的内容，属于另一层故障条件。等待超时或响应丢失也不能反推记录一定没写入，客户端重试仍要遵循生产者的幂等与错误处理规则。 [页缓存与副本恢复的边界](https://kafka.apache.org/41/design/design/)

这与前面 PostgreSQL 组提交的结构相通。多笔事务各有自己的 WAL 目标，一次共享的同步可以覆盖它们，等待者核对完成前沿后分别返回。Kafka 也把“我的目标已覆盖”作为结束条件，但前沿推进所依赖的证据换成了副本复制进度和集合条件。PostgreSQL 那一讲关注本地 WAL 的持久化，Kafka 这一讲关注副本能否承接历史。比较两个前沿时，必须先问它跨过的到底是哪种失败。 [PostgreSQL WAL 同步与组提交](https://www.postgresql.org/docs/18/wal-configuration.html)

留一个推演。图一保持 ISR 为三台，A 和 B 都到 101、C 仍是 100，把 `min.insync.replicas` 从 2 改成 1，能否立刻结束等待？再沿图二，成功确认之后 A、B 都不可用，只剩尚未追上的 C，继续服务与保留已确认历史之间要作出什么选择？
