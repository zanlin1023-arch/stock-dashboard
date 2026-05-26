"""분석 히스토리 — Supabase analysis_history 테이블 조회."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav
from i18n import t

st.set_page_config(page_title="분석 히스토리", page_icon="📜", layout="wide")
init_page("분석 히스토리")
sidebar_nav()
nav_bar("history")

st.title(t("history_title"))

db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()


# ──────────────────────────────────────────
# 종목 필터 (또는 전체)
# ──────────────────────────────────────────
client = db.get_client()
if not client:
    st.error("DB 클라이언트 로드 실패")
    st.stop()

# 전체 데이터 조회
res = client.table("analysis_history").select("*").order("analyzed_at", desc=True).limit(500).execute()
all_records = res.data or []

if not all_records:
    st.info(t("history_empty"))
    st.stop()


# 필터 — 종목 + 스냅샷 종류
fcol1, fcol2 = st.columns([2, 1])
with fcol1:
    codes = sorted({(r["stock_code"], r["stock_name"]) for r in all_records}, key=lambda x: x[1])
    options = [t("filter_all")] + [f"{name} ({code})" for code, name in codes]
    sel = st.selectbox(t("filter_stock"), options)

with fcol2:
    snapshot_options = [t("snapshot_all"), t("snapshot_manual"), t("snapshot_scheduled")]
    snapshot_filter = st.selectbox(t("filter_snapshot"), snapshot_options)

filtered = all_records
if sel != t("filter_all"):
    sel_code = sel.split("(")[-1].rstrip(")")
    filtered = [r for r in filtered if r["stock_code"] == sel_code]

if snapshot_filter == t("snapshot_manual"):
    filtered = [r for r in filtered if r.get("snapshot_type") == "manual"]
elif snapshot_filter == t("snapshot_scheduled"):
    filtered = [r for r in filtered if r.get("snapshot_type") == "scheduled"]


# ──────────────────────────────────────────
# 통계 카드
# ──────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric(t("total_count"), f"{len(filtered)}")
c2.metric(t("stock_count"), f"{len({r['stock_code'] for r in filtered})}")
stances = [r.get("decision_stance") for r in filtered if r.get("decision_stance")]
buy_count = sum(1 for s in stances if s in ("STRONG_BUY", "BUY"))
sell_count = sum(1 for s in stances if s in ("STRONG_SELL", "SELL"))
c3.metric(t("buy_count"), f"{buy_count}")
c4.metric(t("sell_count"), f"{sell_count}")

st.divider()


# ──────────────────────────────────────────
# 테이블
# ──────────────────────────────────────────
rows = []
for r in filtered:
    rows.append({
        "분석시각": r.get("analyzed_at", "")[:19].replace("T", " "),
        "타입": "🤖 자동" if r.get("snapshot_type") == "scheduled" else "👤 수동",
        "종목": f"{r.get('stock_name', '')} ({r.get('stock_code', '')})",
        "현재가": f"{r['price']:,.0f}" if r.get("price") else "-",
        "RSI": f"{r['rsi_14']:.1f}" if r.get("rsi_14") else "-",
        "구름위치": {
            "above": "위 ↑", "below": "아래 ↓", "inside": "안 ↔",
        }.get(r.get("cloud_position", ""), "-"),
        "판단": r.get("decision_action", "-") or "-",
        "N목표": f"{r['target_n']:,.0f}" if r.get("target_n") else "-",
        "손절": f"{r['stop_loss']:,.0f}" if r.get("stop_loss") else "-",
    })

st.subheader(f"📊 분석 기록 ({len(rows)}건)")
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ──────────────────────────────────────────
# 종목별 추이 (선택 시)
# ──────────────────────────────────────────
if sel != "(전체)" and len(filtered) >= 2:
    st.divider()
    st.subheader(f"📈 {sel} 추이")
    trend_df = pd.DataFrame([
        {
            "시각": r["analyzed_at"][:10],
            "현재가": float(r["price"]) if r.get("price") else None,
            "RSI": float(r["rsi_14"]) if r.get("rsi_14") else None,
            "N목표": float(r["target_n"]) if r.get("target_n") else None,
        }
        for r in filtered if r.get("price")
    ]).sort_values("시각")

    if not trend_df.empty:
        tab1, tab2 = st.tabs(["가격 추이", "RSI 추이"])
        with tab1:
            st.line_chart(trend_df.set_index("시각")[["현재가", "N목표"]])
        with tab2:
            st.line_chart(trend_df.set_index("시각")["RSI"])
