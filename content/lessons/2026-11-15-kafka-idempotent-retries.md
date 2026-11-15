# Kafka 的写入确认丢了，重试为什么不会再添一份消息

订单 42 的付款事件已经写入 Kafka，副本也已达到昨天讨论的确认条件。leader 发出成功回复，网络连接却在生产者收到回复前断开。生产者眼里只有一次没有结果的发送，日志里却已经有付款。今天要理解的设计，就藏在这两个视角之间：怎样允许客户端继续尝试，又让同一次发送只占一个日志位置？

最自然的办法是超时后再发一次。若第一次请求根本没到，这样可以补救；若第一次已写入而回复丢失，普通追加就会留下两条付款。反过来，超时后永不重试又可能漏掉真正未写入的事件。单纯延长超时只能改变等待成本，无法让没有收到回复等同于没有执行。重复可以接受、后续已有业务去重时，普通重试仍可实用，但追加层本身没有消除这份歧义。 [Kafka 对发送结果不确定性的说明](https://kafka.apache.org/41/design/design/#message-delivery-semantics)

让 broker 比较消息内容，见过同样的字节就拒收，似乎也能解决问题。可是设备连续上报两次相同温度，可以是两个真实观测；同一个订单 key 下也会有付款、发货等不同事件。内容、路由键和“是不是刚才那次尝试”各有含义。这里的洞察是，把一次逻辑发送的身份跨越网络重试保留下来。重复传输可以发生，接收方据此判断它是否已经兑现过这次追加。

本篇固定 Kafka Java 客户端和 broker 的 4.1.0 实现，使用非事务的幂等生产者，显式设置 `enable.idempotence=true`、`acks=all`，保留默认重试配置。为便于逐步观察，`max.in.flight.requests.per.connection=1`，每个批次只含一条记录。讨论发生在同一个生产者会话内，重试及时完成，leader A 不变，没有其他写入穿插。数字与故障都是教学设定，没有启动集群或做丢包实验。配置契约还要求重试次数大于零，允许的在途请求数最多为 5。 [幂等模式的参数约束](https://kafka.apache.org/41/configuration/producer-configs/#enable.idempotence)

机制位于应用的 `send` 与分区日志的追加之间。Java 客户端先把记录放进对应分区的缓冲，由后台线程组成批次并发送。幂等模式取得 Kafka 分配的 producer ID，批次头还携带 producer epoch 和起始序号。ID 标识生产者，epoch 区分其代际；它不是分区 leader 的任期。序号在同一生产者的同一分区内推进，不是主题的全局计数，也不是业务订单号。 [批次头中的身份字段](https://kafka.apache.org/41/implementation/message-format/#record-batch)

设这次生产者的 ID 为 7、epoch 为 0，下面简写为 `(7, 0)`。它首次向 P0 发送，因此付款批次的序号是 0。P0 此前由其他发送积累了 0 至 99，下一日志位置是 100。序号 0 表示这位生产者在 P0 的第一条记录；offset 100 表示它在整条分区历史中的位置。把它们分开，多个生产者才能各自编号，又共同追加到同一条日志。

客户端排出这个批次时赋予序号。普通网络重试重新排入的是仍带原身份和序号的批次，不会把它当作一条新的应用记录重新编号。真实批次可以有多条记录，消耗相应长度的序号范围；我们把范围缩成 0 至 0。 [首次赋号与重试保留序号的分支](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/internals/RecordAccumulator.java#L896-L918) · [失败批次重新排队](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/internals/Sender.java#L677-L704)

看图一。回复丢失后，客户端再次传来的仍是 `(7, 0)` 的序号 0。broker 应该把日志末尾从 101 推到 102，还是把原来的 100 告诉它？

![图一。教学时序，批次各含一条记录。生产者 7、epoch 0 的付款批次序号 0 首次写到 P0 的 offset 100，末尾为 101，成功回复丢失。客户端保留同一身份重试，broker 识别重复并返回原 offset 100，末尾仍为 101。收到回复后，本次发送完成；下一条发货使用序号 1，写到 offset 101，末尾为 102。箭头表示步骤先后。](assets/figures/kafka-idempotent-retry.svg)

首次请求到达时，A 接受序号 0，把付款写到 offset 100，并更新该分区内生产者 7 的状态，记住 epoch、序号范围以及对应的日志位置。达到复制确认条件后，它发送成功回复。回复丢失改变了客户端掌握的信息，却没有撤销已经发生的追加。

重试到达，A 按 producer ID 找到已有状态，核对 epoch 以及批次首尾序号。它发现 0 至 0 已对应 offset 100，于是走重复批次分支：取回先前的追加信息，跳过真正的日志追加。重试因而仍得到原位置 100，日志末尾继续是 101。源码中的 `findDuplicateBatch` 匹配身份和序号范围，`UnifiedLog` 的重复分支填回旧 offset；另一分支才调用 `localLog.append`。 [重复范围的匹配](https://github.com/apache/kafka/blob/4.1.0/storage/src/main/java/org/apache/kafka/storage/internals/log/ProducerStateEntry.java#L134-L143) · [返回旧位置与执行追加的分岔](https://github.com/apache/kafka/blob/4.1.0/storage/src/main/java/org/apache/kafka/storage/internals/log/UnifiedLog.java#L1205-L1225)

假设这次回复终于到达，客户端这笔发送才有了成功结果。随后应用提交发货事件，新批次使用序号 1，写到 offset 101。这样，不确定的等待结束了，下一次逻辑发送也能继续推进。识别重复与等待复制仍是两个检查：前者决定要不要再次追加，后者决定何时能按 `acks=all` 报成功。幂等没有取消昨天的副本条件，也没有承诺通知消费者已经完成业务。

这条路径要守住的不变量是，在有效的同一生产者身份和分区序号空间里，同一批次的重试不能变成第二次追加，新批次则要接续已有序号。假如客户端把付款重试改编号为 1，broker 会把它认作新发送，完全无法知道应用其实是在弥补丢失的回复。反过来，若把发货冒用成旧序号 0，重复匹配也不会靠内容判断它是另一项业务，可能只返回付款的旧结果。稳定身份必须由协议一致地维护，不能把“字节相等”当成替代条件。

同样，当前已接受到序号 0，若一条新批次直接跳到 2，在本篇状态下会触发顺序检查错误，不会悄悄把缺口当作已完成。等待下一批接续的限制，既帮助避免重复，也让重试时的追加次序可核对。 [同代序号的接续检查](https://github.com/apache/kafka/blob/4.1.0/storage/src/main/java/org/apache/kafka/storage/internals/log/ProducerAppendInfo.java#L125-L153)

那么，应用捕获超时后自己再调用一次 `send`，还能沿用这份保证吗？图二从“付款已经写入 100”另起一个分支，保留相同 key 和内容，只改变调用的身份。

![图二。独立于图一后半段的分支。付款已由生产者 7、epoch 0、序号 0 写入 offset 100。应用在同一会话另调 send，下一条付款得到序号 1，追加到 offset 101；若重建非事务生产者并取得新 ID 8，序号重新从 0 开始，也会追加到 offset 101。两支互斥，都没有其他写入。相同 key 与内容不会使新发送自动归并为旧发送。](assets/figures/kafka-idempotent-scope.svg)

同一生产者再次接受应用调用，这是新的待发送记录，序号成为 1；重建非事务生产者取得新 ID 8 后，序号 0 也属于另一份身份。两者都可能把相同付款再追加到 101。客户端 API 明确说明，应用层重新发送不在自动去重范围内，普通幂等保证限于单个会话。若最终发送报错，业务不能凭这个错误就断言未写入，再无限循环新调用。跨重启的业务恢复需要另行设计事件身份、状态核对或事务协议。 [4.1.0 客户端对重发与会话范围的说明](https://github.com/apache/kafka/blob/4.1.0/clients/src/main/java/org/apache/kafka/clients/producer/KafkaProducer.java#L169-L176)

这份设计把成本放在客户端的批次缓冲、序号维护和错误处理，以及 broker 的生产者状态上。它也没有永久保存所有发送的结果。4.1.0 每个分区内的生产者状态最多保留最近 5 个批次的元数据，允许的在途请求数量与这个有界记忆相配合。不能绕过客户端协议，把很久以前的批次任意重新投递，再期待永久按原位置答复。批次身份还写进日志格式，以支持重新加载时恢复生产者状态；它并非只在某次连接的内存里比较一下内容。 [有界批次记录](https://github.com/apache/kafka/blob/4.1.0/storage/src/main/java/org/apache/kafka/storage/internals/log/ProducerStateEntry.java#L28-L38) · [状态重建对序号保留的要求](https://kafka.apache.org/41/implementation/message-format/#record-batch)

此前 TCP 的序号也处理过相似矛盾：确认丢失可能引起重传，接收方按同一字节区间识别重复，不把它交付为新增字节。Kafka 则把身份延续到应用协议中的日志批次，即使网络连接重建，仍能在上述会话范围内识别追加重试。两者结构相似，承诺却不同：TCP 序号约束一条连接的字节流，Kafka 身份约束生产者向分区的追加；重新调用业务接口会产生新数据，二者都不会自动证明“付款通知只执行一次”。 [TCP 的序号与重复检测](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.3)

留一个推演。图一如果第一次请求没有到达 A，重试的序号 0 会走哪条路径，最终占几个位置？再假设付款已经只有一份，但通知组发完短信、尚未保存消费进度就崩溃，恢复后还会不会重复通知？试着分别指出，发送身份、复制确认和消费恢复位置，各自在证明哪一步已经完成。
