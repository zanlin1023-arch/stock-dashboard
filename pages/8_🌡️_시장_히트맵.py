"""시장 히트맵 — KOSPI/KOSDAQ 시총 상위 종목을 treemap으로 시각화.

각 종목 박스 크기 = 시가총액
색상 = 등락률 (빨강↑ / 파랑↓)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from common import init_page, sidebar_nav, render_macro_header, nav_bar
from i18n import t

st.set_page_config(page_title="시장 히트맵", page_icon="🌡️", layout="wide")
init_page(t("heatmap_title"))
sidebar_nav()
render_macro_header()
nav_bar("heatmap")

st.title(t("heatmap_title"))
st.caption(t("heatmap_caption"))


# ──────────────────────────────────────────
# 컨트롤
# ──────────────────────────────────────────
_market_all = t("heatmap_market_all")
c1, c2, c3 = st.columns(3)
with c1:
    market = st.selectbox(t("heatmap_market"), ["KOSPI", "KOSDAQ", _market_all])
with c2:
    top_n = st.slider(t("heatmap_top_n"), 20, 100, 50, step=10)
with c3:
    refresh = st.button(t("heatmap_refresh"))


@st.cache_data(ttl=600, show_spinner=False)
def _fetch_market_caps(market_filter: str, n: int) -> list[dict]:
    """네이버 시총 상위 페이지 스크래핑 — 인증 불필요, 빠름.

    pykrx는 KRX 신규 API 인증(KRX_ID/PW) 필요해 무료 사용 어려움.
    네이버 sise_market_sum 페이지는 한 페이지에 50종목의 시총/현재가/등락률을
    동시 제공 → 페이지 1~2회 호출로 충분.
    """
    import re
    import requests
    from bs4 import BeautifulSoup

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    }

    if market_filter == "KOSPI":
        sosoks = [("0", "KOSPI")]
    elif market_filter == "KOSDAQ":
        sosoks = [("1", "KOSDAQ")]
    else:
        # "전체" / "全部" 등 모든 다국어 변형 → KOSPI + KOSDAQ
        sosoks = [("0", "KOSPI"), ("1", "KOSDAQ")]

    out: list[dict] = []
    for sosok, _mkt in sosoks:
        pages_needed = (n + 49) // 50
        for page in range(1, pages_needed + 1):
            url = f"https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                r.encoding = "euc-kr"
                soup = BeautifulSoup(r.text, "html.parser")
                rows = soup.select("table.type_2 tr")
                for tr in rows:
                    tds = tr.find_all("td")
                    if len(tds) < 7:
                        continue
                    a = tr.select_one("a.tltle")
                    if not a:
                        continue
                    href = a.get("href", "")
                    m = re.search(r"code=(\d{6})", href)
                    if not m:
                        continue
                    code = m.group(1)
                    name = a.get_text(strip=True)
                    # 현재가
                    try:
                        price = float(tds[2].get_text(strip=True).replace(",", ""))
                    except Exception:
                        continue
                    # 등락률
                    pct_td = tds[4] if len(tds) > 4 else None
                    change_pct = 0.0
                    if pct_td is not None:
                        pct_txt = pct_td.get_text(strip=True).replace("%", "").replace(",", "").replace("+", "")
                        try:
                            change_pct = float(pct_txt)
                            if pct_td.select_one(".nv01") or "blue" in str(pct_td.get("class", "")):
                                change_pct = -abs(change_pct)
                        except Exception:
                            change_pct = 0.0
                    # 시가총액 (백만원 단위 → 원)
                    try:
                        cap_txt = tds[6].get_text(strip=True).replace(",", "")
                        cap = float(cap_txt) * 1e6
                    except Exception:
                        cap = 0.0
                    out.append({
                        "code": code,
                        "name": name,
                        "market_cap": cap,
                        "close": price,
                        "change_pct": change_pct,
                    })
            except Exception:
                continue

    # 시총 내림차순 정렬 → 상위 N
    out = [x for x in out if x["market_cap"] > 0]
    out.sort(key=lambda x: -x["market_cap"])
    return out[:n]


with st.spinner(t("heatmap_loading", market=market, n=top_n)):
    items = _fetch_market_caps(market, top_n)

if not items:
    st.warning(t("heatmap_no_data"))
    st.stop()


# ──────────────────────────────────────────
# Treemap 렌더링 (matplotlib + squarify)
# ──────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 한글 폰트
for fn in ["Malgun Gothic", "NanumGothic", "AppleGothic"]:
    try:
        if any(f.name == fn for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = fn
            break
    except Exception:
        pass
plt.rcParams["axes.unicode_minus"] = False


def _color_for_change(chg: float) -> str:
    """등락률 → 색상 (빨강↑ / 파랑↓, 한국 컬러)."""
    if chg >= 3:
        return "#C0392B"
    if chg >= 1.5:
        return "#E74C3C"
    if chg >= 0.5:
        return "#F1948A"
    if chg > -0.5:
        return "#BDC3C7"
    if chg > -1.5:
        return "#85C1E9"
    if chg > -3:
        return "#3498DB"
    return "#1F618D"


try:
    import squarify
except ImportError:
    st.error(t("heatmap_squarify_missing"))
    st.stop()

sizes = [it["market_cap"] for it in items]
labels = [
    f"{it['name']}\n{it['change_pct']:+.2f}%"
    for it in items
]
colors = [_color_for_change(it["change_pct"]) for it in items]

fig, ax = plt.subplots(figsize=(16, 9))
squarify.plot(
    sizes=sizes,
    label=labels,
    color=colors,
    alpha=0.85,
    text_kwargs={"fontsize": 9, "color": "white", "weight": "bold"},
    pad=True,
    ax=ax,
)
ax.axis("off")
ax.set_title(
    t("heatmap_chart_title", market=market, n=len(items)),
    fontsize=14, fontweight="bold",
)
st.pyplot(fig, use_container_width=True)


# ──────────────────────────────────────────
# 표 (정렬 가능)
# ──────────────────────────────────────────
st.divider()
st.subheader(t("heatmap_table_title"))
import pandas as pd
_hcol_stock = t("heatmap_col_stock")
_hcol_cap = t("heatmap_col_marketcap")
_hcol_close = t("heatmap_col_close")
_hcol_change = t("heatmap_col_change")
rows = []
for it in items:
    rows.append({
        _hcol_stock: f"{it['name']} ({it['code']})",
        _hcol_cap: f"{it['market_cap'] / 1e12:.2f}",
        _hcol_close: f"{int(it['close']):,}",
        _hcol_change: f"{it['change_pct']:+.2f}%",
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# 시장 통계
up = sum(1 for it in items if it["change_pct"] > 0)
down = sum(1 for it in items if it["change_pct"] < 0)
flat = len(items) - up - down
avg_chg = sum(it["change_pct"] for it in items) / len(items)

sc1, sc2, sc3, sc4 = st.columns(4)
sc1.metric(t("heatmap_metric_up"), up)
sc2.metric(t("heatmap_metric_down"), down)
sc3.metric(t("heatmap_metric_flat"), flat)
sc4.metric(t("heatmap_metric_avg"), f"{avg_chg:+.2f}%")
