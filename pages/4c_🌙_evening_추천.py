"""추천 종목 — 🌙 evening (장 마감 후)."""
from __future__ import annotations

import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="🌙 evening 추천", page_icon="🌙", layout="wide")
init_page(t("nav_rec_evening"))
sidebar_nav()
render_macro_header()
nav_bar("recommend")

from analyzer.recommend_view_helpers import render_session_recommendations

st.title(f"🎯 {t('nav_rec_evening')}")

db = get_db()
if not db:
    st.error(t("db_disconnected"))
    st.stop()

render_session_recommendations(db, session="evening")
