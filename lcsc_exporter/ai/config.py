"""AI 配置持久化：存工作区 ai_config.json（已在 .gitignore，绝不入库）。

字段: api_key / base_url / model
优先级: 环境变量 DSH_AI_API_KEY > 配置文件；base_url/model 也有界面可改。
"""
from __future__ import annotations

import json
import os

from .client import DEFAULT_BASE_URL, DEFAULT_MODEL

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ai_config.json")


def load_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_api_key() -> str:
    return os.environ.get("DSH_AI_API_KEY", "").strip() \
        or str(load_config().get("api_key", "")).strip()


def get_base_url() -> str:
    return str(load_config().get("base_url", "")).strip() or DEFAULT_BASE_URL


def get_model() -> str:
    return str(load_config().get("model", "")).strip() or DEFAULT_MODEL


def save_settings(api_key: str, base_url: str, model: str) -> None:
    save_config({"api_key": api_key.strip(),
                 "base_url": base_url.strip(), "model": model.strip()})


def masked_key() -> str:
    """界面显示用的脱敏 key，如 sk-****e30b；未配置返回空串。"""
    k = get_api_key()
    if not k:
        return ""
    return f"{k[:3]}****{k[-4:]}" if len(k) > 7 else "****"
