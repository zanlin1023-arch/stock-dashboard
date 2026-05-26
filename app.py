"""분석 대시보드 - KOSPI/KOSDAQ 일목균형표 + 종합 분석."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# ───────────────────────────────────────────────────────
# 환경 설정 (Streamlit secrets → os.environ 주입)
# ───────────────────────────────────────────────────────
def _setup_environment():
    secret_keys = [
        "OPENDART_API_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
    ]
    for key in secret_keys:
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])


_setup_environment()

# analyzer 패키지를 sys.path에 추가
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "analyzer"))


# ───────────────────────────────────────────────────────
# 페이지 설정
# ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ───────────────────────────────────────────────────────
# 비밀번호 인증
# ───────────────────────────────────────────────────────
def check_password() -> bool:
    """비밀번호 인증. 통과 시 True 반환, 실패 시 페이지 정지."""
    if st.session_state.get("authenticated"):
        return True

    st.title("🔒 분석 대시보드")
    st.markdown("비밀번호를 입력하세요.")

    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")

        if submitted:
            correct_pw = st.secrets.get("app_password", "")
            if not correct_pw:
                st.error("⚠️ 앱 비밀번호가 설정되지 않았습니다. Streamlit Secrets에 `app_password` 추가 필요.")
                st.stop()
            if password == correct_pw:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 틀렸습니다.")

    st.stop()


check_password()


# ───────────────────────────────────────────────────────
# 메인 페이지
# ───────────────────────────────────────────────────────
st.title("📊 분석 대시보드")
st.markdown("KOSPI/KOSDAQ — 일목균형표 + 백테스팅 + 펀더멘털 종합 분석")

# DB 연동 모듈 로드
try:
    from analyzer import db
    _db_available = db.is_db_available()
except Exception as e:
    _db_available = False
    db = None
    _db_err = str(e)

# 사이드바: 종목 입력
with st.sidebar:
    st.header("🔍 종목 검색")
    query = st.text_input(
        "종목명 또는 종목코드",
        value=st.session_state.get("last_query", ""),
        placeholder="예: 삼성전자 또는 005930",
    )
    days = st.slider("분석 기간 (일)", 90, 365, 180, step=30)
    save_to_db = st.checkbox("📥 결과를 DB에 저장", value=_db_available, disabled=not _db_available)
    analyze_btn = st.button("🚀 분석 시작", type="primary", use_container_width=True)

    st.divider()
    if _db_available:
        st.success("✅ DB 연결됨")
    else:
        st.warning("⚠️ DB 미연결 (분석만 가능)")
    st.caption("버전: 0.2.0")

# ───────────────────────────────────────────────────────
# 분석 실행
# ───────────────────────────────────────────────────────
if analyze_btn and query:
    st.session_state["last_query"] = query

    with st.spinner(f"'{query}' 분석 중..."):
        try:
            # 분석 모듈 로드 (sys.path에 analyzer 추가됨)
            from _utils import resolve_ticker
            import technical
            from chart_ichimoku import (
                compute_ichimoku,
                detect_swing_points,
                compute_price_targets,
                make_decision,
                render_ichimoku_chart,
            )

            code, name = resolve_ticker(query)

            # OHLCV + 일목 계산
            df = technical.fetch_ohlcv(code, days=days)
            df = technical.add_indicators(df)
            df = compute_ichimoku(df)

            # 종합 분석
            result = technical.analyze(code, name)

            # 일목 분석
            swings = detect_swing_points(df, lookback=min(80, len(df)))
            A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
            targets = compute_price_targets(A, B, C)
            decision = make_decision(df, swings, targets)

            # 차트 생성 (PNG)
            chart_path = render_ichimoku_chart(code, name, days=days)

        except Exception as e:
            st.error(f"❌ 분석 실패: {e}")
            st.exception(e)
            st.stop()

    # ───────────────────────────────────────────────────
    # 결과 표시
    # ───────────────────────────────────────────────────
    st.success(f"✅ 분석 완료: **{name}** ({code})")

    # 핵심 지표 카드
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "현재가",
            f"{result['current_price']:,}원",
            f"{result['daily_return']:+.2f}%",
        )
    with col2:
        st.metric(
            f"{days}일 수익률",
            f"{result['period_return_180d']:+.1f}%",
        )
    with col3:
        if result["rsi_14"]:
            rsi_status = "🔴 과매수" if result["rsi_14"] >= 70 else ("🟢 과매도" if result["rsi_14"] <= 30 else "🟡 중립")
            st.metric("RSI(14)", f"{result['rsi_14']:.1f}", rsi_status)
    with col4:
        st.metric("거래량", f"{result['volume']:,}주")

    st.divider()

    # 일목 의사결정 박스
    st.subheader("📌 일목균형표 종합 판단")
    decision_color = {
        "STRONG_BUY": "🟢",
        "BUY": "🟢",
        "NEUTRAL": "🟡",
        "SELL": "🟠",
        "STRONG_SELL": "🔴",
    }.get(decision["stance"], "⚪")

    st.markdown(f"### {decision_color} {decision['action']}")

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        cloud_txt = {
            "above": "구름 위 (강세)",
            "below": "구름 아래 (약세)",
            "inside": "구름 안 (횡보)",
        }.get(decision["cloud_pos"], "—")
        st.info(f"**위치**\n\n{cloud_txt}")
    with dc2:
        tk_txt = "전환선 > 기준선 ✅" if decision["tk_bull"] else "전환선 < 기준선 ⚠️"
        st.info(f"**TK 상태**\n\n{tk_txt}")
    with dc3:
        if decision["chikou_ok"] is not None:
            chikou_txt = "26일전 위 ✅" if decision["chikou_ok"] else "26일전 아래 ⚠️"
            st.info(f"**후행스팬**\n\n{chikou_txt}")

    # 목표가 + 손절
    st.subheader("🎯 가격 가이드")
    current_price = decision["price"]

    target_cols = st.columns(4)

    # V/N/E 목표 (가까운 순 정렬)
    sorted_targets = sorted(
        [(k, targets[k]) for k in ["V", "N", "E"]],
        key=lambda x: x[1],
    )
    target_meta = {"V": "1차 익절", "N": "표준 목표", "E": "강세 목표"}

    above = [(k, v) for k, v in sorted_targets if v > current_price]
    for i, (k, v) in enumerate(above[:3]):
        pct = (v / current_price - 1) * 100
        with target_cols[i]:
            st.metric(
                f"🎯 {k} ({target_meta[k]})",
                f"{v:,.0f}원",
                f"{pct:+.1f}%",
            )

    if decision["stop"]:
        with target_cols[3]:
            stop_name, stop_val = decision["stop"]
            pct = (stop_val / current_price - 1) * 100
            st.metric(
                f"🛡 손절 ({stop_name})",
                f"{stop_val:,.0f}원",
                f"{pct:+.1f}%",
                delta_color="inverse",
            )

    # 일목 차트
    st.subheader("📈 일목균형표 차트")
    if chart_path and chart_path.exists():
        st.image(str(chart_path), use_container_width=True)
    else:
        st.warning("차트 생성 실패")

    # 시그널 목록
    st.subheader("🚨 시그널")
    for sig in result.get("signals", []):
        st.markdown(f"- {sig}")

    # 이동평균 표
    with st.expander("📊 이동평균선 상세"):
        ma_data = {
            "기간": ["5일선", "20일선", "60일선", "120일선"],
            "값": [
                f"{result['sma_5']:,.0f}원" if result["sma_5"] else "-",
                f"{result['sma_20']:,.0f}원" if result["sma_20"] else "-",
                f"{result['sma_60']:,.0f}원" if result["sma_60"] else "-",
                f"{result['sma_120']:,.0f}원" if result["sma_120"] else "-",
            ],
        }
        st.table(ma_data)

    # 파동 정보
    with st.expander("🌊 일목 파동 (A → B → C)"):
        st.markdown(
            f"""
            - **A (시작 저점)**: {swings['A']['price']:,.0f}원 ({swings['A']['date'].strftime('%Y-%m-%d')})
            - **B (고점)**: {swings['B']['price']:,.0f}원 ({swings['B']['date'].strftime('%Y-%m-%d')})
            - **C (조정 저점)**: {swings['C']['price']:,.0f}원 ({swings['C']['date'].strftime('%Y-%m-%d')})
            - **C 형성 여부**: {'✅ 형성' if swings.get('c_formed') else '⚠️ 미형성 (신규 추세 진행 중)'}

            **파동론 공식**:
            - V = B + (B − C) = {targets['V']:,.0f}
            - N = C + (B − A) = {targets['N']:,.0f}
            - E = B + (B − A) = {targets['E']:,.0f}
            """
        )

else:
    # 첫 화면 (분석 전)
    st.info("👈 사이드바에서 종목을 입력하고 **분석 시작** 버튼을 눌러주세요.")

    st.markdown(
        """
        ### 🎯 이 대시보드가 제공하는 것

        1. **일목균형표 종합 분석** — 5선 + 구름대 + 삼역호전/역전 자동 감지
        2. **파동론 목표가** — V/N/E 자동 계산 (분할 익절 가이드)
        3. **시간론 변곡 예측** — 9/17/26봉 시간 사이클
        4. **기술적 시그널** — RSI, MACD, 볼린저, 골든/데드크로스
        5. **백테스팅 가격대** — 1년/2년 데이터 기반 분할 매수/익절선
        """
    )

    st.markdown("---")
    st.caption("⚠️ 본 분석은 참고용입니다. 투자 결정은 본인 책임입니다.")
