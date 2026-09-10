"""把多个单元件库合并成一个库文件。

- AD .SchLib：FileHeader 里的元件注册表（COMPCOUNT/LIBREFi/COMPDESCRi/
  PARTCOUNTi/WEIGHT）重排合并，组件 storage 的 Data 自流自包含、原样搬运。
- AD .PcbLib：组件 storage 自流搬运；Library/Models 下模型流按 GUID/内容
  去重后重编号，Models/Data 记录顺序与之一致；Library/Data 尾部重建
  封装名单（u32 总数 + 每条 u32 长+1、u8 长、名字节）。
- KiCad：.kicad_sym 文本块合并；.pretty 目录并集（重名按内容去重/改名）。

全部经 convert/cfbf.py 以 CFBF v3 落盘，AD16 起全版本兼容。
"""
from __future__ import annotations

import glob
import os
import re
import struct

from lcsc_exporter.convert.cfbf import Entry, read_cfbf, write_cfbf_v3


# ---------- 通用小工具 ----------

def _parse_records(data: bytes) -> list[bytes]:
    """拆 4字节LE长度前缀 的记录流；尾部无法解析的二进制原样保留。"""
    recs, pos = [], 0
    while pos + 4 <= len(data):
        ln = struct.unpack_from("<I", data, pos)[0]
        if ln == 0 or pos + 4 + ln > len(data):
            recs.append(data[pos:])          # 尾段（二进制/名单）整条保留
            return recs
        recs.append(data[pos + 4:pos + 4 + ln])
        pos += 4 + ln
    if pos < len(data):
        recs.append(data[pos:])
    return recs


def _pack_records(recs: list[bytes]) -> bytes:
    return b"".join(struct.pack("<I", len(r)) + r for r in recs)


def _child(e: Entry, name: str) -> Entry | None:
    return next((c for c in e.children if c.name == name), None)


def _tokens(rec: bytes) -> list[str]:
    return [t for t in rec.decode("ascii", "replace").strip("\x00")
            .split("|") if t]


_COMP_KEY = re.compile(r"^(%UTF8%)?(LIBREF|COMPDESCR|PARTCOUNT)\d+$")


# CFBF 目录项名最多 31 个 UTF-16 字符；npnp 原件也是"storage 名截断、
# PATTERN/LIBREF/尾部名单保留全名"，这里照做并保证截断后唯一。
def _storage_name(full: str, taken: set) -> str:
    name = full[:31]
    if name not in taken:
        taken.add(name)
        return name
    i = 2
    while True:
        cand = f"{full[:28]}_{i}"
        if cand not in taken:
            taken.add(cand)
            return cand
        i += 1


# ---------- SchLib 合并 ----------

def merge_schlib(paths: list[str], out_path: str) -> int:
    """合并多个 .SchLib 为一个；返回合并后的元件数。"""
    comps: list[Entry] = []                 # 组件 storage
    comp_fields: list[dict[str, str]] = []  # 每元件的注册字段
    base_tokens: list[str] | None = None
    storage_stream: bytes = b""
    weight = 0
    seen: dict[str, bytes] = {}

    for p in paths:
        root = read_cfbf(p)
        fh = _child(root, "FileHeader")
        st = _child(root, "Storage")
        if fh is None:
            continue
        if storage_stream == b"" and st is not None:
            storage_stream = st.data
        recs = _parse_records(fh.data)
        tokens = _tokens(recs[0]) if recs else []
        base = [t for t in tokens if not _COMP_KEY.match(t.split("=", 1)[0])]
        if base_tokens is None:
            base_tokens = base
        for t in base:
            if t.startswith("WEIGHT="):
                try:
                    weight += int(t[7:])
                except ValueError:
                    pass
        # 该文件里的组件（npnp 单元件导出 = 恰 1 个；注册字段下标 0）
        fields = {}
        for t in tokens:
            k, _, v = t.partition("=")
            m = re.match(r"^(%UTF8%)?(LIBREF|COMPDESCR|PARTCOUNT)(\d+)$", k)
            if m:
                fields[(m.group(1) or "") + m.group(2)] = v
        for c in root.children:
            if c.type != 1:
                continue
            data = _child(c, "Data")
            blob = data.data if data else b""
            name = c.name
            if name in seen:
                if seen[name] == blob:
                    continue                      # 完全重复 → 跳过
                name = _free_name(name, seen)     # 同名不同物 → 改名
                c = _rename_sch_component(c, name)
            seen[name] = blob
            comps.append(c)                       # storage 名稍后统一截断
            comp_fields.append({"LIBREF": name,
                                "COMPDESCR": fields.get("COMPDESCR", ""),
                                "%UTF8%COMPDESCR":
                                    fields.get("%UTF8%COMPDESCR", ""),
                                "PARTCOUNT": fields.get("PARTCOUNT", "1")})
    if not comps or base_tokens is None:
        raise ValueError("没有可合并的元件")
    taken: set = set()
    for c, f in zip(comps, comp_fields):
        c.name = _storage_name(f["LIBREF"], taken)

    # 重建 FileHeader 头记录
    out_tokens = []
    for t in base_tokens:
        if t.startswith("WEIGHT="):
            out_tokens.append(f"WEIGHT={weight}")
        elif t.startswith("COMPCOUNT="):
            out_tokens.append(f"COMPCOUNT={len(comps)}")
        else:
            out_tokens.append(t)
    if not any(t.startswith("COMPCOUNT=") for t in out_tokens):
        out_tokens.append(f"COMPCOUNT={len(comps)}")
    for i, f in enumerate(comp_fields):
        out_tokens.append(f"LIBREF{i}={f['LIBREF']}")
        if f["COMPDESCR"]:
            out_tokens.append(f"COMPDESCR{i}={f['COMPDESCR']}")
        if f["%UTF8%COMPDESCR"]:
            out_tokens.append(f"%UTF8%COMPDESCR{i}={f['%UTF8%COMPDESCR']}")
        out_tokens.append(f"PARTCOUNT{i}={f['PARTCOUNT']}")
    header_rec = ("|" + "|".join(out_tokens)).encode("ascii", "replace")

    root = Entry("Root Entry", 5)
    if storage_stream:
        root.children.append(Entry("Storage", 2, storage_stream))
    root.children.append(Entry("FileHeader", 2, _pack_records([header_rec])))
    root.children.extend(comps)
    write_cfbf_v3(out_path, root)
    return len(comps)


def _free_name(name: str, seen: dict) -> str:
    i = 2
    while f"{name}_{i}" in seen:
        i += 1
    return f"{name}_{i}"


def _rename_sch_component(storage: Entry, new: str) -> Entry:
    """SchLib 组件改名：Data 首条文本记录里的 LIBREFERENCE/DESIGNITEMID。"""
    data = _child(storage, "Data")
    if data and data.data:
        recs = _parse_records(data.data)
        old = storage.name.encode()
        newb = new.encode()
        recs[0] = recs[0].replace(b"LIBREFERENCE=" + old,
                                  b"LIBREFERENCE=" + newb)
        recs[0] = recs[0].replace(b"DESIGNITEMID=" + old,
                                  b"DESIGNITEMID=" + newb)
        data.data = _pack_records(recs)
    storage.name = new
    return storage


# ---------- PcbLib 合并 ----------

def merge_pcblib(paths: list[str], out_path: str) -> int:
    """合并多个 .PcbLib 为一个（3D 模型随封装修编）；返回封装数。"""
    footprints: list[Entry] = []
    models: list[tuple[bytes, bytes]] = []   # (zlib STEP, Models/Data 记录)
    model_keys: set[tuple] = set()
    lib_record0: bytes | None = None
    fileheader: bytes = b""
    tex_children: list[Entry] = []
    mne_children: list[Entry] = []
    seen: dict[str, bytes] = {}

    for p in paths:
        root = read_cfbf(p)
        fh = _child(root, "FileHeader")
        lib = _child(root, "Library")
        if fh is None or lib is None:
            continue
        if not fileheader:
            fileheader = fh.data
        lib_data = _child(lib, "Data")
        if lib_record0 is None and lib_data is not None:
            recs = _parse_records(lib_data.data)
            if recs:
                rec0 = re.sub(rb"FILENAME=[^|]*",
                              b"FILENAME=" + os.path.basename(out_path)
                              .encode(), recs[0])
                lib_record0 = rec0
        mdl = _child(lib, "Models")
        mrecs: list[bytes] = []
        mstreams: list[Entry] = []
        if mdl is not None:
            md = _child(mdl, "Data")
            mrecs = _parse_records(md.data) if md and md.data else []
            mstreams = sorted((c for c in mdl.children
                               if c.type == 2 and c.name.isdigit()),
                              key=lambda c: int(c.name))
        for i, s in enumerate(mstreams):
            rec = mrecs[i] if i < len(mrecs) else b"|EMBED=TRUE|"
            key = (len(s.data), rec[-60:])
            if key in model_keys:
                continue
            model_keys.add(key)
            models.append((s.data, rec))
        if not tex_children:
            tex = _child(lib, "Textures")
            tex_children = tex.children if tex else []
        if not mne_children:
            mne = _child(lib, "ModelsNoEmbed")
            mne_children = mne.children if mne else []

        for c in root.children:
            if c.type != 1 or c.name == "Library":
                continue
            blob = (_child(c, "Data").data if _child(c, "Data") else b"")
            full = _fp_full_name(c)               # PATTERN 全名（展示用）
            if full in seen:
                if seen[full] == blob:
                    continue
                new_full = _free_name(full, seen)
                c = _rename_fp_storage(c, full, new_full)
                full = new_full
            seen[full] = blob
            footprints.append((c, full))
    if not footprints or lib_record0 is None:
        raise ValueError("没有可合并的封装")

    # storage 名 ≤31 字符且唯一；尾部名单保留全名（与 npnp 原件一致）
    taken: set = {"Library", "FileHeader"}
    for c, full in footprints:
        c.name = _storage_name(full, taken)
    tail = struct.pack("<I", len(footprints))
    for _c, full in footprints:
        nb = full.encode("ascii", "replace")
        tail += struct.pack("<I", len(nb) + 1) + bytes([len(nb)]) + nb
    lib_data = struct.pack("<I", len(lib_record0)) + lib_record0 + tail

    lib = Entry("Library", 1)
    lib.children.append(Entry("Data", 2, lib_data))
    lib.children.append(Entry("Header", 2, struct.pack("<I", 1)))
    models_st = Entry("Models", 1)
    models_st.children.append(
        Entry("Data", 2, _pack_records([r for _, r in models])))
    models_st.children.append(Entry("Header", 2, struct.pack("<I", len(models))))
    for i, (blob, _rec) in enumerate(models):
        models_st.children.append(Entry(str(i), 2, blob))
    lib.children.append(models_st)
    tex = Entry("Textures", 1)
    tex.children = tex_children or [Entry("Data", 2, b""),
                                    Entry("Header", 2, b"\x00" * 4)]
    lib.children.append(tex)
    mne = Entry("ModelsNoEmbed", 1)
    mne.children = mne_children or [Entry("Data", 2, b""),
                                    Entry("Header", 2, b"\x00" * 4)]
    lib.children.append(mne)

    root = Entry("Root Entry", 5)
    root.children.extend(c for c, _ in footprints)
    root.children.append(lib)
    root.children.append(Entry("FileHeader", 2, fileheader))
    write_cfbf_v3(out_path, root)
    return len(footprints)


def _fp_full_name(storage: Entry) -> str:
    """从 Parameters 流的 PATTERN= 取封装全名（展示名），失败回退 storage 名。"""
    par = _child(storage, "Parameters")
    if par and par.data:
        m = re.search(rb"PATTERN=([^|]*)", par.data)
        if m:
            return m.group(1).decode("ascii", "replace")
    return storage.name


def _rename_fp_storage(storage: Entry, old: str, new: str) -> Entry:
    """PcbLib 封装改名：Data 开头的长度前缀全名 + Parameters PATTERN。"""
    data = _child(storage, "Data")
    if data and data.data:
        ob = old.encode("ascii", "replace")
        nb = new.encode("ascii", "replace")
        head = struct.pack("<I", len(ob) + 1) + bytes([len(ob)]) + ob
        if data.data.startswith(head):
            data.data = (struct.pack("<I", len(nb) + 1) + bytes([len(nb)])
                         + nb + data.data[len(head):])
    par = _child(storage, "Parameters")
    if par and par.data:
        recs = _parse_records(par.data)
        recs = [r.replace(b"PATTERN=" + old.encode(),
                          b"PATTERN=" + new.encode()) for r in recs]
        par.data = _pack_records(recs)
    storage.name = new
    return storage


# ---------- KiCad 合并 ----------

def merge_kicad(sym_paths: list[str], pretty_dirs: list[str],
                out_sym: str, out_pretty: str) -> tuple[int, int]:
    """合并 .kicad_sym（符号块拼接）+ .pretty（目录并集）。返回 (符号数, 封装数)。"""
    # 符号：按括号平衡抽 (symbol "NAME" ...) 块
    symbols: dict[str, str] = {}
    for p in sym_paths:
        try:
            text = open(p, encoding="utf-8").read()
        except OSError:
            continue
        for name, block in _extract_symbol_blocks(text):
            if name not in symbols:
                symbols[name] = block
    if symbols:
        head = '(kicad_symbol_lib (version 20211014) (generator "lcsc2altium"))'
        with open(out_sym, "w", encoding="utf-8", newline="\n") as f:
            f.write(head + "\n" + "".join(symbols.values()) + ")\n")

    # 封装：复制 .kicad_mod（含 STEP 引用同步改名）
    os.makedirs(out_pretty, exist_ok=True)
    placed: dict[str, bytes] = {}
    n_fp = 0
    for d in pretty_dirs:
        for mod in sorted(glob.glob(os.path.join(d, "*.kicad_mod"))):
            name = os.path.splitext(os.path.basename(mod))[0]
            blob = open(mod, "rb").read()
            new = name
            if name in placed:
                if placed[name] == blob:
                    continue
                i = 2
                while f"{name}_{i}" in placed:
                    i += 1
                new = f"{name}_{i}"
                txt = blob.decode("utf-8").replace(
                    f'(footprint "{name}"', f'(footprint "{new}"')
                txt = re.sub(r'\(model "[^"]*"',
                             f'(model "{new}.step"', txt, count=1)
                blob = txt.encode("utf-8")
            placed[new] = blob
            with open(os.path.join(out_pretty, new + ".kicad_mod"),
                      "wb") as f:
                f.write(blob)
            n_fp += 1
            # 同名 STEP 一起搬
            for ext in (".step", ".STEP"):
                src = os.path.join(d, name + ext)
                if os.path.isfile(src):
                    dst = os.path.join(out_pretty, new + ".step")
                    if not os.path.exists(dst):
                        with open(src, "rb") as fi, open(dst, "wb") as fo:
                            fo.write(fi.read())
                    break
    return len(symbols), n_fp


def _extract_symbol_blocks(text: str) -> list[tuple[str, str]]:
    """从 .kicad_sym 文本抽出顶层 (symbol "NAME" ...) 块。"""
    out = []
    for m in re.finditer(r'^\s{2}\(symbol "([^"]+)"', text, re.M):
        start = m.start()
        depth, i = 0, start
        while i < len(text):
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        block = text[start:i]
        if not block.endswith("\n"):
            block += "\n"
        out.append((m.group(1), block))
    return out
