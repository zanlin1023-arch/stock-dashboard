"""Streamlit 공통: 환경설정 + 비밀번호 인증 + analyzer path."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st


def setup_environment():
    """Streamlit secrets → os.environ 주입 (analyzer 모듈이 os.getenv 사용)."""
    secret_keys = [
        "OPENDART_API_KEY",
        "ANTHROPIC_API_KEY",  # 종목 자동 채우기 (Claude)
        "OPENAI_API_KEY",     # 종목 자동 채우기 (대안)
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_DB_PASSWORD",
        "PG_HOST",
        "PG_PORT",
        "PG_USER",
        "PG_DATABASE",
    ]
    for key in secret_keys:
        if key in st.secrets:
            os.environ[key] = str(st.secrets[key])


def setup_analyzer_path():
    """analyzer 패키지를 sys.path에 추가."""
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "analyzer"))


def require_password():
    """비밀번호 인증. 통과 시 True 반환, 미통과 시 페이지 정지."""
    if st.session_state.get("authenticated"):
        return True

    from i18n import t, language_selector
    language_selector("main")  # 로그인 화면에도 언어 선택

    st.title(t("auth_title"))
    st.markdown(t("auth_prompt"))

    with st.form("login_form"):
        password = st.text_input(t("auth_password"), type="password")
        submitted = st.form_submit_button(t("auth_login"))
        if submitted:
            correct_pw = st.secrets.get("app_password", "")
            if not correct_pw:
                st.error(t("auth_no_pw"))
                st.stop()
            if password == correct_pw:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error(t("auth_wrong"))
    st.stop()


def init_page(page_title: str = "분석 대시보드"):
    """페이지 진입 boilerplate. (환경설정 + 인증 + path)"""
    setup_environment()
    setup_analyzer_path()
    require_password()


def get_db():
    """analyzer.db 모듈 또는 None."""
    try:
        from analyzer import db
        if db.is_db_available():
            return db
    except Exception:
        pass
    return None


# ──────────────────────────────────────────
# 네비게이션 (홈/이전 페이지)
# ──────────────────────────────────────────
def nav_bar(current_page: str = ""):
    """페이지 상단 네비게이션 — 홈 + 이전 페이지."""
    # 페이지 히스토리 관리
    if "page_history" not in st.session_state:
        st.session_state["page_history"] = []
    if current_page and (
        not st.session_state["page_history"]
        or st.session_state["page_history"][-1] != current_page
    ):
        st.session_state["page_history"].append(current_page)

    from i18n import t
    cols = st.columns([1, 1, 1, 1, 1, 5])
    with cols[0]:
        if st.button(t("btn_home"), use_container_width=True, key=f"nav_home_{current_page}"):
            st.switch_page("app.py")
    with cols[1]:
        if st.button(t("btn_back"), use_container_width=True, key=f"nav_back_{current_page}"):
            history = st.session_state.get("page_history", [])
            if len(history) >= 2:
                history.pop()
                prev = history.pop()
                _switch_to(prev)
            else:
                st.switch_page("app.py")
    with cols[2]:
        if st.button(t("btn_recommend_short"), use_container_width=True, key=f"nav_r_{current_page}"):
            st.switch_page("pages/4_🎯_추천_종목.py")
    with cols[3]:
        if st.button(t("btn_holdings_short"), use_container_width=True, key=f"nav_h_{current_page}"):
            st.switch_page("pages/1_💼_보유_종목.py")
    with cols[4]:
        if st.button(t("btn_watchlist_short"), use_container_width=True, key=f"nav_w_{current_page}"):
            st.switch_page("pages/2_⭐_관심_종목.py")


def _switch_to(page_name: str):
    """페이지명 → 파일 경로 매핑 후 switch_page."""
    mapping = {
        "home": "app.py",
        "dashboard": "app.py",
        "analyze": "pages/5_🔬_종목_분석.py",
        "holdings": "pages/1_💼_보유_종목.py",
        "watchlist": "pages/2_⭐_관심_종목.py",
        "history": "pages/3_📜_분석_히스토리.py",
        "recommend": "pages/4_🎯_추천_종목.py",
    }
    target = mapping.get(page_name, "app.py")
    st.switch_page(target)


def sidebar_nav():
    """사이드바에 항상 표시되는 페이지 메뉴."""
    from i18n import t, language_selector
    language_selector("sidebar")
    with st.sidebar:
        st.markdown(f"### {t('menu')}")
        st.page_link("app.py", label=t("nav_dashboard"), icon=None)
        st.page_link("pages/5_🔬_종목_분석.py", label=t("nav_analyze"))
        st.page_link("pages/4_🎯_추천_종목.py", label=t("nav_recommend"))
        st.page_link("pages/1_💼_보유_종목.py", label=t("nav_holdings"))
        st.page_link("pages/2_⭐_관심_종목.py", label=t("nav_watchlist"))
        st.page_link("pages/3_📜_분석_히스토리.py", label=t("nav_history"))
        st.divider()
