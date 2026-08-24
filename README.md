# LCSC 元件一键导出工具

输入**立创商城（LCSC）元件编号**，**选择目标 EDA**，一键直出可直接导入的库文件——不需要再用别的工具转换：

| 导出目标 | 产物 | 3D 模型 |
|----------|------|---------|
| **Altium Designer** | `.SchLib` + `.PcbLib`（+ 独立 `.step`） | **内嵌**在 `.PcbLib` 里 |
| **KiCad** | `.kicad_sym` + `{型号}.pretty/*.kicad_mod` | **绑定**在 `.kicad_mod` 旁（同目录 STEP 引用） |

## 特点

- **GUI 操作**：输入编号（单个或批量）→ 选目标 → 点一下 → 产物开箱即用。
- **Altium/KiCad 双直出**：选哪个出哪个，KiCad 由内置 EasyEDA→KiCad 转换器生成，无需外部工具。
- **3D 绑定封装库**：AD 版 STEP 内嵌进 `.PcbLib`；KiCad 版 STEP 与 `.kicad_mod` 同目录自动关联。
- **3D 无底座**：STEP 直接采用立创标准库原生模型，原点 = 元件中心、z=0 = PCB 面。
- **批量支持**：多个编号用空格/逗号/换行分隔，一次性导出。

## 内核与开源归属

本工具的 GUI（PySide6 界面、批量/输出管理）与 **KiCad 转换器**（`lcsc_exporter/convert/`）是自研部分；**立创数据抓取 + Altium `.SchLib` / `.PcbLib` / STEP 生成**的内核是开源工具 **npnp**：

| 项 | 说明 |
|----|------|
| 名称 | npnp（"Normalize Pin Net Pad"） |
| 作者 | **linkyourbin** |
| 实现 | 纯 Rust |
| 仓库 | <https://github.com/yycx2016/npnp>（同 <https://github.com/linkyourbin/npnp>） |
| 许可证 | **Apache-2.0** |

- 本工具内置 `npnp.exe`（v1.0.2，位于 `.tools/bin/`），以**子进程**方式调用其 `export-schlib` / `export-pcblib` / `download-step` / `download-obj` / `export-source` / `bundle` 子命令。
- 分发本工具时请**保留 npnp 的 Apache-2.0 归属**（见仓库 LICENSE）。GUI 壳与 KiCad 转换器代码可自由使用。

## 快速开始

> **全新电脑首次使用**？本工具自包含（只需装 Python）——按 `使用手册.md` 的「部署到一台新电脑」3 步：装 Python → 拷贝整个文件夹 → 双击运行。

```powershell
python -m lcsc_exporter.app
```

或双击工作区根目录的 `lcsc2altium_gui.pyw`（无控制台窗口）。

界面操作：输入 LCSC 编号 → 选输出目录 → **下拉选择导出目标**（默认 Altium Designer）→ 点"开始导出" → 产物在 `out/{型号}/`（目录按元件型号命名，如 `out/STM32F103C8T6/`）。

## 详细文档

- 安装、完整使用步骤、输出说明、常见问题：见 **`使用手册.md`**
