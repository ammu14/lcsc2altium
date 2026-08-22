"""Qt GUI：输入 LCSC 商城元件编号 → 调用 npnp 生成 Altium .SchLib + .PcbLib + STEP。

用法:
  python -m lcsc_exporter.app
或双击工作区根目录的 lcsc2altium_gui.pyw（无控制台窗口）。

Qt 绑定自动适配：PySide6（工作区 .tools/pylibs）→ PyQt6 → PyQt5，
三者装任何一个即可运行（API 差异用下方兼容层抹平）。

导出逻辑：直接调用工作区内的 npnp（Rust 工具）子命令
（export-schlib / export-pcblib / download-step），本 GUI 只是 npnp 的一层皮。
"""
from __future__ import annotations

import glob
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
    from PySide6.QtCore import QThread, Signal, QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (
        QApplication, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
        QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
        QSplitter, QStatusBar, QTableWidget, QTableWidgetItem,
        QVBoxLayout, QWidget,
    )
    QT_BINDING = "PySide6"
except ImportError:
    try:
        from PyQt6.QtCore import QThread, pyqtSignal as Signal, QUrl
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtWidgets import (
            QApplication, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
            QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
            QSplitter, QStatusBar, QTableWidget, QTableWidgetItem,
            QVBoxLayout, QWidget,
        )
        QT_BINDING = "PyQt6"
    except ImportError:
        from PyQt5.QtCore import QThread, pyqtSignal as Signal, QUrl
        from PyQt5.QtGui import QDesktopServices
        from PyQt5.QtWidgets import (
            QApplication, QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
            QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
            QSplitter, QStatusBar, QTableWidget, QTableWidgetItem,
            QVBoxLayout, QWidget,
        )
        QT_BINDING = "PyQt5"

def workspace_root() -> str:
    """工作区根目录（.../lcsc2altium），gui.py 位于 lcsc_exporter/app/ 下两级。"""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_npnp() -> str | None:
    """在工作区内定位 npnp 可执行文件。

    优先 .tools/bin/npnp[.exe]（精简后的固定位置）；
    回退 .tools/rust/*/target/release/（未精简时的构建位置）；
    再回退 PATH 里的 npnp。
    """
    root = workspace_root()
    for c in (
        os.path.join(root, ".tools", "bin", "npnp.exe"),
        os.path.join(root, ".tools", "bin", "npnp"),
    ):
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


class ExportWorker(QThread):
    """后台导出：调用 npnp 子命令（不阻塞 UI）。"""
    log = Signal(str)
    item_done = Signal(object)   # 结果 dict {code, mpn, schlib, pcblib, step, warnings/error}
    all_done = Signal(int, int)  # ok, total

    def __init__(self, codes: list[str], outdir: str,
                 with_step: bool, force: bool, parent=None):
        super().__init__(parent)
        self.codes = codes
        self.outdir = outdir
        self.with_step = with_step
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

    def run(self):
        npnp = find_npnp()
        if not npnp:
            self.log.emit("[ERROR] 找不到 npnp 可执行文件，请确认 .tools/rust/ 下已编译 npnp")
            self.all_done.emit(0, len(self.codes))
            return
        self.log.emit(f"使用 npnp: {npnp}\n")
        ok = 0
        for i, code in enumerate(self.codes, 1):
            self.log.emit(f"--- [{i}/{len(self.codes)}] {code} ---")
            subdir = os.path.join(self.outdir, code)
            os.makedirs(subdir, exist_ok=True)
            r = dict(code=code, mpn="", schlib="", pcblib="", step="", warnings=[])
            try:
                self._run_npnp(npnp, self._npnp_args("export-schlib", code, subdir))
                r["schlib"] = self._find_file(subdir, "SchLib")
                self._run_npnp(npnp, self._npnp_args("export-pcblib", code, subdir))
                r["pcblib"] = self._find_file(subdir, "PcbLib")
                if self.with_step:
                    try:
                        self._run_npnp(npnp, self._npnp_args("download-step", code, subdir))
                        r["step"] = (self._find_file(subdir, "step")
                                     or self._find_file(subdir, "STEP"))
                        if not r["step"]:
                            r["warnings"].append("未生成 STEP")
                    except Exception as e:  # noqa: BLE001 — STEP 失败不阻断整体
                        r["warnings"].append(f"STEP 失败: {e}")
                if not (r["schlib"] and r["pcblib"]):
                    raise RuntimeError("未生成 SchLib/PcbLib 文件")
                ok += 1
            except Exception as e:  # noqa: BLE001 — GUI 需兜底一切异常
                r["error"] = str(e)
                self.log.emit(f"[ERROR] {code}: {e}")
            self.item_done.emit(r)
        self.all_done.emit(ok, len(self.codes))


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCSC 元件 Altium 导出器（.SchLib / .PcbLib / STEP）")
        self.resize(980, 640)
        self._worker: ExportWorker | None = None

        root = QVBoxLayout(self)

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

        # 选项 + 按钮
        row3 = QHBoxLayout()
        self.step_cb = QCheckBox("下载 3D 模型（无底座 STEP）")
        self.step_cb.setChecked(True)
        self.force_cb = QCheckBox("强制重新抓取数据")
        row3.addWidget(self.step_cb)
        row3.addWidget(self.force_cb)
        row3.addStretch(1)
        self.open_dir_btn = QPushButton("打开输出目录")
        self.open_dir_btn.clicked.connect(self._open_out_dir)
        row3.addWidget(self.open_dir_btn)
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
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["编号", "MPN/描述", "SchLib", "PcbLib", "STEP", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch)
        for i in (2, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeToContents)
        splitter.addWidget(self.log_view)
        splitter.addWidget(self.table)
        splitter.setSizes([260, 340])
        root.addWidget(splitter, 1)

        self.statusBar = QStatusBar()
        root.addWidget(self.statusBar)
        self.statusBar.showMessage("就绪")

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
        self.table.setRowCount(0)
        self.progress.setRange(0, len(codes))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.export_btn.setEnabled(False)
        out = self.out_edit.text().strip() or "out"
        self._log(f"开始导出 {len(codes)} 个元件 → {out}\n")
        self._worker = ExportWorker(codes, out,
                                    with_step=self.step_cb.isChecked(),
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
        cell(2, r.get("schlib") or "", r.get("schlib") or "")
        cell(3, r.get("pcblib") or "", r.get("pcblib") or "")
        cell(4, r.get("step") or "", r.get("step") or "")
        if r.get("error"):
            cell(5, "失败", r["error"])
        else:
            warn = "，".join(r.get("warnings", [])) or "成功"
            cell(5, warn, warn)
        self.progress.setValue(self.progress.value() + 1)

    def _all_done(self, ok: int, total: int):
        self.progress.setVisible(False)
        self.export_btn.setEnabled(True)
        self._worker = None
        self.statusBar.showMessage(f"完成: {ok}/{total}")
        out = self.out_edit.text().strip() or "out"
        self._log(f"\n完成: {ok}/{total}，输出目录: {os.path.abspath(out)}")
        self._log("下一步: 在 Altium 中 File → Place → Part 导入 .SchLib，"
                  "PCB 中 Footprint 导入 .PcbLib 验证。")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
