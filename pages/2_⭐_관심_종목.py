"""관심 종목 — Supabase watchlist 테이블 CRUD."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav
from i18n import t

st.set_page_config(page_title="관심 종목", page_icon="⭐", layout="wide")
init_page("관심 종목")
sidebar_nav()
nav_bar("watchlist")

st.title(t("watchlist_title"))

db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()


# ──────────────────────────────────────────
# 신규 추가 — 자동 채우기 지원
# ──────────────────────────────────────────
with st.expander(t("watchlist_add"), expanded=False):
    c1, c2 = st.columns([3, 1])
    with c1:
        query_outside = st.text_input(
            t("search_input"),
            key="watch_query",
            placeholder=t("search_placeholder"),
        )
    with c2:
        st.write("")
        st.write("")
        auto_fill = st.button(t("btn_autofill"), use_container_width=True, key="watch_autofill")

    if auto_fill and query_outside.strip():
        with st.spinner(t("autofill_loading")):
            try:
                from _utils import resolve_ticker
                from enrich import enrich_stock
                code, name = resolve_ticker(query_outside.strip())
                info = enrich_stock(code, name)
                st.session_state["watch_auto_memo"] = info.get("memo", "")
                st.session_state["watch_auto_tags"] = ", ".join(info.get("themes") or [])
                st.session_state["watch_auto_code"] = code
                st.session_state["watch_auto_name"] = name
                src_emoji = {"claude": "🤖", "openai": "🤖", "naver": "🌐", "fdr": "📊"}.get(info.get("source"), "📋")
                st.success(f"{src_emoji} {name} ({code}) | 출처: {info.get('source')}")
            except Exception as e:
                st.error(f"자동 채우기 실패: {e}")

    with st.form("add_watch"):
        note = st.text_input(
            t("note_optional"),
            value=st.session_state.get("watch_auto_memo", ""),
        )
        tags_input = st.text_input(
            t("tags_optional"),
            value=st.session_state.get("watch_auto_tags", ""),
        )
        submitted = st.form_submit_button(t("add_to_watch"), type="primary")

        if submitted:
            target_query = query_outside.strip() or st.session_state.get("watch_auto_name", "")
            if not target_query:
                st.warning("종목명을 입력하세요")
            else:
                try:
                    from _utils import resolve_ticker
                    code, name = resolve_ticker(target_query)
                    tags = [t.strip() for t in tags_input.split(",") if t.strip()]
                    db.add_watch(code, name, note, tags)
                    # 자동 채우기 세션 정리
                    for k in ["watch_auto_memo", "watch_auto_tags", "watch_auto_code", "watch_auto_name"]:
                        st.session_state.pop(k, None)
                    st.success(f"✅ {name} ({code}) 추가됨")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ 추가 실패: {e}")


# ──────────────────────────────────────────
# 관심 목록
# ──────────────────────────────────────────
watchlist = db.list_watchlist()

if not watchlist:
    st.info(t("watchlist_empty"))
    st.stop()


@st.cache_data(ttl=300)
def _fetch_current(code: str):
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
        import technical
        df = technical.fetch_ohlcv(code, days=10)
        if df.empty:
            return None, None
        last = float(df["close"].iloc[-1])
        prev = float(df["close"].iloc[-2]) if len(df) > 1 else last
        chg = (last / prev - 1) * 100 if prev else 0.0
        return last, chg
    except Exception:
        return None, None


rows = []
for w in watchlist:
    cur, chg = _fetch_current(w["stock_code"])
    rows.append({
        "id": w["id"],
        "종목": f"{w['stock_name']} ({w['stock_code']})",
        "현재가": f"{cur:,.0f}" if cur else "-",
        "전일대비": f"{chg:+.2f}%" if chg is not None else "-",
        "태그": ", ".join(w.get("tags") or []) or "-",
        "메모": w.get("note", "") or "-",
        "추가일": w.get("added_at", "")[:10] if w.get("added_at") else "-",
    })


st.subheader(f"{t('watchlist_list')} ({len(rows)})")
df_display = pd.DataFrame(rows).drop(columns=["id"])
st.dataframe(df_display, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────
# 분석으로 이동
# ──────────────────────────────────────────
st.divider()
st.subheader(t("quick_analyze"))
options = {r["종목"]: r["종목"].split(" (")[1].rstrip(")") for r in rows}
sel = st.selectbox(t("select_to_analyze"), list(options.keys()))
if st.button(t("goto_analyze"), type="primary"):
    st.session_state["last_query"] = options[sel]
    st.switch_page("app.py")


# ──────────────────────────────────────────
# 삭제
# ──────────────────────────────────────────
with st.expander(t("delete_stock")):
    del_opts = {r["종목"]: r["id"] for r in rows}
    del_sel = st.selectbox(t("delete_target"), del_opts.keys(), key="watch_del")
    if st.button(t("btn_delete"), type="secondary", key="watch_del_btn"):
        try:
            db.delete_watch(del_opts[del_sel])
            st.success(t("delete_done"))
            st.rerun()
        except Exception as e:
            st.error(f"❌ {e}")
