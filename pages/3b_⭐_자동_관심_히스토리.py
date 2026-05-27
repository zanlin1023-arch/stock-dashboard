"""분석 히스토리 — ⭐ 자동 · 관심 일일 스냅샷."""
from __future__ import annotations

import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="자동 관심 히스토리", page_icon="⭐", layout="wide")
init_page(t("nav_hist_auto_watch"))
sidebar_nav()
render_macro_header()
nav_bar("history")

from analyzer.history_helpers import load_history_records, _render_auto_section

st.title(f"📜 {t('nav_hist_auto_watch')}")

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

_render_auto_section(
    records=data["auto_watch"],
    key_prefix="auto_watch",
    caption_msg=t("hist_watch_caption"),
    empty_msg=t("hist_watch_empty"),
    records_title=t("hist_watch_records_title"),
)
