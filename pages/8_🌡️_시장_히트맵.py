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


def _parse_change_pct(tds) -> float:
    """네이버 시총표 행에서 등락률을 부호까지 정확히 파싱.

    텍스트 부호(+/-) → 색상 클래스(red↑/nv↓) → 전일비 blind(상승/하락/보합)
    순으로 방향을 판정. 셋 다 없으면 0.0(보합) 처리.
    """
    import re

    if len(tds) <= 4:
        return 0.0
    pct_td = tds[4]
    raw = pct_td.get_text(strip=True).replace("%", "").replace(",", "").replace(" ", "")
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not m:
        return 0.0
    val = abs(float(m.group()))
    if val == 0:
        return 0.0

    sign = 0
    if raw.startswith("-"):
        sign = -1
    elif raw.startswith("+"):
        sign = 1
    else:
        span = pct_td.select_one("span")
        cls = " ".join(span.get("class", [])) if span else ""
        if "nv" in cls:
            sign = -1
        elif "red" in cls:
            sign = 1
        else:
            blind = tds[3].select_one("span.blind") if len(tds) > 3 else None
            btxt = blind.get_text(strip=True) if blind else ""
            if "하락" in btxt or "하한" in btxt:
                sign = -1
            elif "상승" in btxt or "상한" in btxt:
                sign = 1
    return val * (sign if sign else 1)


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
                    # 등락률 — 부호 판정 다단계 fallback
                    # ① td[4] 텍스트의 +/- → ② span 색상 클래스(red=상승/nv=하락)
                    # → ③ td[3] 전일비 blind 텍스트(상승/하락/보합)
                    change_pct = _parse_change_pct(tds)
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

# CJK 폰트 fallback chain (한글 + 번체/간체 한자 모두 커버)
# 한국 폰트는 KS 한자만 → 번체 전용 한자(値, 檔, 顏 등) 글리프 없어 □ 표시 발생
# 여러 폰트 우선순위 등록 시 matplotlib가 글리프 없는 문자에 대해 자동 fallback
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = [
    "Malgun Gothic",         # Windows 한글
    "NanumGothic",           # Linux 한글 (Streamlit Cloud)
    "AppleGothic",           # macOS 한글
    "Noto Sans CJK TC",      # 번체 (Cloud, packages.txt로 설치)
    "Noto Sans CJK JP",      # 일본어 + 번체 일부
    "Noto Sans CJK KR",      # 한글 (CJK 통합)
    "Microsoft JhengHei",    # Windows 번체
    "Microsoft YaHei",       # Windows 간체+번체 일부
    "PingFang TC",           # macOS 번체
    "DejaVu Sans",
]
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
