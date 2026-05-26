"""보유 종목 관리 — Supabase holdings 테이블 CRUD."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav
from i18n import t

st.set_page_config(page_title="보유 종목", page_icon="💼", layout="wide")
init_page("보유 종목")
sidebar_nav()
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


rows = []
total_buy = 0.0
total_eval = 0.0
for h in holdings:
    cur = _fetch_current_price(h["stock_code"])
    avg = float(h["avg_price"])
    qty = int(h["quantity"])
    buy_amount = avg * qty
    eval_amount = (cur or avg) * qty
    pnl = eval_amount - buy_amount
    pnl_pct = (pnl / buy_amount * 100) if buy_amount else 0.0
    total_buy += buy_amount
    total_eval += eval_amount
    rows.append({
        "id": h["id"],
        "종목": f"{h['stock_name']} ({h['stock_code']})",
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
