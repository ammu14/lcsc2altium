"""符号/封装预览：npnp 取 EasyEDA 源 → convert.easyeda 解析 → QPainter 渲染。

数据流复用 KiCad 转换器的解析器（毫米单位中间模型），
渲染只读不改：符号画引脚/矩形/圆/折线，封装画焊盘/丝印/装配层。
"""
from __future__ import annotations

import glob
import json
import math
import os
import shutil
import subprocess

# 与 gui.py 相同的 Qt 绑定回退链
try:
    from PySide6.QtCore import QThread, Signal, Qt, QPointF, QRectF
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
    from PySide6.QtWidgets import (
        QDialog, QLabel, QTabWidget, QVBoxLayout, QWidget)
except ImportError:
    try:
        from PyQt6.QtCore import QThread, pyqtSignal as Signal, Qt, QPointF, QRectF
        from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush
        from PyQt6.QtWidgets import (
            QDialog, QLabel, QTabWidget, QVBoxLayout, QWidget)
    except ImportError:
        from PyQt5.QtCore import QThread, pyqtSignal as Signal, Qt, QPointF, QRectF
        from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QBrush
        from PyQt5.QtWidgets import (
            QDialog, QLabel, QTabWidget, QVBoxLayout, QWidget)

from lcsc_exporter.convert import easyeda

_ALIGN_RVC = int(Qt.AlignRight | Qt.AlignVCenter)
_ALIGN_LVC = int(Qt.AlignLeft | Qt.AlignVCenter)
_ALIGN_HC = int(Qt.AlignHCenter | Qt.AlignVCenter)
_ALIGN_HB = int(Qt.AlignHCenter | Qt.AlignBottom)
_ALIGN_HT = int(Qt.AlignHCenter | Qt.AlignTop)


class PreviewWorker(QThread):
    """后台跑 npnp export-source 取符号+封装源 JSON（不阻塞 UI）。"""
    done = Signal(object, object, str)   # sym_src, fp_src, error

    def __init__(self, code: str, parent=None):
        super().__init__(parent)
        self.code = code

    def run(self):
        tmp = ""
        try:
            from lcsc_exporter.app.gui import find_npnp, workspace_root
            npnp = find_npnp()
            if not npnp:
                raise RuntimeError("找不到 npnp（.tools/bin/）")
            # 临时目录放工作区内（npnp 对沙箱外目录可能无写权限），用完即删。
            # 不用管道捕获子进程输出（沙箱下管道会被拒），改为写日志文件；
            # 不用 tempfile.mkdtemp（其受限 ACL 与沙箱不兼容），os.mkdir 正常。
            import uuid
            tmp = os.path.join(workspace_root(),
                               f"lcsc_preview_{uuid.uuid4().hex[:8]}")
            os.mkdir(tmp)
            log_path = os.path.join(tmp, "npnp.log")
            with open(log_path, "w", encoding="utf-8", errors="replace") as lf:
                proc = subprocess.run(
                    [npnp, "export-source", self.code, "--output", tmp],
                    stdout=lf, stderr=subprocess.STDOUT, timeout=300,
                    cwd=workspace_root())
            if proc.returncode != 0:
                tail = ""
                try:
                    with open(log_path, encoding="utf-8", errors="replace") as f:
                        tail = f.read().strip()[-200:]
                except OSError:
                    pass
                raise RuntimeError(f"npnp 退出码 {proc.returncode}: {tail}")
            syms = sorted(glob.glob(os.path.join(tmp, "*_symbol_easyeda.json")))
            fps = sorted(glob.glob(os.path.join(tmp, "*_footprint_easyeda.json")))
            if not (syms and fps):
                raise RuntimeError("未取到源数据（编号可能有误）")
            with open(syms[0], encoding="utf-8") as f:
                sym_src = json.load(f)
            with open(fps[0], encoding="utf-8") as f:
                fp_src = json.load(f)
            self.done.emit(sym_src, fp_src, "")
        except Exception as e:  # noqa: BLE001 — 预览失败只弹提示
            self.done.emit(None, None, str(e))
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)


class _Canvas(QWidget):
    """通用画布：按内容 bbox 自动缩放居中，毫米坐标系，y 向下。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 340)
        self._bbox: tuple[float, float, float, float] | None = None

    def _fit(self, p: QPainter, bbox):
        x1, y1, x2, y2 = bbox
        bw = max(x2 - x1, 0.1)
        bh = max(y2 - y1, 0.1)
        w, h = self.width(), self.height()
        scale = min(w / bw, h / bh) * 0.82
        p.translate(w / 2, h / 2)
        p.scale(scale, scale)
        p.translate(-(x1 + x2) / 2, -(y1 + y2) / 2)

    @staticmethod
    def _pen(color: str, width_mm: float, dashed: bool = False) -> QPen:
        pen = QPen(QColor(color))
        pen.setWidthF(width_mm)
        if dashed:
            pen.setStyle(Qt.DashLine)
        return pen


class SymbolCanvas(_Canvas):
    """原理图符号预览（引脚 + 本体图形 + 引脚名/编号）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sym: easyeda.Symbol | None = None

    def set_symbol(self, sym: easyeda.Symbol):
        self.sym = sym
        xs, ys = [], []
        for pin in sym.pins:
            xs += [pin.x, easyeda.pin_body_end(pin)[0]]
            ys += [pin.y, easyeda.pin_body_end(pin)[1]]
            xs.append(pin.x + len(pin.name) * 1.1)  # 名字占位
        for r in sym.rects:
            xs += [r.x1, r.x2]
            ys += [r.y1, r.y2]
        for e in sym.ellipses:
            xs += [e.cx - e.rx, e.cx + e.rx]
            ys += [e.cy - e.ry, e.cy + e.ry]
        for pl in sym.polylines:
            xs += [pt[0] for pt in pl.points]
            ys += [pt[1] for pt in pl.points]
        if xs:
            self._bbox = (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        sym = self.sym
        if not sym or not self._bbox:
            p.drawText(self.rect(), _ALIGN_HC, "无符号数据")
            p.end()
            return
        self._fit(p, self._bbox)

        # 本体图形
        p.setPen(self._pen("#333333", 0.2))
        p.setBrush(QBrush(Qt.NoBrush))
        for r in sym.rects:
            p.drawRect(QRectF(QPointF(r.x1, r.y1), QPointF(r.x2, r.y2)))
        for e in sym.ellipses:
            p.drawEllipse(QPointF(e.cx, e.cy), e.rx, e.ry)
        for pl in sym.polylines:
            if len(pl.points) >= 2:
                p.drawPolyline([QPointF(x, y) for x, y in pl.points])

        # 引脚（线 + 编号 + 名称）
        font = QFont()
        font.setPixelSize(0)  # 用 pointSizeF 走世界变换
        font.setPointSizeF(1.3)
        p.setFont(font)
        for pin in sym.pins:
            bx, by = easyeda.pin_body_end(pin)
            p.setPen(self._pen("#1e6091", 0.25))
            p.drawLine(QPointF(pin.x, pin.y), QPointF(bx, by))
            rad = math.radians(pin.rotation)
            dx, dy = math.cos(rad), math.sin(rad)
            # 名称：本体端再往里 0.6mm，朝向决定对齐
            p.setPen(self._pen("#222222", 0.05))
            if pin.show_name and pin.name:
                tx, ty = bx + dx * 0.6, by + dy * 0.6
                align = _ALIGN_LVC if dx > 0.5 else (
                    _ALIGN_RVC if dx < -0.5 else (
                        _ALIGN_HT if dy > 0.5 else _ALIGN_HB))
                p.drawText(QRectF(tx - 15, ty - 1.2, 30, 2.4), align, pin.name)
            # 编号：连线中点上方
            if pin.show_number and pin.number:
                mx, my = (pin.x + bx) / 2 - dy * 0.9, (pin.y + by) / 2 - dx * 0.9
                p.drawText(QRectF(mx - 10, my - 1.0, 20, 2.0), _ALIGN_HC,
                           pin.number)
        p.end()


class FootprintCanvas(_Canvas):
    """PCB 封装预览（焊盘 + 丝印/装配线 + 焊盘编号）。"""

    _SILK = (3, 49)    # 顶层丝印
    _FAB = (48,)       # 装配层

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fp: easyeda.Footprint | None = None

    def set_footprint(self, fp: easyeda.Footprint):
        self.fp = fp
        xs, ys = [], []
        for pad in fp.pads:
            r = max(pad.w, pad.h) / 2 + 0.3
            xs += [pad.x - r, pad.x + r]
            ys += [pad.y - r, pad.y + r]
        for ln in fp.lines:
            xs += [pt[0] for pt in ln.points]
            ys += [pt[1] for pt in ln.points]
        for c in fp.circles:
            xs += [c.cx - c.r, c.cx + c.r]
            ys += [c.cy - c.r, c.cy + c.r]
        for t in fp.texts:
            xs.append(t.x)
            ys.append(t.y)
        if xs:
            self._bbox = (min(xs) - 1, min(ys) - 1, max(xs) + 1, max(ys) + 1)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#fdfbf7"))
        fp = self.fp
        if not fp or not self._bbox:
            p.drawText(self.rect(), _ALIGN_HC, "无封装数据")
            p.end()
            return
        self._fit(p, self._bbox)

        # 装配层（虚线灰）与丝印（实线浅灰）
        for ln in fp.lines:
            if ln.layer in self._FAB:
                p.setPen(self._pen("#aaaaaa", 0.12, dashed=True))
            elif ln.layer in self._SILK:
                p.setPen(self._pen("#888888", max(ln.width, 0.12)))
            else:
                continue
            p.setBrush(QBrush(Qt.NoBrush))
            if len(ln.points) >= 2:
                p.drawPolyline([QPointF(x, y) for x, y in ln.points])
        for c in fp.circles:
            p.setPen(self._pen("#888888", max(c.width, 0.12)))
            p.setBrush(QBrush(Qt.NoBrush))
            p.drawEllipse(QPointF(c.cx, c.cy), c.r, c.r)

        # 焊盘（顶层铜红；带孔的画黑孔）
        font = QFont()
        font.setPixelSize(0)
        font.setPointSizeF(0.9)
        p.setFont(font)
        for pad in fp.pads:
            p.save()
            p.translate(pad.x, pad.y)
            p.rotate(pad.rotation)
            w = max(pad.w, 0.1)
            h = max(pad.h, 0.1)
            p.setPen(self._pen("#8c2f1b", 0.08))
            p.setBrush(QBrush(QColor("#d3503a")))
            if pad.shape.upper() in ("OVAL", "ELLIPSE") and abs(w - h) < 0.01:
                p.drawEllipse(QPointF(0, 0), w / 2, h / 2)
            elif pad.shape.upper() in ("OVAL", "ELLIPSE"):
                p.drawRoundedRect(QRectF(-w / 2, -h / 2, w, h),
                                  min(w, h) / 2, min(w, h) / 2)
            else:
                p.drawRect(QRectF(-w / 2, -h / 2, w, h))
            if pad.hole_d > 0:
                p.setBrush(QBrush(QColor("#111111")))
                p.drawEllipse(QPointF(0, 0), pad.hole_d / 2, pad.hole_d / 2)
            if pad.number and max(w, h) > 0.5:
                p.setPen(self._pen("#ffffff", 0.05))
                p.drawText(QRectF(-w / 2, -h / 2, w, h), _ALIGN_HC, pad.number)
            p.restore()
        p.end()


class PreviewDialog(QDialog):
    """符号 + 封装双页签预览窗。"""

    def __init__(self, sym_src: dict, fp_src: dict, code: str, parent=None):
        super().__init__(parent)
        sym = easyeda.parse_symbol(sym_src)
        fp = easyeda.parse_footprint(fp_src)
        title = sym.name or fp.name or code
        self.setWindowTitle(f"预览：{title}（{code}）")
        self.resize(720, 560)
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            f"符号：{sym.name or '—'}　|　封装：{fp.name or '—'}　|　"
            f"引脚 {len(sym.pins)} 个 · 焊盘 {len(fp.pads)} 个"))
        tabs = QTabWidget()
        sc, fc = SymbolCanvas(), FootprintCanvas()
        sc.set_symbol(sym)
        fc.set_footprint(fp)
        tabs.addTab(sc, "原理图符号")
        tabs.addTab(fc, "PCB 封装")
        root.addWidget(tabs, 1)
