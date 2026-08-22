"""LCSC 元件 Altium 导出器 — GUI 启动器（双击运行，无控制台）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lcsc_exporter.app.gui import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
