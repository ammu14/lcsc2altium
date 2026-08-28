"""LCSC 元件 Altium 导出器 — GUI 启动器（双击运行，无控制台）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lcsc_exporter.app.gui import main  # noqa: E402

if __name__ == "__main__":
    if os.environ.get("LCSC2ALTIUM_SELFTEST") == "1":
        # 打包产物自检：跑完整事件循环后正常退出（无头环境可跑）
        from lcsc_exporter.app import gui as g
        app = g.QApplication([])
        w = g.MainWindow()
        w.show()
        npnp = g.find_npnp() or "NOT-FOUND"
        with open(os.path.join(g.workspace_root(), "selftest_ok.txt"),
                  "w", encoding="utf-8") as f:
            f.write(f"npnp={npnp}\n")
        g.QTimer.singleShot(300, app.quit)
        code = app.exec()
        w.close()
        w.deleteLater()
        app.processEvents()
        sys.exit(code)
    sys.exit(main())
