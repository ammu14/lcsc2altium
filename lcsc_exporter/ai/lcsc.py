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


_MALL_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.szlcsc.com/",
}


def _fetch_mall_info(datasheet_url: str, timeout: float = 8.0) -> dict:
    """从立创商城详情页抓 库存/单价（EDA API 没有这两个字段）。

    datasheet_url 形如 https://item.szlcsc.com/datasheet/{MPN}/{数字id}.html；
    详情页 HTML 内嵌 "stockNumber":N 和 JSON-LD "price":X。失败静默返回 {}。
    """
    m = re.search(r"item\.szlcsc\.com/(?:datasheet/[^/]+/)?(\d+)\.html",
                  datasheet_url or "")
    if not m:
        return {}
    try:
        req = urllib.request.Request(
            f"https://item.szlcsc.com/{m.group(1)}.html", headers=_MALL_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 — 商城页失败不阻塞核验主流程
        return {}
    info: dict = {}
    ms = re.search(r'"stockNumber":\s*(\d+)', body)
    if ms:
        info["stock"] = int(ms.group(1))
    mp = re.search(r'"price":\s*([\d.]+)\s*,\s*"priceCurrency":\s*"CNY"', body)
    if not mp:  # 有的页面 price 在 currency 后面
        mp = re.search(r'"priceCurrency":\s*"CNY"[^}]*?"price":\s*([\d.]+)', body)
    if mp:
        info["price"] = float(mp.group(1))
    return info


def verify(mpn: str, timeout: float = 10.0, with_mall: bool = True) -> dict:
    """核验单个型号。

    返回 {query, found, mpn?, code?, desc?, manufacturer?, footprint?,
          basic?, datasheet?, stock?, price?, error?}
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
            attrs = r.get("attributes") or {}
            out = {"query": mpn, "found": True, "mpn": base,
                   "code": str(r.get("product_code") or ""),
                   "desc": str(r.get("title") or "")[:60],
                   "manufacturer": str(attrs.get("Manufacturer") or ""),
                   "footprint": str(attrs.get("Supplier Footprint") or ""),
                   "basic": str(attrs.get("JLCPCB Part Class") or "")
                            .lower().startswith("basic"),
                   "datasheet": str(attrs.get("Datasheet") or "")}
            if with_mall:
                out.update(_fetch_mall_info(out["datasheet"], timeout=8.0))
            return out
    return {"query": mpn, "found": False}
