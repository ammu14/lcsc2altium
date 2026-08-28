"""Qt GUI：输入 LCSC 商城元件编号 → 按目标 EDA 一键导出可直接使用的库文件。

支持的目标:
  - Altium Designer: .SchLib + .PcbLib + STEP（npnp 直出，3D 内嵌 .PcbLib）
  - KiCad:           .kicad_sym + {型号}.pretty/封装库（npnp 取源 +
                     内置转换器直出，STEP 与 .kicad_mod 同目录绑定 3D）

用法:
  python -m lcsc_exporter.app
或双击工作区根目录的 lcsc2altium_gui.pyw（无控制台窗口）。

Qt 绑定自动适配：PySide6（工作区 .tools/pylibs）→ PyQt6 → PyQt5。
KiCad 转换为内置实现（lcsc_exporter.convert，EasyEDA 源 → KiCad 6+ 格式），
无需安装任何外部工具。
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys

# .tools/pylibs 引导（PySide6 安装在工作区内时优先）
_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".tools", "pylibs")
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

try:
    from PySide6.QtCore import QThread, QTimer, Signal, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
        QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
        QPushButton, QSplitter, QStatusBar, QTabWidget, QTableWidget,
        QTableWidgetItem, QVBoxLayout, QWidget,
    )
    QT_BINDING = "PySide6"
except ImportError:
    try:
        from PyQt6.QtCore import QThread, pyqtSignal as Signal, QUrl
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtWidgets import (
            QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
            QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
            QPushButton, QSplitter, QStatusBar, QTabWidget, QTableWidget,
            QTableWidgetItem, QVBoxLayout, QWidget,
        )
        QT_BINDING = "PyQt6"
    except ImportError:
        from PyQt5.QtCore import QThread, pyqtSignal as Signal, QUrl
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import (
            QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
            QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar,
            QPushButton, QSplitter, QStatusBar, QTabWidget, QTableWidget,
            QTableWidgetItem, QVBoxLayout, QWidget,
        )
        QT_BINDING = "PyQt5"

def workspace_root() -> str:
    """工作区根目录。PyInstaller 冻结后 = exe 所在目录（npnp 等资源在 _internal/）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_npnp() -> str | None:
    """在工作区内定位 npnp 可执行文件。

    优先 .tools/bin/npnp[.exe]（精简后的固定位置）；
    回退 .tools/rust/*/target/release/（未精简时的构建位置）；
    再回退 PATH 里的 npnp。
    """
    root = workspace_root()
    candidates = [
        os.path.join(root, ".tools", "bin", "npnp.exe"),
        os.path.join(root, ".tools", "bin", "npnp"),
    ]
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: add-data 落在 _internal/npnp/npnp.exe
        candidates.insert(0, os.path.join(root, "_internal", "npnp", "npnp.exe"))
        candidates.insert(1, os.path.join(root, "npnp", "npnp.exe"))
    for c in candidates:
        if os.path.isfile(c):
            return c
    for pat in (
        os.path.join(root, ".tools", "rust", "*", "target", "release", "npnp.exe"),
        os.path.join(root, ".tools", "rust", "*", "target", "release", "npnp"),
    ):
        m = glob.glob(pat)
        if m:
            return m[0]
    import shutil
    return shutil.which("npnp")


def parse_codes(text: str) -> list[str]:
    parts = re.split(r"[\s,;，；\u3000]+", text.strip())
    seen: set[str] = set()
    out = []
    for p in parts:
        p = p.strip().upper()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


# 导出目标: 键 -> 界面显示文本
TARGETS = {
    "altium": "Altium Designer（.SchLib + .PcbLib，3D 内嵌）",
    "kicad": "KiCad（.kicad_sym + .pretty 封装库，3D 绑定）",
}


class ExportWorker(QThread):
    """后台导出：调用 npnp 子命令 + 内置 KiCad 转换器（不阻塞 UI）。"""
    log = Signal(str)
    item_done = Signal(object)   # 结果 dict {code, mpn, files, warnings/error}
    all_done = Signal(int, int)  # ok, total

    def __init__(self, codes: list[str], outdir: str,
                 target: str, force: bool, parent=None):
        super().__init__(parent)
        self.codes = codes
        self.outdir = outdir
        self.target = target
        self.force = force

    def _npnp_args(self, sub: str, code: str, subdir: str) -> list[str]:
        args = [sub, code, "--output", subdir]
        if self.force:
            args.append("--force")
        return args

    def _run_npnp(self, npnp: str, args: list[str]) -> None:
        cmd = [npnp] + args
        self.log.emit("$ " + " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=600, cwd=workspace_root())
        except subprocess.TimeoutExpired:
            raise RuntimeError("npnp 超时（10 分钟）")
        for line in (proc.stdout or "").strip().splitlines():
            self.log.emit("   " + line)
        for line in (proc.stderr or "").strip().splitlines():
            self.log.emit("   [err] " + line)
        if proc.returncode != 0:
            raise RuntimeError(f"npnp 退出码 {proc.returncode}")

    @staticmethod
    def _find_file(subdir: str, ext: str) -> str:
        m = glob.glob(os.path.join(subdir, f"*.{ext}"))
        return os.path.basename(m[0]) if m else ""

    def _rename_to_mpn(self, subdir: str, code: str, mpn: str) -> None:
        """导出完成后把 out/{编号}/ 重命名为 out/{型号}/。

        型号含 Windows 非法字符时替换为 _；目标目录已存在时回退为
        {型号}_{编号}；仍冲突或重命名失败则保留原编号目录（仅告警）。
        """
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", mpn).strip(" .")
        if not name:
            return
        target = os.path.join(self.outdir, name)
        if os.path.normcase(os.path.abspath(target)) == \
                os.path.normcase(os.path.abspath(subdir)):
            return
        if os.path.exists(target):
            target = os.path.join(self.outdir, f"{name}_{code}")
        if os.path.exists(target):
            self.log.emit(f"[warn] 目录 {os.path.basename(target)}/ 已存在，"
                          f"保留 {code}/")
            return
        try:
            os.rename(subdir, target)
            self.log.emit(f"输出目录: {code}/ → {os.path.basename(target)}/")
        except OSError as e:
            self.log.emit(f"[warn] 目录重命名失败，保留 {code}/: {e}")

    # 目录命名优先级: 从产物文件名推断元件型号（保留 MPN 原始大小写的优先）
    _MPN_SUFFIXES = (".SchLib", ".kicad_sym", "_symbol_easyeda.json",
                     "_bundle.json", ".PcbLib", ".kicad_mod",
                     ".step", ".STEP", ".obj")

    @classmethod
    def _derive_mpn(cls, files: list[str]) -> str:
        for suffix in cls._MPN_SUFFIXES:
            for f in files:
                if f.endswith(suffix):
                    return f[:-len(suffix)]
        return ""

    def _sub(self, npnp: str, sub: str, code: str, subdir: str) -> None:
        self._run_npnp(npnp, self._npnp_args(sub, code, subdir))

    def _export_altium(self, npnp: str, code: str, subdir: str, r: dict) -> None:
        """AD 三件套: .SchLib + .PcbLib（3D 已内嵌）+ 独立 .step。"""
        files: list[str] = r["files"]
        for sub, ext in (("export-schlib", "SchLib"),
                         ("export-pcblib", "PcbLib")):
            self._sub(npnp, sub, code, subdir)
            m = glob.glob(os.path.join(subdir, f"*.{ext}"))
            if not m:
                raise RuntimeError(f"{ext} 未生成")
            files.append(os.path.basename(m[0]))
        try:
            self._sub(npnp, "download-step", code, subdir)
            step = (self._find_file(subdir, "step")
                    or self._find_file(subdir, "STEP"))
            if step:
                files.append(step)
            else:
                r["warnings"].append("STEP 未生成")
        except Exception as e:  # noqa: BLE001 — STEP 缺失不阻断
            r["warnings"].append(f"STEP 失败: {e}")

    def _export_kicad(self, npnp: str, code: str, subdir: str, r: dict) -> None:
        """KiCad 套件: .kicad_sym + <MPN>.pretty/<封装>.kicad_mod + 绑定 STEP。"""
        from lcsc_exporter.convert.kicad import convert_to_kicad
        files: list[str] = r["files"]
        # 1) 取 EasyEDA 源（中间产物，用完即删）
        self._sub(npnp, "export-source", code, subdir)
        syms = sorted(glob.glob(os.path.join(subdir, "*_symbol_easyeda.json")))
        fps = sorted(glob.glob(os.path.join(subdir, "*_footprint_easyeda.json")))
        if not (syms and fps):
            raise RuntimeError("未取到符号/封装源数据")
        # 2) 取 STEP（3D，绑定进封装库目录）
        step_path = ""
        try:
            self._sub(npnp, "download-step", code, subdir)
            m = glob.glob(os.path.join(subdir, "*.step")) \
                + glob.glob(os.path.join(subdir, "*.STEP"))
            step_path = m[0] if m else ""
            if not step_path:
                r["warnings"].append("STEP 未生成（封装将无 3D）")
        except Exception as e:  # noqa: BLE001
            r["warnings"].append(f"STEP 失败: {e}")
        # 3) 转换为 KiCad 原生库（STEP 移入 .pretty 绑定）
        with open(syms[0], encoding="utf-8") as f:
            sym_src = json.load(f)
        with open(fps[0], encoding="utf-8") as f:
            fp_src = json.load(f)
        out = convert_to_kicad(sym_src, fp_src, subdir, step_path)
        files += [out["sym"], out["mod"], out["step"]]
        files = [f for f in files if f]
        r["files"] = files
        # 4) 清理中间产物
        for p in syms + fps:
            try:
                os.remove(p)
            except OSError:
                pass
        self.log.emit(f"KiCad 转换: {out['sym']}, {out['pretty']}/")

    def _export_one(self, npnp: str, code: str, subdir: str, r: dict) -> None:
        if self.target == "kicad":
            self._export_kicad(npnp, code, subdir, r)
        else:
            self._export_altium(npnp, code, subdir, r)

    def run(self):
        npnp = find_npnp()
        if not npnp:
            self.log.emit("[ERROR] 找不到 npnp 可执行文件，请确认 .tools/bin/ 下有 npnp")
            self.all_done.emit(0, len(self.codes))
            return
        self.log.emit(f"使用 npnp: {npnp}")
        self.log.emit(f"导出目标: {TARGETS.get(self.target, self.target)}\n")
        ok = 0
        for i, code in enumerate(self.codes, 1):
            self.log.emit(f"--- [{i}/{len(self.codes)}] {code} ---")
            subdir = os.path.join(self.outdir, code)
            os.makedirs(subdir, exist_ok=True)
            r = dict(code=code, mpn="", files=[], warnings=[])
            try:
                self._export_one(npnp, code, subdir, r)
                if not r["files"]:
                    raise RuntimeError("未生成任何文件")
                r["mpn"] = self._derive_mpn(r["files"])
                self._rename_to_mpn(subdir, code, r["mpn"])
                ok += 1
            except Exception as e:  # noqa: BLE001 — GUI 需兜底一切异常
                r["error"] = str(e)
                self.log.emit(f"[ERROR] {code}: {e}")
            self.item_done.emit(r)
        self.all_done.emit(ok, len(self.codes))


class _UpdateWorker(QThread):
    """启动后后台检查 GitHub 新版本；无新版/无网 → emit None（静默）。"""
    done = Signal(object)

    def run(self):
        try:
            from lcsc_exporter.app import update
            self.done.emit(update.check_newer())
        except Exception:  # noqa: BLE001 — 更新检查永远不许炸 GUI
            self.done.emit(None)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCSC 元件导出器（Altium / KiCad 一键直出 + AI 选型）")
        self.resize(980, 640)
        self._worker: ExportWorker | None = None

        # 双页签：元件导出 + AI 助手（导出 UI 铺在 export_tab 里）
        tabs = QTabWidget(self)
        export_tab = QWidget()
        root = QVBoxLayout(export_tab)

        # 编号输入
        row1 = QHBoxLayout()
        row1.addWidget(self._label("LCSC 编号:"))
        self.codes_edit = QLineEdit()
        self.codes_edit.setPlaceholderText(
            "立创商城元件编号，例如 C25161；多个用空格/逗号/换行分隔，如 C25161 C8734")
        row1.addWidget(self.codes_edit, 1)
        root.addLayout(row1)

        # 输出目录
        row2 = QHBoxLayout()
        row2.addWidget(self._label("输出目录:"))
        self.out_edit = QLineEdit("out")
        row2.addWidget(self.out_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_out)
        row2.addWidget(browse)
        root.addLayout(row2)

        # 导出目标选择（选了哪种就直接出哪种，无需再转换）
        fmt_row = QHBoxLayout()
        fmt_row.addWidget(self._label("导出目标:"))
        self.target_cb = QComboBox()
        for key, text in TARGETS.items():
            self.target_cb.addItem(text, key)
        self.target_cb.setCurrentIndex(0)
        fmt_row.addWidget(self.target_cb, 1)
        fmt_row.addStretch(1)
        root.addLayout(fmt_row)

        # 选项 + 按钮
        row3 = QHBoxLayout()
        self.force_cb = QCheckBox("强制重新抓取数据")
        row3.addWidget(self.force_cb)
        row3.addStretch(1)
        self.open_dir_btn = QPushButton("打开输出目录")
        self.open_dir_btn.clicked.connect(self._open_out_dir)
        row3.addWidget(self.open_dir_btn)
        self.preview_btn = QPushButton("预览符号/封装")
        self.preview_btn.setToolTip("先抓取并画出该编号的原理图符号和 PCB 封装，"
                                    "确认无误再导出；结果表里双击某行也可预览")
        self.preview_btn.clicked.connect(self._preview_input)
        row3.addWidget(self.preview_btn)
        self.export_btn = QPushButton("开始导出")
        self.export_btn.setDefault(True)
        self.export_btn.setMinimumWidth(140)
        self.export_btn.clicked.connect(self._start_export)
        row3.addWidget(self.export_btn)
        root.addLayout(row3)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        # 日志 + 结果
        splitter = QSplitter()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("导出日志…")
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["编号", "MPN/描述", "产物文件", "状态"])
        self.table.itemDoubleClicked.connect(
            lambda item: self._start_preview(
                self.table.item(item.row(), 0).text()))
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        splitter.addWidget(self.log_view)
        splitter.addWidget(self.table)
        splitter.setSizes([260, 340])
        root.addWidget(splitter, 1)

        self.statusBar = QStatusBar()
        root.addWidget(self.statusBar)
        self.statusBar.showMessage("就绪")

        # 组装页签：AI 助手需要 PySide6（工作区自带）
        tabs.addTab(export_tab, "元件导出")
        self._tabs = tabs
        if QT_BINDING == "PySide6":
            try:
                from lcsc_exporter.app.ai_tab import AIChatTab
                self._ai_tab = AIChatTab(self)
                self._ai_tab.send_to_export.connect(self._accept_ai_codes)
                tabs.addTab(self._ai_tab, "AI 助手")
            except Exception as e:  # noqa: BLE001 — AI 页签故障不影响导出主功能
                self.statusBar.showMessage(f"AI 助手加载失败: {e}")
        tabs.setCurrentIndex(0)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(tabs)

        # 启动后后台检查新版本（无网/无新版都静默）
        self._upd = _UpdateWorker(self)
        self._upd.done.connect(self._on_update_result)
        self._upd.start()

    def _on_update_result(self, info):
        if not info:
            return
        from lcsc_exporter import __version__
        btn = QMessageBox.information(
            self, "发现新版本",
            f"当前版本 v{__version__}，GitHub 已发布新版本 v{info['version']}。\n\n"
            "是否打开发布页下载安装包？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if btn == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(info["url"]))

    # ---------- 符号/封装预览 ----------

    def _preview_input(self):
        codes = parse_codes(self.codes_edit.text())
        if not codes:
            self.statusBar.showMessage("请先输入 LCSC 元件编号再预览")
            return
        self._start_preview(codes[0])

    def _start_preview(self, code: str):
        if not code:
            return
        try:
            from lcsc_exporter.app.preview import PreviewDialog, PreviewWorker
        except Exception as e:  # noqa: BLE001
            self.statusBar.showMessage(f"预览模块加载失败: {e}")
            return
        self.preview_btn.setEnabled(False)
        self.preview_btn.setText("抓取中…")
        self.statusBar.showMessage(f"正在抓取 {code} 的符号/封装数据…")
        self._pv_worker = PreviewWorker(code, parent=self)
        self._pv_worker.done.connect(
            lambda sym, fp, err, c=code: self._on_preview(c, sym, fp, err))
        self._pv_worker.start()

    def _on_preview(self, code: str, sym_src, fp_src, err: str):
        self.preview_btn.setEnabled(True)
        self.preview_btn.setText("预览符号/封装")
        if err:
            self.statusBar.showMessage(f"预览失败: {err}")
            QMessageBox.warning(self, "预览失败", f"{code}: {err}")
            return
        self.statusBar.showMessage(f"{code} 预览就绪")
        from lcsc_exporter.app.preview import PreviewDialog
        PreviewDialog(sym_src, fp_src, code, parent=self).exec()

    def _accept_ai_codes(self, codes: str):
        """AI 助手核验通过的编号 → 填入导出框并切回导出页签。"""
        self.codes_edit.setText(codes)
        self._tabs.setCurrentIndex(0)
        self.statusBar.showMessage("已填入核验通过的编号，点「开始导出」即可")

    @staticmethod
    def _label(text: str):
        return QLabel(text)

    def _browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                             self.out_edit.text() or ".")
        if d:
            self.out_edit.setText(d.replace("\\", "/"))

    def _open_out_dir(self):
        d = self.out_edit.text().strip() or "out"
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(d)))

    def _log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def _start_export(self):
        if self._worker is not None and self._worker.isRunning():
            return
        codes = parse_codes(self.codes_edit.text())
        if not codes:
            self.statusBar.showMessage("请先输入 LCSC 元件编号")
            return
        target = self.target_cb.currentData() or "altium"
        self.table.setRowCount(0)
        self.progress.setRange(0, len(codes))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.export_btn.setEnabled(False)
        out = self.out_edit.text().strip() or "out"
        self._log(f"开始导出 {len(codes)} 个元件 → {out}（目标: {TARGETS[target]}）\n")
        self._worker = ExportWorker(codes, out,
                                    target=target,
                                    force=self.force_cb.isChecked(),
                                    parent=self)
        self._worker.log.connect(self._log)
        self._worker.item_done.connect(self._item_done)
        self._worker.all_done.connect(self._all_done)
        self._worker.start()

    def _item_done(self, r: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)
        def cell(col, text, title=""):
            it = QTableWidgetItem(text)
            it.setToolTip(title)
            self.table.setItem(row, col, it)
        cell(0, r.get("code", ""))
        mpn = r.get("mpn", "")
        cell(1, mpn, mpn)
        files = r.get("files", [])
        cell(2, "; ".join(files), "\n".join(files))
        if r.get("error"):
            cell(3, "失败", r["error"])
        else:
            warn = "，".join(r.get("warnings", [])) or "成功"
            cell(3, warn, warn)
        self.progress.setValue(self.progress.value() + 1)

    def _all_done(self, ok: int, total: int):
        self.progress.setVisible(False)
        self.export_btn.setEnabled(True)
        self._worker = None
        self.statusBar.showMessage(f"完成: {ok}/{total}")
        out = self.out_edit.text().strip() or "out"
        self._log(f"\n完成: {ok}/{total}，输出目录: {os.path.abspath(out)}")
        self._log("提示: AD 目标出 .SchLib/.PcbLib；KiCad 目标出 .kicad_sym/.kicad_mod"
                  "（含 STEP 3D 关联），复制进对应库目录即可使用。")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    w.show()
    code = app.exec()
    # PyInstaller 冻结后解释器退出时 Qt DLL 卸载顺序会致崩（0xC0000409），
    # 主动先销毁窗口与应用对象可规避；源码运行下同样安全。
    w.close()
    w.deleteLater()
    app.processEvents()
    del w
    return code


if __name__ == "__main__":
    sys.exit(main())
