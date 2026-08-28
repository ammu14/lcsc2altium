"""启动时检查 GitHub 有没有新版本（读 latest Release，静默失败）。

返回 {"version": "1.2.0", "url": "https://github.com/.../releases/tag/..."}
没有 Release / 版本不新 / 网络失败 → 返回 None（绝不打扰用户）。
"""
from __future__ import annotations

import json
import re
import urllib.request

from .. import GITHUB_REPO, __version__

_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _parse_ver(s: str) -> tuple[int, ...] | None:
    m = re.match(r"^v?(\d+(?:\.\d+){0,3})$", (s or "").strip())
    if not m:
        return None
    return tuple(int(x) for x in m.group(1).split("."))


def check_newer(current: str = __version__, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(
            _API, headers={"User-Agent": f"lcsc2altium/{current}",
                           "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 — 没网/没 Release 都静默
        return None
    tag = str(data.get("tag_name") or "")
    new_v, cur_v = _parse_ver(tag), _parse_ver(current)
    if not new_v or not cur_v:
        return None
    # 补齐长度再比（1.2 == 1.2.0）
    n = max(len(new_v), len(cur_v))
    new_v += (0,) * (n - len(new_v))
    cur_v += (0,) * (n - len(cur_v))
    if new_v > cur_v:
        return {"version": tag.lstrip("v"),
                "url": str(data.get("html_url") or
                           f"https://github.com/{GITHUB_REPO}/releases")}
    return None
