"""거시경제 지표 — 시장 헤더용.

데이터 소스 우선순위:
  1. 네이버 finance (다중 셀렉터 시도)
  2. pykrx (지수만, 환율 X)
  3. 실패 시 None
"""
from __future__ import annotations

import re
import warnings
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


def _to_float(txt: str) -> float | None:
    if not txt:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", txt.replace(",", ""))
    try:
        return float(cleaned) if cleaned not in ("", "-", ".") else None
    except Exception:
        return None


# ────────────────────────────────────────────────
# 1. 네이버 지수 (KOSPI/KOSDAQ/KOSPI200)
# ────────────────────────────────────────────────
def _fetch_naver_index(symbol: str) -> dict | None:
    """네이버 지수 페이지 — 다중 셀렉터 시도."""
    url = f"https://finance.naver.com/sise/sise_index.naver?code={symbol}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")

        # 현재가 셀렉터 후보
        value = None
        for sel in ["#now_value", "em#now_value", "strong#now_value",
                    ".no_today .blind", ".today .no_today em",
                    "p.no_today em"]:
            el = soup.select_one(sel)
            if el:
                v = _to_float(el.get_text(strip=True))
                if v and v > 0:
                    value = v
                    break

        # 전일대비 (절대값)
        change = None
        for sel in ["#change_value_top", "em#change_value_top",
                    ".no_exday em:nth-of-type(1) .blind",
                    "p.no_exday em.no_up", "p.no_exday em.no_down",
                    ".no_exday em .blind"]:
            el = soup.select_one(sel)
            if el:
                c = _to_float(el.get_text(strip=True))
                if c is not None:
                    change = c
                    break

        # 등락률
        change_pct = None
        for sel in ["#change_rate_top", "em#change_rate_top",
                    ".no_exday em:nth-of-type(2) .blind",
                    ".no_exday em.no_up + em .blind",
                    ".no_exday em.no_down + em .blind"]:
            el = soup.select_one(sel)
            if el:
                p = _to_float(el.get_text(strip=True))
                if p is not None:
                    change_pct = p
                    break

        # 상승/하락 부호 결정 — 시세 헤더 영역(.no_exday 또는 .today)으로 한정
        # 페이지 전체에서 검색하면 푸터/광고 영역의 .down 등에 false-positive 발생
        head = (
            soup.select_one(".no_exday")
            or soup.select_one(".today")
            or soup.select_one(".rate_info")
            or soup
        )
        is_down = bool(head.select_one(".no_down, em.no_down, .down"))
        is_up = bool(head.select_one(".no_up, em.no_up, .up"))

        if value is None:
            return None

        if change is not None:
            if is_down and change > 0:
                change = -change
            elif is_up and change < 0:
                change = abs(change)
        if change_pct is not None:
            if is_down and change_pct > 0:
                change_pct = -change_pct
            elif is_up and change_pct < 0:
                change_pct = abs(change_pct)

        return {
            "value": value,
            "change": change or 0.0,
            "change_pct": change_pct or 0.0,
        }
    except Exception:
        return None


# ────────────────────────────────────────────────
# 2. pykrx fallback (지수만)
# ────────────────────────────────────────────────
PYKRX_INDEX_CODE = {
    "KOSPI":    "1001",
    "KOSDAQ":   "2001",
    "KPI200":   "1028",  # KOSPI200
}


def _fetch_pykrx_index(symbol: str) -> dict | None:
    """pykrx로 최근 2영업일 OHLCV → 현재가/등락 계산."""
    ticker = PYKRX_INDEX_CODE.get(symbol)
    if not ticker:
        return None
    try:
        from pykrx import stock
        today = datetime.now()
        start = (today - timedelta(days=10)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        df = stock.get_index_ohlcv_by_date(start, end, ticker)
        if df is None or df.empty or len(df) < 1:
            return None
        last_close = float(df["종가"].iloc[-1])
        if len(df) >= 2:
            prev_close = float(df["종가"].iloc[-2])
            change = last_close - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0
        else:
            change = 0.0
            change_pct = 0.0
        return {
            "value": last_close,
            "change": change,
            "change_pct": change_pct,
        }
    except Exception:
        return None


def _get_index(symbol: str) -> dict | None:
    """네이버 우선, 실패 시 pykrx."""
    v = _fetch_naver_index(symbol)
    # 네이버에서 가져왔으나 등락 정보가 0/None이면 pykrx로 보강
    if v and (v.get("change_pct") in (0.0, None) and v.get("change") in (0.0, None)):
        pk = _fetch_pykrx_index(symbol)
        if pk and pk.get("change_pct"):
            # 값은 네이버 것 유지, 등락만 pykrx
            v["change"] = pk["change"]
            v["change_pct"] = pk["change_pct"]
        return v
    if v:
        return v
    return _fetch_pykrx_index(symbol)


# ────────────────────────────────────────────────
# 3. 환율 (USD/KRW) — 네이버 marketindex
# ────────────────────────────────────────────────
def _fetch_naver_usdkrw() -> dict | None:
    url = "https://finance.naver.com/marketindex/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        # 환율 박스 — 보통 첫 번째 li 또는 #exchangeList의 첫 항목
        box = (
            soup.select_one("#exchangeList li.on")
            or soup.select_one("#exchangeList li:nth-of-type(1)")
            or soup.select_one(".market1 .head_info")
        )
        if not box:
            return None
        value_el = box.select_one(".value, .head_info .value")
        change_el = box.select_one(".change, .head_info .change")
        if not value_el:
            return None
        value = _to_float(value_el.get_text(strip=True))
        change = _to_float(change_el.get_text(strip=True)) if change_el else 0.0
        is_down = bool(box.select_one(".down, .blind"))  # blind는 부정확하니 down만 우선
        is_down = bool(box.select_one(".down"))
        if is_down and change and change > 0:
            change = -change
        if value is None:
            return None
        change = change or 0.0
        pct = (change / (value - change) * 100) if (value - change) and value else 0.0
        return {"value": value, "change": change, "change_pct": pct}
    except Exception:
        return None


def _fetch_alt_usdkrw() -> dict | None:
    """대체 환율 소스 — exchangerate.host (무료)."""
    try:
        r = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "KRW"},
            timeout=8,
        )
        data = r.json()
        rate = data.get("rates", {}).get("KRW")
        if rate:
            return {"value": float(rate), "change": 0.0, "change_pct": 0.0}
    except Exception:
        pass
    return None


def _get_usdkrw() -> dict | None:
    v = _fetch_naver_usdkrw()
    if v:
        return v
    return _fetch_alt_usdkrw()


# ────────────────────────────────────────────────
# 4. 통합 스냅샷
# ────────────────────────────────────────────────
def get_macro_snapshot() -> dict:
    """주요 거시 지표 한 번에 (실패 항목은 None)."""
    return {
        "kospi":    _get_index("KOSPI"),
        "kosdaq":   _get_index("KOSDAQ"),
        "kospi200": _get_index("KPI200"),
        "usdkrw":   _get_usdkrw(),
    }


MACRO_META = {
    "kospi":    {"label": "KOSPI",    "emoji": "🇰🇷", "unit": ""},
    "kosdaq":   {"label": "KOSDAQ",   "emoji": "📈", "unit": ""},
    "kospi200": {"label": "KOSPI200", "emoji": "📊", "unit": ""},
    "usdkrw":   {"label": "USD/KRW",  "emoji": "💵", "unit": "원"},
}


if __name__ == "__main__":
    import json
    snap = get_macro_snapshot()
    print(json.dumps(snap, ensure_ascii=False, indent=2))
