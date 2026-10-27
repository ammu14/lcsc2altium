"""LCSC 元件 Altium 导出器 — GUI 启动器（双击运行，无控制台）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _show_fatal(exc: Exception) -> None:
    """pythonw 没有控制台，启动失败必须弹窗，不能静默退出。"""
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        None,
        "LCSC 元件导出器启动失败。\n\n"
        "请使用 64 位 Python 3.10 - 3.14，并确认安装目录中的 .tools 完整。\n\n"
        f"详细信息：{exc}",
        "LCSC 元件导出器",
        0x10,
    )


try:
    from lcsc_exporter.app.gui import main  # noqa: E402
except Exception as exc:  # noqa: BLE001 — 给无控制台的 pythonw 用户可见错误
    if __name__ != "__main__" or os.environ.get("LCSC2ALTIUM_SELFTEST") == "1":
        raise
    _show_fatal(exc)
    sys.exit(1)


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
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 — pythonw 下弹窗而非无声退出
        _show_fatal(exc)
        sys.exit(1)
