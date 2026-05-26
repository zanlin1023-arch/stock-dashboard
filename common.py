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

    st.title("🔒 분석 대시보드")
    st.markdown("비밀번호를 입력하세요.")

    with st.form("login_form"):
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")
        if submitted:
            correct_pw = st.secrets.get("app_password", "")
            if not correct_pw:
                st.error("⚠️ 앱 비밀번호가 설정되지 않았습니다.")
                st.stop()
            if password == correct_pw:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("❌ 비밀번호가 틀렸습니다.")
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

    cols = st.columns([1, 1, 1, 1, 6])
    with cols[0]:
        if st.button("🏠 홈", use_container_width=True, key=f"nav_home_{current_page}"):
            st.switch_page("app.py")
    with cols[1]:
        if st.button("← 뒤로", use_container_width=True, key=f"nav_back_{current_page}"):
            history = st.session_state.get("page_history", [])
            if len(history) >= 2:
                # 현재 페이지 제거하고 이전으로
                history.pop()
                prev = history.pop()
                _switch_to(prev)
            else:
                st.switch_page("app.py")
    with cols[2]:
        if st.button("💼 보유", use_container_width=True, key=f"nav_h_{current_page}"):
            st.switch_page("pages/1_💼_보유_종목.py")
    with cols[3]:
        if st.button("⭐ 관심", use_container_width=True, key=f"nav_w_{current_page}"):
            st.switch_page("pages/2_⭐_관심_종목.py")


def _switch_to(page_name: str):
    """페이지명 → 파일 경로 매핑 후 switch_page."""
    mapping = {
        "home": "app.py",
        "holdings": "pages/1_💼_보유_종목.py",
        "watchlist": "pages/2_⭐_관심_종목.py",
        "history": "pages/3_📜_분석_히스토리.py",
    }
    target = mapping.get(page_name, "app.py")
    st.switch_page(target)


def sidebar_nav():
    """사이드바에 항상 표시되는 페이지 메뉴."""
    with st.sidebar:
        st.markdown("### 🗺 메뉴")
        st.page_link("app.py", label="🏠 홈 / 종목 분석", icon=None)
        st.page_link("pages/1_💼_보유_종목.py", label="💼 보유 종목")
        st.page_link("pages/2_⭐_관심_종목.py", label="⭐ 관심 종목")
        st.page_link("pages/3_📜_분석_히스토리.py", label="📜 분석 히스토리")
        st.divider()
