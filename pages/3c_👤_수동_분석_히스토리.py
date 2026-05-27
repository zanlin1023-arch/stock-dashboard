"""분석 히스토리 — 👤 수동 · 일회성 깊은 분석."""
from __future__ import annotations

import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="수동 분석 히스토리", page_icon="👤", layout="wide")
init_page(t("nav_hist_manual"))
sidebar_nav()
render_macro_header()
nav_bar("history")

from analyzer.history_helpers import load_history_records, _render_manual_section

st.title(f"📜 {t('nav_hist_manual')}")

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

_render_manual_section(data["manual"])
