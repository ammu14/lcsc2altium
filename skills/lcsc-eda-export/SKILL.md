---
name: lcsc-eda-export
description: 立创商城（LCSC）元件编号 → 各 EDA（Altium/KiCad）可直接导入的符号库+封装库+3D 的完整实现方法。涵盖 LCEDA API 数据流、EasyEDA 源格式逆向结论、KiCad 6+ 库文件生成、npnp 内核用法、GUI 集成模式与全部踩坑记录。当需要为本仓库扩展导出格式、修复转换问题、或在其他项目复现 LCSC→EDA 转换时使用。
---

# LCSC → EDA 库导出 实施手册

本 skill 沉淀 `lcsc2altium` 项目的全部实现知识。核心结论：**数据抓取/AD 生成用 npnp 内核（子进程），KiCad 用内置转换器（EasyEDA 源 → KiCad 原生格式），GUI 只做目标选择与调度**。

## 1. 总体架构

```
用户输入 LCSC 编号 (如 C25161)
  └─ GUI (PySide6, lcsc_exporter/app/gui.py)
       ├─ 目标 = Altium:  npnp export-schlib + export-pcblib + download-step
       │                  → {型号}.SchLib + {封装}.PcbLib(3D已内嵌) + {封装}.step
       └─ 目标 = KiCad:   npnp export-source + download-step
                          → 内置转换器 (lcsc_exporter/convert/)
                          → {型号}.kicad_sym
                          → {型号}.pretty/{封装}.kicad_mod + {封装}.step(同目录绑定)
       中间产物 (*_easyeda.json) 转换完即删；目录按 MPN 命名（out/{型号}/）
```

**关键设计决策**：
- npnp 以**子进程**调用（`.tools/bin/npnp.exe`），不链接不改源码 → 许可清晰（npnp = Apache-2.0，作者 linkyourbin，仓库 github.com/yycx2016/npnp ≡ github.com/linkyourbin/npnp）
- KiCad 转换器**自研**（KiCad 格式是公开 S 表达式），不依赖 easyeda2kicad 等外部工具 → 零安装、开箱即用
- 界面是**目标 EDA 下拉单选**（不要给用户"源文件/格式复选框"——用户要的是"选 AD 出 AD、选 KiCad 出 KiCad"）

## 2. LCEDA API 数据流（npnp 用的端点，逆向确认）

```
搜索:  GET https://pro.lceda.cn/api/szlcsc/eda/product/list?wd=<关键词>
       → result[]: {display_title, product_code, attributes{Symbol,Footprint,"3D Model"},
                    symbol.uuid, footprint.uuid, footprint.display_title}
详情:  GET https://pro.lceda.cn/api/components/{uuid}?uuid={uuid}
       → {code:0, result:{dataStr, model_3d.uri, ...}}   dataStr = EasyEDA 源(字符串)
3D:    GET https://modules.lceda.cn/qAxj6KHrDKw4blvCG8QJPs7Y/{model_uuid}   (STEP)
       GET https://modules.lceda.cn/3dmodel/{uuid}                          (OBJ)
重试:  3 次, 退避 250ms×2ⁿ; 超时/连接错误/408/425/429/5xx 可重试
```

本机网络注意：**沙箱内 schannel 凭据被禁 → git/Invoke-WebRequest 访问 https 会失败**；npnp（Rust rustls）不受影响；git 操作提权到 danger-full-access 后正常。GitHub SSH(22端口) 网络层被拒，只能走 HTTPS。

## 3. EasyEDA 源格式（dataStr）逆向结论

`result.dataStr` 是字符串，内容为**每行一个 JSON 数组**的记录流（`["DOCTYPE","FOOTPRINT","1.8"]` 开头）。

### 单位（极易搞错）
| 源类型 | 1 单位 = | 换算到 mm |
|--------|---------|-----------|
| 符号 | **10 mil** | × 0.254 |
| 封装 | **1 mil** | × 0.0254 |

坐标系：符号 Y 轴向上（与 Altium/KiCad 符号一致）；封装 Y 轴向下（与 KiCad 封装一致）。**均无需翻转**。

### 符号记录
- `["PIN", id, ?, null, x, y, length, rotation, ...]` — (x,y) 是**连接点**（外端），rotation 是**从连接点指向本体**的方向（度）
- `["ATTR", 自身id, 宿主id, key, value, visible?, showText?, x, y, rot, 字体, ?]` — 通过**宿主id**关联：`NAME`/`NUMBER`/`Pin Type` 挂在 PIN 的 id 上；`Symbol`(元件名)/`Designator`(位号前缀如 R?) 是顶层属性
- `["RECT", id, x1, y1, x2, y2, ...]`、`["ELLIPSE", id, cx, cy, rx, ry, ...]`
- Pin Type 映射 KiCad：Input→input, Output→output, I/O→bidirectional, Power→power_in, Undefined→passive

### 封装记录
- `["LAYER", id, "名称", ...]` — 层映射见下表
- `["PAD", id, ?, ?, layer, number, x, y, rotation, null, [形状, w, h], [], ...]`
  - **焊盘朝向直接编码在形状宽高里**（左/右列焊盘 w×h 互换），rotation 通常为 0；不要看后面的 90/0 字段（是冗余提示）
  - 形状：`RECT`/`OVAL`（椭圆长条→KiCad oval）/圆形/多边形
- `["POLY", id, ?, ?, layer, width, [x1,y1,"L",x2,y2,...], ?]` — ⚠️ **点列表里混着 "L" 字符串段标记**，解析时先过滤掉非数值再两两配对，否则坐标全错位
- `["FILL", id, ?, ?, layer, width, ?, [[形状...],...], ?]` — 内部形状是 `["CIRCLE",cx,cy,r]` 或 `["RECT",...]` 或裸点列表（裸点列表=敷铜区，跳过）
- `["ATTR", id, 0, "", layer, null, null, "Footprint", 封装名, x, y, ...]` — 封装名在此

### 层映射（EasyEDA → KiCad）
| EasyEDA | 含义 | KiCad |
|---------|------|-------|
| 1 TOP / 2 BOTTOM | 铜层 | F.Cu / B.Cu（焊盘另加 F.Paste+F.Mask） |
| 3 / 4 | 丝印 | F.SilkS / B.SilkS |
| 48 COMPONENT_SHAPE | 实体外形 | F.Fab |
| 49 COMPONENT_MARKING | 丝印标记 | F.SilkS |
| 13 DOCUMENT | 文档层 | Dwgs.User（或跳过） |
| 50 PIN_SOLDERING / 52 COMPONENT_MODEL | 焊接/模型内部层 | **跳过** |

## 4. KiCad 6+ 输出约定（开箱即用的关键）

### 目录结构（封装库 = 一个 `.pretty` 目录）
```
{型号}.kicad_sym                        ← 符号库（单个文件即库）
{型号}.pretty/                          ← 封装库（目录即库）
    {封装}.kicad_mod
    {封装}.step                         ← 3D 与封装同目录
```

### 3D 绑定
`.kicad_mod` 内写 `(model "{封装}.step" (offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))`，**裸文件名**，STEP 与 .kicad_mod 同目录 → KiCad 按封装文件相对路径解析，无需设环境变量。（KiCad 不像 AD 把 3D 嵌入库文件，引用即绑定。）

### 符号↔封装关联
符号 `Footprint` 属性写 `"{型号}:{封装名}"`。用户把 `.pretty` 添加为封装库时**默认昵称=目录名**，自动对上。

### 格式骨架
```lisp
(kicad_symbol_lib (version 20221018) (generator "lcsc2altium")
  (symbol "X" (in_bom yes) (on_board yes)
    (property "Reference" "R?" (at 0 0 0) (effects (font (size 1.27 1.27))))
    (property "Value" "X" ...) (property "Footprint" "X:FP" (at 0 0 0) (effects ... hide))
    (symbol "X_0_1" (rectangle (start ..) (end ..) (stroke (width 0.254)(type default)) (fill (type outline))))
    (symbol "X_1_1" (pin passive line (at x y 角度) (length 2.54)
                      (name "VCC" (effects ...)) (number "1" (effects ...))))))

(footprint "FP" (version 20221018) (generator "lcsc2altium")
  (layer "F.Cu") (attr smd)
  (fp_text reference "REF**" ...) (fp_text value "FP" ...)
  (fp_line (start ..) (end ..) (stroke (width 0.12)(type solid)) (layer "F.SilkS"))
  (pad "1" smd rect (at x y 0) (size w h) (layers "F.Cu" "F.Paste" "F.Mask"))
  (model "FP.step" ...))
```
- KiCad 引脚 `(at x y angle)` 语义与 EasyEDA 一致（角度=连接点指向本体方向）→ **直接抄角度**
- SMD 焊盘层组：`"F.Cu" "F.Paste" "F.Mask"`；通孔：`"*.Cu" "*.Mask"` + `(drill d)`
- 数值格式：mm，最多 4 位小数去尾零

## 5. Altium 侧要点（npnp 直出，仅作背景）

- `.SchLib`/`.PcbLib` = **CFBF (OLE2) 复合文档**，major version 4 = 4096 字节扇区；<4096 的流必须走 mini-stream；目录项须按 (名称长度, 不区分大小写名称) BST 排序，否则 ole32 拒绝打开
- **AD16 及更早版本打不开 v4 容器**（只认 v3/512B 扇区）→ `convert/cfbf.py` 把 npnp 产物无损重写为 v3：读 v4 全部流（含嵌套 storage）→ 重建 v3（目录/miniFAT/miniStream/大流/FAT/DIFAT 布局，流数据逐字节不变）；验证 = 往返一致 + ole32 StgOpenStorage 可开
- 记录 = `4字节LE长度 + |KEY=VALUE|...|` ASCII 文本；中文走 `%UTF8%` 前缀字段
- `.PcbLib` 的 `Library/Models/0` 流内嵌完整 STEP（~MB 级）→ AD 的"3D 绑定"是真内嵌
- 验证手段：Windows ole32 API（StgOpenStorageEx / OpenStream mode=STGM_SHARE_EXCLUSIVE=0x10）

## 6. GUI 集成模式（PySide6）

- `QThread` Worker 跑子进程，`Signal` 回传日志/进度/结果 → UI 不卡
- `subprocess.run(..., timeout=600, cwd=工作区)`，逐行回显 stdout/stderr
- 结果表：编号 | MPN | 产物文件 | 状态（告警不阻断：单格式失败只记 warning，全空才算失败）
- 目录命名：导出时先落 `out/{编号}/`，完成后按产物文件名推断 MPN 重命名为 `out/{型号}/`；非法字符→`_`，冲突→`{型号}_{编号}`
- Qt 绑定自动适配 PySide6→PyQt6→PyQt5；第三方库放 `.tools/pylibs` 并插 sys.path

## 7. 踩坑记录（已踩过，勿再踩）

1. **EasyEDA POLY 点列表混有 "L" 字符串** — 必须过滤非数值再配对（否则丝印线全乱）
2. **PAD 的旋转不在后面的 90/0 字段** — 朝向编码在形状宽高里，rotation 取 idx8（通常为 0）
3. **符号/封装单位不同** — 10mil vs 1mil，错一个差 10 倍
4. **PowerShell 5.1 无三元运算符** `?:` — 用 if/else
5. **控制台 GBK** — Python 脚本加 `-X utf8`；写文件统一 UTF-8
6. **沙箱网络** — schannel 被禁时 git/HTTPS 全挂，提权 danger-full-access 可解；SSH 22 端口彻底不通
7. **改名防冲突** — 导出目录重命名要处理重名（回退 `{型号}_{编号}`）

## 8. 验证清单（改动后必跑）

```powershell
# 1. 转换器样本回归（tests/samples/ 有 0402 + STM32 两个 EasyEDA 源）
python -X utf8 -c "import sys, json; sys.path.insert(0,'.')
from lcsc_exporter.convert.kicad import convert_to_kicad
s=json.load(open('tests/samples/STM32F103C8T6_symbol_easyeda.json',encoding='utf-8'))
f=json.load(open('tests/samples/STM32F103C8T6_footprint_easyeda.json',encoding='utf-8'))
print(convert_to_kicad(s,f,'tests/out'))"

# 2. 坐标 sanity：0402 焊盘 ±0.433mm/0.566×0.54mm；LQFP48 焊盘 0.27×1.5mm @ 0.5mm 间距、本体 7×7mm
# 3. 端到端（真实联网）：
python -X utf8 -c "import sys; sys.path.insert(0,'.')
from lcsc_exporter.app.gui import ExportWorker
w=ExportWorker(['C25161'],'out_test','kicad',False); w.run()"

# 4. 离屏 GUI 构建：
$env:QT_QPA_PLATFORM='offscreen'; python -X utf8 -c "import sys; sys.path.insert(0,'.');sys.path.insert(0,'.tools/pylibs')
from lcsc_exporter.app.gui import MainWindow
from PySide6.QtWidgets import QApplication; app=QApplication([]); w=MainWindow(); print('OK')"
```

最终在真实 AD / KiCad 里导入验证由用户完成（本机无这两款软件）。

## 9. 已知边界（转换器 v1）

- 已覆盖：RECT/OVAL 焊盘、POLY 折线、FILL 圆/矩形、引脚（名/号/角度/电气类型）、文本
- 未覆盖：圆弧（ARC 段）、异形/多边形焊盘、通孔焊盘的钻孔提取、敷铜区、符号复杂图元（贝塞尔等）
- 遇到怪异封装出错时：把对应 LCSC 编号的 `*_easyeda.json` 源拿到手，按第 3 节格式对照补解析分支
