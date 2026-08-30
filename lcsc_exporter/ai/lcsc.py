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


# AI 回复里的全角符号会打断 token（如 MP2307－LF），先归一成半角
_FULLWIDTH = str.maketrans("－—–／．：；（）", "---/.::()")


def extract_candidates(text: str, limit: int = 8) -> list[str]:
    """从 AI 回复里抽出疑似型号（MPN）的 token，优先取 **加粗** 的。"""
    text = text.translate(_FULLWIDTH)
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


def _query_variants(mpn: str) -> list[str]:
    """为查询生成逐步放宽的关键词变体。

    AI 给的型号可能带包装/环保后缀（-LF-Z、/NOPB、-TR）或是完整料号，
    立创 EDA 的 wd= 搜索对这些敏感，所以逐层剥后缀重试：
      MP2307DN-LF-Z → MP2307DN-LF → MP2307DN → MP2307
    """
    out = [mpn]
    cur = mpn
    while True:
        nxt = re.sub(r"[-/][A-Za-z0-9.]+$", "", cur)   # 剥最后一段 -xx 或 /xx
        if nxt == cur:
            break
        cur = nxt
        out.append(cur)
    # 再补一个"截到最后一个数字"的基型号变体：TPS5430DDAR → TPS5430
    base = re.sub(r"[A-Za-z]+$", "", out[-1])
    if base != out[-1] and len(base) >= 4:
        out.append(base)
    seen, variants = set(), []
    for v in out:
        if len(v) >= 4 and v not in seen:
            seen.add(v)
            variants.append(v)
    return variants


def _match_score(query_norm: str, title_norm: str) -> int:
    """归一化后的匹配强度：3=完全相等 2=互为前缀 1=互相包含 0=不像。"""
    if not title_norm or not query_norm:
        return 0
    if title_norm == query_norm:
        return 3
    if title_norm.startswith(query_norm) or query_norm.startswith(title_norm):
        return 2
    if query_norm in title_norm or title_norm in query_norm:
        return 1
    return 0


def verify(mpn: str, timeout: float = 10.0, with_mall: bool = True) -> dict:
    """核验单个型号。

    返回 {query, found, mpn?, code?, desc?, manufacturer?, footprint?,
          basic?, datasheet?, stock?, price?, hints?, error?}
    found: True=EDA 库有, False=EDA 库没有（商城可能有售但无库可导出）,
           None=查询失败（网络问题，不算不存在）。
    """
    # 1) 多关键词重试，汇拢所有候选
    pool: dict[str, dict] = {}
    for kw in _query_variants(mpn):
        try:
            for r in search(kw, timeout):
                code = str(r.get("product_code") or id(r))
                pool.setdefault(code, r)
        except Exception as e:  # noqa: BLE001 — 网络问题如实上报
            return {"query": mpn, "found": None,
                    "error": f"{type(e).__name__}: {e}"}

    # 2) 打分排序：精确 > 前缀 > 包含；同分取标题更短者（更贴近基型号，
    #    天然把 MS/TP/HS 前缀的仿制料排到原厂料后面）
    nq = _norm(mpn)
    scored = []
    for r in pool.values():
        base = re.sub(r"_C\d+$", "", str(r.get("display_title") or ""))
        s = _match_score(nq, _norm(base))
        if s:
            scored.append((-s, len(base), base, r))
    scored.sort(key=lambda t: (t[0], t[1]))

    if scored:
        _, _, base, r = scored[0]
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

    # 3) 没找到：附上 API 返回的最接近候选，供用户人工确认
    hints = [re.sub(r"_C\d+$", "", str(r.get("display_title") or ""))
             for r in list(pool.values())[:3]]
    return {"query": mpn, "found": False,
            "hints": [h for h in hints if h]}
