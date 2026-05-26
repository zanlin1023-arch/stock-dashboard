"""관심 종목 — Supabase watchlist 테이블 CRUD."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav

st.set_page_config(page_title="관심 종목", page_icon="⭐", layout="wide")
init_page("관심 종목")
sidebar_nav()
nav_bar("watchlist")

st.title("⭐ 관심 종목")

db = get_db()
if db is None:
    st.error("⚠️ Supabase DB 미연결.")
    st.stop()


# ──────────────────────────────────────────
# 신규 추가 — 자동 채우기 지원
# ──────────────────────────────────────────
with st.expander("➕ 관심 종목 추가", expanded=False):
    # 종목명 + 자동 채우기 버튼 (form 밖 — 즉시 응답)
    c1, c2 = st.columns([3, 1])
    with c1:
        query_outside = st.text_input(
            "종목명 또는 종목코드",
            key="watch_query",
            placeholder="예: 삼성전자",
        )
    with c2:
        st.write("")  # 정렬용
        st.write("")
        auto_fill = st.button("🔮 자동 채우기", use_container_width=True, key="watch_autofill")

    # 자동 채우기 트리거
    if auto_fill and query_outside.strip():
        with st.spinner("종목 정보 수집 중..."):
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

    # 폼 (자동 채우기 결과를 디폴트로)
    with st.form("add_watch"):
        note = st.text_input(
            "메모 (선택)",
            value=st.session_state.get("watch_auto_memo", ""),
            placeholder="예: AI MLCC 테마",
        )
        tags_input = st.text_input(
            "태그 (쉼표 구분, 선택)",
            value=st.session_state.get("watch_auto_tags", ""),
            placeholder="예: 반도체, AI, 6G",
        )
        submitted = st.form_submit_button("⭐ 추가", type="primary")

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
    st.info("관심 종목이 없습니다. 위에서 추가하거나 종목 분석 화면에서 ⭐ 버튼으로 추가하세요.")
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


st.subheader(f"📋 관심 목록 ({len(rows)}개)")
df_display = pd.DataFrame(rows).drop(columns=["id"])
st.dataframe(df_display, use_container_width=True, hide_index=True)


# ──────────────────────────────────────────
# 분석으로 이동
# ──────────────────────────────────────────
st.divider()
st.subheader("🔬 빠른 분석")
options = {r["종목"]: r["종목"].split(" (")[1].rstrip(")") for r in rows}
sel = st.selectbox("분석할 종목 선택", list(options.keys()))
if st.button("🚀 분석 페이지로 이동", type="primary"):
    st.session_state["last_query"] = options[sel]
    st.switch_page("app.py")


# ──────────────────────────────────────────
# 삭제
# ──────────────────────────────────────────
with st.expander("🗑 종목 삭제"):
    del_opts = {r["종목"]: r["id"] for r in rows}
    del_sel = st.selectbox("삭제할 종목", del_opts.keys(), key="watch_del")
    if st.button("삭제", type="secondary", key="watch_del_btn"):
        try:
            db.delete_watch(del_opts[del_sel])
            st.success("✅ 삭제 완료")
            st.rerun()
        except Exception as e:
            st.error(f"❌ 삭제 실패: {e}")
