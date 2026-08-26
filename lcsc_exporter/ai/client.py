"""OpenAI 兼容大模型客户端（仅用标准库，零依赖）。

默认走阿里云百炼（DashScope）兼容端点，也兼容 DeepSeek 官方及任何
OpenAI 协议的端点——Base URL / Model / Key 均可在界面里改。

DashScope 兼容模式文档: https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
DeepSeek 官方文档:     https://api-docs.deepseek.com/zh-cn/
  POST {base_url}/chat/completions
  Header: Authorization: Bearer <key>
  Body:   {"model": "...", "messages": [...], "stream": false}
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

# 预置端点（界面下拉，也可手填其他 OpenAI 兼容地址）
PRESETS = {
    "阿里云百炼（qwen-plus）": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "阿里云百炼（deepseek-v3）": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1", "deepseek-v3"),
    "DeepSeek 官方（deepseek-chat）": (
        "https://api.deepseek.com", "deepseek-chat"),
}

DEFAULT_BASE_URL = PRESETS["阿里云百炼（qwen-plus）"][0]
DEFAULT_MODEL = PRESETS["阿里云百炼（qwen-plus）"][1]


class AIError(Exception):
    """对用户友好的错误（message 可直接显示在界面上）。"""


def _friendly_http_error(code: int, detail: str) -> str:
    base = {
        400: "请求参数错误",
        401: "API Key 无效或已过期，请检查设置",
        403: "没有权限访问该模型，请到控制台开通",
        404: "接口或模型不存在，请检查 Base URL / Model",
        429: "请求过快或超出限额，请稍后再试",
    }.get(code)
    if base is None:
        base = "服务端开小差了，请稍后重试" if code >= 500 else f"HTTP {code}"
    return base + (f"（{detail}）" if detail else "")


class ChatClient:
    """OpenAI 兼容聊天客户端。"""

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL, timeout: float = 120.0):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL
        self.timeout = timeout

    def chat(self, messages: list[dict]) -> str:
        """发送完整对话历史，返回助手回复文本。"""
        if not self.api_key:
            raise AIError("未设置 API Key——请先在上方粘贴 key 并保存")
        body = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = json.loads(e.read().decode("utf-8"))["error"]["message"]
            except Exception:  # noqa: BLE001 — 错误详情拿不到就算了
                pass
            raise AIError(_friendly_http_error(e.code, detail)) from None
        except urllib.error.URLError as e:
            raise AIError(f"网络连接失败：{e.reason}") from None
        except TimeoutError:
            raise AIError("请求超时，请检查网络后重试") from None
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIError("返回格式异常，未取到回复内容") from None
