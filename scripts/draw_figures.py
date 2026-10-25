#!/usr/bin/env python3
"""Regenerate teaching diagrams with only the Python standard library."""
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'assets/figures'
INK, MUTED, LINE = '#18283b', '#5b6877', '#d9dfdc'
RUST, TEAL = '#a54426', '#287467'
PAPER, WHITE, GREEN, PEACH = '#f7f5f0', '#fffefb', '#e7f2ed', '#fae9df'


class Drawing:
    def __init__(self, name, height, title, subtitle):
        self.name, self.height = name, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="560" height="{height}" '
                      f'viewBox="0 0 560 {height}" role="img" aria-labelledby="title desc">',
                      f'<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>',
                      '<defs>']
        for key, color in [('ink', INK), ('teal', TEAL), ('rust', RUST)]:
            self.parts.append(f'<marker id="{key}" viewBox="0 0 10 10" refX="9" refY="5" '
                              f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                              f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>')
        self.parts.extend(['</defs>', '<g font-family="-apple-system,BlinkMacSystemFont,PingFang SC,Microsoft YaHei,sans-serif">'])
        self.rect(0, 0, 560, height, PAPER, radius=12, stroke='none')
        self.text(32, 48, title, size=26, weight=650)
        self.text(32, 80, subtitle, size=20, color=MUTED)

    def rect(self, x, y, w, h, fill=WHITE, radius=10, stroke=LINE, dash=False):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
                          f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"' +
                          (' stroke-dasharray="7 5"' if dash else '') + '/>')

    def text(self, x, y, value, size=24, color=INK, weight=400, anchor='start'):
        self.parts.append(f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
                          f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>')

    def arrow(self, points, color='ink', dash=False):
        stroke = {'ink': INK, 'teal': TEAL, 'rust': RUST}[color]
        path = 'M ' + ' L '.join(f'{x} {y}' for x, y in points)
        self.parts.append(f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="2.5" '
                          f'marker-end="url(#{color})"' + (' stroke-dasharray="7 5"' if dash else '') + '/>')

    def rule(self, y):
        self.parts.append(f'<path d="M 32 {y} H 528" stroke="{LINE}"/>')

    def card(self, x, y, w, h, title, detail='', fill=WHITE, color=INK, size=24):
        self.rect(x, y, w, h, fill)
        self.text(x + w / 2, y + (h / 2 + 8 if not detail else 34), title,
                  size=size, color=color, weight=600, anchor='middle')
        if detail:
            self.text(x + w / 2, y + 65, detail, size=20, color=MUTED, anchor='middle')

    def save(self):
        self.parts.extend(['</g>', '</svg>'])
        (OUT / (self.name + '.svg')).write_text('\n'.join(self.parts) + '\n', encoding='utf-8')


def pipe_flow():
    d = Drawing('pipe-flow', 650, '接口负责连接，程序负责自己的工作', '实线箭头：字节流向 · 与正文的四行日志对应')
    rows = [(112, 'app.log', '四行日志，其中两行以 ERROR 开头', WHITE),
            (234, 'grep', '筛选 ERROR → 标准输出 fd 1', WHITE),
            (356, '内核管道缓冲区', '传递字节，不解释日志的业务含义', GREEN),
            (478, 'wc -l', '标准输入 fd 0 → 统计换行符', WHITE)]
    for y, title, detail, fill in rows:
        d.card(40, y, 480, 86, title, detail, fill)
    for y in [198, 320, 442]:
        d.arrow([(280, y + 5), (280, y + 30)], color='teal')
    d.rule(591)
    d.text(280, 626, '最终输出 2；两边无需知道对方是谁', size=22, anchor='middle')
    d.save()


def pipe_eof():
    d = Drawing('pipe-eof', 608, '缓冲区为空，还不能说明输入结束', '普通阻塞管道 · 两个状态只差最后一个写端引用')
    for y, title, refs, result, fill, color in [
        (112, '① grep 退出，父进程仍保留写端', '1', 'wc 的 read 继续等待', PEACH, RUST),
        (364, '② 父进程关闭最后一个写端', '0', 'read 返回 0 → wc 输出 2', GREEN, TEAL),
    ]:
        d.rect(24, y, 512, 202, fill)
        d.text(44, y + 36, title, size=23, weight=600)
        d.card(44, y + 58, 232, 64, '缓冲区：空', size=23)
        d.card(294, y + 58, 222, 64, '写端引用：' + refs, size=23)
        d.text(280, y + 167, result, color=color, weight=600, anchor='middle')
    d.arrow([(280, 320), (280, 352)])
    d.text(280, 594, 'EOF 需要：数据读空，并且所有写端都关闭', size=21, anchor='middle')
    d.save()


def vm_mapping():
    d = Drawing('vm-mapping', 570, '相同虚拟地址，可以指向不同物理页', '教学模型：页大小 4096 字节 · 箭头表示地址翻译')
    for y, name, ppn, address, fill in [
        (122, '编辑器的映射上下文', '9', '0x9234', GREEN),
        (312, '索引器的映射上下文', '20', '0x14234', PEACH),
    ]:
        d.text(40, y, name, size=23, weight=600)
        d.card(32, y + 20, 212, 100, '虚拟地址 0x1234', '页 1 · 偏移 0x234', size=21)
        d.card(314, y + 20, 214, 100, '物理地址 ' + address, '物理页 ' + ppn + ' · 偏移不变', fill, size=20)
        d.arrow([(252, y + 69), (306, y + 69)], color='teal')
        d.text(280, y + 154, '改的是页号，保留同一个页内偏移', size=21, color=MUTED, anchor='middle')
    d.rule(502)
    d.text(280, 541, '物理地址 = 物理页号 × 4096 + 0x234', size=22, anchor='middle')
    d.save()


def cow_states():
    d = Drawing('cow-states', 718, '写时复制：先共享，实际写入时分离', '箭头表示映射 · A / B 表示目标字节的内容')
    d.text(32, 124, '① fork 后：同一页，双方都暂时只读', size=23, weight=600)
    d.card(32, 148, 224, 82, '父进程 · 虚拟页 1', '只读 / COW', size=22)
    d.card(304, 148, 224, 82, '子进程 · 虚拟页 1', '只读 / COW', size=22)
    d.card(148, 276, 264, 82, '物理页 9 · A', '引用计数 2', GREEN)
    d.arrow([(144, 234), (144, 254), (210, 254), (210, 270)], color='teal')
    d.arrow([(416, 234), (416, 254), (350, 254), (350, 270)], color='teal')
    d.rule(382)
    d.text(32, 417, '② 子进程触发异常：复制、改映射、重试', size=22, weight=600)
    d.card(32, 444, 224, 82, '父进程 · 虚拟页 1', '仍只读 / COW', size=22)
    d.card(304, 444, 224, 82, '子进程 · 虚拟页 1', '已恢复写权限', PEACH, size=22)
    d.card(32, 570, 224, 82, '物理页 9 · A', '引用计数 1', GREEN)
    d.card(304, 570, 224, 82, '物理页 20 · B', '复制 A 后重试写入 B', PEACH, size=23)
    d.arrow([(144, 532), (144, 563)], color='teal')
    d.arrow([(416, 532), (416, 563)], color='rust')
    d.text(280, 694, '写入落到私有副本，父进程仍读取 A', size=22, anchor='middle')
    d.save()


def wal_commit():
    d = Drawing('wal-commit', 640, '日志里有新页面，不等于事务已提交', 'SQLite WAL 教学模型 · 省略文件头、校验与锁')
    d.card(32, 112, 496, 80, '主数据库始终暂存 A0、B0', '下面观察提交前后的 WAL 与读者视图')
    for y, heading, wal, view, fill, color in [
        (220, '① 尚未追加', 'WAL：无新页面', '可见 A0、B0', WHITE, INK),
        (352, '② 只追加 A1', 'WAL：A1，尚无提交边界', '仍可见 A0、B0', PEACH, RUST),
        (484, '③ 提交边界有效', 'WAL：A1、B1 + 提交边界', '新读者可见 A1、B1', GREEN, TEAL),
    ]:
        d.rect(32, y, 496, 112, fill)
        d.text(52, y + 30, heading, size=22, weight=600)
        d.text(52, y + 62, wal, size=21, color=MUTED)
        d.text(52, y + 94, view, size=22, color=color, weight=600)
    d.text(280, 625, '可见性看提交边界；掉电保证还要看同步策略', size=20, anchor='middle')
    d.save()


def wal_readers():
    d = Drawing('wal-readers', 704, '旧读者守住旧边界，新读者看到新提交', '时间自上而下 · 首次读取才建立本例的旧快照')
    x = 56
    d.arrow([(x, 117), (x, 654)], color='teal')
    for y, heading, detail, fill in [
        (116, '① R：BEGIN 后执行 SELECT', '读取 A0、B0，固定旧的可见边界', WHITE),
        (266, '② 写者提交 A1、B1', '主数据库仍为 A0、B0；新版本在 WAL', GREEN),
        (416, '③ R 在同一读事务内再次查询', '仍读到 A0、B0，不跨过旧边界', WHITE),
        (566, '④ N 开始新的读事务', '按新边界从 WAL 读到 A1、B1', GREEN),
    ]:
        d.card(88, y, 440, 92, heading, detail, fill, size=22)
    d.text(280, 689, 'R 的旧视图维持到读事务结束', size=22, anchor='middle')
    d.save()


def git_objects():
    d = Drawing('git-objects', 650, '完整版本，共享同一份未变化内容', '实线：对象引用 · 虚线：提交的父关系')
    d.card(32, 112, 216, 60, '提交 C0')
    d.card(312, 112, 216, 60, '提交 C1', fill=PEACH)
    d.arrow([(306, 142), (254, 142)], dash=True)
    for x, label, fill in [(32, '0', WHITE), (312, '1', PEACH)]:
        d.card(x, 220, 216, 64, '根 tree · T' + label, fill=fill, size=23)
        d.card(x, 334, 216, 84, 'notes tree · D' + label, '记录文件名 → blob', fill, size=23)
        d.arrow([(x + 108, 177), (x + 108, 213)])
        d.arrow([(x + 108, 290), (x + 108, 327)])
    d.card(24, 510, 150, 68, 'blob M0', size=23)
    d.card(205, 510, 150, 68, 'blob N0', fill=GREEN, color=TEAL, size=23)
    d.card(386, 510, 150, 68, 'blob M1', fill=PEACH, color=RUST, size=23)
    d.arrow([(94, 424), (94, 503)])
    d.arrow([(199, 424), (240, 468), (250, 503)], color='teal')
    d.arrow([(365, 424), (326, 468), (310, 503)], color='teal')
    d.arrow([(462, 424), (462, 503)], color='rust')
    d.text(280, 483, '共享', size=20, color=TEAL, anchor='middle')
    d.text(99, 607, 'memory.md', size=20, anchor='middle')
    d.text(280, 607, 'network.md', size=20, anchor='middle')
    d.text(461, 607, 'memory.md', size=20, anchor='middle')
    d.text(280, 637, 'memory.md 改为 M1；network.md 仍为 N0', size=21, anchor='middle')
    d.save()


def git_refs():
    d = Drawing('git-refs', 580, '移动分支名字，保留已有的内容与历史', '实线：分支引用 · 虚线：提交的父关系')
    d.text(32, 121, '① 创建 experiment：只新增一个引用', size=22, weight=600)
    d.card(32, 145, 224, 58, 'main', fill=GREEN, color=TEAL)
    d.card(304, 145, 224, 58, 'experiment', fill=PEACH, color=RUST)
    d.card(184, 255, 192, 60, 'C1')
    d.arrow([(144, 209), (144, 234), (230, 234), (230, 248)], color='teal')
    d.arrow([(416, 209), (416, 234), (330, 234), (330, 248)], color='rust')
    d.rule(341)
    d.text(32, 379, '② 新提交 C2：只移动 experiment', size=22, weight=600)
    d.card(32, 403, 224, 58, 'main', fill=GREEN, color=TEAL)
    d.card(304, 403, 224, 58, 'experiment', fill=PEACH, color=RUST)
    d.card(56, 503, 176, 58, 'C1')
    d.card(328, 503, 176, 58, 'C2', fill=PEACH)
    d.arrow([(144, 466), (144, 496)], color='teal')
    d.arrow([(416, 466), (416, 496)], color='rust')
    d.arrow([(322, 532), (238, 532)], dash=True)
    d.text(280, 520, '父提交', size=20, color=MUTED, anchor='middle')
    d.save()


def tcp_window():
    d = Drawing('tcp-window', 660, '确认推进，新的发送额度随之释放', '教学模型：有效窗口恒为 4000 字节 · 每格 1000 字节')
    x0, cell = 36, 97
    for y, heading, states in [
        (153, '① 已发三段，尚未收到确认', ['在途', '在途', '在途', '可发送', '窗外']),
        (417, '② 收到 ACK 2000，尚未发送新数据', ['已确认', '在途', '在途', '可发送', '可发送']),
    ]:
        d.text(32, y - 35, heading, size=23, weight=600)
        for i, state in enumerate(states):
            color = GREEN if state in ('可发送', '已确认') else PEACH if state == '在途' else WHITE
            d.rect(x0 + i * cell, y, cell - 4, 68, color, radius=5)
            d.text(x0 + i * cell + 45, y + 42, state, size=22, anchor='middle')
        for i in range(6):
            d.text(x0 + i * cell, y + 98, str(1000 + i * 1000), size=20,
                   color=MUTED, anchor='middle')
        start = 0 if y == 153 else 1
        d.parts.append(f'<path d="M {x0+start*cell} {y+125} v 10 h {4*cell-4} v -10" '
                       f'fill="none" stroke="{TEAL}" stroke-width="2.5"/>')
        d.text(280, y + 169, '发送范围 [1000, 5000)' if start == 0 else '发送范围 [2000, 6000)',
               size=23, color=TEAL, anchor='middle')
    d.text(280, 637, '下一个待发送位置仍为 4000；剩余额度 1000 → 2000', size=20, anchor='middle')
    d.save()


def tcp_gap():
    d = Drawing('tcp-gap', 660, '后面的字节到了，确认也不能跨过缺口', '接收端视图 · ACK 表示下一个期望收到的字节序号')
    for y, title, middle, ack, fill in [
        (154, '① 第二段丢失，第三段已到达', '缺失', 'ACK 2000', PEACH),
        (422, '② 第二段重传到达，连续前缀补齐', '已收到', 'ACK 4000', GREEN),
    ]:
        d.text(32, y - 36, title, size=22, weight=600)
        for i, state in enumerate(['已收到', middle, '已收到']):
            x = 32 + i * 168
            d.card(x, y, 160, 100, state, str(1000 + i * 1000) + '—' + str(1999 + i * 1000),
                   fill if i == 1 else GREEN, size=23)
        boundary = 200 if y == 154 else 528
        d.arrow([(boundary, y + 138), (boundary, y + 105)], color='rust' if y == 154 else 'teal')
        d.text(280, y + 172, ack + ('：前沿停在缺口前' if y == 154 else '：前沿越过已补齐区间'),
               size=23, color=RUST if y == 154 else TEAL, anchor='middle')
    d.text(280, 645, '乱序缓存不等于连续收到；累计确认承诺连续前缀', size=20, anchor='middle')
    d.save()


def bloom_bits(d, y, bits, highlights=()):
    for i, value in enumerate(bits):
        x = 36 + i * 61
        d.text(x + 27, y - 14, str(i), size=22, color=MUTED, anchor='middle')
        d.rect(x, y, 55, 56, GREEN if value else WHITE, radius=5,
               stroke=TEAL if i in highlights else LINE)
        d.text(x + 27, y + 37, str(value), size=27, weight=600, anchor='middle')


def bloom_insert():
    d = Drawing('bloom-insert', 638, '标记可以叠加，不需要专属位置', '教学模型：m = 8 位，k = 2 · 向下箭头表示时间')
    for y, heading, bits, highlights in [
        (158, '① 初始：所有位置为 0', [0] * 8, ()),
        (337, '② 插入 24：置位 (1, 4)', [0, 1, 0, 0, 1, 0, 0, 0], (1, 4)),
        (516, '③ 插入 31：置位 (4, 6)', [0, 1, 0, 0, 1, 0, 1, 0], (4, 6)),
    ]:
        d.text(32, y - 49, heading, size=24, weight=600)
        bloom_bits(d, y, bits, highlights)
    for y in (225, 404):
        d.arrow([(280, y), (280, y + 30)], color='teal')
    d.text(280, 614, '位置 4 被共享；插入只置 1，不清零', size=23, anchor='middle')
    d.save()


def bloom_query():
    d = Drawing('bloom-query', 742, '相同最终答案，不同查询成本', '教学集合 {24, 31} · 箭头表示处理顺序')
    bloom_bits(d, 133, [0, 1, 0, 0, 1, 0, 1, 0])
    for x, key, positions, values, decision, end, fill, color in [
        (32, '57', '(2, 6)', '(0, 1)', '一定不存在', '跳过精确查询', GREEN, 'teal'),
        (294, '29', '(1, 6)', '(1, 1)', '可能存在', '继续精确查询', PEACH, 'rust'),
    ]:
        d.card(x, 234, 234, 87, '查询 ' + key, '位置 ' + positions, size=26)
        d.arrow([(x + 117, 325), (x + 117, 350)], color=color)
        d.card(x, 358, 234, 87, '读到 ' + values, decision, fill, size=25)
        d.arrow([(x + 117, 449), (x + 117, 474)], color=color)
        d.card(x, 482, 234, 87, end, '最终：不存在', fill, size=24)
        d.text(x + 117, 616, '可靠否定' if key == '57' else '一次误报',
               size=24, color=TEAL if key == '57' else RUST, weight=600, anchor='middle')
    d.rule(652)
    d.text(280, 695, '“可能存在”只放行，精确查询负责最终确认', size=22, anchor='middle')
    d.save()


def snapshot_money():
    d = Drawing('snapshot-money', 670, '钱会离开账户，却没有离开系统', '教学模型 · 横向为转移方向，向下为阶段顺序')
    for y, heading, a, channel, b in [
        (135, '① 发送前', 'A：100 元', '通道：空', 'B：100 元'),
        (323, '② x 已发送，尚未接收', 'A：90 元', 'x：10 元', 'B：100 元'),
        (511, '③ B 收到 x', 'A：90 元', '通道：空', 'B：110 元'),
    ]:
        d.text(32, y - 27, heading, size=24, weight=600)
        d.card(32, y, 150, 68, a, size=23)
        d.card(206, y, 148, 68, channel, fill=PEACH if 'x' in channel else GREEN, size=23)
        d.card(378, y, 150, 68, b, size=23)
        d.arrow([(184, y + 34), (202, y + 34)], color='teal')
        d.arrow([(356, y + 34), (374, y + 34)], color='teal')
        d.text(280, y + 102, '90 + 10 + 100 = 200' if 'x' in channel else
               ('100 + 0 + 100 = 200' if y == 135 else '90 + 0 + 110 = 200'),
               size=23, anchor='middle')
    for y in (253, 441):
        d.arrow([(280, y), (280, y + 28)], color='ink')
    d.text(280, 648, '通道里的业务消息，也是全局状态', size=24, anchor='middle')
    d.save()


def snapshot_marker():
    d = Drawing('snapshot-marker', 960, '保存的照片，不跟着实时状态改', '同一轮快照 · x 已发送 · 向下表示本例事件顺序')
    rows = [
        (110, '① B 发起：保存 B = 100',
         '开始记录 A→B；B→A 发出 M_B', 'A→B 中仍有 x；B 尚未收到', WHITE),
        (299, '② A 收到 M_B：保存 A = 90',
         '记录 B→A 为空；发出 M_A', 'A→B 的交付顺序：x → M_A', WHITE),
        (488, '③ B 收到 x：实时余额 = 110',
         '保存的 B 仍是 100，不再修改', 'A→B 清单：加入 x（10 元）', PEACH),
        (677, '④ B 收到 M_A：关闭清单',
         'A→B 保存 x；B→A 保存空', '两端与两条通道记录均已完成', GREEN),
    ]
    for y, heading, line1, line2, fill in rows:
        d.rect(32, y, 496, 149, fill)
        d.text(52, y + 37, heading, size=24, weight=600)
        d.text(52, y + 80, line1, size=23)
        d.text(52, y + 119, line2, size=23, color=MUTED)
        if y != 677:
            d.arrow([(280, y + 155), (280, y + 181)], color='teal')
    d.rule(856)
    d.text(280, 897, '收集结果：90 + 100 + 10 + 0 = 200', size=24, anchor='middle')
    d.text(280, 935, 'M_A、M_B 是标记，不转移金额', size=22, color=MUTED, anchor='middle')
    d.save()


def snapshot_order():
    d = Drawing('snapshot-order', 658, '标记一旦超车，记录就会漏钱', '同样保存 A = 90、B = 100 · 横向为 B 的接收顺序')
    for y, heading, first, second, record, result, fill, color in [
        (117, '① 正确：业务消息先到', 'x：10 元', 'M_A',
         '记录 x 后，标记关闭清单', '通道保存 10 元；合计 200 元', GREEN, 'teal'),
        (375, '② 反事实：标记超过 x', 'M_A', 'x：10 元',
         '先关闭空清单，x 随后才到', '通道保存 0 元；合计 190 元', PEACH, 'rust'),
    ]:
        d.rect(32, y, 496, 224, fill)
        d.text(52, y + 36, heading, size=24, weight=600)
        d.card(64, y + 54, 184, 59, first, size=24)
        d.card(312, y + 54, 184, 59, second, size=24)
        d.arrow([(258, y + 83), (300, y + 83)], color=color)
        d.text(280, y + 155, record, size=23, anchor='middle')
        d.text(280, y + 195, result, size=23, weight=600,
               color=TEAL if color == 'teal' else RUST, anchor='middle')
    d.text(280, 636, '业务消息与标记，需要同一逻辑通道的顺序保证', size=21, anchor='middle')
    d.save()


def lsm_path():
    d = Drawing('lsm-path', 860, '同一批修改，需要两种不同表示', '教学模型：单数据分组 · WAL 开启 · sync=true')
    d.card(32, 112, 496, 90, '应用：Put / Delete', '修改 a、b、c；需要查询，也需要恢复')
    d.card(32, 258, 236, 100, 'WAL', '按修改顺序记录', PEACH)
    d.card(292, 258, 236, 100, 'memtable', '内存中的有序数据', GREEN)
    d.arrow([(220, 210), (150, 248)], color='rust')
    d.arrow([(340, 210), (410, 248)], color='teal')
    d.text(150, 402, '恢复依据完成同步', size=21, color=RUST, anchor='middle')
    d.text(150, 434, '成功返回前的必要条件', size=20, color=MUTED, anchor='middle')
    d.card(32, 478, 496, 86, '冻结旧 memtable，启用新的 memtable', '旧批次稳定下来，新修改继续进入内存', GREEN, size=22)
    d.arrow([(410, 366), (410, 450), (280, 450), (280, 470)], color='teal')
    d.card(32, 612, 496, 86, '刷出：生成 L0 的新 SST 文件', 'S1、S2、S3 各自按键有序，写完后保持不变', size=22)
    d.arrow([(280, 572), (280, 604)], color='teal')
    d.card(32, 746, 496, 78, '后台合并：重建新的有序文件', '维持读取答案，控制重复版本与候选文件', GREEN, size=22)
    d.arrow([(280, 706), (280, 738)], color='teal')
    d.text(280, 847, '箭头表示流向，不表示完整并发调用时序', size=20, color=MUTED, anchor='middle')
    d.save()


def lsm_versions():
    d = Drawing('lsm-versions', 738, '文件各自有序，同一个键仍有多个版本', '删除标记已刷出 · 本例按串行刷出顺序查找 L0')
    rows = [
        (122, 'S3：最新批次', 'a@5 = DEL', 'Get(a) → 不存在；到这里结束', PEACH, RUST),
        (314, 'S2：第二批次', 'b@3 = 21，c@4 = 30', 'Get(b) → 21；不用取 S1 的旧值', GREEN, TEAL),
        (506, 'S1：第一批次', 'a@1 = 10，b@2 = 20', '旧记录仍在文件里，已被更新覆盖', WHITE, MUTED),
    ]
    for y, title, data, result, fill, color in rows:
        d.rect(32, y, 496, 150, fill)
        d.text(54, y + 34, title, size=24, weight=600)
        d.text(280, y + 81, data, size=26, anchor='middle')
        d.text(280, y + 123, result, size=22, color=color, anchor='middle')
    d.arrow([(16, 156), (16, 528)], color='teal')
    d.text(280, 699, 'DEL 是覆盖证据；文件缺失一个键只排除该文件', size=21, anchor='middle')
    d.text(280, 727, '@ 后的数字是修改序号，不是时间戳', size=20, color=MUTED, anchor='middle')
    d.save()


def lsm_delete():
    d = Drawing('lsm-delete', 888, '删掉删除标记，旧数据可能重新出现', '教学模型：没有旧快照 · 所有相关文件在图中')
    d.rect(32, 116, 496, 290, PEACH)
    d.text(54, 154, '反事实：只处理 S3', size=25, weight=600)
    d.card(54, 180, 224, 72, 'a@5 = DEL', size=24)
    d.card(348, 180, 158, 72, '无输出', size=24)
    d.arrow([(286, 216), (338, 216)], color='rust')
    d.text(280, 293, 'S1 仍有 a@1 = 10', size=25, anchor='middle')
    d.arrow([(280, 308), (280, 337)], color='rust')
    d.text(280, 375, 'Get(a) → 10：已删除的值“复活”', size=23, color=RUST, weight=600, anchor='middle')
    d.rect(32, 442, 496, 374, GREEN)
    d.text(54, 480, '正确：完整覆盖 S1、S2、S3', size=24, weight=600)
    d.text(280, 533, 'a：DEL@5 与 10@1 → 都省去', size=23, anchor='middle')
    d.text(280, 577, 'b：21@3 与 20@2 → 留 21@3', size=23, anchor='middle')
    d.text(280, 621, 'c：30@4 → 留 30@4', size=23, anchor='middle')
    d.arrow([(280, 643), (280, 674)], color='teal')
    d.card(54, 688, 452, 72, '新文件：b@3 = 21，c@4 = 30', size=24)
    d.text(280, 794, 'Get(a) → 不存在；读取答案保持一致', size=23, color=TEAL, weight=600, anchor='middle')
    d.text(280, 855, '仍有更旧记录或旧快照时，不能照此省去', size=22, anchor='middle')
    d.save()


def rocksdb_version_readers():
    d = Drawing('rocksdb-version-readers', 886, '入口切换了，旧读者仍有自己的路径', '教学模型：单列族 · 序号 5 · 箭头表示持有')
    d.rect(32, 112, 496, 280, PEACH)
    d.text(54, 150, '旧迭代器 R：发布前创建，尚未关闭', size=23, weight=600)
    d.card(54, 172, 452, 66, 'R → V0 = {S1, S2, S3}', size=25)
    d.arrow([(280, 246), (280, 273)], color='rust')
    for y, label in [(306, 'S1：a@1=10，b@2=20'), (342, 'S2：b@3=21，c@4=30'), (378, 'S3：a@5=DEL')]:
        d.text(280, y, label, size=23, anchor='middle')
    d.rect(32, 426, 496, 222, GREEN)
    d.text(54, 465, '新请求 N：发布后取得当前集合', size=23, weight=600)
    d.card(54, 487, 452, 66, 'N → V1 = {S4}', size=25)
    d.arrow([(280, 561), (280, 588)], color='teal')
    d.text(280, 625, 'S4：b@3=21，c@4=30', size=25, anchor='middle')
    d.rule(690)
    d.text(280, 733, '两条读取路径：a 不存在，b=21，c=30', size=24, weight=600, anchor='middle')
    d.text(280, 779, '旧文件集合 ≠ 旧修改序号', size=25, color=TEAL, anchor='middle')
    d.text(280, 820, '假设：无旧快照、无其他相关文件', size=22, color=MUTED, anchor='middle')
    d.text(280, 855, '图中省略 memtable 与 SuperVersion', size=21, color=MUTED, anchor='middle')
    d.save()


def rocksdb_publication_crash():
    d = Drawing('rocksdb-publication-crash', 945, '落盘的成员记录决定重启后用谁', '教学模型：正常同步成功 · 向下箭头表示顺序')
    d.card(40, 116, 480, 90, '① 写完 S4，同步文件与目录', 'S4 内容：b@3=21，c@4=30', size=24)
    d.arrow([(280, 214), (280, 249)], color='teal')
    d.rect(40, 265, 480, 124, PEACH)
    d.text(280, 305, '断电 A：edit 尚未追加', size=24, weight=600, anchor='middle')
    d.text(280, 342, '恢复 V0 = {S1, S2, S3}', size=24, color=RUST, anchor='middle')
    d.text(280, 374, 'S4 存在，也尚未取得成员资格', size=21, anchor='middle')
    d.arrow([(280, 397), (280, 433)], color='teal')
    d.card(40, 449, 480, 90, '② 完整 edit 追加并同步成功', '移除 S1、S2、S3；加入 S4', size=24)
    d.arrow([(280, 547), (280, 582)], color='teal')
    d.rect(40, 598, 480, 110, GREEN)
    d.text(280, 638, '断电 B：尚未发布内存集合', size=24, weight=600, anchor='middle')
    d.text(280, 678, '恢复 V1 = {S4}', size=25, color=TEAL, anchor='middle')
    d.arrow([(280, 716), (280, 752)], color='teal')
    d.card(40, 768, 480, 66, '③ 正常运行中发布 V1', size=25)
    d.text(280, 882, '追加后、同步结果未知：不在 A 的范围内', size=22, anchor='middle')
    d.text(280, 919, 'VersionEdit 是逻辑替换，不是磁盘原子写', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_retirement():
    d = Drawing('rocksdb-retirement', 893, '不再接待新读者，不代表可以销毁', '教学模型：无其他持有者 · 不画精确引用计数')
    d.rect(32, 112, 496, 207, PEACH)
    d.text(54, 153, '① 发布 V1；R 还在读取', size=25, weight=600)
    d.card(54, 173, 452, 66, '当前入口 → V1 → S4', size=25)
    d.text(280, 284, 'R → V0 → S1、S2、S3', size=25, color=RUST, anchor='middle')
    d.arrow([(280, 327), (280, 365)], color='teal')
    d.rect(32, 381, 496, 200, GREEN)
    d.text(54, 422, '② R 关闭；所有旧持有者结束', size=24, weight=600)
    d.card(54, 445, 452, 66, 'V0 不再存活', size=25)
    d.text(280, 552, 'S1、S2、S3 满足回收条件', size=24, color=TEAL, anchor='middle')
    d.arrow([(280, 589), (280, 627)], color='teal')
    d.card(32, 643, 496, 90, '③ 清理工作实际删除旧文件', '满足条件与执行删除，可以相隔一段时间', size=24)
    d.rule(768)
    d.text(280, 810, '持久性保护：恢复不能依赖缺失文件', size=23, anchor='middle')
    d.text(280, 850, '生命周期保护：活读者不能失去依赖', size=23, anchor='middle')
    d.save()


def rocksdb_pressure_loop():
    d = Drawing('rocksdb-pressure-loop', 820, '后台压力，要能返回写入入口', '实线：工作推进 · 虚线：压力反馈 · 教学示意')
    d.card(40, 116, 480, 90, '写入入口：r 受压力约束', 'r 是获准进入的用户字节速率', size=25)
    d.arrow([(280, 214), (280, 248)], color='teal')
    d.card(40, 264, 480, 90, 'memtable：接收更新，冻结后待刷', '压力①：待刷缓冲', size=23)
    d.arrow([(280, 362), (280, 396)], color='teal')
    d.text(319, 388, 'flush', size=22, color=TEAL)
    d.card(40, 412, 480, 90, 'L0：刚刷出的 SST 文件', '压力②：L0 文件数量', size=25)
    d.arrow([(280, 510), (280, 544)], color='teal')
    d.card(40, 560, 480, 90, 'compaction：整理各层文件', '压力③：估计待合并字节', size=25)
    d.arrow([(40, 605), (16, 605), (16, 161), (32, 161)], color='rust', dash=True)
    d.arrow([(40, 309), (16, 309)], color='rust', dash=True)
    d.arrow([(40, 457), (16, 457)], color='rust', dash=True)
    d.rule(693)
    d.text(280, 734, '不同部件，暴露不同的积压位置', size=25, weight=600, anchor='middle')
    d.text(280, 775, 'WAL 另存恢复依据，不负责偿还整理工作', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_debt_budget():
    d = Drawing('rocksdb-debt-budget', 806, '缓冲买到时间，减速才能让欠账下降', '教学模型：1 MiB 用户更新 → 3 MiB 工作量')
    d.text(32, 124, 'Q：等价工作量 / MiB', size=22)
    xs = [100, 200, 300, 400, 500]
    y_for = lambda q: 484 - 3 * q
    for q in [0, 20, 40, 60, 80, 100]:
        y = y_for(q)
        color = RUST if q == 100 else (TEAL if q == 60 else LINE)
        d.parts.append(f'<path d="M 82 {y} H 510" stroke="{color}" stroke-width="1" stroke-dasharray="4 5"/>')
        d.text(67, y + 7, str(q), size=21, anchor='end')
    d.arrow([(80, 484), (80, 146)])
    d.arrow([(80, 484), (526, 484)])
    for t, x in enumerate(xs):
        d.text(x, 518, str(t), size=22, anchor='middle')
    d.text(280, 558, '时间 / 秒（每秒末重新记账）', size=22, anchor='middle')
    def line(qs, color, offset=0):
        coords = ' '.join(f'{xs[i+offset]},{y_for(q)}' for i, q in enumerate(qs))
        d.parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round"/>')
        for i, q in enumerate(qs):
            d.parts.append(f'<circle cx="{xs[i+offset]}" cy="{y_for(q)}" r="5" fill="{color}"/>')
    line([20, 40, 60], INK)
    line([60, 80, 100], RUST, 2)
    line([60, 50, 40], TEAL, 2)
    d.text(493, 173, '停止线 100', size=21, color=RUST, anchor='end')
    d.text(510, 293, '减速线 60', size=21, color=TEAL, anchor='end')
    d.card(32, 590, 240, 92, '放任：每秒 +20', 'r=20：新增60，完成40', PEACH, RUST, size=22)
    d.card(288, 590, 240, 92, '减速：每秒 −10', 'r=10：新增30，完成40', GREEN, TEAL, size=22)
    d.text(280, 723, '共同路径 Q：20 → 40 → 60', size=24, anchor='middle')
    d.text(280, 763, '教学恢复线 40；不是 RocksDB 的配置项', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_stall_recovery():
    d = Drawing('rocksdb-stall-recovery', 927, '入口可以停，偿还工作不能停', '教学模型：后台一秒无推进后，Q 达到 100')
    rows = [(116, '第5→6秒：停止接收', 'Q：100 → 60', 'r=0，μ=40：只消化积欠', PEACH, RUST),
            (302, '第6→7秒：慢速接收', 'Q：60 → 50', 'r=10，μ=40：新增30，完成40', GREEN, TEAL),
            (488, '第7→8秒：慢速接收', 'Q：50 → 40', 'r=10，μ=40：新增30，完成40', GREEN, TEAL),
            (674, '第8→9秒：应用不再提交', 'Q：40 → 0', 'r=0，μ=40：本轮积欠排空', WHITE, INK)]
    for y, title, state, detail, fill, color in rows:
        d.rect(32, y, 496, 148, fill)
        d.text(54, y + 35, title, size=24, weight=600)
        d.text(280, y + 81, state, size=27, color=color, weight=600, anchor='middle')
        d.text(280, y + 121, detail, size=22, anchor='middle')
    for y in [272, 458, 644]:
        d.arrow([(280, y), (280, y + 22)], color='teal')
    d.text(280, 865, 'Q：MiB 工作量；μ：MiB 工作量/秒', size=22, anchor='middle')
    d.text(280, 904, 'r：MiB 用户数据/秒；不计外部排队', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_snapshot_views():
    d = Drawing('rocksdb-snapshot-views', 1000, '边界固定，更新继续前进', '教学模型：单列族普通更新 · 向下为操作顺序')
    rows = [(1, 'a = 10', ''), (2, 'b = 20', '登记 P2：边界 2'),
            (3, 'b = 21', ''), (4, 'c = 30', '登记 P4：边界 4'),
            (5, 'a = DEL', ''), (6, 'b = 22', ''), (7, 'b = 23', '观察最新视图')]
    d.arrow([(58, 124), (58, 565)], color='teal')
    for i, (seq, value, note) in enumerate(rows):
        y = 108 + i * 66
        d.rect(84, y, 444, 56, GREEN if seq in (2, 4) else WHITE)
        d.text(100, y + 37, str(seq), size=25, weight=600)
        d.text(145, y + 37, value, size=24)
        if note:
            d.text(512, y + 36, note, size=22, color=TEAL, anchor='end')
    d.rule(588)
    for y, title, values, fill in [
        (615, 'P2：只考虑序号 ≤ 2', 'a=10，b=20，c 不存在', WHITE),
        (727, 'P4：只考虑序号 ≤ 4', 'a=10，b=21，c=30', GREEN),
        (839, '最新：本例更新止于序号 7', 'a 不存在，b=23，c=30', PEACH),
    ]:
        d.rect(32, y, 496, 96, fill)
        d.text(54, y + 34, title, size=24, weight=600)
        d.text(54, y + 73, values, size=24)
    d.text(280, 975, 'DEL 是删除标记；序号不是墙钟时间', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_snapshot_stripes():
    d = Drawing('rocksdb-snapshot-stripes', 880, '留下答案，丢掉被遮住的中间值', '教学模型：P2、P4 活跃 · 同键按新到旧处理')
    d.text(54, 129, '记录', size=23, weight=600)
    d.text(282, 129, '所在区间 / 作用', size=23, weight=600)
    rows = [(154, 'b@7 = 23', 'P4 之后：最新答案', GREEN, TEAL),
            (230, 'b@6 = 22', 'P4 之后：被 7 遮住', PEACH, RUST),
            (306, 'b@3 = 21', '(2, 4]：P4 的答案', WHITE, INK),
            (382, 'b@2 = 20', '≤ 2：P2 的答案', WHITE, INK)]
    for y, record, meaning, fill, color in rows:
        d.rect(32, y, 496, 62, fill)
        d.text(52, y + 40, record, size=25, color=color, weight=600)
        d.text(286, y + 40, meaning, size=22, color=color)
    d.text(280, 487, '没有 P6：无人需要 22 → 可以丢弃', size=24, color=RUST, anchor='middle')
    d.rule(519)
    d.text(32, 558, 'a 的旧值与删除必须配套留下', size=24, weight=600)
    d.card(32, 583, 232, 100, 'a@5 = DEL', '最新视图：不存在', PEACH, RUST, size=25)
    d.card(296, 583, 232, 100, 'a@1 = 10', 'P2、P4：都返回 10', GREEN, TEAL, size=25)
    d.rect(32, 716, 496, 102, WHITE)
    d.text(54, 751, '只删 DEL、留下旧值，会发生什么？', size=23, weight=600)
    d.text(54, 791, '最新视图错误返回 10：旧值复活', size=24, color=RUST)
    d.text(280, 855, '更换文件，不能更换受保护的读取答案', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_snapshot_release():
    d = Drawing('rocksdb-snapshot-release', 990, '释放边界，后续合并才有更多自由', '教学语义记录数 · 无新写入、无其他历史保护')
    rows = [(112, '① P2、P4 都活跃：6 条',
             ['a：DEL@5，10@1', 'b：23@7，21@3，20@2', 'c：30@4'], WHITE),
            (394, '② 只剩 P4：5 条',
             ['a：DEL@5，10@1', 'b：23@7，21@3', 'c：30@4'], GREEN),
            (676, '③ 两者都释放：2 条',
             ['a：删除与旧值一同清掉', 'b：23@7', 'c：30@4'], PEACH)]
    for y, title, records, fill in rows:
        d.rect(32, y, 496, 196, fill)
        d.text(54, y + 37, title, size=25, weight=600)
        for i, record in enumerate(records):
            d.text(54, y + 83 + i * 40, record, size=25)
    for y, text in [(324, '安全释放 P2 → 再次合并'),
                    (606, '安全释放 P4 → 完整覆盖历史')]:
        d.arrow([(58, y), (58, y + 54)], color='teal')
        d.text(100, y + 32, text, size=24, color=TEAL)
    d.text(280, 915, '最后一步还须：下层无遗漏旧值', size=23, anchor='middle')
    d.text(280, 953, 'ReleaseSnapshot 不同步保证磁盘回收', size=22, color=MUTED, anchor='middle')
    d.save()



def rocksdb_batch_publication():
    d = Drawing('rocksdb-batch-publication', 1010, '内部逐条安装，外部只取完整边界', '教学模型：甲、乙总量 140 · 下箭头表示步骤')
    rows = [(112, '① 初始：V = 2', '甲@1=100，乙@2=40',
             '边界 2 的答案：(100, 40)', WHITE),
            (378, '② 仅安装甲@3=90：V 仍为 2', '新甲在内存里，还不能对读者公布',
             '跳过序号 3 → 仍读 (100, 40)', PEACH),
            (644, '③ 两条安装完成：V 推进到 4', '新记录：甲@3=90，乙@4=50',
             '新边界 4 的答案：(90, 50)', GREEN)]
    for y, title, detail, answer, fill in rows:
        d.rect(32, y, 496, 198, fill)
        d.text(52, y+38, title, size=24, weight=600)
        d.text(52, y+85, detail, size=23)
        d.text(52, y+136, answer, size=23, color=TEAL, weight=600)
        if y == 378:
            d.text(52, y+174, 'V 不能提前公布为 3', size=22, color=RUST)
        elif y == 644:
            d.text(52, y+174, '旧 P2 仍读 (100, 40)', size=22)
    for y in [322, 588]:
        d.arrow([(280,y),(280,y+42)], color='teal')
    d.rule(873)
    d.text(280, 918, '本例先完成 WAL 写入与要求的同步', size=23, anchor='middle')
    d.text(280, 958, '再安装记录、发布边界、返回成功', size=23, anchor='middle')
    d.text(280, 991, '物理位置变化，不必同时发生', size=21, color=MUTED, anchor='middle')
    d.save()


def rocksdb_batch_read_view():
    d = Drawing('rocksdb-batch-read-view', 1030, '原子写入，还要配合一致的读取视图', '教学模型：批次前 (100,40)，批次后 (90,50)')
    d.text(32, 124, '① 两次独立 Get：跨了两个时点', size=24, weight=600)
    for y, title, fill in [(148, 'Get 甲 → 100（旧视图）', WHITE),
                            (251, '完整批次公布 → V = 4', GREEN),
                            (354, 'Get 乙 → 50（新视图）', WHITE)]:
        d.card(80, y, 448, 73, title, fill=fill, size=24)
    d.arrow([(54, 165), (54, 408)], color='rust')
    d.text(280, 465, '拼出 100 + 50 = 150：不是一个视图', size=23, color=RUST, anchor='middle')
    d.rule(499)
    d.text(32, 540, '② 两次 Get 都使用同一个 P2', size=24, weight=600)
    for y, title, fill in [(564, 'P2 下 Get 甲 → 100', WHITE),
                            (667, '完整批次公布 → V = 4', GREEN),
                            (770, 'P2 下 Get 乙 → 40', WHITE)]:
        d.card(80, y, 448, 73, title, fill=fill, size=24)
    d.arrow([(54, 581), (54, 824)], color='teal')
    d.text(280, 882, '同一旧视图：100 + 40 = 140', size=24, color=TEAL, anchor='middle')
    d.text(280, 940, 'P2 固定在 2，不跟随 V 推进', size=23, anchor='middle')
    d.text(280, 990, '箭头表示调用顺序，不是运行追踪', size=22, color=MUTED, anchor='middle')
    d.save()



def rocksdb_txn_conflict():
    d = Drawing('rocksdb-txn-conflict', 940, '旧答案仍可读，旧依据未必可提交', '实线：推进 · 虚线：T2 保留待提交状态')
    d.card(32, 112, 496, 100, '两事务基准 = 2', '甲@1=100，乙@2=40', size=25)
    d.card(32, 258, 232, 110, 'T1：转移 10', '暂存 (90, 50)', GREEN, TEAL, size=24)
    d.card(296, 258, 232, 110, 'T2：转移 20', '暂存 (80, 60)', PEACH, RUST, size=24)
    d.arrow([(148, 217), (148, 250)], color='teal')
    d.arrow([(412, 217), (412, 250)], color='rust')
    d.rect(32, 414, 496, 164, GREEN)
    d.text(52, 451, '① T1 校验通过，完整写入生效', size=24, weight=600)
    d.text(52, 496, '甲@3=90，乙@4=50', size=25, color=TEAL)
    d.text(52, 541, '数据库现在是 (90, 50)', size=24)
    d.arrow([(148, 374), (148, 407)], color='teal')
    d.arrow([(412, 374), (544, 374), (544, 616), (412, 616), (412, 632)], color='rust', dash=True)
    d.rect(32, 640, 496, 184, PEACH)
    d.text(52, 677, '② T2 校验：修改已越过基准 2', size=24, weight=600)
    d.text(52, 724, '甲：3 > 2；乙：4 > 2', size=25, color=RUST)
    d.text(52, 767, '冲突 Busy → 不写入 (80, 60)', size=24, color=RUST)
    d.text(52, 803, '数据库仍为 (90, 50)', size=23)
    d.arrow([(280, 585), (280, 632)], color='rust')
    d.text(280, 869, '假设内存修改历史足够，且没有其他错误', size=22, anchor='middle')
    d.text(280, 908, 'T2 的旧读取视图与提交校验各有职责', size=22, color=MUTED, anchor='middle')
    d.save()


def rocksdb_txn_retry():
    d = Drawing('rocksdb-txn-retry', 962, '重试保留业务意图，重新取得依据', '教学时序：无进一步干扰 · 总量始终为 140')
    rows = [(112, '① 终止失败的 T2 尝试', '旧基准 2、旧结果 (80,60) 均不复用', PEACH),
            (298, '② 创建 T2′，新基准 = 4', '重新读取：甲=90，乙=50', WHITE),
            (484, '③ 仍要从甲转给乙 20', '重新计算：(90−20, 50+20)=(70,70)', GREEN),
            (670, '④ 新校验通过，完整生效', '甲@5=70，乙@6=70 → 两笔均完成', GREEN)]
    for y, title, detail, fill in rows:
        d.rect(32, y, 496, 136, fill)
        d.text(52, y+38, title, size=24, weight=600)
        d.text(52, y+91, detail, size=22)
    for y in [256, 442, 628]:
        d.arrow([(280,y),(280,y+31)], color='teal')
    d.rule(840)
    d.text(280, 888, '结束条件：T1 成功，T2′ 成功', size=24, anchor='middle')
    d.text(280, 930, '反复提交旧结果，不会修复过时计算', size=22, color=RUST, anchor='middle')
    d.save()



def pg_row_versions():
    d = Drawing('pg-row-versions', 854, '更新生成新行，旧行暂时仍有用途', '教学模型：行标记是事务身份，不是提交顺序')
    for y, key, old, new in [(126, '甲', '100', '90'), (398, '乙', '40', '50')]:
        d.text(32, y, key + '：T101 更新，尚未提交', size=24, weight=600)
        for x, title, xmin, xmax, fill in [(32, '旧行：' + old, '100', '101', WHITE),
                                         (312, '新行：' + new, '101', '0', PEACH)]:
            d.rect(x, y+24, 216, 166, fill)
            d.text(x+108, y+63, title, size=25, weight=600, anchor='middle')
            d.text(x+108, y+109, 'xmin = ' + xmin, size=24, anchor='middle')
            d.text(x+108, y+155, 'xmax = ' + xmax, size=24, anchor='middle')
        d.arrow([(256,y+107),(304,y+107)], color='rust')
        d.text(280, y+223, '创建者 / 替换者决定版本怎样被解释', size=22, color=MUTED, anchor='middle')
    d.rule(682)
    d.text(280, 730, '旧行创建于 T100，替换动作属于 T101', size=23, anchor='middle')
    d.text(280, 772, '新行创建于 T101；xmax=0 表示尚无替换', size=22, anchor='middle')
    d.text(280, 822, '箭头：生成新版本；省略索引与页面布局', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_snapshot_hole():
    d = Drawing('pg-snapshot-hole', 920, '编号上界之内，也有未完成的空洞', '教学快照 S：101:103:101 · 顶层事务，无回绕')
    d.rect(32, 112, 496, 111, GREEN)
    d.text(54, 148, 'S.xmin = 101，S.xmax = 103', size=25, weight=600)
    d.text(54, 190, 'S.active = {101}：取快照时未完成', size=23)
    rows = [(257, '100 < 101', '取快照前已提交；不在进行中范围', WHITE, INK),
            (389, '101 ∈ {101}', '取快照时未完成；之后仍被 S 排除', PEACH, RUST),
            (521, '102 < 103', '不在集合，且已提交；可以使用', GREEN, TEAL),
            (653, '编号 ≥ 103', '相对 S 尚未完成；不纳入此次视图', WHITE, MUTED)]
    for y, title, detail, fill, color in rows:
        d.rect(32, y, 496, 105, fill)
        d.text(54, y+36, title, size=26, weight=600, color=color)
        d.text(54, y+78, detail, size=22, color=color)
    d.rule(793)
    d.text(280, 836, '快照时已结束 ≠ 现在已经结束', size=24, anchor='middle')
    d.text(280, 881, '行是否可见，还要检查创建与替换事务', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_snapshot_readers():
    d = Drawing('pg-snapshot-readers', 1030, '后来提交，不会重写旧快照的事实', '教学时序：R 只读 Repeatable Read · 下为时间')
    rows = [(112, '① T101 更新额度，尚未提交', '甲、乙的新版本为 (90,50)', PEACH),
            (278, '② T102 后取得编号，却先提交', '只把无关备注改成“已核”', GREEN),
            (444, '③ R 第一次 SELECT，固定 S', 'S=101:103:101 → 额度 (100,40)', WHITE),
            (610, '④ T101 提交两份额度更新', '当前已提交额度变成 (90,50)', GREEN)]
    for y, title, detail, fill in rows:
        d.rect(32, y, 496, 123, fill)
        d.text(52, y+37, title, size=24, weight=600)
        d.text(52, y+85, detail, size=23)
    for y in [243, 409, 575, 741]:
        d.arrow([(280,y),(280,y+26)], color='teal')
    d.rect(32, 778, 496, 151, WHITE)
    d.text(52, 815, '⑤ R 再查：仍为 (100,40)', size=24, weight=600)
    d.text(52, 861, 'N 的新快照：得到 (90,50)', size=24, color=TEAL)
    d.text(52, 904, 'R 的 S 不变；结束事务才退出旧视图', size=22)
    d.text(280, 987, '100、101、102 是事务编号，不是时间', size=22, color=MUTED, anchor='middle')
    d.save()



def pg_hot_chain():
    d = Drawing('pg-hot-chain', 1040, '入口不变，快照决定选哪个版本', '教学模型：同一表页 42 · 箭头表示引用或后继')
    d.card(32, 112, 496, 88, 'B-tree：键 7 → TID (42,1)', '只有 id 索引；balance 没有索引', size=25)
    d.arrow([(280,208),(280,244)], color='teal')
    d.rect(32, 252, 496, 454, WHITE)
    d.text(52, 290, '表页 42：新旧版本都在本页', size=25, weight=600)
    d.rect(56, 316, 448, 142, WHITE)
    d.text(76, 352, '槽位 1 → 旧行：id=7，额度 100', size=24, weight=600)
    d.text(76, 394, 'xmin=100，xmax=101', size=24)
    d.text(76, 435, 'HOT 后继：t_ctid=(42,4)', size=23, color=RUST)
    d.arrow([(280,466),(280,510)], color='rust')
    d.rect(56, 518, 448, 156, GREEN)
    d.text(76, 555, '槽位 4 → 新行：id=7，额度 90', size=24, weight=600)
    d.text(76, 599, 'xmin=101，xmax=0', size=24)
    d.text(76, 643, 'heap-only：没有独立索引入口', size=23, color=TEAL)
    d.text(32, 753, 'T101 提交后，两个读者都从槽位 1 进入', size=23, weight=600)
    d.card(32, 782, 496, 88, 'R：旧快照 → 在旧行停下 → 100', fill=WHITE, size=24)
    d.card(32, 893, 496, 88, 'N：新快照 → 沿链到新行 → 90', fill=GREEN, color=TEAL, size=24)
    d.text(280, 1015, '槽位号不是行数据的字节偏移', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_hot_prune():
    d = Drawing('pg-hot-prune', 1020, '旧数据可回收，外部入口还要保留', '教学模型：先保留旧版本，再满足回收条件')
    for y, title, root, fill in [(112, '① 清理前：旧读者仍可能需要 100', '槽位 1 → 旧行 100 → 槽位 4', WHITE),
                                 (533, '② 清理后：旧版本已无人需要', '槽位 1：LP_REDIRECT → 槽位 4', GREEN)]:
        d.rect(32, y, 496, 320, fill)
        d.text(52, y+37, title, size=24, weight=600)
        d.text(52, y+88, '索引：键 7 → (42,1)　保持不变', size=23)
        d.arrow([(280,y+103),(280,y+134)], color='teal')
        d.rect(52, y+145, 456, 58, WHITE)
        d.text(280, y+182, root, size=23, anchor='middle')
        d.arrow([(280,y+211),(280,y+240)], color='teal')
        d.text(280, y+278, '槽位 4 → 新行 90', size=25, color=TEAL, weight=600, anchor='middle')
    d.text(280, 472, '旧快照结束，满足回收条件并取得同步', size=22, anchor='middle')
    d.arrow([(280,484),(280,522)], color='rust')
    d.text(280, 902, '可回收：旧行 100 的数据区域', size=24, color=TEAL, anchor='middle')
    d.text(280, 949, '仍保留：索引引用的根槽位 1', size=24, color=RUST, anchor='middle')
    d.text(280, 994, '清理并整理页内空间；不是运行追踪', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_ios_candidates():
    d = Drawing('pg-ios-candidates', 1020, '数值在索引里，能否使用仍要判断', '教学模型：T101 已提交，旧快照 R 仍在')
    d.text(32, 124, '同一个 id=7，暂存两份索引候选', size=25, weight=600)
    d.card(32, 150, 496, 86, '额度 100 → TID (42,1)', fill=WHITE, size=25)
    d.card(32, 256, 496, 86, '额度 90 → TID (42,4)', fill=PEACH, size=25)
    d.arrow([(280,350),(280,390)], color='rust')
    d.card(32, 398, 496, 100, 'V[42] = 0：没有整页保证', '0 不等于不可见；必须检查表行', PEACH, RUST, size=25)
    d.arrow([(280,506),(280,548)], color='rust')
    d.rect(32, 556, 496, 240, WHITE)
    d.text(52, 597, '访问表页 42，按各自快照判断', size=24, weight=600)
    d.text(52, 652, 'R：接受旧版本，排除新版本', size=24)
    d.text(52, 704, 'N：排除旧版本，接受新版本', size=24, color=TEAL)
    d.text(52, 757, '候选检查顺序不按本图固定', size=22, color=MUTED)
    d.arrow([(280,804),(280,846)], color='teal')
    d.card(32, 854, 496, 90, '从通过检查的索引项取值', 'R → 100；N → 90；各返回一行', GREEN, TEAL, size=25)
    d.text(280, 991, '箭头：检查流程 · 未运行数据库', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_ios_lifecycle():
    d = Drawing('pg-ios-lifecycle', 1050, '撤销保证要及时，重建保证要有依据', '教学时序：页 42 · 向下表示事件先后')
    rows = [(112, '① 初始已确认：V[42] = 1', '索引中的 100 可直接返回', '表页此前满足全部可见条件', GREEN),
            (344, '② T101 更新：V[42] = 0', '额度 100 → 90，建立新索引项', '新入口发布前，先撤销整页保证', PEACH),
            (576, '③ T101 提交：V[42] 仍为 0', '旧快照 R 还要 100；N 要 90', '提交不等于对所有快照可见', WHITE),
            (808, '④ 条件满足，VACUUM → V = 1', '清旧行、旧索引项，核对整页', '此后新查询可直接采用索引的 90', GREEN)]
    for y, title, detail, condition, fill in rows:
        d.rect(32, y, 496, 177, fill)
        d.text(52, y+38, title, size=24, weight=600)
        d.text(52, y+91, detail, size=23)
        d.text(52, y+143, condition, size=22, color=MUTED)
    for y in [297,529,761]:
        d.arrow([(280,y),(280,y+37)], color='teal')
    d.text(280, 1022, '④ 还要求 R 结束且其他保护条件允许', size=22, anchor='middle')
    d.save()


def pg_ssi_write_skew():
    d = Drawing('pg-ssi-write-skew', 936, '各自保留旧视图，仍可能一起做错', '教学模型：Repeatable Read · 向下为事件推进')
    d.card(32, 112, 496, 92, '初始：甲在岗，乙在岗', '业务不变量：人数至少为 1', GREEN, TEAL, size=25)
    d.arrow([(280,212),(280,253)], color='teal')
    d.rect(32, 261, 496, 158, WHITE)
    d.text(52, 300, 'A 读人数 → 2，批准甲下班', size=24, weight=600)
    d.text(52, 352, 'B 读人数 → 2，批准乙下班', size=24, weight=600)
    d.text(52, 395, '两次读取都在任何更新之前', size=22, color=MUTED)
    d.arrow([(280,427),(280,468)], color='rust')
    d.rect(32, 476, 496, 158, PEACH)
    d.text(52, 515, 'A：只修改甲 → 离岗', size=25)
    d.text(52, 566, 'B：只修改乙 → 离岗', size=25)
    d.text(52, 610, '没有同一行的写写冲突', size=22, color=RUST)
    d.arrow([(280,642),(280,683)], color='rust')
    d.card(32, 691, 496, 112, '两笔都可提交 → 在岗人数 0', '快照稳定，业务规则仍被破坏', PEACH, RUST, size=25)
    d.text(280, 863, 'A：甲的申请；B：乙的申请', size=23, anchor='middle')
    d.text(280, 907, '这不是脏读，也不是覆盖同一行', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_ssi_dependencies():
    d = Drawing('pg-ssi-dependencies', 848, '两条顺序要求，无法同时满足', 'rw 箭头：读者 → 改变其读取依据的写者')
    d.card(32, 112, 496, 110, 'A：甲申请下班', '读乙在岗；写甲离岗', WHITE, size=26)
    d.card(32, 496, 496, 110, 'B：乙申请下班', '读甲在岗；写乙离岗', WHITE, size=26)
    d.arrow([(72,230),(72,488)], color='rust')
    d.arrow([(488,488),(488,230)], color='teal')
    d.text(280, 315, 'A → B：A 读旧乙，B 改乙', size=24, color=RUST, anchor='middle')
    d.text(280, 369, 'B → A：B 读旧甲，A 改甲', size=24, color=TEAL, anchor='middle')
    d.text(280, 433, '要求 A 在 B 前，也要求 B 在 A 前', size=23, anchor='middle')
    d.rule(654)
    d.text(280, 703, '这是依赖环，不是线程等待图', size=24, weight=600, anchor='middle')
    d.text(280, 755, '不表示消息方向或实际提交顺序', size=23, color=MUTED, anchor='middle')
    d.text(280, 807, '图用于解释异常，不是完整 SSI 算法', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_ssi_retry():
    d = Drawing('pg-ssi-retry', 1010, '重做判断，才能得到合法的业务结果', '教学结局之一：A 成功，B 失败 · 向下为步骤')
    rows = [(112, '① A 提交：甲离岗，乙仍在岗', 'B 的旧尝试失败并回滚：40001', PEACH),
            (318, '② B′：开始新的 Serializable 事务', '重读人数 → 1，放弃旧的批准依据', WHITE),
            (524, '③ 业务判断：拒绝乙下班', '不把乙改成离岗，正常结束事务', GREEN),
            (730, '④ 最终：甲离岗，乙继续值班', '在岗人数 = 1，规则仍成立', GREEN)]
    for y, title, detail, fill in rows:
        d.rect(32, y, 496, 145, fill)
        d.text(52, y+40, title, size=23, weight=600)
        d.text(52, y+100, detail, size=23)
    for y in [265,471,677]:
        d.arrow([(280,y),(280,y+43)], color='teal')
    d.text(280, 928, '冲突回滚 ≠ 业务拒绝下班', size=24, anchor='middle')
    d.text(280, 975, '不承诺固定失败者或固定报错时机', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_group_frontier():
    d = Drawing('pg-group-frontier', 1010, '写出到 240，还不等于持久化到 240', '教学位置：KiB · 省略共同基址与实际记录布局')
    d.card(32, 112, 496, 100, '提交目标：A=160，B=200，C=240', '目标是提交记录结束位置，不是事务号', size=24)
    d.rect(32, 260, 496, 240, PEACH)
    d.text(52, 303, '① 已写出：W=240，F=120', size=25, weight=600)
    d.text(52, 360, '日志可能仍在易失缓存里', size=24)
    d.text(52, 414, '120 < 160、200、240', size=25, color=RUST)
    d.text(52, 468, '三笔的本地持久化义务均未满足', size=23, color=RUST)
    d.arrow([(500,508),(500,566)], color='teal')
    d.text(52, 548, '完成所选方法要求的同步', size=22)
    d.rect(32, 574, 496, 240, GREEN)
    d.text(52, 617, '② 已可靠刷新：F=240', size=25, weight=600)
    d.text(52, 674, '240 ≥ 160；240 ≥ 200；240 ≥ 240', size=23)
    d.text(52, 728, '一份连续前缀，覆盖三个目标', size=24, color=TEAL)
    d.text(52, 782, '各自继续完成事务结束与响应', size=23, color=TEAL)
    d.rule(857)
    d.text(280, 904, 'W：写出前沿；F：已持久化前沿', size=23, anchor='middle')
    d.text(280, 957, '假设写出与同步可区分；不是运行追踪', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_group_followers():
    d = Drawing('pg-group-followers', 1040, '等别人完成后，先重查自己的条件', '教学时序：位置单位 KiB · 向下表示事件推进')
    rows = [(112, '① A 请求刷新到 160，F=120', '准备 I/O 时，完整日志前缀已到 240', WHITE),
            (330, '② A 负责一次写出与同步', 'B、C 等待；完成后公布 F=240', GREEN),
            (548, '③ B、C 重检目标 200、240', '条件已满足 → 跳过重复同步', GREEN),
            (766, '④ 后来的 D：目标 280', '240 < 280 → 仍要等后续刷新', PEACH)]
    for y, title, detail, fill in rows:
        d.rect(32, y, 496, 152, fill)
        d.text(52, y+42, title, size=24, weight=600)
        d.text(52, y+105, detail, size=23)
    for y in [272,490,708]:
        d.arrow([(280,y),(280,y+47)], color='teal')
    d.text(280, 970, '共享 I/O；A、B、C 仍是独立事务', size=23, anchor='middle')
    d.text(280, 1014, '不保证固定领头者、批量或响应先后', size=22, color=MUTED, anchor='middle')
    d.save()


def pg_checkpoint_moving_pages():
    d = Drawing('pg-checkpoint-moving-pages', 1060, '各页陆续写回，不必同时最新', '教学时序 · 向下为时间 · 位置单位 KiB')
    rows = [(112, '① 开始前：内存 A80、B60', '磁盘 A0、B0；旧修改日志已可靠保存', WHITE),
            (270, '② 建立重做起点 R=100', '固定本轮需要承接的旧历史', GREEN),
            (428, '③ A 更新到 120，再写回 A120', '磁盘 A120、B0', WHITE),
            (586, '④ B 更新到 140；A 又更新到 160', '内存 A160、B140；磁盘 A120、B0', PEACH),
            (744, '⑤ 写回 B140，完成必要同步', '磁盘 A120、B140；A160 仍脏', GREEN)]
    for y, title, detail, fill in rows:
        d.rect(32,y,496,120,fill)
        d.text(50,y+38,title,size=23,weight=600)
        d.text(50,y+87,detail,size=22)
    for y in [239,397,555,713]:
        d.arrow([(280,y),(280,y+22)], color='teal')
    d.rule(904)
    d.text(280,948,'旧历史已承接 ≠ 内存再无脏页',size=25,anchor='middle')
    d.text(280,995,'A160 可由 R 之后的 WAL 补齐',size=24,color=TEAL,anchor='middle')
    d.text(280,1035,'省略其他页、提交记录与真实日志布局',size=21,color=MUTED,anchor='middle')
    d.save()


def pg_checkpoint_redo_start():
    d = Drawing('pg-checkpoint-redo-start', 950, '完成记录的位置，不是重做起点', '教学对照 · 假设相关事务均已同步提交')
    d.card(32,112,496,104,'完成记录 C=200，内含 redo=100', '崩溃后磁盘：A120、B140',size=24)
    d.rect(32,265,496,245,GREEN)
    d.text(52,309,'正确：从 R=100 开始扫描',size=25,weight=600)
    d.text(52,369,'解释 120、140、160 等后续记录',size=23)
    d.text(52,428,'找到尚未落盘的 A160 修改',size=24,color=TEAL)
    d.text(52,484,'最终：A160、B140',size=25,color=TEAL,weight=600)
    d.rect(32,557,496,245,PEACH)
    d.text(52,601,'错误：从 C=200 开始扫描',size=25,weight=600)
    d.text(52,661,'跳过 160，日志补齐路线被切断',size=23)
    d.text(52,720,'磁盘仍是 A120，内存 A160 已丢',size=23,color=RUST)
    d.text(52,776,'已确认的修改无法恢复',size=25,color=RUST,weight=600)
    d.rule(845)
    d.text(280,889,'保留扫描范围，才能容许数据页落后',size=23,anchor='middle')
    d.text(280,931,'不是重放业务 SQL，也不是实际恢复追踪',size=21,color=MUTED,anchor='middle')
    d.save()


def pg_checkpoint_publication():
    d = Drawing('pg-checkpoint-publication', 970, '先完成承接，再发布恢复入口', '教学顺序 · 两个故障点只取明确的持久化边界')
    d.card(32,112,496,110,'① 可靠保存本轮必需数据与状态', '不能只有 write 返回；还需必要同步',fill=WHITE,size=24)
    d.text(52,269,'此时若尚未写新完成记录就崩溃：',size=22)
    d.text(52,310,'仍使用此前已发布的检查点',size=24,color=RUST)
    d.arrow([(500,230),(500,348)],color='teal')
    d.card(32,364,496,110,'② 写并刷新完整的完成记录', 'C=200；记录内保存 R=100',fill=GREEN,size=24)
    d.arrow([(280,485),(280,533)],color='teal')
    d.card(32,550,496,110,'③ 持久更新 pg_control 指向 C', '启动由 C 找到 R，再从 R 扫描',fill=GREEN,size=24)
    d.text(52,715,'此步可靠完成后若崩溃：',size=23)
    d.text(52,762,'采用新入口，从 R=100 恢复',size=24,color=TEAL)
    d.rule(810)
    d.text(280,853,'仅建立 R，不代表本轮检查点已完成',size=23,anchor='middle')
    d.text(280,900,'不推断控制文件写入途中或损坏的结果',size=21,color=MUTED,anchor='middle')
    d.text(280,943,'完整协议还包括其他持久状态的协调',size=21,color=MUTED,anchor='middle')
    d.save()


def linux_vfs_open_state():
    d = Drawing('linux-vfs-open-state', 970, '共享数据，不等于共享读取进度', '教学引用图 · 箭头表示关联或持有关系')
    d.card(32,112,496,80,'目录中的名字：app.log',size=25)
    d.arrow([(280,202),(280,240)],color='teal')
    d.card(32,252,496,104,'文件身份 I17', '内容：ABCDEF（没有复制数据）',fill=GREEN,size=25)
    d.card(32,450,236,110,'打开对象 X', '偏移 = 4',size=24)
    d.card(292,450,236,110,'打开对象 Y', '偏移 = 2',size=24)
    d.arrow([(150,440),(150,366)],color='teal')
    d.arrow([(410,440),(410,366)],color='teal')
    for x,title in [(32,'fd 3'),(208,'fd 4'),(384,'fd 5')]:
        d.card(x,690,144,76,title,size=25)
    d.arrow([(104,680),(104,615),(150,615),(150,570)],color='teal')
    d.arrow([(280,680),(280,595),(220,595),(220,570)],color='teal')
    d.arrow([(456,680),(456,615),(410,615),(410,570)],color='teal')
    d.text(280,818,'3 读 AB；4 接着读 CD；5 独立读 AB',size=23,anchor='middle')
    d.rule(850)
    d.text(280,894,'dup 共享 X；再次 open 新建 Y',size=24,anchor='middle')
    d.text(280,940,'省略 dentry、挂载与其他内核中间结构',size=21,color=MUTED,anchor='middle')
    d.save()


def linux_vfs_unlink_lifetime():
    d = Drawing('linux-vfs-unlink-lifetime', 1070, '同名新文件，不会接管旧描述符', '教学时序 · 向下为时间 · 旧对象无其他持有者')
    rows = [(112,'① unlink，再创建同名 app.log','新名字 → I23，内容 XYZ；新 fd 6',GREEN),
            (314,'② 旧引用仍通往 I17：ABCDEF','3、4 → X，偏移 4；5 → Y，偏移 2',PEACH),
            (516,'③ 沿各自对象继续读取','各自推进打开对象里的偏移',WHITE),
            (718,'④ 关闭 3、4，仍有 5 引用 Y','再关闭 5 → I17 才满足回收条件',GREEN)]
    for y,title,detail,fill in rows:
        d.rect(32,y,496,140,fill)
        d.text(50,y+42,title,size=23,weight=600)
        if y == 516:
            d.text(50,y+80,'4 读 EF → X 偏移 6',size=22)
            d.text(50,y+118,'6 读 XYZ → Z 偏移 3',size=22)
        else:
            d.text(50,y+103,detail,size=22)
    for y in [263,465,667]:
        d.arrow([(280,y),(280,y+38)],color='teal')
    d.rule(902)
    d.text(280,949,'I17 硬链接数为 0，仍可被打开引用持有',size=23,anchor='middle')
    d.text(280,995,'名称、打开引用、偏移：三种不同状态',size=24,anchor='middle')
    d.text(280,1043,'图中排除其他硬链接、映射与后台持有关系',size=21,color=MUTED,anchor='middle')
    d.save()


def linux_pagecache_shared():
    d = Drawing('linux-pagecache-shared', 960, '独立打开状态，共用文件缓存', '教学模型 · 实线：关联 · 虚线：稍后写回路径')
    d.card(32,112,236,108,'写者 fd 3', '偏移 100 写 XY',size=24)
    d.card(292,112,236,108,'读者 fd 5', '偏移 100 读得 XY',size=24)
    d.arrow([(150,230),(150,287),(240,287),(240,338)],color='teal')
    d.arrow([(410,230),(410,287),(320,287),(320,338)],color='teal')
    d.rect(32,350,496,198,GREEN)
    d.text(52,392,'I17 的共享页缓存 P0',size=25,weight=600)
    d.text(52,448,'字节 100、101：XY',size=25)
    d.text(52,509,'D=1：待写回；W=0：尚未接手',size=23,color=TEAL)
    d.arrow([(280,560),(280,651)],color='rust',dash=True)
    d.card(32,665,496,110,'设备稳定存储：仍是 AB', 'write 返回 2，尚未要求 fsync',fill=PEACH,size=25)
    d.rule(820)
    d.text(280,865,'读者可见 ≠ 已获得断电持久化保证',size=24,anchor='middle')
    d.text(280,910,'P0 大小按 4096 字节设定，非磁盘扇区',size=21,color=MUTED,anchor='middle')
    d.text(280,944,'仅标出字节 100、101；其余内容不变',size=21,color=MUTED,anchor='middle')
    d.save()


def linux_pagecache_redirty():
    d = Drawing('linux-pagecache-redirty', 1080, '旧写回结束，不能抹掉新修改', '教学时序 · 向下为时间 · D：脏，W：写回中')
    rows = [(112,'① write 返回 2；缓存 XY','D=1，W=0：有待写回工作',WHITE),
            (279,'② 本轮接手 XY，I/O 尚未结束','D=0，W=1：不代表已经持久化',WHITE),
            (446,'③ 再改 Y → Z；缓存变成 XZ','D=1，W=1：新旧两份责任并存',PEACH),
            (613,'④ 旧轮完成：只结束 W','D=1，W=0：XZ 仍需再次写回',GREEN),
            (780,'⑤ 下一轮写回 XZ，期间不再修改','D=0，W=0：本轮也已结束',GREEN)]
    for y,title,detail,fill in rows:
        d.rect(32,y,496,125,fill)
        d.text(50,y+39,title,size=23,weight=600)
        d.text(50,y+94,detail,size=23)
    for y in [245,412,579,746]:
        d.arrow([(280,y),(280,y+25)],color='teal')
    d.rule(944)
    d.text(280,985,'选定旧轮只携带 XY，不承诺写回快照',size=22,anchor='middle')
    d.text(280,1027,'D=0、W=0 不等于 fsync 已成功',size=24,color=RUST,anchor='middle')
    d.text(280,1065,'省略块级标记、索引标签与同步保护',size=21,color=MUTED,anchor='middle')
    d.save()


def linux_mmap_fault():
    d = Drawing('linux-mmap-fault', 1050, '映射成功以后，缺页才兑现具体数据', '教学模型：4096 字节一页 · 冷缓存的一条成功路径')
    rows = [
        (112, '① 建立映射区域 VMA', 'a = 0x40000000，映射文件偏移 4096', '权限：只读；目标页表项：尚未建立', WHITE),
        (284, '② 读取 a + 0x34 → 缺页', '文件偏移 = 0x1000 + 0x34', '= 0x1034：P1 内偏移 52 的字节', PEACH),
        (456, '③ 取得文件页 P1 的有效数据', '缓存原先没有 P1：读取，可能等待', '教学物理页 F42：页内偏移 52 是 K', WHITE),
        (628, '④ 建立只读页表项', '甲的虚拟页 → P1 / F42', '文件、偏移、权限与数据有效性须一致', GREEN),
        (800, '⑤ 重试原来的内存读取', 'CPU 翻译到 F42，读取页内偏移 52', '甲得到 K，继续执行索引器', GREEN),
    ]
    for y, title, first, second, fill in rows:
        d.rect(32, y, 496, 140, fill)
        d.text(50, y + 36, title, size=25, weight=600)
        d.text(50, y + 78, first, size=22)
        d.text(50, y + 116, second, size=22, color=MUTED)
    for y in [252, 424, 596, 768]:
        d.arrow([(280, y + 5), (280, y + 26)], color='teal')
    d.rule(968)
    d.text(280, 1006, '省略预读与重试；箭头不是设备请求计数', size=22, color=MUTED, anchor='middle')
    d.save()


def linux_mmap_sharing():
    d = Drawing('linux-mmap-sharing', 1080, '不同的虚拟地址，接到同一份文件页', '教学模型：同一文件 I17、同一偏移、P1 保持驻留')
    for x, name, addr in [(32, '进程甲', '0x40000034'), (298, '进程乙', '0x70000034')]:
        d.rect(x, 114, 230, 182)
        d.text(x + 115, 151, name, size=26, weight=600, anchor='middle')
        d.text(x + 115, 194, addr, size=23, anchor='middle')
        d.text(x + 115, 233, '各自的只读页表项', size=22, anchor='middle')
        d.text(x + 115, 272, '页内偏移 52', size=22, color=MUTED, anchor='middle')
    d.arrow([(147, 302), (147, 334), (225, 388)], color='teal')
    d.arrow([(413, 302), (413, 334), (335, 388)], color='teal')
    d.text(280, 362, '地址翻译', size=22, color=TEAL, anchor='middle')
    d.card(80, 396, 400, 100, '同一个缓存页 P1 / F42', '页内偏移 52 的字节：K', GREEN, size=25)
    d.arrow([(280, 504), (280, 554)], dash=True)
    d.card(80, 568, 400, 100, '文件 I17 的第二页 P1', '文件偏移 4096—8191', size=25)
    d.text(280, 711, '虚线：文件页的身份关系', size=22, color=MUTED, anchor='middle')
    d.rule(744)
    d.text(32, 789, '随后，甲解除自己的映射', size=26, weight=600)
    d.card(32, 814, 230, 100, '甲：映射已撤销', 'a 不再提供该访问', PEACH, RUST, size=24)
    d.card(298, 814, 230, 100, '乙：仍有映射', 'b 仍可以读到 K', GREEN, size=24)
    d.arrow([(413, 922), (413, 959), (350, 959)], color='teal')
    d.card(80, 930, 268, 58, 'P1 / F42 仍被引用', fill=GREEN, size=23)
    d.text(280, 1034, '全部解除映射，也不要求立即清空页缓存', size=22, color=MUTED, anchor='middle')
    d.save()



def linux_epoll_ready():
    d = Drawing('linux-epoll-ready', 1040, '长期登记不变，只有就绪线索进入本轮', '教学模型：A=fd 7，B=fd 8，C=fd 9 · 默认水平触发')
    d.card(32, 112, 496, 90, '应用 → E：登记 A、B、C 的 EPOLLIN', 'epoll_ctl(ADD) 建立持续的关注关系', size=23)
    for x, name in [(32, 'A / fd 7'), (204, 'B / fd 8'), (376, 'C / fd 9')]:
        d.arrow([(x + 76, 210), (x + 76, 250)], dash=True)
        d.card(x, 262, 152, 88, name, '登记保留', size=23)
    d.arrow([(280, 358), (280, 399)], color='teal')
    d.card(56, 410, 448, 100, 'B 的接收缓冲：Hi', 'A、C 仍为空；对端均未关闭', PEACH, size=25)
    d.arrow([(280, 518), (280, 552)], color='teal')
    d.card(56, 562, 448, 100, '对象唤醒 → epoll 回调', '把 B 接入就绪候选，唤醒等待者', size=25)
    d.arrow([(280, 670), (280, 704)], color='teal')
    d.card(56, 714, 448, 100, 'epoll_wait：复查后报告 B', '返回标记 B 与 EPOLLIN，不搬走 Hi', GREEN, size=25)
    d.rule(850)
    d.text(280, 895, '虚线：持续登记；实线：本次处理顺序', size=22, color=MUTED, anchor='middle')
    d.text(280, 939, '重复通知可以合并，不是数据包日志', size=24, weight=600, anchor='middle')
    d.text(280, 987, '登记时也检查已就绪状态，避免只等新变化', size=22, color=MUTED, anchor='middle')
    d.save()


def linux_epoll_level():
    d = Drawing('linux-epoll-level', 1070, '缓冲是否有数据，与候选是否保留分开看', '教学时序：只有 B 收到 Hi；A、C 为空且未关闭')
    rows = [
        (112, '① B 收到 Hi', '接收缓冲：Hi；就绪候选：B', '长期关注 A、B、C 的登记仍存在', PEACH),
        (282, '② 第一次 wait 报告 B；应用读 H', '接收缓冲：i；就绪候选：B', '水平触发交付时，B 已重新排队', GREEN),
        (452, '③ 第二次 wait 仍报告 B；应用读 i', '接收缓冲：空；就绪候选：B', '读取不会直接同步删除候选项', GREEN),
        (622, '④ 第三次 wait 重新检查 B', 'B 已无可报告条件 → 移出候选', '候选为空，但 A、B、C 仍受关注', WHITE),
        (792, '⑤ 受保护地复查并建立等待', '没有事件时，线程才可以睡眠', '后续 C 到来：候选与唤醒协议接手', WHITE),
    ]
    for y, title, first, second, fill in rows:
        d.rect(32, y, 496, 140, fill)
        d.text(48, y + 35, title, size=23, weight=600)
        d.text(48, y + 78, first, size=23)
        d.text(48, y + 116, second, size=22, color=MUTED)
    for y in [252, 422, 592, 762]:
        d.arrow([(280, y + 4), (280, y + 24)], color='teal')
    d.rule(962)
    d.text(280, 1003, '时间向下推进 · 此图省略并发与错误分支', size=22, color=MUTED, anchor='middle')
    d.text(280, 1040, '候选是复查责任，不是缓冲状态快照', size=24, color=TEAL, anchor='middle')
    d.save()



def linux_futex_handoff():
    d = Drawing('linux-futex-handoff', 1070, '所有权靠原子操作取得，等待交给内核', '教学模型：同进程 A、B · 锁字 L 初始 0，计数 X 初始 0')
    rows = [
        (112, '① A：CAS 把 L 从 0 改成 1', '成功取得锁；X 目前为 0', '无竞争获取：只需用户态原子操作', GREEN),
        (282, '② B：CAS 失败，exchange 1 → 2', 'A 仍持锁；B 标记竞争后 WAIT(2)', '选定此时序：B 已经入队等待', PEACH),
        (452, '③ A：X 加到 1，释放 L：2 → 0', '旧值是 2 → 发起 WAKE，最多唤醒 1 人', 'B 获得再次竞争的机会，尚未持锁', WHITE),
        (622, '④ B：exchange 读到 0，写入 2', '这次才取得锁；读取 X=1，再加到 2', '保留 2：不丢弃可能仍有的唤醒责任', GREEN),
        (792, '⑤ B：释放 L：2 → 0，再 WAKE', '无其他等待者：唤醒数量可以为 0', '本次结束：L=0，X=2', GREEN),
    ]
    for y, title, first, second, fill in rows:
        d.rect(32, y, 496, 140, fill)
        d.text(48, y + 35, title, size=23, weight=600)
        d.text(48, y + 78, first, size=22)
        d.text(48, y + 116, second, size=22, color=MUTED)
    for y in [252, 422, 592, 762]:
        d.arrow([(280, y + 4), (280, y + 24)], color='teal')
    d.rule(962)
    d.text(280, 1003, '箭头表示时间推进，不是实测线程轨迹', size=22, color=MUTED, anchor='middle')
    d.text(280, 1040, 'L=2 不是人数，也不等于刚被唤醒者持锁', size=23, color=TEAL, anchor='middle')
    d.save()


def linux_futex_check_sleep():
    d = Drawing('linux-futex-check-sleep', 910, '唤醒先到，不代表后来就该直接睡下', '另一条教学时序：释放早于 WAIT 检查 · 无新增竞争者')
    rows = [
        (112, '① B 标记 L：1 → 2', '知道 A 仍持锁，准备执行 WAIT(2)', '此刻 B 尚未进入内核等待队列', PEACH),
        (282, '② A 先释放 L：2 → 0，再 WAKE', '队列中没有 B，唤醒数量为 0', 'L 已经改变，不能再按旧判断入睡', WHITE),
        (452, '③ B 进入 WAIT：期望 L=2', '内核检查到 L=0，与期望值不同', '返回 EAGAIN，不把 B 留在队列里睡眠', GREEN),
        (622, '④ B 重试 exchange：旧值为 0', '原子地把 L 改为 2，成功取得锁', '由用户态继续推进，不再等待旧通知', GREEN),
    ]
    for y, title, first, second, fill in rows:
        d.rect(32, y, 496, 140, fill)
        d.text(48, y + 35, title, size=23, weight=600)
        d.text(48, y + 78, first, size=22)
        d.text(48, y + 116, second, size=22, color=MUTED)
    for y in [252, 422, 592]:
        d.arrow([(280, y + 4), (280, y + 24)], color='teal')
    d.rule(796)
    d.text(280, 837, '比较与阻塞必须衔接，避免双方都错过', size=24, color=TEAL, anchor='middle')
    d.text(280, 878, '若 B 先建立等待，就由后续 WAKE 接住它', size=22, color=MUTED, anchor='middle')
    d.save()



def linux_pidns_views():
    d = Drawing('linux-pidns-views', 860, '同一进程，可以有两套 PID 表示', '教学模型：N1 是 N0 的子命名空间 · 不复制进程')
    d.text(147, 132, '外层视图 N0', size=25, weight=600, anchor='middle')
    d.text(413, 132, '内层视图 N1', size=25, weight=600, anchor='middle')
    rows = [
        (160, 'P：4200', '监督者只属于 N0', 'P：没有对应 PID', '不能用外层编号寻找 P', WHITE, PEACH),
        (340, 'I：4201', '同一个初始化进程 I', 'I：1', '同一个初始化进程 I', GREEN, GREEN),
        (520, 'W：4202', '同一个工作进程 W', 'W：2', '同一个工作进程 W', WHITE, WHITE),
    ]
    for y, left, ld, right, rd, lf, rf in rows:
        d.card(32, y, 230, 112, left, ld, lf, size=24)
        d.card(298, y, 230, 112, right, rd, rf, size=24)
        if y != 160:
            d.arrow([(269, y + 54), (291, y + 54)], color='teal')
        else:
            d.text(280, y + 63, '×', size=25, color=RUST, anchor='middle')
    d.rule(680)
    d.text(280, 724, '查找目标需要：命名空间 + 该处的编号', size=24, weight=600, anchor='middle')
    d.text(280, 770, '箭头仅表示编号对应，不表示复制或父子关系', size=22, color=MUTED, anchor='middle')
    d.text(280, 817, '4200、4201、4202、1、2 均为教学假设', size=22, color=MUTED, anchor='middle')
    d.save()


def linux_pidns_lifecycle():
    d = Drawing('linux-pidns-lifecycle', 1050, '局部 PID 1，把创建与结束组织起来', '教学模型：P → I → W 是父子关系 · 下方两栏互斥')
    d.card(32, 112, 496, 100, 'P 创建 N1 中第一个进程 I', 'I 的编号：N0 中 4201，N1 中 1', size=25)
    d.arrow([(280, 220), (280, 250)], color='teal')
    d.card(32, 262, 496, 100, 'I 再 fork 工作进程 W', 'W 的编号：N0 中 4202，N1 中 2', size=25)
    d.arrow([(280, 370), (280, 398), (147, 425), (147, 452)], color='teal')
    d.arrow([(280, 398), (413, 425), (413, 452)], color='rust')
    for x, title, fill, color in [(32, '正常结束', GREEN, TEAL), (298, 'I 提前退出', PEACH, RUST)]:
        d.rect(x, 464, 230, 414, fill)
        d.text(x + 115, 504, title, size=26, weight=600, color=color, anchor='middle')
    for x, lines in [
        (147, [(550, '① W 先退出'), (590, 'I 等待 PID 2'), (626, '并回收 W'),
               (684, '② I 再退出'), (724, 'P 等待 PID 4201'), (760, '并回收 I'), (830, '内外各用自己的编号')]),
        (413, [(550, '① I 退出时'), (590, 'W 仍在运行'), (636, '② 内核终止 W'),
               (672, '并等待清理'), (724, '③ P 等待 4201'), (760, '回收 I'), (830, '原 N1 不能重新开工')]),
    ]:
        for y, value in lines:
            d.text(x, y, value, size=22, anchor='middle')
    d.rule(920)
    d.text(280, 963, '两栏是不同结束顺序，不能先左后右', size=24, weight=600, anchor='middle')
    d.text(280, 1010, '省略其他子进程、信号处理与收养规则', size=22, color=MUTED, anchor='middle')
    d.save()



def main():
    OUT.mkdir(parents=True, exist_ok=True)
    drawings = [pipe_flow, pipe_eof, vm_mapping, cow_states, wal_commit, wal_readers,
                git_objects, git_refs, tcp_window, tcp_gap, bloom_insert, bloom_query,
                snapshot_money, snapshot_marker, snapshot_order,
                lsm_path, lsm_versions, lsm_delete,
                rocksdb_version_readers, rocksdb_publication_crash, rocksdb_retirement,
                rocksdb_pressure_loop, rocksdb_debt_budget, rocksdb_stall_recovery,
                rocksdb_snapshot_views, rocksdb_snapshot_stripes, rocksdb_snapshot_release,
                rocksdb_batch_publication, rocksdb_batch_read_view,
                rocksdb_txn_conflict, rocksdb_txn_retry,
                pg_row_versions, pg_snapshot_hole, pg_snapshot_readers,
                pg_hot_chain, pg_hot_prune, pg_ios_candidates, pg_ios_lifecycle,
                pg_ssi_write_skew, pg_ssi_dependencies, pg_ssi_retry,
                pg_group_frontier, pg_group_followers,
                pg_checkpoint_moving_pages, pg_checkpoint_redo_start, pg_checkpoint_publication,
                linux_vfs_open_state, linux_vfs_unlink_lifetime,
                linux_pagecache_shared, linux_pagecache_redirty,
                linux_mmap_fault, linux_mmap_sharing,
                linux_epoll_ready, linux_epoll_level,
                linux_futex_handoff, linux_futex_check_sleep,
                linux_pidns_views, linux_pidns_lifecycle]
    for draw in drawings:
        draw()
    print(f'Generated {len(drawings)} teaching diagrams in assets/figures/')


if __name__ == '__main__':
    main()
