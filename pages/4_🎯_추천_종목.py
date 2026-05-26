"""신규 종목 추천 — 시점별 3가지 모드.

🌅 장 시작 전 / ☀️ 장 중 / 🌙 장 마감 후 — 각각 다른 알고리즘.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav

st.set_page_config(page_title="추천 종목", page_icon="🎯", layout="wide")
init_page("추천 종목")
sidebar_nav()
nav_bar("recommend")

st.title("🎯 신규 종목 추천")


# ──────────────────────────────────────────
# 현재 시각 기반 디폴트 탭 자동 선택
# ──────────────────────────────────────────
KST = ZoneInfo("Asia/Seoul")
now = datetime.now(KST)
hour = now.hour
minute = now.minute

if hour < 9:
    default_tab = 0  # 장 시작 전
    session_label = "🌅 장 시작 전"
elif hour < 15 or (hour == 15 and minute < 30):
    default_tab = 1  # 장 중
    session_label = "☀️ 장 중"
else:
    default_tab = 2  # 장 마감 후
    session_label = "🌙 장 마감 후"

st.caption(f"🕐 현재 한국 시각: **{now.strftime('%H:%M')}** — 자동 추천 모드: **{session_label}**")


# ──────────────────────────────────────────
# 공통 옵션 (항상 보이게)
# ──────────────────────────────────────────
col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
with col1:
    top_n = st.slider("Tier별 추천 수", 1, 10, 3, step=1)
with col2:
    exclude_holdings = st.checkbox("보유 종목 제외", value=True)
    exclude_watchlist = st.checkbox("관심 종목 제외", value=False)
with col3:
    st.write("")
    refresh = st.button("🔄 새로 분석", type="primary", use_container_width=True)
with col4:
    st.write("")
    st.caption("⏱ 캐시 10분 · 새로 분석 시 30초~1분")


# 제외 종목 코드 수집
exclude_codes: list[str] = []
db = get_db()
if db and exclude_holdings:
    for h in db.list_holdings():
        exclude_codes.append(h["stock_code"])
if db and exclude_watchlist:
    for w in db.list_watchlist():
        exclude_codes.append(w["stock_code"])


# ──────────────────────────────────────────
# 추천 실행 (캐시)
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


if refresh:
    _run_recommend.clear()
    st.toast("🔄 캐시 비움 — 새로 분석합니다", icon="✅")


# ──────────────────────────────────────────
# 종목 카드 (공통)
# ──────────────────────────────────────────
def _stock_card(stock: dict, rank: int, mode: str = "morning"):
    """종목 카드 1개. mode에 따라 강조 정보 다름."""
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
        hc1, hc2, hc3 = st.columns([3, 2, 2])
        with hc1:
            st.markdown(f"### #{rank}  {name}  `{code}`")
        with hc2:
            change_str = f"{change_pct:+.2f}%" if change_pct else None
            st.metric("현재가", f"{int(price):,}원" if price else "-", change_str)
        with hc3:
            st.metric("추천 점수", f"{score:+}")

        # 모드별 핵심 정보
        dc1, dc2, dc3, dc4 = st.columns(4)
        with dc1:
            st.metric("시가총액", f"{market_cap:,}억" if market_cap else "-")
        with dc2:
            f_color = "🟢" if foreign_5d > 0 else "🔴"
            st.metric("외인 5일", f"{f_color} {foreign_5d:+,}억" if foreign_5d else "-")
        with dc3:
            i_color = "🟢" if inst_5d > 0 else "🔴"
            st.metric("기관 5일", f"{i_color} {inst_5d:+,}억" if inst_5d else "-")
        with dc4:
            if st.button("🔬 상세 분석", key=f"analyze_{mode}_{code}", use_container_width=True):
                st.session_state["last_query"] = name
                st.switch_page("app.py")

        if signals:
            with st.expander(f"📊 시그널 {len(signals)}개"):
                for sig in signals[:5]:
                    st.markdown(f"- {sig}")


def _render_results(mode: str):
    """추천 결과 렌더링 (Tier별)."""
    with st.spinner("🔍 시장 데이터 수집 + 외인/기관 수급 계산 + 점수화 (30초~1분 소요)..."):
        try:
            results = _run_recommend(top_n, tuple(sorted(set(exclude_codes))))
        except Exception as e:
            st.error(f"❌ 추천 실패: {e}")
            with st.expander("🐛 상세 에러"):
                st.exception(e)
            return

    # 빈 결과 체크
    total = sum(len(results.get(k, [])) for k in ["large", "mid", "small"])
    if total == 0:
        st.warning(
            "⚠️ 추천 종목이 없습니다.\n\n"
            "**가능한 원인**:\n"
            "- 한국 시장 휴장 시간 (네이버 데이터 제한)\n"
            "- 모든 후보가 보유/관심 종목과 중복되어 제외됨\n"
            "- 시장 데이터 일시적 접근 실패\n\n"
            "**해결**: 옵션에서 '보유/관심 제외' 체크 해제 후 다시 분석"
        )
        with st.expander("🐛 디버그 정보"):
            st.json({
                "results_keys": list(results.keys()),
                "tier_counts": {k: len(results.get(k, [])) for k in ["large", "mid", "small"]},
                "exclude_codes_count": len(exclude_codes),
                "top_n": top_n,
            })
        return

    tier_meta = {
        "large": ("🏛 대형주", "시총 5조원 이상"),
        "mid": ("🏢 중형주", "5천억 ~ 5조원"),
        "small": ("🏠 소형주", "1천억 ~ 5천억원"),
    }

    # 요약 카드
    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric("총 추천", f"{total}개")
    sc2.metric("🏛 대형", f"{len(results.get('large', []))}개")
    sc3.metric("🏢 중형", f"{len(results.get('mid', []))}개")
    sc4.metric("🏠 소형", f"{len(results.get('small', []))}개")
    st.markdown("")

    for tier_key in ["large", "mid", "small"]:
        label, desc = tier_meta[tier_key]
        tier_data = results.get(tier_key, [])
        st.markdown(f"### {label} _({desc})_")
        if not tier_data:
            st.info("이 Tier에 추천 종목 없음")
            continue
        for i, stock in enumerate(tier_data, 1):
            _stock_card(stock, i, mode)
        st.markdown("")


# ──────────────────────────────────────────
# 탭 3개
# ──────────────────────────────────────────
tab_names = ["🌅 장 시작 전", "☀️ 장 중", "🌙 장 마감 후"]
tabs = st.tabs(tab_names)


# ============================================================
# 🌅 장 시작 전 — 외인/기관 동반 매수 + 5일 누적 우선
# ============================================================
with tabs[0]:
    if default_tab == 0:
        st.success("✅ 지금 추천된 모드 — 현재가 장 시작 전")
    st.markdown(
        """
        ### 🎯 이 모드의 포커스
        - **전일 외인+기관 동반 매수** 종목 우선 (가장 신뢰도 ↑)
        - **5일 누적 수급** 안정적 종목
        - **밤사이 글로벌 시장** 동향 반영 (미국 증시 마감 후)
        - **추천 시각**: 08:00~09:00 (장 시작 직전 확인)

        ### 📋 추천 매매 전략
        1. **장 시작 시 호가창 확인** — 갭상승 종목은 추격 X
        2. **분할 매수** — 첫 거래 후 안정화되면 1차 진입
        3. **외인+기관 동반 매수 종목 우선**
        """
    )
    st.divider()
    _render_results("morning")


# ============================================================
# ☀️ 장 중 — 실시간 모멘텀 + 거래량 폭증
# ============================================================
with tabs[1]:
    if default_tab == 1:
        st.success("✅ 지금 추천된 모드 — 현재가 장 중")
    st.markdown(
        """
        ### 🎯 이 모드의 포커스
        - **실시간 거래대금/거래량 폭증** 종목
        - **외인 매수 전환** (어제 매도 → 오늘 매수)
        - **상승률 상위** 단기 모멘텀
        - **추천 시각**: 09:30~15:00 (장 중 수시)

        ### ⚠️ 주의사항
        - **추격매수 위험** — 이미 +5% 이상 갭상승 종목은 차익 매물 출회 가능
        - **점심 시간(11:30~13:00)** 거래 약해서 시그널 신뢰도 ↓
        - **변동성 큰 종목** 손절선 짧게 (2%)

        ### 📋 추천 매매 전략
        1. **분할 매수** — 1차 30%, 흐름 보고 추가 매수
        2. **거래대금 상위 + 외인 매수** 조합이 안전
        3. **단타 손절: -2% / 익절: +3~4%**
        """
    )
    st.divider()
    _render_results("intraday")


# ============================================================
# 🌙 장 마감 후 — 오늘 종가 기반 내일 전략
# ============================================================
with tabs[2]:
    if default_tab == 2:
        st.success("✅ 지금 추천된 모드 — 현재가 장 마감 후")
    st.markdown(
        """
        ### 🎯 이 모드의 포커스
        - **오늘 종가 확정** 데이터 기반
        - **일목 시그널 변화** (어제 vs 오늘 — 구름 돌파, TK 골든)
        - **내일 매매 후보** 선별 + 매수 가격대 제시
        - **추천 시각**: 16:00~18:00 (장 마감 후)

        ### 📋 추천 매매 전략
        1. **오늘 신고가 갱신 + 외인 매수 = 내일 추격 검토**
        2. **장 마감 5분 거래량 급증** 종목 주목
        3. **분할 매수가 = 오늘 종가 대비 -2~3% 지정가**
        4. **내일 시초가 갭하락 시 분할 매수 시작**

        ### 💡 보유 종목 점검
        매일 18:00 KST에 보유/관심 종목 자동 스냅샷이 [📜 분석 히스토리]에 누적됩니다.
        장 마감 후 그쪽도 같이 확인하세요.
        """
    )
    st.divider()
    _render_results("evening")


# ──────────────────────────────────────────
# 푸터
# ──────────────────────────────────────────
st.divider()
st.caption(
    f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')} (KST)  ·  "
    f"💾 캐시 10분  ·  "
    f"🔄 새로 분석은 옵션 패널에서"
)


# 점수 가이드
with st.expander("📖 추천 점수 산정 기준"):
    st.markdown(
        """
        | 항목 | 점수 |
        |---|---|
        | 외인+기관 **동반 매수** | **+30** |
        | 외인 매수 전환 | +20 |
        | 외인 5일 누적 매수 | +10 |
        | 기관 5일 누적 매수 | +10 |
        | 외인 연속 매수 5일+ | +15 |
        | 외인 매도 전환 | **-20** |
        | 외인+기관 **동반 매도** | **-30** |
        | + 모멘텀 시그널 (50% 가중) | RSI/MACD/신고가/거래량 |

        ### 데이터 소스 (매번 실시간 수집)
        - KOSPI/KOSDAQ × {거래대금, 상승률, 거래량, 시가총액} = 8 페이지
        - ETF/ETN/우선주/스팩 자동 제외

        ### Tier 분류
        - 🏛 **대형주**: 시총 5조원+
        - 🏢 **중형주**: 5천억 ~ 5조원
        - 🏠 **소형주**: 1천억 ~ 5천억원
        """
    )
