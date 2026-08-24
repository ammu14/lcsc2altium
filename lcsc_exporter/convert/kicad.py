"""中间模型 → KiCad 6+ 原生格式 (.kicad_sym / .kicad_mod)。"""
from __future__ import annotations

import os

from .easyeda import Symbol, Footprint, Pad

KICAD_VERSION = "20221018"

# EasyEDA 层号 -> KiCad 层名（封装）
LAYER_MAP = {
    1: "F.Cu",
    2: "B.Cu",
    3: "F.SilkS",
    4: "B.SilkS",
    9: "F.Fab",       # TOP_ASSEMBLY
    10: "B.Fab",
    13: "Dwgs.User",  # DOCUMENT
    48: "F.Fab",      # COMPONENT_SHAPE 实体外形
    49: "F.SilkS",    # COMPONENT_MARKING 丝印标记
    # 50 PIN_SOLDERING / 52 COMPONENT_MODEL 等跳过
}

# EasyEDA Pin Type -> KiCad 电气类型
PIN_TYPE_MAP = {
    "Input": "input",
    "Output": "output",
    "I/O": "bidirectional",
    "Power": "power_in",
    "Undefined": "passive",
}


def _fmt(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return s if s else "0"


# ---------- 符号 ----------

def write_symbol(sym: Symbol, path: str, footprint_name: str = "") -> None:
    """写 .kicad_sym 单符号库文件。"""
    lines = [
        f'(kicad_symbol_lib (version {KICAD_VERSION}) (generator "lcsc2altium")',
        f'  (symbol "{sym.name}" (in_bom yes) (on_board yes)',
        f'    (property "Reference" "{sym.designator}" (at 0 0 0)',
        '      (effects (font (size 1.27 1.27))))',
        f'    (property "Value" "{sym.name}" (at 0 0 0)',
        '      (effects (font (size 1.27 1.27))))',
        f'    (property "Footprint" "{footprint_name}" (at 0 0 0)',
        '      (effects (font (size 1.27 1.27)) hide))',
        '    (property "Datasheet" "" (at 0 0 0)',
        '      (effects (font (size 1.27 1.27)) hide))',
        f'    (symbol "{sym.name}_0_1"',
    ]
    for r in sym.rects:
        lines.append(
            f'      (rectangle (start {_fmt(r.x1)} {_fmt(r.y1)}) (end {_fmt(r.x2)} {_fmt(r.y2)})'
            ' (stroke (width 0.254) (type default)) (fill (type outline)))')
    for e in sym.ellipses:
        lines.append(
            f'      (circle (center {_fmt(e.cx)} {_fmt(e.cy)}) (radius {_fmt(e.rx)})'
            ' (stroke (width 0.254) (type default)) (fill (type none)))')
    for pl in sym.polylines:
        pts = " ".join(f"(xy {_fmt(x)} {_fmt(y)})" for x, y in pl.points)
        lines.append(
            f'      (polyline (pts {pts})'
            ' (stroke (width 0.254) (type default)) (fill (type none)))')
    lines.append('    )')
    lines.append(f'    (symbol "{sym.name}_1_1"')
    for p in sym.pins:
        etype = PIN_TYPE_MAP.get(p.pintype, "passive")
        name_eff = '(effects (font (size 1.27 1.27)))' + ('' if p.show_name else ' (hide yes)')
        num_eff = '(effects (font (size 1.27 1.27)))' + ('' if p.show_number else ' (hide yes)')
        lines.append(
            f'      (pin {etype} line (at {_fmt(p.x)} {_fmt(p.y)} {_fmt(p.rotation)})'
            f' (length {_fmt(p.length)})'
            f' (name "{p.name}" {name_eff}) (number "{p.number}" {num_eff}))')
    lines.append('    )')
    lines.append('  )')
    lines.append(')')
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


# ---------- 封装 ----------

def _pad_kicad_shape(pad: Pad) -> str:
    """EasyEDA 形状 -> KiCad 焊盘形状。OVAL(长条) -> oval; RECT -> rect。"""
    return {"OVAL": "oval", "RECT": "rect", "ROUND": "roundrect",
            "ELLIPSE": "circle", "POLYGON": "rect"}.get(pad.shape.upper(), "rect")


def _pad_layers(pad: Pad) -> str:
    if pad.hole_d > 0:
        return '"*.Cu" "*.Mask"'
    if pad.layer == 1:
        return '"F.Cu" "F.Paste" "F.Mask"'
    if pad.layer == 2:
        return '"B.Cu" "B.Paste" "B.Mask"'
    return '"F.Cu" "F.Paste" "F.Mask"'


def write_footprint(fp: Footprint, path: str, step_file: str = "") -> None:
    """写 .kicad_mod 封装文件; step_file 非空则关联同名 STEP。"""
    smd = all(p.hole_d == 0 for p in fp.pads) if fp.pads else True
    lines = [
        f'(footprint "{fp.name}" (version {KICAD_VERSION}) (generator "lcsc2altium")',
        '  (layer "F.Cu")',
        f'  (attr {"smd" if smd else "through_hole"})',
        '  (fp_text reference "REF**" (at 0 0 0) (layer "F.SilkS")',
        '    (effects (font (size 1 1) (thickness 0.15))))',
        f'  (fp_text value "{fp.name}" (at 0 0 0) (layer "F.Fab")',
        '    (effects (font (size 1 1) (thickness 0.15))))',
    ]
    for ln in fp.lines:
        kl = LAYER_MAP.get(ln.layer)
        if not kl or len(ln.points) < 2:
            continue
        pts = ln.points
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            if (x1, y1) == (x2, y2):
                continue
            lines.append(
                f'  (fp_line (start {_fmt(x1)} {_fmt(y1)}) (end {_fmt(x2)} {_fmt(y2)})'
                f' (stroke (width {_fmt(ln.width)}) (type solid)) (layer "{kl}"))')
    for c in fp.circles:
        kl = LAYER_MAP.get(c.layer)
        if not kl:
            continue
        lines.append(
            f'  (fp_circle (center {_fmt(c.cx)} {_fmt(c.cy)})'
            f' (end {_fmt(c.cx + c.r)} {_fmt(c.cy)})'
            f' (stroke (width {_fmt(c.width)}) (type solid)) (fill none) (layer "{kl}"))')
    for t in fp.texts:
        kl = LAYER_MAP.get(t.layer)
        if not kl:
            continue
        lines.append(
            f'  (fp_text user "{t.text}" (at {_fmt(t.x)} {_fmt(t.y)}) (layer "{kl}")'
            f' (effects (font (size {_fmt(t.height)} {_fmt(t.height)}) (thickness 0.15))))')
    for p in fp.pads:
        kshape = _pad_kicad_shape(p)
        layers = _pad_layers(p)
        hole = ""
        if p.hole_d > 0:
            hole = f' (drill {_fmt(p.hole_d)})'
            ptype = "thru_hole"
        else:
            ptype = "smd"
        # OVAL: EasyEDA w=短边 h=长边; KiCad oval size 直接用 w×h + rotation
        lines.append(
            f'  (pad "{p.number}" {ptype} {kshape} (at {_fmt(p.x)} {_fmt(p.y)} {_fmt(p.rotation)})'
            f' (size {_fmt(p.w)} {_fmt(p.h)}) (layers {layers}){hole})')
    if step_file:
        lines.append(
            f'  (model "{step_file}"'
            ' (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
    lines.append(')')
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def convert_to_kicad(symbol_src: dict, footprint_src: dict,
                     outdir: str, step_path: str = "") -> dict:
    """EasyEDA 源 -> 可直接导入的 KiCad 库结构:

        outdir/{型号}.kicad_sym            符号库
        outdir/{型号}.pretty/{封装}.kicad_mod   封装库（.pretty 目录即库）
        outdir/{型号}.pretty/{封装}.step        3D，与 .kicad_mod 同目录绑定

    符号的 Footprint 属性写成 "{型号}:{封装名}" —— 用户把 .pretty 目录
    添加为封装库时默认昵称=目录名，符号↔封装自动关联。
    返回 {"sym","mod","step","pretty"}（相对 outdir 的路径）。
    """
    import shutil

    from .easyeda import parse_symbol, parse_footprint

    sym = parse_symbol(symbol_src)
    fp = parse_footprint(footprint_src)
    lib = sym.name                          # 库名 = 型号
    pretty = os.path.join(outdir, f"{lib}.pretty")
    os.makedirs(pretty, exist_ok=True)

    # 3D: STEP 移入 .pretty, .kicad_mod 用裸文件名引用（KiCad 按封装相对解析）
    step_name = ""
    if step_path and os.path.isfile(step_path):
        step_name = os.path.basename(step_path)
        dst = os.path.join(pretty, step_name)
        if os.path.abspath(step_path) != os.path.abspath(dst):
            shutil.move(step_path, dst)

    sym_path = os.path.join(outdir, f"{lib}.kicad_sym")
    fp_path = os.path.join(pretty, f"{fp.name}.kicad_mod")
    write_symbol(sym, sym_path, footprint_name=f"{lib}:{fp.name}")
    write_footprint(fp, fp_path, step_file=step_name)
    return {
        "sym": f"{lib}.kicad_sym",
        "mod": f"{lib}.pretty/{fp.name}.kicad_mod",
        "step": f"{lib}.pretty/{step_name}" if step_name else "",
        "pretty": f"{lib}.pretty",
    }
