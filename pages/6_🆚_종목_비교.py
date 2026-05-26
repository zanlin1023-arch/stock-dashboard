"""[deprecated] 종목 비교 — 🎯 추천 종목 카드 내부로 통합됨."""
from __future__ import annotations

import streamlit as st

from common import init_page, sidebar_nav

st.set_page_config(page_title="종목 비교 (이동됨)", page_icon="🆚", layout="wide")
init_page("종목 비교")
sidebar_nav()

st.title("🆚 종목 비교")
st.info(
    "이 기능은 **🎯 추천 종목** 페이지 각 카드 내부의 "
    "**🏢 섹터 · 관련주 비교** expander로 통합되었습니다."
)
if st.button("🎯 추천 종목으로 이동", type="primary"):
    st.switch_page("pages/4_🎯_추천_종목.py")
