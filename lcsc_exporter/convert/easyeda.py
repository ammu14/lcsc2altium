"""EasyEDA 源 JSON (dataStr) 解析 → 中间模型。

EasyEDA 源格式（LCEDA 标准版）:
  - dataStr 是「每行一个 JSON 数组」的记录流
  - 符号: HEAD/PART/ATTR/PIN/RECT/ELLIPSE/POLYLINE...
  - 封装: LAYER/PAD/POLY/FILL/ATTR...
  - 单位: 符号 1 单位 = 10 mil = 0.254mm; 封装 1 单位 = 1 mil = 0.0254mm
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

SYM_UNIT = 0.254      # 符号单位 -> mm
FP_UNIT = 0.0254      # 封装单位 -> mm


# ---------- 中间模型 ----------

@dataclass
class SymPin:
    name: str = ""
    number: str = ""
    x: float = 0.0        # 连接点, mm
    y: float = 0.0
    length: float = 2.54  # mm
    rotation: float = 0.0  # 度, 从连接点指向本体
    pintype: str = "Undefined"
    show_name: bool = True
    show_number: bool = True


@dataclass
class SymRect:
    x1: float; y1: float; x2: float; y2: float


@dataclass
class SymEllipse:
    cx: float; cy: float; rx: float; ry: float


@dataclass
class SymPolyline:
    points: list[tuple[float, float]]


@dataclass
class Symbol:
    name: str = ""
    designator: str = "U?"
    pins: list[SymPin] = field(default_factory=list)
    rects: list[SymRect] = field(default_factory=list)
    ellipses: list[SymEllipse] = field(default_factory=list)
    polylines: list[SymPolyline] = field(default_factory=list)
    description: str = ""


@dataclass
class Pad:
    number: str = ""
    shape: str = "RECT"      # RECT/OVAL/ROUND...
    x: float = 0.0           # mm
    y: float = 0.0
    w: float = 0.0           # mm
    h: float = 0.0
    rotation: float = 0.0
    layer: int = 1           # 1=TOP 2=BOTTOM 12=MULTI
    hole_d: float = 0.0      # mm, >0 则为通孔焊盘


@dataclass
class FpLine:
    layer: int
    points: list[tuple[float, float]]
    width: float = 0.2


@dataclass
class FpCircle:
    layer: int
    cx: float; cy: float; r: float
    width: float = 0.2


@dataclass
class FpText:
    layer: int
    text: str
    x: float; y: float
    height: float = 1.0


@dataclass
class Footprint:
    name: str = ""
    pads: list[Pad] = field(default_factory=list)
    lines: list[FpLine] = field(default_factory=list)
    circles: list[FpCircle] = field(default_factory=list)
    texts: list[FpText] = field(default_factory=list)
    description: str = ""


# ---------- 解析 ----------

def _records(src_json: dict) -> list[list]:
    ds = src_json["result"]["dataStr"]
    out = []
    for ln in ds.split("\n"):
        ln = ln.strip()
        if ln:
            rec = json.loads(ln)
            if rec:
                out.append(rec)
    return out


def _collect_attrs(records: list[list]) -> dict[str, dict[str, list]]:
    """ATTR 记录: [ATTR, 自身id, 宿主id, key, value, ...] → {宿主id: {key: [值,...]}}"""
    attrs: dict[str, dict[str, list]] = {}
    for rec in records:
        if rec[0] != "ATTR" or len(rec) < 5:
            continue
        _, _id, owner, key, value = rec[0], rec[1], rec[2], rec[3], rec[4]
        owner = owner or ""
        attrs.setdefault(owner, {}).setdefault(str(key), []).append(rec)
    return attrs


def parse_symbol(src_json: dict) -> Symbol:
    records = _records(src_json)
    attrs = _collect_attrs(records)
    sym = Symbol()

    # 顶层属性（owner 无关, 直接扫所有 ATTR）
    for owner, kv in attrs.items():
        for key, recs in kv.items():
            if key == "Symbol" and recs:
                sym.name = str(recs[0][4])
            elif key == "Designator" and recs:
                sym.designator = str(recs[0][4])

    for rec in records:
        t = rec[0]
        if t == "PIN":
            # ["PIN", id, ?, null, x, y, length, rotation, ...]
            pid = rec[1]
            pin = SymPin(
                x=float(rec[4]) * SYM_UNIT,
                y=float(rec[5]) * SYM_UNIT,
                length=float(rec[6]) * SYM_UNIT,
                rotation=float(rec[7] or 0),
            )
            for key, recs in attrs.get(pid, {}).items():
                if key == "NAME" and recs:
                    pin.name = str(recs[0][4])
                    pin.show_name = bool(recs[0][6]) if len(recs[0]) > 6 else True
                elif key == "NUMBER" and recs:
                    pin.number = str(recs[0][4])
                    pin.show_number = bool(recs[0][6]) if len(recs[0]) > 6 else True
                elif key == "Pin Type" and recs:
                    pin.pintype = str(recs[0][4])
            sym.pins.append(pin)
        elif t == "RECT":
            # ["RECT", id, x1, y1, x2, y2, ...]
            sym.rects.append(SymRect(
                float(rec[2]) * SYM_UNIT, float(rec[3]) * SYM_UNIT,
                float(rec[4]) * SYM_UNIT, float(rec[5]) * SYM_UNIT))
        elif t == "ELLIPSE":
            # ["ELLIPSE", id, cx, cy, rx, ry, ...]
            sym.ellipses.append(SymEllipse(
                float(rec[2]) * SYM_UNIT, float(rec[3]) * SYM_UNIT,
                float(rec[4]) * SYM_UNIT, float(rec[5]) * SYM_UNIT))
        elif t in ("POLYLINE", "POLY") and len(rec) > 2 and isinstance(rec[-2], list):
            pts = rec[-2]
            sym.polylines.append(SymPolyline(
                [(float(pts[i]) * SYM_UNIT, float(pts[i + 1]) * SYM_UNIT)
                 for i in range(0, len(pts) - 1, 2)
                 if isinstance(pts[i], (int, float))]))
    return sym


def parse_footprint(src_json: dict) -> Footprint:
    records = _records(src_json)
    fp = Footprint()

    for rec in records:
        t = rec[0]
        if t == "ATTR" and len(rec) >= 8 and rec[6] == "Footprint":
            fp.name = str(rec[7])
        elif t == "PAD":
            # ["PAD", id, ?, ?, layer, number, x, y, rotation, null,
            #  [SHAPE, w, h, ...], [], ..., hole...]
            pad = Pad(
                layer=int(rec[4]),
                number=str(rec[5]),
                x=float(rec[6]) * FP_UNIT,
                y=float(rec[7]) * FP_UNIT,
                rotation=float(rec[8] or 0),
            )
            shape = rec[10] if len(rec) > 10 else None
            if isinstance(shape, list) and shape:
                pad.shape = str(shape[0])
                if len(shape) >= 3:
                    pad.w = float(shape[1]) * FP_UNIT
                    pad.h = float(shape[2]) * FP_UNIT
            # OVAL: w=短边 h=长边; RECT: w×h
            fp.pads.append(pad)
        elif t == "POLY":
            # ["POLY", id, ?, ?, layer, width, [x1,y1,"L",x2,y2,...], ?]
            pts_raw = rec[6] if len(rec) > 6 else []
            nums = [v for v in pts_raw if isinstance(v, (int, float))]
            pts = [(float(nums[i]) * FP_UNIT, float(nums[i + 1]) * FP_UNIT)
                   for i in range(0, len(nums) - 1, 2)]
            if pts:
                fp.lines.append(FpLine(layer=int(rec[4]), points=pts,
                                       width=float(rec[5] or 7.874) * FP_UNIT))
        elif t == "FILL":
            # ["FILL", id, ?, ?, layer, width, ?, [[shape...],[shape...]], ?]
            layer = int(rec[4])
            shapes = rec[7] if len(rec) > 7 else []
            for sh in shapes if isinstance(shapes, list) else []:
                if not isinstance(sh, list) or not sh:
                    continue
                if sh[0] == "CIRCLE" and len(sh) >= 4:
                    fp.circles.append(FpCircle(
                        layer=layer,
                        cx=float(sh[1]) * FP_UNIT, cy=float(sh[2]) * FP_UNIT,
                        r=float(sh[3]) * FP_UNIT))
                elif sh[0] == "RECT" and len(sh) >= 5:
                    x1, y1 = float(sh[1]) * FP_UNIT, float(sh[2]) * FP_UNIT
                    x2, y2 = float(sh[3]) * FP_UNIT, float(sh[4]) * FP_UNIT
                    fp.lines.append(FpLine(layer=layer, points=[
                        (x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)]))
    # 封装名回退
    if not fp.name:
        fp.name = str(src_json.get("result", {}).get("display_title", "")) or "footprint"
    return fp


def pin_body_end(pin: SymPin) -> tuple[float, float]:
    """引脚与本体相交的一端坐标 (mm)。"""
    rad = math.radians(pin.rotation)
    return (pin.x + pin.length * math.cos(rad),
            pin.y + pin.length * math.sin(rad))
