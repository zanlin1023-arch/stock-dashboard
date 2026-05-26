"""신규 종목 추천 — 매일 시장 데이터 기반 동적 추천.

장 마감 후 또는 장 중에 새로운 종목 찾을 때 사용.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav

st.set_page_config(page_title="추천 종목", page_icon="🎯", layout="wide")
init_page("추천 종목")
sidebar_nav()
nav_bar("recommend")

st.title("🎯 신규 종목 추천")
st.markdown("**실시간 시장 데이터 기반** — 거래대금/상승률/거래량/시총 상위에서 동적 수집 → 외인+기관 수급 기반 점수화")


# ──────────────────────────────────────────
# 옵션
# ──────────────────────────────────────────
col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
with col1:
    top_n = st.slider("Tier별 추천 수", 1, 10, 3, step=1)
with col2:
    exclude_holdings = st.checkbox("보유 종목 제외", value=True)
with col3:
    exclude_watchlist = st.checkbox("관심 종목 제외", value=False)
with col4:
    st.write("")
    refresh = st.button("🔄 새로 분석", type="primary", use_container_width=True)


# ──────────────────────────────────────────
# 캐시된 추천 결과
# ──────────────────────────────────────────
@st.cache_data(ttl=600, show_spinner=False)
def _run_recommend(top_n: int, exclude_codes: tuple[str, ...]) -> dict:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
    import recommend
    return recommend.recommend(
        top_n_per_tier=top_n,
        exclude=set(exclude_codes),
    )


# 제외 종목 코드 수집
exclude_codes: list[str] = []
db = get_db()
if db and exclude_holdings:
    for h in db.list_holdings():
        exclude_codes.append(h["stock_code"])
if db and exclude_watchlist:
    for w in db.list_watchlist():
        exclude_codes.append(w["stock_code"])


if refresh:
    _run_recommend.clear()

with st.spinner("🔍 시장 데이터 수집 + 점수 계산 중... (30초~1분)"):
    try:
        results = _run_recommend(top_n, tuple(sorted(set(exclude_codes))))
    except Exception as e:
        st.error(f"❌ 추천 실패: {e}")
        st.exception(e)
        st.stop()


# ──────────────────────────────────────────
# Tier별 출력
# ──────────────────────────────────────────
tier_meta = {
    "large": {"label": "🏛 대형주", "desc": "시총 5조원 이상", "color": "#1F4E79"},
    "mid": {"label": "🏢 중형주", "desc": "시총 5천억~5조원", "color": "#2E86AB"},
    "small": {"label": "🏠 소형주", "desc": "시총 1천억~5천억원", "color": "#A23B72"},
}


def _stock_card(stock: dict, rank: int, color: str):
    """종목 카드 1개 렌더링."""
    code = stock.get("code", "")
    name = stock.get("name", "")
    price = stock.get("price", 0)
    change_pct = stock.get("change_pct", 0)
    score = stock.get("score", 0)
    market_cap = stock.get("market_cap_eok", 0)
    foreign_5d = stock.get("foreign_5d", 0)
    inst_5d = stock.get("inst_5d", 0)
    signals = stock.get("signals", [])

    with st.container(border=True):
        # 헤더
        hc1, hc2, hc3 = st.columns([3, 2, 2])
        with hc1:
            st.markdown(f"### #{rank}  {name}  `{code}`")
        with hc2:
            change_color = "🔴" if change_pct > 0 else ("🔵" if change_pct < 0 else "⚪")
            st.metric(
                "현재가",
                f"{int(price):,}원" if price else "-",
                f"{change_pct:+.2f}%" if change_pct else None,
            )
        with hc3:
            st.metric("추천 점수", f"{score:+}", help="외인+기관 수급 + 모멘텀 종합")

        # 상세
        dc1, dc2, dc3, dc4 = st.columns(4)
        with dc1:
            st.metric("시가총액", f"{market_cap:,}억원" if market_cap else "-")
        with dc2:
            f_color = "🟢" if foreign_5d > 0 else "🔴"
            st.metric("외인 5일", f"{f_color} {foreign_5d:+,}억" if foreign_5d else "-")
        with dc3:
            i_color = "🟢" if inst_5d > 0 else "🔴"
            st.metric("기관 5일", f"{i_color} {inst_5d:+,}억" if inst_5d else "-")
        with dc4:
            # 종목 액션 버튼
            if st.button("🔬 상세 분석", key=f"analyze_{code}", use_container_width=True):
                st.session_state["last_query"] = name
                st.switch_page("app.py")

        # 시그널 (있으면)
        if signals:
            with st.expander(f"📊 시그널 {len(signals)}개"):
                for sig in signals[:5]:
                    st.markdown(f"- {sig}")


# Tier 별 표시
for tier_key in ["large", "mid", "small"]:
    meta = tier_meta[tier_key]
    tier_data = results.get(tier_key, [])

    st.markdown(f"## {meta['label']}  _{meta['desc']}_")

    if not tier_data:
        st.info(f"이 Tier에 추천 종목이 없습니다.")
        continue

    for i, stock in enumerate(tier_data, 1):
        _stock_card(stock, i, meta["color"])

    st.markdown("")  # 공백


# ──────────────────────────────────────────
# 요약 + 액션
# ──────────────────────────────────────────
st.divider()
total = sum(len(results.get(k, [])) for k in ["large", "mid", "small"])

ca1, ca2, ca3 = st.columns(3)
with ca1:
    st.metric("총 추천 종목", f"{total}개")
with ca2:
    st.metric("Tier 분포", f"대 {len(results.get('large', []))} / 중 {len(results.get('mid', []))} / 소 {len(results.get('small', []))}")
with ca3:
    st.metric("제외 종목", f"{len(exclude_codes)}개")

st.caption(f"🕐 분석 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 캐시 10분 (새로 분석은 우상단 버튼)")


# ──────────────────────────────────────────
# 사용 가이드
# ──────────────────────────────────────────
with st.expander("📖 추천 점수 기준 (어떻게 계산되나?)"):
    st.markdown(
        """
        ### 점수 산정 (외인+기관 수급 기반)
        | 항목 | 점수 |
        |---|---|
        | 외인+기관 **동반 매수** | **+30** |
        | 외인 매수 전환 (어제 매도 → 오늘 매수) | **+20** |
        | 외인 5일 누적 매수 | +10 (Tier별 배수) |
        | 기관 5일 누적 매수 | +10 |
        | 외인 연속 매수 5일+ | +15 |
        | 외인 매도 전환 | **-20** |
        | 외인+기관 **동반 매도** | **-30** |
        | + 모멘텀 시그널 (50% 가중) | RSI, MACD, 신고가, 거래량 등 |

        ### 데이터 소스 (8개 페이지 통합)
        - KOSPI/KOSDAQ × 4 (거래대금/상승률/거래량/시총 상위)
        - ETF/ETN/우선주/스팩 자동 제외

        ### Tier 분류 (시가총액)
        - 🏛 **대형주**: 5조원+
        - 🏢 **중형주**: 5천억 ~ 5조원
        - 🏠 **소형주**: 1천억 ~ 5천억원
        - (1천억 미만 제외)
        """
    )
