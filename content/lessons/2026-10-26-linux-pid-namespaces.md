# Linux：同一个进程，为什么在容器内外有不同的 PID

假设一台机器要同时运行两套服务。每套服务都有自己的启动程序、工作进程和监控脚本，希望管理自己的一组进程；机器外层的管理程序，又必须能统一观察并停止它们。如果所有程序只使用同一套全局 PID，进程编号就会把两套服务混在同一个管理世界里。今天要理解的设计，是 Linux 怎样让内部拥有局部的进程视图，同时保留外层的管理入口，而不是给每一套服务都复制一个内核。

最自然的办法，是约定某个 PID 范围属于某套服务，再让脚本只显示这个范围。作为受信任程序之间的管理约定，这可以有用；但隐藏 `ps` 的几行输出，并不会改变 `getpid`、父子关系或按 PID 寻找目标的系统调用。另一种办法是使用虚拟机，每套系统运行自己的内核，独立的 PID 世界自然成立；如果需求只是在同一 Linux 内核上组织不同的资源视图，就值得考虑更局部的边界。

Linux 的 namespace（命名空间）把某类原本全局的资源组织成带上下文的视图。容器运行时会组合多种 namespace 与其他机制；这里仅吃透 PID namespace，不把整个容器压成一张功能清单。它位于进程创建、PID 查找、信号和进程生命周期之间，改变的是这些接口怎样解释进程编号。[Linux namespaces 的定位与分类](https://man7.org/linux/man-pages/man7/namespaces.7.html)

## 先把对象，与看见对象的编号分开

关键洞察是：进程本身和进程在某个视图里的编号，不必是一回事。可以让内层拥有从 1 开始的编号空间，同一进程又在外层保留另一个编号。内部程序使用局部数字，外层管理者使用外层数字；两边操作的仍是同一个实际进程。这不是把内部的“进程 2”复制一份到外面，而是给同一对象保存不同上下文中的名字。

固定一个教学例子。最外层 PID namespace 叫 N0，监督者 P 在其中的 PID 是 4200。P 具备所需权限，使用带 `CLONE_NEWPID`、以 `SIGCHLD` 报告孩子退出的 `clone` 调用，得到新 namespace N1 中的第一个进程 I。假设 I 在 N0 分到 4201，在 N1 则是 1。随后 I 普通 `fork` 一个工作进程 W，假设 W 在 N0 分到 4202，在 N1 分到 2。这些数字是为推演选定的分配结果，没有在本机创建容器或记录实际 PID；内核细节固定核对 Linux 6.12，所有进程按单线程模型讨论。[创建新 PID namespace 的接口](https://man7.org/linux/man-pages/man2/clone.2.html)

看下面的对应关系：如果 I 说“我的孩子是 2”，P 应该把同一个孩子记作多少？

![教学编号对应：外层 N0 中 P=4200、I=4201、W=4202；内层 N1 中 I=1、W=2，P 没有内层可用 PID。两侧的 I 和 W 各自是同一个进程，没有复制。](assets/figures/linux-pidns-views.svg)

图 1：箭头只表示同一进程的编号对应，不表示父子关系或额外创建。N1 是 N0 的子 namespace；图不代表运行截图。

Linux 源码中的 `struct pid` 就保存了这种分离：其中的 `numbers` 数组由若干 `upid` 组成，每项包含一个数字和一个 namespace。分配 PID 时，`alloc_pid` 沿当前 namespace 向父级分配并记录各层编号。因此，真正有意义的查找条件是“哪个 namespace 里的哪个数字”，单独一个 2 还没有确定目标。[固定源码：PID 的多层表示](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/include/linux/pid.h#L43)，[各层编号的分配](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/kernel/pid.c#L166)

## 同一棵进程关系，怎样从两侧使用

P 创建 I 后，创建操作在 P 一侧返回的是外层编号 4201，P 才能用自己的接口继续管理孩子。I 调用 `getpid` 得到 1；I 创建 W 后，在 I 一侧得到的子进程编号是 2，W 自己调用 `getpid` 也得到 2。W 的 `getppid` 为 1，因为其父亲 I 在自己的视图中就是 1。I 的父亲却是外层 P，在 N1 中没有可用编号，所以 I 的 `getppid` 返回 0；这个 0 不代表 I 没有实际父亲。[getpid/getppid 与跨 namespace 的父关系](https://man7.org/linux/man-pages/man2/getpid.2.html)

这里的可见性具有方向：N0 的管理者能够按外层 PID 找到 N1 中的进程，N1 的程序不能反过来用 PID 寻找只存在于祖先视图的 P。内层再知道“外面的 P 是 4200”，也不能把 4200 当成跳过上下文的通行证；这个数字仍要在 N1 里解释。我们的例子里 N1 只有 1 和 2，4200 找不到 P；将来 N1 真有一个 4200，它也会是另一个局部目标。能找到对象与是否有权向它发送信号，仍是两层判断。[PID namespace 的层级与可见方向](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)

这给出了必须守住的不变量：**输入 PID 时按调用者的视图解析，输出 PID 时按相应视图表达，不能把一层的裸数字当成另一层的对象身份**。`find_vpid` 会把数字连同当前进程的活动 PID namespace 交给查找函数，而 `pid_nr_ns` 负责按指定 namespace 取得编号。假如日志代理把 W 报来的“2”直接当成外层目标，外层 PID 2 若存在，就会定位到完全无关的对象；即便权限检查阻止了后续操作，目标解析也已经错了。系统之间传递进程信息时必须保留足够的上下文。[固定源码：带视图的查找](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/kernel/pid.c#L318)，[按视图取得编号](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/kernel/pid.c#L485)

上面比较的是同一时刻仍存活的进程。旧进程结束并回收后，PID 还可能复用；补上 namespace 能解决视图混淆，却不能让数字成为永久身份。若要跨时间持有对特定进程的引用，还需要在正确时机取得 pidfd 等句柄，本篇不展开这条管理协议。[pidfd 的对象引用与 PID 复用边界](https://man7.org/linux/man-pages/man2/pidfd_open.2.html)

创建接口还有一个容易踩错的细节。若 P 先调用 `unshare(CLONE_NEWPID)`，改变的是后续孩子进入哪个 PID namespace，P 自己不会立刻变成内层 PID 1；必须再创建孩子，孩子才成为新视图中的第一个进程。进程所属的活动 PID namespace 在创建时确定，不能靠这一步把既有进程的身份重写掉。这个限制也使父子管理接口可以继续使用稳定的上下文。[unshare 的 CLONE_NEWPID 语义](https://man7.org/linux/man-pages/man2/unshare.2.html)

## 局部的 PID 1，还接过了什么责任

编号视图必须与退出管理配合，否则内部看似一套小系统，却没有人承接孩子的结束。在本例里，父进程正常等待、不设置自动回收选项：W 正常退出后，I 用内层编号 2 执行等待并回收它；I 最后退出，P 用外层编号 4201 回收 I。外层知道 W 的 4202，并不意味着 P 自动成为 W 的直接父亲，也不意味着可以忽略父子关系、用普通等待接口回收任意可见进程。[waitpid 的子进程与回收语义](https://man7.org/linux/man-pages/man2/waitpid.2.html)

观察两种结束顺序：如果 I 提前退出，而 W 还在运行，会只是让 W 换个父亲继续做事吗？

![教学生命周期：P 创建 I，I 再创建 W；正常分支中 W 退出由 I 按内层 PID 2 回收，I 退出由 P 按外层 PID 4201 回收；另一分支中 I 在 W 仍运行时退出，内核终止 N1 中剩余进程，P 再回收 I。](assets/figures/linux-pidns-lifecycle.svg)

图 2：上方是共同的创建过程，下方两栏是互斥的结束分支，不能把左栏结束后再接到右栏。省略其他子进程、信号处理与回收策略。

I 作为 N1 的 init，不仅恰好叫 1，还承担该局部进程世界的特殊职责，包括在相应收养规则下接管孤儿进程。若这个 init 退出，Linux 会终止该 namespace 中其他进程，因而不能把它当成随时可结束的普通启动脚本。固定版本源码的 `zap_pid_ns_processes` 先禁止继续分配 PID，再向剩余进程发送 `SIGKILL` 并等待清理。即使还有引用让 namespace 对象本身留存，也不能往已经失去 init 的同一个视图里重新开始一组进程。[固定源码：init 退出后的清理](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/kernel/pid_namespace.c#L170)，[禁止继续分配的检查](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/kernel/pid.c#L255)

因此，容器内部的第一个程序需要承担怎样的回收与退出行为，是设计问题，而不是只看它能否启动业务。还要留意内层 PID 1 的信号处理具有特殊规则，不能把普通进程的默认终止行为不加区别地套上去。本文推演的是主动退出的两条路径，没有执行信号注入，也没有覆盖所有收养与子收割者规则。[namespace init 的信号规则](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)

## 视图独立，哪些东西仍然共享

这种设计的美在于让局部管理与外层管理同时成立：内部用自己的名字组织服务，外部保留对同一批真实进程的管理能力。成本则落在各层编号的分配和查找、init 的生命周期职责，以及工具与上下文的配合。一个典型边界是 `/proc`：它显示哪套 PID 视图，与挂载它时的 PID namespace 有关，并不会因为某个读者进入另一个视图就自动改换。准备容器的 `/proc` 时，通常还要配合独立的挂载视图；只看 `ps` 输出，不足以证明所有接口都已获得预期上下文。[固定源码：procfs 记录 PID namespace](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/fs/proc/root.c#L244)，[procfs 与 PID 视图的配合](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)

PID namespace 也不自动生成独立的文件、网络或用户身份世界，这些边界由其他机制分别承担。CPU 和内存额度则属于 cgroups 等资源控制的职责：进程在局部看起来独立，不代表它拥有独占的物理资源。把“叫什么、能找到谁”与“允许做什么、能用多少资源”分开，才知道一个容器配置具体兑现了哪种承诺。[namespace 的资源分类](https://man7.org/linux/man-pages/man7/namespaces.7.html)，[cgroups 的资源控制职责](https://man7.org/linux/man-pages/man7/cgroups.7.html)

可以先独立判断：如果另建一个与 N1 平级的 N2，其中第一个进程也叫 1，N1 的 W 能否只凭这个数字找到它？若监督者只记下一条“工作进程 PID=2”，缺少了什么，才让这条记录无法可靠用于后续管理？不要急着补命令，先沿编号和对象关系回答。

类似的判断也适用于 PostgreSQL 的 schema。`tenant_a.orders` 与 `tenant_b.orders` 可以是两张不同的表，裸写 `orders` 时由 `search_path` 决定先找谁；名字必须连同解析上下文才有确定含义。共同结构是让局部名字可复用，把对象定位交给带上下文的规则。区别是 PostgreSQL 允许在权限满足时显式写出 schema 去访问另一张表，而内层进程不能给祖先 PID 加一个文本前缀，就越过 PID 可见边界。两者都不能把命名组织直接当成完整的权限或资源隔离。这是结构比较，不是在声称它们具有相同安全保证。[PostgreSQL 17 的 schema、查找路径与权限](https://www.postgresql.org/docs/17/ddl-schemas.html)
