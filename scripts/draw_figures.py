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
                pg_row_versions, pg_snapshot_hole, pg_snapshot_readers]
    for draw in drawings:
        draw()
    print(f'Generated {len(drawings)} teaching diagrams in assets/figures/')


if __name__ == '__main__':
    main()
