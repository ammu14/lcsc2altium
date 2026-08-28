"""CFBF (OLE2 复合文档) 读写：把 npnp 生成的 v4 容器重写为 v3，兼容 AD16 等老版本。

背景：npnp 输出的 .SchLib/.PcbLib 是 CFBF major version 4（4096 字节扇区）。
AD16 及更早的 Altium 用 Windows 结构化存储的老路径，只认 version 3
（512 字节扇区），表现就是「打不开」。容器内的记录内容两边完全一致，
所以只需无损搬运流数据重建 v3 容器即可（v3 新版 AD 也照常打开）。

实现要点（MS-CFB）：
- v3: 扇区 512B，头部 DIFAT 109 项，超出用 DIFAT 扇区链
- 流 < 4096B 走 mini-stream（64B 迷你扇区，挂在根存储的流上）
- 目录项为红黑树：比较键 = (名称UTF-16含null的字节数, 大写名称)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

FREE = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC

MINI_CUTOFF = 4096


@dataclass(eq=False)   # 需要按对象身份做 dict key
class Entry:
    name: str
    type: int                       # 1=storage 2=stream 5=root
    data: bytes = b""               # type2 的流内容
    children: list = field(default_factory=list)  # type1/5 的子项


# ---------- 读取（v3/v4 通吃） ----------

class _Reader:
    def __init__(self, path: str):
        self.blob = open(path, "rb").read()
        h = self.blob[:512]
        if h[:8] != bytes.fromhex("d0cf11e0a1b11ae1"):
            raise ValueError("不是 CFBF 文件")
        self.major = struct.unpack_from("<H", h, 26)[0]
        self.sect_size = 1 << struct.unpack_from("<H", h, 30)[0]
        self.mini_size = 1 << struct.unpack_from("<H", h, 32)[0]
        self.num_fat = struct.unpack_from("<I", h, 44)[0]
        self.dir_start = struct.unpack_from("<I", h, 48)[0]
        self.minifat_start = struct.unpack_from("<I", h, 60)[0]
        self.num_minifat = struct.unpack_from("<I", h, 64)[0]
        self.difat_start = struct.unpack_from("<I", h, 68)[0]
        self.num_difat = struct.unpack_from("<I", h, 72)[0]
        self.hdr_difat = list(struct.unpack_from("<109I", h, 76))

    def _sect(self, sid: int) -> bytes:
        off = (sid + 1) * self.sect_size
        return self.blob[off:off + self.sect_size]

    def _chain(self, start: int, fat: list[int]) -> bytes:
        out = bytearray()
        sid = start
        while sid not in (ENDOFCHAIN, FREE) and sid < len(fat):
            out += self._sect(sid)
            sid = fat[sid]
        return bytes(out)

    def read(self) -> Entry:
        # FAT
        difat = [s for s in self.hdr_difat if s != FREE]
        sid = self.difat_start
        for _ in range(self.num_difat):
            if sid in (ENDOFCHAIN, FREE):
                break
            sec = self._sect(sid)
            vals = struct.unpack(f"<{self.sect_size // 4}I", sec)
            difat += [v for v in vals[:-1] if v != FREE]
            sid = vals[-1]
        fat: list[int] = []
        for fs in difat[:self.num_fat]:
            fat += list(struct.unpack(f"<{self.sect_size // 4}I",
                                      self._sect(fs)))
        # miniFAT
        minifat: list[int] = []
        if self.num_minifat and self.minifat_start not in (ENDOFCHAIN, FREE):
            raw = self._chain(self.minifat_start, fat)
            minifat = list(struct.unpack(f"<{len(raw) // 4}I", raw))
        # 目录
        dir_raw = self._chain(self.dir_start, fat)
        entries = []
        for off in range(0, len(dir_raw) - 127, 128):
            e = dir_raw[off:off + 128]
            nlen = struct.unpack_from("<H", e, 64)[0]
            name = e[:max(0, nlen - 2)].decode("utf-16-le", "replace") \
                if nlen >= 2 else ""
            entries.append({
                "name": name, "type": e[66],
                "left": struct.unpack_from("<I", e, 68)[0],
                "right": struct.unpack_from("<I", e, 72)[0],
                "child": struct.unpack_from("<I", e, 76)[0],
                "start": struct.unpack_from("<I", e, 116)[0],
                "size": struct.unpack_from("<Q", e, 120)[0]})
        if not entries:
            raise ValueError("空目录")

        def read_stream(idx: int) -> bytes:
            ent = entries[idx]
            size, start = ent["size"], ent["start"]
            if size == 0 or start in (ENDOFCHAIN, FREE):
                return b""
            if size < MINI_CUTOFF and ent["type"] == 2:
                out = bytearray()
                msid = start
                while msid not in (ENDOFCHAIN, FREE) and msid < len(minifat):
                    off = msid * self.mini_size
                    out += mini_stream[off:off + self.mini_size]
                    msid = minifat[msid]
                return bytes(out[:size])
            return self._chain(start, fat)[:size]

        root_ent = entries[0]
        mini_stream = self._chain(root_ent["start"], fat)[:root_ent["size"]] \
            if root_ent["start"] not in (ENDOFCHAIN, FREE) else b""

        def walk(idx: int) -> list[Entry]:
            """递归收集以 idx 为根的 BST 全树（左/中序/右）。"""
            if idx in (FREE, ENDOFCHAIN) or idx >= len(entries):
                return []
            e = entries[idx]
            out = walk(e["left"])
            if e["type"] in (1, 2):
                node = Entry(e["name"], e["type"])
                if e["type"] == 2:
                    node.data = read_stream(idx)
                else:
                    node.children = walk_children(e["child"])
                out.append(node)
            return out + walk(e["right"])

        def walk_children(child_idx: int) -> list[Entry]:
            return walk(child_idx)

        root = Entry(root_ent["name"] or "Root Entry", 5)
        root.children = walk_children(root_ent["child"])
        return root


def read_cfbf(path: str) -> Entry:
    return _Reader(path).read()


# ---------- 写 v3 ----------

def _sort_key(name: str):
    utf16 = name.encode("utf-16-le") + b"\x00\x00"
    return (len(utf16), name.upper())


def _build_bst(entries: list[Entry], ids: dict) -> int:
    """按 (名长, 大写名) 建平衡 BST，返回树根在 ids 里的序号；-1 为空。"""
    if not entries:
        return FREE
    order = sorted(range(len(entries)),
                   key=lambda i: _sort_key(entries[i].name))

    def place(lo: int, hi: int) -> int:
        if lo > hi:
            return FREE
        mid = (lo + hi) // 2
        idx = order[mid]
        entries[idx]._left = place(lo, mid - 1)
        entries[idx]._right = place(mid + 1, hi)
        return ids[entries[idx]]

    return place(0, len(order) - 1)


def write_cfbf_v3(path: str, root: Entry) -> None:
    S = 512  # 扇区
    # 1) 扁平化目录（root 固定 0 号），并挂好 BST
    flat: list[Entry] = [root]

    def add_children(storage: Entry):
        for ch in storage.children:
            flat.append(ch)
        for ch in storage.children:
            if ch.type == 1:
                add_children(ch)

    add_children(root)
    ids = {e: i for i, e in enumerate(flat)}
    for e in flat:
        e._left = e._right = FREE
    root._child = _build_bst(root.children, ids)

    def set_children(storage: Entry):
        for ch in storage.children:
            ch._child = _build_bst(ch.children, ids) if ch.type == 1 else FREE
            if ch.type == 1:
                set_children(ch)

    set_children(root)

    # 2) mini-stream：所有 <4096 的流拼进 64B 迷你扇区
    mini = bytearray()
    minifat: list[int] = []
    for e in flat:
        if e.type != 2:
            continue
        if 0 < len(e.data) < MINI_CUTOFF:
            n = (len(e.data) + 63) // 64
            e._start = len(minifat)
            e._msize = len(e.data)
            for i in range(n):
                minifat.append(len(minifat) + 1 if i < n - 1 else ENDOFCHAIN)
                off = (len(minifat) - 1) * 64
                mini[off:off + 64] = e.data[i * 64:(i + 1) * 64].ljust(64, b"\0")
        else:
            e._start = None  # 常规 FAT，稍后分配

    # 3) 计算各区块扇区数（目录 / minifat / ministream / 大流 / FAT）
    def nsects(nbytes: int) -> int:
        return (nbytes + S - 1) // S

    dir_bytes = len(flat) * 128
    n_dir = nsects(dir_bytes)
    n_minifat = nsects(len(minifat) * 4) if minifat else 0
    n_mini = nsects(len(mini)) if mini else 0
    big = [e for e in flat if e.type == 2 and e._start is None and e.data]
    n_big = {e: nsects(len(e.data)) for e in big}

    # 迭代求 FAT 扇区数（FAT 自己也占扇区）
    n_fat = 1
    while True:
        total = n_dir + n_minifat + n_mini + sum(n_big.values()) + n_fat
        need = nsects(total * 4)
        if need == n_fat:
            break
        n_fat = need
    # DIFAT 扇区（>109 个 FAT 扇区时）
    n_difat = 0
    while n_fat > 109 + n_difat * 127:
        n_difat += 1

    # 4) 扇区布局：目录 → minifat → ministream → 大流 → FAT → DIFAT
    cursor = 0
    dir_start = cursor
    cursor += n_dir
    minifat_start = cursor if n_minifat else ENDOFCHAIN
    cursor += n_minifat
    mini_start = cursor if n_mini else ENDOFCHAIN
    cursor += n_mini
    for e in big:
        e._start = cursor
        cursor += n_big[e]
    fat_start = cursor
    cursor += n_fat
    difat_start = cursor if n_difat else ENDOFCHAIN
    cursor += n_difat

    fat = [FREE] * (n_fat * (S // 4))

    def link(start: int, count: int, mark_last=ENDOFCHAIN):
        for i in range(count):
            fat[start + i] = start + i + 1 if i < count - 1 else mark_last

    link(dir_start, n_dir)
    if n_minifat:
        link(minifat_start, n_minifat)
    if n_mini:
        link(mini_start, n_mini)
    for e in big:
        link(e._start, n_big[e])
    for i in range(n_fat):
        fat[fat_start + i] = FATSECT
    if n_difat:
        link(difat_start, n_difat)

    # 5) 落盘
    out = bytearray(S * (1 + cursor))
    # 头部（注意：必须独立 bytearray 再赋回，bytearray 切片是副本）
    hdr = bytearray(S)
    hdr[:8] = bytes.fromhex("d0cf11e0a1b11ae1")
    struct.pack_into("<HHHHH", hdr, 24, 0x003E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<I", hdr, 40, 0)               # v3 目录扇区数固定 0
    struct.pack_into("<I", hdr, 44, n_fat)
    struct.pack_into("<I", hdr, 48, dir_start)
    struct.pack_into("<I", hdr, 52, 0)
    struct.pack_into("<I", hdr, 56, MINI_CUTOFF)
    struct.pack_into("<I", hdr, 60, minifat_start)
    struct.pack_into("<I", hdr, 64, n_minifat)
    struct.pack_into("<I", hdr, 68, difat_start)
    struct.pack_into("<I", hdr, 72, n_difat)
    fat_ids = [fat_start + i for i in range(n_fat)]
    for i in range(109):
        hdr[76 + i * 4:80 + i * 4] = struct.pack(
            "<I", fat_ids[i] if i < len(fat_ids) else FREE)
    out[:S] = hdr

    def put_sect(sid: int, data: bytes):
        off = (sid + 1) * S
        out[off:off + S] = data.ljust(S, b"\0")[:S]

    # 目录流
    dirbuf = bytearray()
    for i, e in enumerate(flat):
        ent = bytearray(128)
        nm = e.name.encode("utf-16-le") + b"\x00\x00"
        ent[:len(nm)] = nm[:64]
        struct.pack_into("<H", ent, 64, min(len(nm), 64))
        ent[66] = e.type
        ent[67] = 1  # black
        struct.pack_into("<I", ent, 68, getattr(e, "_left", FREE))
        struct.pack_into("<I", ent, 72, getattr(e, "_right", FREE))
        child = getattr(e, "_child", FREE) if e.type in (1, 5) else FREE
        struct.pack_into("<I", ent, 76, child)
        if e.type == 5:
            start = mini_start if n_mini else ENDOFCHAIN
            size = len(mini)
        elif e.type == 2:
            start = e._start if e._start is not None else (
                getattr(e, "_start", None) if e.data else ENDOFCHAIN)
            if e.data and len(e.data) < MINI_CUTOFF:
                start = e._start  # mini 扇区号
            start = start if start is not None else ENDOFCHAIN
            size = len(e.data)
        else:
            start, size = ENDOFCHAIN, 0
        struct.pack_into("<I", ent, 116, start)
        struct.pack_into("<Q", ent, 120, size)
        dirbuf += ent
    for i in range(n_dir):
        put_sect(dir_start + i, bytes(dirbuf[i * S:(i + 1) * S]))
    # miniFAT / ministream / 大流
    mf = b"".join(struct.pack("<I", v) for v in minifat)
    for i in range(n_minifat):
        put_sect(minifat_start + i, mf[i * S:(i + 1) * S])
    for i in range(n_mini):
        put_sect(mini_start + i, bytes(mini[i * S:(i + 1) * S]))
    for e in big:
        for i in range(n_big[e]):
            put_sect(e._start + i, e.data[i * S:(i + 1) * S])
    # FAT / DIFAT
    fb = b"".join(struct.pack("<I", v) for v in fat)
    for i in range(n_fat):
        put_sect(fat_start + i, fb[i * S:(i + 1) * S])
    for d in range(n_difat):
        vals = [FREE] * (S // 4)
        base = 109 + d * 127
        for j in range(127):
            if base + j < len(fat_ids):
                vals[j] = fat_ids[base + j]
        vals[-1] = difat_start + d + 1 if d < n_difat - 1 else ENDOFCHAIN
        put_sect(difat_start + d, b"".join(struct.pack("<I", v) for v in vals))

    with open(path, "wb") as f:
        f.write(bytes(out))


def convert_file_to_v3(path: str) -> None:
    """把 npnp 生成的 v4 CFBF 文件无损重写为 v3（原地覆盖）。"""
    root = read_cfbf(path)
    write_cfbf_v3(path, root)
