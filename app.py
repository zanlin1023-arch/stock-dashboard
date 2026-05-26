"""분석 대시보드 - KOSPI/KOSDAQ 일목균형표 + 종합 분석."""
from __future__ import annotations

import streamlit as st

from common import init_page, get_db, sidebar_nav

# ───────────────────────────────────────────────────────
# 페이지 설정
# ───────────────────────────────────────────────────────
st.set_page_config(
    page_title="분석 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_page("홈")
sidebar_nav()


# ───────────────────────────────────────────────────────
# 메인 페이지
# ───────────────────────────────────────────────────────
st.title("📊 분석 대시보드")
st.markdown("KOSPI/KOSDAQ — 일목균형표 + 백테스팅 + 펀더멘털 종합 분석")

# DB 연동
db = get_db()
_db_available = db is not None

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

    # DB 저장
    if save_to_db and _db_available and db is not None:
        try:
            tech_for_db = dict(result)
            tech_for_db.update({
                "tenkan": float(df["tenkan"].iloc[-1]) if df["tenkan"].notna().any() else None,
                "kijun": float(df["kijun"].iloc[-1]) if df["kijun"].notna().any() else None,
                "senkou_a": float(df["senkou_a"].iloc[-1]) if df["senkou_a"].notna().any() else None,
                "senkou_b": float(df["senkou_b"].iloc[-1]) if df["senkou_b"].notna().any() else None,
            })
            saved = db.save_analysis(code, name, tech_for_db, decision, targets, swings)
            if saved:
                st.success(f"📥 DB 저장 완료 (id: {saved.get('id')})")
        except Exception as e:
            st.warning(f"⚠️ DB 저장 실패: {e}")

    # 관심종목 추가 버튼
    if _db_available and db is not None:
        wcol1, wcol2 = st.columns([1, 5])
        with wcol1:
            if st.button("⭐ 관심 종목 추가", use_container_width=True):
                try:
                    db.add_watch(code, name)
                    st.success(f"✅ {name} 관심 종목에 추가됨")
                except Exception as e:
                    st.error(f"❌ 추가 실패: {e}")

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
