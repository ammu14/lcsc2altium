"""lcsc_exporter — 立创商城元件一键导出工具（GUI 套 npnp 皮）。

输入 LCSC 元件编号，导出：
  - Altium 原理图库 .SchLib
  - Altium PCB 封装库 .PcbLib（可嵌入 STEP 3D 模型）
  - 3D STEP（标准库原生，无底座）

实现：GUI（PySide6/PyQt）调用工作区内的 npnp（Rust，Apache-2.0）子命令
（export-schlib / export-pcblib / download-step）生成上述文件。

署名（Apache-2.0）：
  - yycx2016/npnp  https://github.com/yycx2016/npnp
"""

__version__ = "0.2.0"
