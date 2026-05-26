"""보유 종목 관리 — Supabase holdings 테이블 CRUD."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="보유 종목", page_icon="💼", layout="wide")
init_page("보유 종목")
sidebar_nav()
render_macro_header()
nav_bar("holdings")

st.title(t("holdings_title"))

db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()


# ──────────────────────────────────────────
# 신규 등록
# ──────────────────────────────────────────
with st.expander(t("holdings_add"), expanded=False):
    # 종목명 + 자동 채우기 (form 밖)
    qc1, qc2 = st.columns([3, 1])
    with qc1:
        query_outside = st.text_input(
            t("search_input"),
            key="hold_query",
            placeholder=t("search_placeholder"),
        )
    with qc2:
        st.write("")
        st.write("")
        auto_btn = st.button(t("btn_autofill"), use_container_width=True, key="hold_autofill")

    if auto_btn and query_outside.strip():
        with st.spinner(t("autofill_loading")):
            try:
                from _utils import resolve_ticker
                from enrich import enrich_stock
                code, name = resolve_ticker(query_outside.strip())
                info = enrich_stock(code, name)
                st.session_state["hold_auto_note"] = info.get("memo", "")
                st.session_state["hold_auto_name"] = name
                st.session_state["hold_auto_code"] = code
                src_emoji = {"claude": "🤖", "openai": "🤖", "naver": "🌐", "fdr": "📊"}.get(info.get("source"), "📋")
                st.success(f"{src_emoji} {name} ({code}) | 출처: {info.get('source')}")
            except Exception as e:
                st.error(f"자동 채우기 실패: {e}")

    with st.form("add_holding"):
        col1, col2 = st.columns(2)
        with col1:
            avg_price = st.number_input(t("avg_price"), min_value=1, value=10000, step=100)
        with col2:
            quantity = st.number_input(t("quantity"), min_value=1, value=10, step=1)
        col3, col4 = st.columns(2)
        with col3:
            date_unknown = st.checkbox(t("purchase_date_unknown"), value=False)
        with col4:
            purchase_date = st.date_input(
                t("purchase_date"),
                value=date.today(),
                disabled=date_unknown,
            )
        note = st.text_input(
            t("note_optional"),
            value=st.session_state.get("hold_auto_note", ""),
        )
        submitted = st.form_submit_button(t("btn_register"), type="primary")

        if submitted:
            target_query = query_outside.strip() or st.session_state.get("hold_auto_name", "")
            if not target_query:
                st.warning("종목명을 입력하세요")
            else:
                try:
                    from _utils import resolve_ticker
                    code, name = resolve_ticker(target_query)
                    use_date = None if date_unknown else purchase_date
                    db.add_holding(code, name, avg_price, quantity, use_date, note)
                    for k in ["hold_auto_note", "hold_auto_name", "hold_auto_code"]:
                        st.session_state.pop(k, None)
                    st.success(f"✅ {name} ({code}) 등록 완료")

                    # 신규 등록 즉시 1회 종목 분석 → 히스토리에 저장
                    with st.spinner(f"🔬 {name} 자동 분석 중..."):
                        try:
                            import technical
                            from chart_ichimoku import (
                                compute_ichimoku, detect_swing_points,
                                compute_price_targets, make_decision,
                                compute_time_cycles, project_future_path,
                            )
                            df_ana = technical.fetch_ohlcv(code, days=180)
                            df_ana = technical.add_indicators(df_ana)
                            df_ana = compute_ichimoku(df_ana)
                            result = technical.analyze(code, name)
                            swings = detect_swing_points(df_ana, lookback=min(80, len(df_ana)))
                            A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
                            targets = compute_price_targets(A, B, C)
                            decision = make_decision(df_ana, swings, targets)

                            tech_for_db = dict(result)
                            for col in ["tenkan", "kijun", "senkou_a", "senkou_b"]:
                                if col in df_ana.columns and df_ana[col].notna().any():
                                    tech_for_db[col] = float(df_ana[col].iloc[-1])

                            # 시간 사이클 + 미래 추세 경로 + 수급 — DB 누적 분석용
                            cycles = compute_time_cycles(swings["C"]["idx"], len(df_ana))
                            future_path = project_future_path(
                                decision["price"], cycles, targets, decision.get("stop"),
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

                            saved = db.save_analysis(
                                code, name, tech_for_db, decision, targets, swings,
                                snapshot_type="manual",
                                cycles=cycles,
                                future_path=future_path,
                                flow=flow_data,
                            )
                            if saved:
                                st.success(f"📥 분석 히스토리 저장 완료 — {decision.get('action', '')}")
                        except Exception as ana_err:
                            st.warning(f"⚠️ 자동 분석 실패 (등록은 완료): {ana_err}")

                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 등록 실패: {e}")


# ──────────────────────────────────────────
# 보유 목록
# ──────────────────────────────────────────
holdings = db.list_holdings()

if not holdings:
    st.info(t("holdings_empty"))
    st.stop()


# 실시간 시세 + 손익 계산
@st.cache_data(ttl=300)
def _fetch_current_price(code: str) -> float | None:
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
        import technical
        df = technical.fetch_ohlcv(code, days=10)
        return float(df["close"].iloc[-1]) if not df.empty else None
    except Exception:
        return None


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_meta(code: str, name: str) -> dict:
    """업종/테마 (24h 캐시)."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
        import enrich
        m = enrich._enrich_via_naver(code, name)
        return {
            "sector": (m.get("sector") or "").strip(),
            "themes": m.get("themes") or [],
        }
    except Exception:
        return {"sector": "", "themes": []}


rows = []
total_buy = 0.0
total_eval = 0.0
for h in holdings:
    cur = _fetch_current_price(h["stock_code"])
    meta = _fetch_meta(h["stock_code"], h["stock_name"])
    avg = float(h["avg_price"])
    qty = int(h["quantity"])
    buy_amount = avg * qty
    eval_amount = (cur or avg) * qty
    pnl = eval_amount - buy_amount
    pnl_pct = (pnl / buy_amount * 100) if buy_amount else 0.0
    total_buy += buy_amount
    total_eval += eval_amount
    themes_str = " · ".join(meta["themes"][:3])
    rows.append({
        "id": h["id"],
        "종목": f"{h['stock_name']} ({h['stock_code']})",
        "섹터": meta["sector"] or "-",
        "테마": themes_str or "-",
        "평단가": f"{avg:,.0f}",
        "현재가": f"{cur:,.0f}" if cur else "-",
        "수량": qty,
        "매수금액": f"{buy_amount:,.0f}",
        "평가금액": f"{eval_amount:,.0f}",
        "손익": f"{pnl:+,.0f}",
        "수익률": f"{pnl_pct:+.2f}%",
        "매수일": h["purchase_date"],
        "메모": h.get("note", "") or "",
    })


# 포트폴리오 요약
total_pnl = total_eval - total_buy
total_pnl_pct = (total_pnl / total_buy * 100) if total_buy else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric(t("total_buy"), f"{total_buy:,.0f}")
c2.metric(t("total_eval"), f"{total_eval:,.0f}")
c3.metric(t("total_pnl"), f"{total_pnl:+,.0f}")
c4.metric(t("pnl_pct"), f"{total_pnl_pct:+.2f}%", delta_color="normal")

st.divider()

st.subheader(t("holdings_list"))
df_display = pd.DataFrame(rows).drop(columns=["id"])
st.dataframe(df_display, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────
# 삭제
# ──────────────────────────────────────────
with st.expander(t("delete_stock")):
    options = {f"{r['종목']} (id={r['id']})": r["id"] for r in rows}
    selected = st.selectbox(t("delete_target"), options.keys())
    if st.button(t("btn_delete"), type="secondary"):
        try:
            db.delete_holding(options[selected])
            st.success(t("delete_done"))
            st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")
