"""분석 히스토리 — 💼 자동 · 보유 일일 스냅샷."""
from __future__ import annotations

import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="자동 보유 히스토리", page_icon="💼", layout="wide")
init_page(t("nav_hist_auto_hold"))
sidebar_nav()
render_macro_header()
nav_bar("history")

from analyzer.history_helpers import load_history_records, _render_auto_section

st.title(f"📜 {t('nav_hist_auto_hold')}")

db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()

data = load_history_records(db)
if data.get("client_fail"):
    st.error(t("history_db_client_fail"))
    st.stop()
if data.get("empty"):
    st.info(t("history_empty"))
    st.stop()

# 보유 평단가 lookup (V/N/E 표시에 평단 대비 % 추가)
holdings_map = {}
try:
    for h in db.list_holdings():
        code = (h.get("stock_code") or "").zfill(6)
        avg = h.get("avg_price")
        if code and avg:
            holdings_map[code] = float(avg)
except Exception:
    pass

_render_auto_section(
    records=data["auto_hold"],
    key_prefix="auto_hold",
    caption_msg=t("hist_auto_caption"),
    empty_msg=t("hist_auto_empty"),
    records_title=t("hist_auto_records_title"),
    holdings_map=holdings_map,
)
