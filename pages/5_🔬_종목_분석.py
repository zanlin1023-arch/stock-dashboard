"""종목 분석 페이지 — KOSPI/KOSDAQ 일목균형표 + 종합 분석."""
from __future__ import annotations

import streamlit as st

from common import init_page, get_db, sidebar_nav, nav_bar, render_macro_header
from i18n import t, td

st.set_page_config(
    page_title="종목 분석",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_page(t("analyze_page_title"))
sidebar_nav()
render_macro_header()
nav_bar("analyze")


# ───────────────────────────────────────────────────────
# 페이지 헤더
# ───────────────────────────────────────────────────────
st.title("🔬 " + t("analyze_page_title"))
st.markdown(t("home_subtitle"))

# DB 연동
db = get_db()
_db_available = db is not None

# 사이드바엔 DB 상태/버전만 표시 (입력 위젯은 메인 본문으로 이동)
with st.sidebar:
    st.divider()
    if _db_available:
        st.success(t("db_connected"))
    else:
        st.warning(t("db_disconnected"))
    st.caption(f"{t('version')}: 0.3.0")

# ───────────────────────────────────────────────────────
# 본문 상단 — 종목 입력 (사이드바에서 이동)
# ───────────────────────────────────────────────────────
with st.container(border=True):
    st.markdown(f"#### 🔎 {t('search_header')}")
    qc1, qc2, qc3, qc4 = st.columns([4, 2, 2, 2])
    with qc1:
        query = st.text_input(
            t("search_input"),
            value=st.session_state.get("last_query", ""),
            placeholder=t("search_placeholder"),
            label_visibility="collapsed",
        )
    with qc2:
        days = st.slider(t("analyze_period"), 90, 365, 180, step=30)
    with qc3:
        save_to_db = st.checkbox(
            t("save_to_db"),
            value=_db_available,
            disabled=not _db_available,
        )
    with qc4:
        st.write("")
        analyze_btn = st.button(
            t("btn_analyze"),
            type="primary",
            use_container_width=True,
        )

# ───────────────────────────────────────────────────────
# 분석 실행
# ───────────────────────────────────────────────────────
if analyze_btn and query:
    st.session_state["last_query"] = query

    with st.spinner(f"'{query}' {t('analyzing')}"):
        try:
            # 분석 모듈 로드 (sys.path에 analyzer 추가됨)
            from _utils import resolve_ticker
            import technical
            from chart_ichimoku import (
                compute_ichimoku,
                detect_swing_points,
                compute_price_targets,
                cap_targets,
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
            # ATR cap 통일 — 카드/파동 expander/DB 저장이 모두 동일한 cap된 목표가 사용
            _cur_price = float(df["close"].iloc[-1])
            _atr_cap = (
                float(df["atr_14"].iloc[-1])
                if "atr_14" in df.columns and df["atr_14"].iloc[-1] == df["atr_14"].iloc[-1]
                else None
            )
            targets = cap_targets(targets, _cur_price, _atr_cap)
            decision = make_decision(df, swings, targets)

            # 차트 생성 (PNG)
            chart_path = render_ichimoku_chart(code, name, days=days)

        except Exception as e:
            st.error(f"{t('analysis_failed')}: {e}")
            st.exception(e)
            st.stop()

    # ───────────────────────────────────────────────────
    # 결과 표시
    # ───────────────────────────────────────────────────
    st.success(f"{t('analysis_complete')}: **{name}** ({code})")

    # 핵심 지표 카드
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            t("current_price"),
            f"{result['current_price']:,}",
            f"{result['daily_return']:+.2f}%",
        )
    with col2:
        st.metric(
            f"{days}d {t('period_return')}",
            f"{result['period_return_180d']:+.1f}%",
        )
    with col3:
        if result["rsi_14"]:
            rsi_status = t("rsi_overbought") if result["rsi_14"] >= 70 else (t("rsi_oversold") if result["rsi_14"] <= 30 else t("rsi_neutral"))
            st.metric("RSI(14)", f"{result['rsi_14']:.1f}", rsi_status)
    with col4:
        st.metric(t("volume"), f"{result['volume']:,}")

    st.divider()

    # 일목 의사결정 박스
    st.subheader(t("ichimoku_decision"))
    decision_color = {
        "STRONG_BUY": "🟢",
        "BUY": "🟢",
        "NEUTRAL": "🟡",
        "SELL": "🟠",
        "STRONG_SELL": "🔴",
    }.get(decision["stance"], "⚪")

    st.markdown(f"### {decision_color} {td(decision['action'])}")

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        cloud_txt = {
            "above": t("cloud_above"),
            "below": t("cloud_below"),
            "inside": t("cloud_inside"),
        }.get(decision["cloud_pos"], "—")
        st.info(f"**{t('position')}**\n\n{cloud_txt}")
    with dc2:
        tk_txt = t("tk_bull") if decision["tk_bull"] else t("tk_bear")
        st.info(f"**{t('tk_state')}**\n\n{tk_txt}")
    with dc3:
        if decision["chikou_ok"] is not None:
            chikou_txt = t("chikou_above") if decision["chikou_ok"] else t("chikou_below")
            st.info(f"**{t('chikou')}**\n\n{chikou_txt}")

    # 목표가 + 손절
    st.subheader(t("price_guide"))
    current_price = decision["price"]

    target_cols = st.columns(4)

    # V/N/E 목표 (가까운 순 정렬)
    sorted_targets = sorted(
        [(k, targets[k]) for k in ["V", "N", "E"]],
        key=lambda x: x[1],
    )
    target_meta = {"V": t("target_v"), "N": t("target_n"), "E": t("target_e")}

    above = [(k, v) for k, v in sorted_targets if v > current_price]
    for i, (k, v) in enumerate(above[:3]):
        pct = (v / current_price - 1) * 100
        with target_cols[i]:
            st.metric(
                f"🎯 {k} ({target_meta[k]})",
                f"{v:,.0f}",
                f"{pct:+.1f}%",
            )

    if decision["stop"]:
        with target_cols[3]:
            stop_name, stop_val = decision["stop"]
            pct = (stop_val / current_price - 1) * 100
            st.metric(
                f"{t('stop_loss')} ({stop_name})",
                f"{stop_val:,.0f}",
                f"{pct:+.1f}%",
                delta_color="inverse",
            )

    # 일목 차트
    st.subheader(t("ichimoku_chart"))
    if chart_path and chart_path.exists():
        from common import render_zoomable_image
        render_zoomable_image(str(chart_path), alt="일목 차트")
    else:
        st.warning(t("chart_failed"))

    # ───── 동종업종 비교 위젯 ─────
    st.divider()
    st.subheader(t("analyze_sector_compare"))

    @st.cache_data(ttl=600, show_spinner=False)
    def _sector_data(stock_code: str) -> dict:
        try:
            import sector_compare as sc
            return sc.compare_to_peers(stock_code, max_peers=10)
        except Exception:
            return {"sector_no": None, "sector_name": "", "peers": [], "self_in_peers": False}

    with st.spinner(t("analyze_sector_loading")):
        sec = _sector_data(code)

    if sec.get("peers"):
        sector_label = sec.get("sector_name") or t("analyze_sector_default_label")
        st.caption(t("analyze_sector_top", label=sector_label, n=len(sec["peers"])))

        import pandas as pd
        _sc_compare = t("analyze_sector_col_compare")
        _sc_stock = t("analyze_sector_col_stock")
        _sc_price = t("analyze_sector_col_price")
        _sc_change = t("analyze_sector_col_change")
        rows = []
        for p in sec["peers"]:
            is_self = p["code"] == code
            rows.append({
                _sc_compare: t("analyze_sector_self") if is_self else "",
                _sc_stock: f"{p['name']} ({p['code']})",
                _sc_price: f"{int(p['price']):,}" if p['price'] else "-",
                _sc_change: f"{p['change_pct']:+.2f}%",
            })
        df_sec = pd.DataFrame(rows)
        st.dataframe(df_sec, use_container_width=True, hide_index=True)

        avg_chg = sum(p["change_pct"] for p in sec["peers"]) / len(sec["peers"])
        sec_color = "#E74C3C" if avg_chg > 0 else ("#0064FF" if avg_chg < 0 else "#7F8C8D")
        st.markdown(
            f"<div style='padding:8px 12px;border-radius:6px;background:{sec_color}10;"
            f"border-left:3px solid {sec_color};font-size:0.9rem;'>"
            + t("analyze_sector_summary", color=sec_color, avg=avg_chg, own=(result.get("daily_return") or 0))
            + "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.caption(t("analyze_sector_unavailable"))

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
            # 시간 사이클 + 미래 추세 + 수급 + 패턴 매칭 (DB 누적 분석용)
            from chart_ichimoku import compute_time_cycles, project_future_path
            cycles = compute_time_cycles(swings["C"]["idx"], len(df))
            _atr_val = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns and df["atr_14"].iloc[-1] == df["atr_14"].iloc[-1] else None
            future_path = project_future_path(
                decision["price"], cycles, targets, decision.get("stop"),
                swings=swings, atr_value=_atr_val,
            )
            flow_data = None
            try:
                import market_context as mc
                rev = mc.detect_flow_reversal(code, lookback=7)
                if rev.get("available"):
                    flow_data = {
                        "verdict": rev.get("verdict"),
                        "daily": rev.get("daily", [])[:7],
                        "signals": rev.get("signals", []),
                    }
            except Exception:
                pass

            pattern_data = None
            try:
                import pattern_match as pm
                pattern_data = pm.predict_future_path(
                    code=code, current_price=decision["price"],
                    window=60, n_future=20, top_k=3,
                )
            except Exception:
                pass

            # 종목이 보유/관심에 있으면 → scheduled (자동·보유/자동·관심으로 자동 분류)
            snap_type = "manual"
            try:
                code6 = (code or "").zfill(6)
                if any(((h.get("stock_code") or "").zfill(6) == code6) for h in db.list_holdings()):
                    snap_type = "scheduled"
                elif any(((w.get("stock_code") or "").zfill(6) == code6) for w in db.list_watchlist()):
                    snap_type = "scheduled"
            except Exception:
                pass

            saved = db.save_analysis(
                code, name, tech_for_db, decision, targets, swings,
                snapshot_type=snap_type,
                cycles=cycles, future_path=future_path, flow=flow_data,
                pattern_match=pattern_data,
            )
            if saved:
                st.success(f"{t('db_save_done')} (id: {saved.get('id')})")
        except Exception as e:
            st.warning(f"{t('analyze_db_save_warn')}: {e}")

    # 관심종목 추가 버튼
    if _db_available and db is not None:
        wcol1, wcol2 = st.columns([1, 5])
        with wcol1:
            if st.button(t("add_to_watch"), use_container_width=True):
                try:
                    db.add_watch(code, name)
                    st.success(f"{t('add_to_watch_done')}: {name}")
                except Exception as e:
                    st.error(f"❌ {e}")

    # 시그널 목록
    st.subheader(t("signals"))
    for sig in result.get("signals", []):
        st.markdown(f"- {td(sig)}")

    # 이동평균 표
    with st.expander(t("moving_averages")):
        _won = t("analyze_won_suffix")
        ma_data = {
            t("analyze_ma_period"): [t("analyze_ma_5"), t("analyze_ma_20"), t("analyze_ma_60"), t("analyze_ma_120")],
            t("analyze_ma_value"): [
                f"{result['sma_5']:,.0f}{_won}" if result["sma_5"] else "-",
                f"{result['sma_20']:,.0f}{_won}" if result["sma_20"] else "-",
                f"{result['sma_60']:,.0f}{_won}" if result["sma_60"] else "-",
                f"{result['sma_120']:,.0f}{_won}" if result["sma_120"] else "-",
            ],
        }
        st.table(ma_data)

    # 파동 정보
    with st.expander(t("ichimoku_wave")):
        c_formed_txt = t("analyze_wave_c_formed") if swings.get("c_formed") else t("analyze_wave_c_not_formed")
        st.markdown(
            t(
                "analyze_wave_body",
                a_price=swings["A"]["price"],
                a_date=swings["A"]["date"].strftime("%Y-%m-%d"),
                b_price=swings["B"]["price"],
                b_date=swings["B"]["date"].strftime("%Y-%m-%d"),
                c_price=swings["C"]["price"],
                c_date=swings["C"]["date"].strftime("%Y-%m-%d"),
                c_formed=c_formed_txt,
                v=targets["V"],
                n=targets["N"],
                e=targets["E"],
            )
        )

else:
    # 첫 화면 (분석 전)
    st.info(t("intro_prompt"))
    st.markdown("---")
    st.caption(t("disclaimer"))
