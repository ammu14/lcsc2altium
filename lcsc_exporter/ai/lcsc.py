"""立创 EDA 库型号核验：把 AI 推荐的型号拿到立创搜一遍，只信真实存在的。

用 npnp 同款公开端点（GET 无需登录）:
  https://pro.lceda.cn/api/szlcsc/eda/product/list?wd=<关键词>
返回 result[]: {display_title(型号名), product_code(C编号), title(描述), ...}
注意 display_title 常带 "_C6186" 后缀，比较前先剥掉。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

SEARCH_API = "https://pro.lceda.cn/api/szlcsc/eda/product/list?wd="

# 纯封装/位号前缀的 token 不是型号（SOT-23、SOP-8、TO-220……）
_PKG_RE = re.compile(
    r"^(SOT|SOP|SOIC|SSOP|TSSOP|MSOP|QFN|QFP|LQFP|TQFP|BGA|DIP|DFN|SOD|TO|SMA|SMB|SMC|DO)"
    r"[-]?\d[\d\-]*$", re.I)
# 纯数值+单位（3.3V、300mA、10uF……）
_UNIT_RE = re.compile(
    r"^\d+(\.\d+)?(V|A|mA|uA|nA|W|mW|Hz|kHz|MHz|GHz|nF|uF|pF|mH|uH|nH|R|K|M|S|ms|us|ns|%)$", re.I)
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{2,29}")
_BOLD_RE = re.compile(r"\*\*([A-Za-z0-9][A-Za-z0-9._\-*]{2,29})\*\*")


def _norm(s: str) -> str:
    return re.sub(r"[-_.\s]", "", s).upper()


def extract_candidates(text: str, limit: int = 8) -> list[str]:
    """从 AI 回复里抽出疑似型号（MPN）的 token，优先取 **加粗** 的。"""
    ordered: list[str] = []
    bold = [t.strip("*") for t in _BOLD_RE.findall(text)]
    for tok in bold + _TOKEN_RE.findall(text):
        if len(tok) < 4:
            continue
        if not any(c.isdigit() for c in tok):      # 必须含数字
            continue
        if not any(c.isalpha() for c in tok):      # 必须含字母
            continue
        if _PKG_RE.match(tok) or _UNIT_RE.match(tok):
            continue
        if tok.upper() in ("MPN", "LCSC", "EDA", "PCB", "BOM"):
            continue
        if tok not in ordered:
            ordered.append(tok)
        if len(ordered) >= limit:
            break
    return ordered


def search(keyword: str, timeout: float = 10.0) -> list[dict]:
    url = SEARCH_API + urllib.parse.quote(keyword)
    req = urllib.request.Request(url, headers={"User-Agent": "lcsc2altium/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("result") or []


def verify(mpn: str, timeout: float = 10.0) -> dict:
    """核验单个型号。返回 {query, found, mpn?, code?, desc?, error?}。

    found: True=立创有, False=没有, None=查询失败（网络问题，不算不存在）。
    """
    try:
        results = search(mpn, timeout)
    except Exception as e:  # noqa: BLE001 — 网络问题如实上报
        return {"query": mpn, "found": None, "error": f"{type(e).__name__}: {e}"}
    nq = _norm(mpn)
    for r in results:
        title = str(r.get("display_title") or "")
        base = re.sub(r"_C\d+$", "", title)      # 剥掉 "_C6186" 后缀
        nt = _norm(base)
        if nt and (nt == nq or nt.startswith(nq) or nq.startswith(nt)):
            return {"query": mpn, "found": True, "mpn": base,
                    "code": str(r.get("product_code") or ""),
                    "desc": str(r.get("title") or "")[:60]}
    return {"query": mpn, "found": False}
