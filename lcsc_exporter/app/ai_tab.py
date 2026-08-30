"""AI 助手页签：选型对话（OpenAI 兼容端点，默认阿里云百炼 qwen-plus）。

设计要点:
  - 系统提示词把助手定位成「立创选型工程师」，用户描述需求 → AI 推荐型号
  - 聊天在 QThread 里跑，不阻塞界面
  - API Key/Base URL/Model 可配置，保存到 ai_config.json（.gitignore 已排除）
"""
from __future__ import annotations

import os
import sys

_TOOLS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".tools", "pylibs")
if os.path.isdir(_TOOLS) and _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from PySide6.QtCore import QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextBrowser, QVBoxLayout, QWidget,
)

from ..ai.client import PRESETS, ChatClient, AIError
from ..ai import config, lcsc


class _VerifyWorker(QThread):
    """后台逐个核验 AI 提到的型号在立创是否存在。"""
    done = Signal(list)   # list[verify() 结果 dict]

    def __init__(self, candidates: list[str], parent=None):
        super().__init__(parent)
        self._candidates = candidates

    def run(self):
        self.done.emit([lcsc.verify(mpn) for mpn in self._candidates])

SYSTEM_PROMPT = (
    "你是资深硬件工程师，帮助用户在立创商城（LCSC）选型。"
    "用户描述需求时：\n"
    "1) 推荐 2~4 个具体候选型号，只推荐立创商城大概率在售的常见现货型号；\n"
    "2) 每个候选型号的完整 MPN 用 **加粗** 单独标出（程序要据此自动核验立创库存）；\n"
    "3) 每个候选用一行给出关键参数（封装、供电、精度等）和推荐理由；\n"
    "4) 参数不足时，先问一个最关键的澄清问题再给推荐；\n"
    "5) 回答用简体中文，简洁，可用 Markdown 表格。"
)


class _ChatWorker(QThread):
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, messages: list[dict], parent=None):
        super().__init__(parent)
        self._messages = messages

    def run(self):
        try:
            client = ChatClient(config.get_api_key(),
                                config.get_base_url(), config.get_model())
            self.done.emit(client.chat(self._messages))
        except AIError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001 — UI 兜底
            self.failed.emit(f"意外错误: {e}")


class AIChatTab(QWidget):
    """AI 选型对话 + 立创库存核验。send_to_export 携带核验过的 C 编号串。"""
    send_to_export = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _ChatWorker | None = None
        self._verifier: _VerifyWorker | None = None
        self._history: list[dict] = []
        self._md_log = ""
        self._verified_codes: list[str] = []

        root = QVBoxLayout(self)

        # --- 配置行 ---
        cfg = QHBoxLayout()
        cfg.addWidget(QLabel("API Key:"))
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText(
            "用自己的 key（sk-...），没有就点右边「申请 Key」免费领")
        if config.get_api_key():
            self.key_edit.setText(config.get_api_key())
        cfg.addWidget(self.key_edit, 2)
        get_key_btn = QPushButton("申请 Key")
        get_key_btn.setToolTip("打开所选服务商的控制台，注册后免费创建 API Key")
        get_key_btn.clicked.connect(self._open_key_page)
        cfg.addWidget(get_key_btn)

        cfg.addWidget(QLabel("端点:"))
        self.preset_cb = QComboBox()
        self.preset_cb.setEditable(True)
        for label, (url, _model) in PRESETS.items():
            self.preset_cb.addItem(label, (url, _model))
        cur = config.get_base_url()
        idx = next((i for i in range(self.preset_cb.count())
                    if self.preset_cb.itemData(i)[0] == cur), -1)
        if idx >= 0:
            self.preset_cb.setCurrentIndex(idx)
        cfg.addWidget(self.preset_cb, 2)

        cfg.addWidget(QLabel("模型:"))
        self.model_edit = QLineEdit(config.get_model())
        self.model_edit.setMaximumWidth(160)
        cfg.addWidget(self.model_edit)

        save_btn = QPushButton("保存配置")
        save_btn.clicked.connect(self._save)
        cfg.addWidget(save_btn)
        root.addLayout(cfg)

        self.status_lbl = QLabel()
        root.addWidget(self.status_lbl)
        self._refresh_status()

        # --- 聊天显示 ---
        self.chat = QTextBrowser()
        # 数据手册等外链交给系统浏览器打开；QTextBrowser 自己导航 PDF
        # 会渲染失败变成一片空白（还会把聊天记录顶掉）
        self.chat.setOpenExternalLinks(True)
        root.addWidget(self.chat, 1)

        # --- 输入行 ---
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText(
            "描述你要的元件，如：3.3V LDO，SOT-23，低静态电流，给 3.7V 锂电用")
        self.input.returnPressed.connect(self._send)
        row.addWidget(self.input, 1)
        self.send_btn = QPushButton("发送")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        clear_btn = QPushButton("清空对话")
        clear_btn.clicked.connect(self._clear)
        row.addWidget(clear_btn)
        root.addLayout(row)

        # 核验后浮现的「填入导出框」按钮
        self.export_btn = QPushButton()
        self.export_btn.setVisible(False)
        self.export_btn.setStyleSheet(
            "QPushButton { background:#1e88e5; color:white; font-weight:bold; padding:4px }")
        self.export_btn.clicked.connect(self._send_verified)
        root.addWidget(self.export_btn)

        self._append("系统",
                     "我是立创选型助手。描述你需要的元件特征，我来推荐型号，"
                     "并**自动到立创核验是否真实存在**（只信核验通过的）。\n"
                     "核验通过后点下方按钮，一键把编号填进「元件导出」页签。")

    def _refresh_status(self):
        mk = config.masked_key()
        self.status_lbl.setText(
            f"当前: {config.get_base_url()} | {config.get_model()} | "
            + (f"Key 已配置（{mk}）" if mk
               else "⚠ 未配置 Key（本工具不含任何 Key，请使用自己的）"))
        self.status_lbl.setStyleSheet(
            "color: gray" if mk else "color: #c0392b")

    def _open_key_page(self):
        """按所选端点打开对应服务商的 Key 申请页。"""
        preset = self.preset_cb.currentData()
        base = (preset[0] if preset else self.preset_cb.currentText()).lower()
        if "dashscope" in base or "aliyun" in base:
            url = "https://bailian.console.aliyun.com/?apiKey=1#/api-key"
        elif "deepseek" in base:
            url = "https://platform.deepseek.com/api_keys"
        else:
            url = "https://platform.deepseek.com/api_keys"
        QDesktopServices.openUrl(QUrl(url))

    def _save(self):
        preset = self.preset_cb.currentData()
        if preset:                      # 选了预置端点：URL 和模型一起带出来
            base_url, model = preset
            self.model_edit.setText(model)
        else:                           # 手填的自定义端点
            base_url = self.preset_cb.currentText().strip()
            model = self.model_edit.text()
        config.save_settings(self.key_edit.text(), base_url, model)
        self._refresh_status()
        self._append("系统", "配置已保存。")

    def _clear(self):
        self._history.clear()
        self._md_log = ""
        self.chat.setMarkdown("")
        self._append("系统", "对话已清空。")

    def _append(self, who: str, text: str):
        if who == "你":
            safe = text.replace("&", "&amp;").replace("<", "&lt;")
            self._md_log += f"\n\n> 🧑 **你**：{safe}\n"
        elif who == "AI":
            self._md_log += f"\n\n🤖 **助手**：\n\n{text}\n"
        else:
            self._md_log += f"\n\n*— {text} —*\n"
        self.chat.setMarkdown(self._md_log)
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _send(self):
        text = self.input.text().strip()
        if not text or (self._worker and self._worker.isRunning()):
            return
        self.input.clear()
        self._append("你", text)
        self._history.append({"role": "user", "content": text})
        messages = ([{"role": "system", "content": SYSTEM_PROMPT}]
                    + self._history[-20:])   # 控制上下文长度
        self.send_btn.setEnabled(False)
        self.send_btn.setText("思考中…")
        self._worker = _ChatWorker(messages, parent=self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _finish(self):
        self.send_btn.setEnabled(True)
        self.send_btn.setText("发送")

    def _on_done(self, reply: str):
        self._history.append({"role": "assistant", "content": reply})
        self._append("AI", reply)
        self._finish()
        self._start_verify(reply)

    def _on_failed(self, err: str):
        self._append("系统", f"调用失败：{err}")
        self._finish()

    # ---------- 立创核验 ----------

    def _start_verify(self, reply: str):
        candidates = lcsc.extract_candidates(reply)
        if not candidates:
            return
        self._append("系统", f"🔍 正在立创核验 {len(candidates)} 个候选型号："
                             + "、".join(candidates) + " …")
        self._verifier = _VerifyWorker(candidates, parent=self)
        self._verifier.done.connect(self._on_verified)
        self._verifier.start()

    def _on_verified(self, results: list[dict]):
        ok = [r for r in results if r.get("found") is True]
        no = [r for r in results if r.get("found") is False]
        err = [r for r in results if r.get("found") is None]
        lines = ["**📋 立创核验结果**：", ""]
        for r in ok:
            parts = [f"**{r['mpn']}**（{r['code']}）"]
            if r.get("manufacturer"):
                parts.append(r["manufacturer"])
            if r.get("footprint"):
                parts.append(r["footprint"])
            if r.get("basic"):
                parts.append("基础库·贴片免换料费")
            if r.get("stock") is not None:
                parts.append(f"库存 {r['stock']:,}")
            if r.get("price") is not None:
                parts.append(f"¥{r['price']:g}")
            line = "- ✅ " + " · ".join(parts)
            if r.get("datasheet"):
                line += f"　[📄 数据手册]({r['datasheet']})"
            lines.append(line)
        for r in no:
            hints = "、".join(r.get("hints") or [])
            if hints:
                lines.append(f"- ❌ {r['query']} —— 立创 EDA 库未找到该型号"
                             f"（最接近：{hints}，请确认是否笔误）")
            else:
                lines.append(f"- ❌ {r['query']} —— 立创 EDA 库未收录"
                             "（商城可能有售，但无封装库可供导出）")
        for r in err:
            lines.append(f"- ⚠ {r['query']} —— 核验失败（{r['error']}），请自行到立创搜索确认")
        self._md_log += "\n\n" + "\n".join(lines) + "\n"
        self.chat.setMarkdown(self._md_log)
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())
        if ok:
            self._verified_codes = [r["code"] for r in ok if r.get("code")]
            self.export_btn.setText(
                f"⬇ 把 {len(self._verified_codes)} 个已核验编号填入「元件导出」")
            self.export_btn.setVisible(bool(self._verified_codes))

    def _send_verified(self):
        if self._verified_codes:
            self.send_to_export.emit(" ".join(self._verified_codes))
