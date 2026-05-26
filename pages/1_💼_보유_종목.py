"""보유 종목 관리 — Supabase holdings 테이블 CRUD."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav

st.set_page_config(page_title="보유 종목", page_icon="💼", layout="wide")
init_page("보유 종목")
sidebar_nav()
nav_bar("holdings")

st.title("💼 보유 종목")

db = get_db()
if db is None:
    st.error("⚠️ Supabase DB가 연결되지 않았습니다. Secrets 확인하세요.")
    st.stop()


# ──────────────────────────────────────────
# 신규 등록
# ──────────────────────────────────────────
with st.expander("➕ 보유 종목 추가", expanded=False):
    with st.form("add_holding"):
        col1, col2 = st.columns(2)
        with col1:
            query = st.text_input("종목명 또는 종목코드", placeholder="예: 삼성전자 또는 005930")
            avg_price = st.number_input("평단가 (원)", min_value=1, value=10000, step=100)
        with col2:
            quantity = st.number_input("수량", min_value=1, value=10, step=1)
            purchase_date = st.date_input("매수일", value=date.today())
        note = st.text_input("메모 (선택)", placeholder="예: 분할매수 1차")
        submitted = st.form_submit_button("💾 등록", type="primary")

        if submitted and query.strip():
            try:
                from _utils import resolve_ticker
                code, name = resolve_ticker(query.strip())
                row = db.add_holding(code, name, avg_price, quantity, purchase_date, note)
                st.success(f"✅ {name} ({code}) 등록 완료")
                st.rerun()
            except Exception as e:
                st.error(f"❌ 등록 실패: {e}")


# ──────────────────────────────────────────
# 보유 목록
# ──────────────────────────────────────────
holdings = db.list_holdings()

if not holdings:
    st.info("보유 종목이 없습니다. 위에서 추가하세요.")
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
c1.metric("총 매수금액", f"{total_buy:,.0f}원")
c2.metric("총 평가금액", f"{total_eval:,.0f}원")
c3.metric("평가 손익", f"{total_pnl:+,.0f}원")
c4.metric("수익률", f"{total_pnl_pct:+.2f}%", delta_color="normal")

st.divider()

st.subheader("📋 보유 목록")
df_display = pd.DataFrame(rows).drop(columns=["id"])
st.dataframe(df_display, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────
# 삭제
# ──────────────────────────────────────────
with st.expander("🗑 종목 삭제"):
    options = {f"{r['종목']} (id={r['id']})": r["id"] for r in rows}
    selected = st.selectbox("삭제할 종목 선택", options.keys())
    if st.button("삭제", type="secondary"):
        try:
            db.delete_holding(options[selected])
            st.success("✅ 삭제 완료")
            st.rerun()
        except Exception as e:
            st.error(f"❌ 삭제 실패: {e}")
