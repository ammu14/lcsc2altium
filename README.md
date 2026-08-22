# LCSC 元件一键导出工具

输入**立创商城（LCSC）元件编号**，一键导出 Altium Designer 可用的三件套：

| 文件 | 说明 |
|------|------|
| `.SchLib` | Altium **原理图库**（符号 + 引脚 + 参数元数据） |
| `.PcbLib` | Altium **PCB 封装库**（焊盘/丝印/阻焊/钢网/机械层，内嵌 3D 模型） |
| `.step` | **3D 封装 STEP**（立创标准库原生，无底座，单位 mm） |

## 特点

- **GUI 操作**：输入编号（单个或批量）→ 点一下 → 自动抓取并生成全部文件。
- **Altium 原生格式**：`.SchLib` / `.PcbLib` 为 Altium Designer 二进制格式，导入即用。
- **3D 无底座**：STEP 直接采用立创标准库原生模型，原点 = 元件中心、z=0 = PCB 面，可直接装配仿真。
- **批量支持**：多个编号用空格/逗号/换行分隔，一次性导出。

## 内核与开源归属

本工具的 GUI（PySide6 界面、批量/输出管理）是自研的**薄壳**；真正完成**立创数据抓取 + Altium `.SchLib` / `.PcbLib` / STEP 生成**的内核，是开源工具 **npnp**：

| 项 | 说明 |
|----|------|
| 名称 | npnp（"Normalize Pin Net Pad"） |
| 作者 | **yycx2016** |
| 实现 | 纯 Rust |
| 仓库 | <https://github.com/yycx2016/npnp> |
| 许可证 | **Apache-2.0** |

- 本工具内置 `npnp.exe`（v1.0.2，位于 `.tools/bin/`），以**子进程**方式调用其 `export-schlib` / `export-pcblib` / `download-step` 子命令。
- 分发本工具时请**保留 npnp 的 Apache-2.0 归属**（见仓库 LICENSE）。本 GUI 壳代码可自由使用，但 npnp 内核的版权与许可证归原作者所有。

## 快速开始

> **全新电脑首次使用**？本工具自包含（只需装 Python）——按 `使用手册.md` 的「部署到一台新电脑」3 步：装 Python → 拷贝整个文件夹 → 双击运行。

```powershell
python -m lcsc_exporter.app
```

或双击工作区根目录的 `lcsc2altium_gui.pyw`（无控制台窗口）。

界面操作：输入 LCSC 编号 → 选输出目录 → 勾选"下载 3D 模型"/"强制重新抓取"（可选）→ 点"开始导出" → 产物在 `out/{编号}/`。

## 详细文档

- 安装、完整使用步骤、输出说明、常见问题：见 **`使用手册.md`**
