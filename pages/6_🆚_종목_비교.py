"""[deprecated] 종목 비교 — 🎯 추천 종목 카드 내부로 통합됨."""
from __future__ import annotations

import streamlit as st

from common import init_page, sidebar_nav
from i18n import t

st.set_page_config(page_title="종목 비교 (이동됨)", page_icon="🆚", layout="wide")
init_page(t("compare_title"))
sidebar_nav()

st.title(t("compare_title"))
st.info(t("compare_moved_info"))
if st.button(t("compare_goto_recommend"), type="primary"):
    st.switch_page("pages/4_🎯_추천_종목.py")
