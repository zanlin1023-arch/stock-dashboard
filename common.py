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
    """비밀번호 인증. 통과 시 True 반환, 미통과 시 페이지 정지.

    secrets.toml에 `skip_password = true` 설정 시 인증 우회 (개발 편의).
    """
    # DEV 우회 — secrets.toml에 skip_password = true 일 때만
    try:
        if st.secrets.get("skip_password"):
            st.session_state["authenticated"] = True
            return True
    except Exception:
        pass

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
    """페이지 진입 boilerplate. (환경설정 + 인증 + path + 현재 페이지명 저장)"""
    setup_environment()
    setup_analyzer_path()
    # require_password()  # 비밀번호 인증 비활성화 (사용자 요청)
    # sidebar_nav에서 현재 페이지에 맞는 하위 메뉴 표시용
    st.session_state["_current_page"] = page_title


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
            st.switch_page("pages/4a_🌅_morning_추천.py")
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
        "history": "pages/3a_💼_자동_보유_히스토리.py",
        "recommend": "pages/4a_🌅_morning_추천.py",
        "compare": "pages/6_🆚_종목_비교.py",
        "calendar": "pages/7_📅_캘린더.py",
        "heatmap": "pages/8_🌡️_시장_히트맵.py",
    }
    target = mapping.get(page_name, "app.py")
    st.switch_page(target)


def sidebar_nav():
    """사이드바에 항상 표시되는 페이지 메뉴 (sub-nav 포함)."""
    from i18n import t, language_selector
    language_selector("sidebar")
    with st.sidebar:
        # 들여쓴 sub-link 스타일 (page_link 대상)
        st.markdown(
            """
            <style>
            section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]
                > div.subnav-wrap {
                margin: -2px 0 6px 14px;
                padding: 2px 0 2px 10px;
                border-left: 2px solid #E0E0E0;
            }
            section[data-testid="stSidebar"] div.subnav-wrap a[data-testid="stPageLink-NavLink"] {
                padding: 2px 6px !important;
            }
            section[data-testid="stSidebar"] div.subnav-wrap a[data-testid="stPageLink-NavLink"] p,
            section[data-testid="stSidebar"] div.subnav-wrap a[data-testid="stPageLink-NavLink"] span {
                font-size: 0.82rem !important;
                color: #555 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(f"### {t('menu')}")

        def _safe_page_link(path: str, label: str):
            """Cloud 배포 race condition 방어 — 페이지 못 찾으면 스킵."""
            try:
                st.page_link(path, label=label)
            except Exception:
                pass

        _safe_page_link("app.py", t("nav_dashboard"))
        _safe_page_link("pages/5_🔬_종목_분석.py", t("nav_analyze"))

        # 🎯 추천 종목 + sub-nav (세션별)
        st.markdown(f"**{t('nav_recommend')}**")
        st.markdown('<div class="subnav-wrap">', unsafe_allow_html=True)
        _safe_page_link("pages/4a_🌅_morning_추천.py", t("nav_rec_morning"))
        _safe_page_link("pages/4c_🌙_evening_추천.py", t("nav_rec_evening"))
        st.markdown('</div>', unsafe_allow_html=True)

        _safe_page_link("pages/1_💼_보유_종목.py", t("nav_holdings"))
        _safe_page_link("pages/2_⭐_관심_종목.py", t("nav_watchlist"))

        # 📜 분석 히스토리 + sub-nav (카테고리 3개)
        st.markdown(f"**{t('nav_history')}**")
        st.markdown('<div class="subnav-wrap">', unsafe_allow_html=True)
        _safe_page_link("pages/3a_💼_자동_보유_히스토리.py", t("nav_hist_auto_hold"))
        _safe_page_link("pages/3b_⭐_자동_관심_히스토리.py", t("nav_hist_auto_watch"))
        _safe_page_link("pages/3c_👤_수동_분석_히스토리.py", t("nav_hist_manual"))
        st.markdown('</div>', unsafe_allow_html=True)

        # 종목 비교는 추천 종목 카드 내부에 통합되어 별도 메뉴 제거
        _safe_page_link("pages/7_📅_캘린더.py", t("nav_calendar"))
        _safe_page_link("pages/8_🌡️_시장_히트맵.py", t("nav_heatmap"))
        st.divider()


# ──────────────────────────────────────────
# 거시경제 헤더 (모든 페이지 상단 띠)
# ──────────────────────────────────────────
@st.cache_data(ttl=180, show_spinner=False)
def _fetch_macro() -> dict:
    """3분 캐시."""
    try:
        setup_analyzer_path()
        import macro
        return macro.get_macro_snapshot()
    except Exception:
        return {}


def render_macro_header():
    """페이지 최상단에 거시경제 지표 한 줄 띠 (KOSPI/KOSDAQ/KOSPI200/USDKRW)."""
    snap = _fetch_macro()
    if not snap:
        return
    try:
        from analyzer.macro import MACRO_META
    except Exception:
        try:
            import macro as _macro
            MACRO_META = _macro.MACRO_META
        except Exception:
            return

    parts = []
    for key in ["kospi", "kosdaq", "kospi200", "usdkrw"]:
        val = snap.get(key)
        meta = MACRO_META.get(key, {"label": key, "emoji": "📊", "unit": ""})
        if val:
            change_pct = val.get("change_pct") or 0
            color = "#E74C3C" if change_pct > 0 else ("#0064FF" if change_pct < 0 else "#7F8C8D")
            arrow = "▲" if change_pct > 0 else ("▼" if change_pct < 0 else "—")
            parts.append(
                f"<span style='display:inline-flex;align-items:baseline;gap:6px;"
                f"padding:0 16px;border-right:1px solid #E5E5E5;'>"
                f"<span style='color:#888;font-size:0.72rem;font-weight:500;'>"
                f"{meta['emoji']} {meta['label']}</span>"
                f"<strong style='font-size:0.95rem;color:#222;'>"
                f"{val['value']:,.2f}{meta['unit']}</strong>"
                f"<span style='color:{color};font-size:0.78rem;font-weight:600;'>"
                f"{arrow} {change_pct:+.2f}%</span>"
                f"</span>"
            )
        else:
            parts.append(
                f"<span style='display:inline-flex;align-items:baseline;gap:6px;"
                f"padding:0 16px;border-right:1px solid #E5E5E5;color:#BBB;'>"
                f"<span style='font-size:0.72rem;'>{meta['emoji']} {meta['label']}</span>"
                f"<span style='font-size:0.85rem;'>—</span></span>"
            )

    if not parts:
        return

    # 마지막 항목 우측 border 제거
    parts[-1] = parts[-1].replace(
        "border-right:1px solid #E5E5E5;", ""
    )
    html = (
        "<div style='background:#FAFAFA;border:1px solid #EEE;border-radius:6px;"
        "padding:8px 4px;margin:0 0 12px 0;line-height:1.8;"
        "white-space:nowrap;overflow-x:auto;text-align:center;'>"
        + "".join(parts) +
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)
