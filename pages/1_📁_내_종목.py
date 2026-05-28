"""📁 내 종목 — 보유(holdings) + 관심(watchlist) 통합 페이지.

기존의 `1_💼_보유_종목.py` + `2_⭐_관심_종목.py`를 하나로 합친 통합 페이지.
필터(전체/보유만/관심만) + 통합 테이블 + 추가/삭제/유형 전환 기능 제공.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t, td

st.set_page_config(page_title="내 종목", page_icon="📁", layout="wide")
init_page(t("nav_my_stocks"))
sidebar_nav()
render_macro_header()
nav_bar("my_stocks")

# 타이틀: i18n 키에 이미 📁 포함되어 있어 prefix 제거 (이모지 중복 방지)
st.title(t("nav_my_stocks"))

db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()


# ──────────────────────────────────────────
# 시세 / 메타 조회 (기존 1·2번 페이지의 캐시 함수 통합)
# ──────────────────────────────────────────
@st.cache_data(ttl=60)  # 5분 → 1분 (장중 갱신 빠르게)
def _fetch_current_price(code: str):
    """현재가 + 전일대비(%) — 네이버 실시간 우선(장중 ~1분 지연), 실패 시 FDR 일봉."""
    # 1차: 네이버 모바일 /basic 실시간 (closePrice=현재가, 장중 반영 빠름)
    try:
        import requests
        r = requests.get(
            f"https://m.stock.naver.com/api/stock/{code}/basic",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.stock.naver.com/"},
            timeout=5,
        )
        if r.status_code == 200:
            data = r.json() or {}
            cur = data.get("closePrice")
            chg = data.get("fluctuationsRatio")
            if cur:
                cur = float(str(cur).replace(",", ""))
                try:
                    chg = float(str(chg).replace(",", "")) if chg is not None else 0.0
                except (TypeError, ValueError):
                    chg = 0.0
                return cur, chg
    except Exception:
        pass
    # 2차: FDR 일봉 (장 마감/주말 fallback)
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


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_meta(code: str, name: str) -> dict:
    """업종/테마 (24h 캐시)."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
        import enrich
        m = enrich._enrich_via_naver(code, name)
        return {
            "sector": (m.get("sector") or "").strip(),
            "themes": m.get("themes") or [],
        }
    except Exception:
        return {"sector": "", "themes": []}


# ──────────────────────────────────────────
# 데이터 로드 + 병렬 prefetch (시세 + 메타) — A+C 최적화
# ──────────────────────────────────────────
holdings = db.list_holdings() or []
watchlist = db.list_watchlist() or []

# A: 종목별 시세 + 메타를 ThreadPool로 병렬 prefetch (캐시 워밍업)
# C: @st.cache_data 5분 → 두 번째 진입은 즉시
_all_codes_meta = [(h["stock_code"], h["stock_name"]) for h in holdings] + \
                  [(w["stock_code"], w["stock_name"]) for w in watchlist]
if _all_codes_meta:
    from concurrent.futures import ThreadPoolExecutor
    with st.spinner(f"⏳ 시세/섹터 조회 중 ({len(_all_codes_meta)}개)..."):
        with ThreadPoolExecutor(max_workers=10) as _ex:
            list(_ex.map(_fetch_current_price, [c for c, _ in _all_codes_meta]))
            list(_ex.map(lambda x: _fetch_meta(x[0], x[1]), _all_codes_meta))


# ──────────────────────────────────────────
# 상단 컨트롤 — 필터
# ──────────────────────────────────────────
filter_options = {
    t("mystocks_filter_all"): "all",
    t("mystocks_filter_holdings"): "holdings",
    t("mystocks_filter_watchlist"): "watchlist",
}
filter_choice = st.radio(
    "🔍",
    list(filter_options.keys()),
    horizontal=True,
    label_visibility="collapsed",
    key="my_stocks_filter",
)
filter_mode = filter_options[filter_choice]


# ──────────────────────────────────────────
# 통합 row 빌드 + 통계
# ──────────────────────────────────────────
_lbl_type = t("mystocks_type")
_lbl_stock = t("holdings_col_stock")
_lbl_sector = t("holdings_col_sector")
_lbl_theme = t("holdings_col_theme")
_lbl_avg = t("holdings_col_avg")
_lbl_cur = t("holdings_col_cur")
_lbl_prev = t("watchlist_col_prev")
_lbl_qty = t("holdings_col_qty")
_lbl_buy_amt = t("holdings_col_buy_amt")
_lbl_eval_amt = t("holdings_col_eval_amt")
_lbl_pnl = t("holdings_col_pnl")
_lbl_pnl_pct = t("holdings_col_pnl_pct")
_lbl_buy_date = t("holdings_col_buy_date")
_lbl_note = t("holdings_col_note")
_lbl_tags = t("watchlist_col_tags")

_type_hold = t("mystocks_type_holding")
_type_watch = t("mystocks_type_watch")

rows: list[dict] = []
total_buy = 0.0
total_eval = 0.0
hold_count = len(holdings)

if filter_mode in ("all", "holdings"):
    for h in holdings:
        cur, chg = _fetch_current_price(h["stock_code"])
        meta = _fetch_meta(h["stock_code"], h["stock_name"])
        avg = float(h["avg_price"])
        qty = int(h["quantity"])
        buy_amount = avg * qty
        eval_amount = (cur or avg) * qty
        pnl = eval_amount - buy_amount
        pnl_pct = (pnl / buy_amount * 100) if buy_amount else 0.0
        total_buy += buy_amount
        total_eval += eval_amount
        themes_str = " · ".join(meta["themes"][:3])
        rows.append({
            "_id": h["id"],
            "_kind": "holding",
            "_code": h["stock_code"],
            "_name": h["stock_name"],
            _lbl_type: _type_hold,
            _lbl_stock: f"{h['stock_name']} ({h['stock_code']})",
            _lbl_sector: meta["sector"] or "-",
            _lbl_theme: themes_str or "-",
            _lbl_avg: f"{avg:,.0f}",
            _lbl_cur: f"{cur:,.0f}" if cur else "-",
            _lbl_prev: f"{chg:+.2f}%" if chg is not None else "-",
            _lbl_qty: qty,
            _lbl_buy_amt: f"{buy_amount:,.0f}",
            _lbl_eval_amt: f"{eval_amount:,.0f}",
            _lbl_pnl: f"{pnl:+,.0f}",
            _lbl_pnl_pct: f"{pnl_pct:+.2f}%",
            _lbl_buy_date: str(h.get("purchase_date") or "-"),
            _lbl_note: h.get("note", "") or "",
            _lbl_tags: "-",
        })

if filter_mode in ("all", "watchlist"):
    for w in watchlist:
        cur, chg = _fetch_current_price(w["stock_code"])
        meta = _fetch_meta(w["stock_code"], w["stock_name"])
        themes_str = " · ".join(meta["themes"][:3])
        added = w.get("added_at", "")
        added_str = added[:10] if added else "-"
        rows.append({
            "_id": w["id"],
            "_kind": "watch",
            "_code": w["stock_code"],
            "_name": w["stock_name"],
            _lbl_type: _type_watch,
            _lbl_stock: f"{w['stock_name']} ({w['stock_code']})",
            _lbl_sector: meta["sector"] or "-",
            _lbl_theme: themes_str or "-",
            _lbl_avg: "-",
            _lbl_cur: f"{cur:,.0f}" if cur else "-",
            _lbl_prev: f"{chg:+.2f}%" if chg is not None else "-",
            _lbl_qty: "-",
            _lbl_buy_amt: "-",
            _lbl_eval_amt: "-",
            _lbl_pnl: "-",
            _lbl_pnl_pct: "-",
            _lbl_buy_date: added_str,
            _lbl_note: w.get("note", "") or "-",
            _lbl_tags: ", ".join(w.get("tags") or []) or "-",
        })


# ──────────────────────────────────────────
# 통계 카드 (4개)
# ──────────────────────────────────────────
total_pnl = total_eval - total_buy
total_pnl_pct = (total_pnl / total_buy * 100) if total_buy else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric(t("mystocks_holdings_count"), f"{hold_count:,}")
c2.metric(t("total_buy"), f"{total_buy:,.0f}")
c3.metric(t("total_eval"), f"{total_eval:,.0f}")
c4.metric(
    t("total_pnl"),
    f"{total_pnl:+,.0f}",
    delta=f"{total_pnl_pct:+.2f}%" if total_buy else None,
)

st.divider()


# ──────────────────────────────────────────
# 통합 테이블
# ──────────────────────────────────────────
if not rows:
    if filter_mode == "holdings":
        st.info(t("holdings_empty"))
    elif filter_mode == "watchlist":
        st.info(t("watchlist_empty"))
    else:
        st.info(t("holdings_empty"))
else:
    df_display = pd.DataFrame(rows).drop(columns=["_id", "_kind", "_code", "_name"])
    st.dataframe(df_display, use_container_width=True, hide_index=True)


st.divider()


# ──────────────────────────────────────────
# ➕ 종목 추가
# ──────────────────────────────────────────
with st.expander(t("mystocks_add_section"), expanded=False):
    add_kind = st.radio(
        t("mystocks_add_type"),
        [_type_hold, _type_watch],
        horizontal=True,
        key="add_kind_radio",
    )

    # 종목명 + 자동 채우기 (form 밖)
    qc1, qc2 = st.columns([3, 1])
    with qc1:
        query_outside = st.text_input(
            t("search_input"),
            key="mystocks_query",
            placeholder=t("search_placeholder"),
        )
    with qc2:
        st.write("")
        st.write("")
        auto_btn = st.button(t("btn_autofill"), use_container_width=True, key="mystocks_autofill")

    if auto_btn and query_outside.strip():
        with st.spinner(t("autofill_loading")):
            try:
                from _utils import resolve_ticker
                from enrich import enrich_stock
                code, name = resolve_ticker(query_outside.strip())
                info = enrich_stock(code, name)
                st.session_state["mystocks_auto_note"] = info.get("memo", "")
                st.session_state["mystocks_auto_tags"] = ", ".join(info.get("themes") or [])
                st.session_state["mystocks_auto_name"] = name
                st.session_state["mystocks_auto_code"] = code
                src_emoji = {"claude": "🤖", "openai": "🤖", "naver": "🌐", "fdr": "📊"}.get(info.get("source"), "📋")
                st.success(f"{src_emoji} {name} ({code}) | {t('holdings_source')}: {info.get('source')}")
            except Exception as e:
                st.error(f"{t('holdings_autofill_fail')}: {e}")

    if add_kind == _type_hold:
        with st.form("add_holding_form"):
            col1, col2 = st.columns(2)
            with col1:
                avg_price = st.number_input(t("avg_price"), min_value=1, value=10000, step=100)
            with col2:
                quantity = st.number_input(t("quantity"), min_value=1, value=10, step=1)
            col3, col4 = st.columns(2)
            with col3:
                date_unknown = st.checkbox(t("purchase_date_unknown"), value=False)
            with col4:
                purchase_date = st.date_input(
                    t("purchase_date"),
                    value=date.today(),
                    disabled=date_unknown,
                )
            note = st.text_input(
                t("note_optional"),
                value=st.session_state.get("mystocks_auto_note", ""),
            )
            submitted = st.form_submit_button(t("btn_register"), type="primary")

            if submitted:
                target_query = query_outside.strip() or st.session_state.get("mystocks_auto_name", "")
                if not target_query:
                    st.warning(t("holdings_input_name_required"))
                else:
                    try:
                        from _utils import resolve_ticker
                        code, name = resolve_ticker(target_query)
                        use_date = None if date_unknown else purchase_date
                        db.add_holding(code, name, avg_price, quantity, use_date, note)
                        for k in [
                            "mystocks_auto_note", "mystocks_auto_tags",
                            "mystocks_auto_name", "mystocks_auto_code",
                        ]:
                            st.session_state.pop(k, None)
                        st.success(f"✅ {name} ({code}) {t('holdings_register_done')}")

                        # 신규 등록 즉시 1회 종목 분석 → 히스토리에 저장
                        with st.spinner(f"🔬 {name} {t('holdings_auto_analyzing')}"):
                            try:
                                import technical
                                from chart_ichimoku import (
                                    compute_ichimoku, detect_swing_points,
                                    compute_price_targets, cap_targets, make_decision,
                                    compute_time_cycles, project_future_path,
                                )
                                df_ana = technical.fetch_ohlcv(code, days=180)
                                df_ana = technical.add_indicators(df_ana)
                                df_ana = compute_ichimoku(df_ana)
                                result = technical.analyze(code, name)
                                swings = detect_swing_points(df_ana, lookback=min(80, len(df_ana)))
                                A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
                                targets = compute_price_targets(A, B, C)
                                # ATR cap 통일 (전 경로 동일 목표가)
                                _atr_val = (
                                    float(df_ana["atr_14"].iloc[-1])
                                    if "atr_14" in df_ana.columns
                                    and df_ana["atr_14"].iloc[-1] == df_ana["atr_14"].iloc[-1]
                                    else None
                                )
                                targets = cap_targets(targets, float(df_ana["close"].iloc[-1]), _atr_val)
                                decision = make_decision(df_ana, swings, targets)

                                tech_for_db = dict(result)
                                for col in ["tenkan", "kijun", "senkou_a", "senkou_b"]:
                                    if col in df_ana.columns and df_ana[col].notna().any():
                                        tech_for_db[col] = float(df_ana[col].iloc[-1])
                                if _atr_val is not None:
                                    tech_for_db["atr_14"] = _atr_val

                                # 시간 사이클 + 미래 추세 경로 + 수급
                                cycles = compute_time_cycles(swings["C"]["idx"], len(df_ana))
                                future_path = project_future_path(
                                    decision["price"], cycles, targets, decision.get("stop"),
                                    swings=swings, atr_value=_atr_val,
                                )
                                flow_data = None
                                try:
                                    import market_context as mc
                                    rev = mc.detect_flow_reversal(code, lookback=7)
                                    if rev.get("available"):
                                        flow_data = {
                                            "verdict": rev.get("verdict"),
                                            "daily": rev.get("daily", [])[:7],
                                            "signals": rev.get("signals", []),
                                        }
                                except Exception:
                                    pass

                                pattern_data = None
                                try:
                                    import pattern_match as pm
                                    pattern_data = pm.predict_future_path(
                                        code=code, current_price=decision["price"],
                                        window=60, n_future=20, top_k=3,
                                    )
                                except Exception:
                                    pass

                                saved = db.save_analysis(
                                    code, name, tech_for_db, decision, targets, swings,
                                    snapshot_type="manual",
                                    cycles=cycles,
                                    future_path=future_path,
                                    flow=flow_data,
                                    pattern_match=pattern_data,
                                )
                                if saved:
                                    st.success(
                                        f"{t('holdings_history_saved')} — {td(decision.get('action', ''))}"
                                    )
                            except Exception as ana_err:
                                st.warning(f"{t('holdings_auto_analysis_fail')}: {ana_err}")

                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {t('holdings_register_fail')}: {e}")
    else:
        # 관심 종목 추가
        with st.form("add_watch_form"):
            note = st.text_input(
                t("note_optional"),
                value=st.session_state.get("mystocks_auto_note", ""),
            )
            tags_input = st.text_input(
                t("tags_optional"),
                value=st.session_state.get("mystocks_auto_tags", ""),
            )
            submitted = st.form_submit_button(t("add_to_watch"), type="primary")

            if submitted:
                target_query = query_outside.strip() or st.session_state.get("mystocks_auto_name", "")
                if not target_query:
                    st.warning(t("holdings_input_name_required"))
                else:
                    try:
                        from _utils import resolve_ticker
                        code, name = resolve_ticker(target_query)
                        tags = [tg.strip() for tg in tags_input.split(",") if tg.strip()]
                        db.add_watch(code, name, note, tags)
                        for k in [
                            "mystocks_auto_note", "mystocks_auto_tags",
                            "mystocks_auto_name", "mystocks_auto_code",
                        ]:
                            st.session_state.pop(k, None)
                        st.success(f"✅ {name} ({code}) {t('watchlist_added')}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {t('watchlist_add_fail')}: {e}")


# ──────────────────────────────────────────
# ✏️ 수량/평단 수정 (보유 종목)
# ──────────────────────────────────────────
with st.expander(t("mystocks_edit_section")):
    hold_opts = {f"{h['stock_name']} ({h['stock_code']})": h for h in holdings}
    if not hold_opts:
        st.info(t("mystocks_edit_empty"))
    else:
        sel_edit = st.selectbox(t("mystocks_edit_target"), list(hold_opts.keys()), key="edit_select")
        _h = hold_opts[sel_edit]
        with st.form("edit_holding_form"):
            ec1, ec2 = st.columns(2)
            with ec1:
                new_qty = st.number_input(
                    t("holdings_col_qty"), min_value=1, step=1,
                    value=int(_h["quantity"]),
                )
            with ec2:
                new_avg = st.number_input(
                    t("holdings_col_avg"), min_value=1, step=100,
                    value=int(float(_h["avg_price"])),
                )
            if st.form_submit_button(t("btn_save"), type="primary"):
                try:
                    db.update_holding(_h["id"], quantity=int(new_qty), avg_price=float(new_avg))
                    st.success(t("mystocks_edited"))
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")


# ──────────────────────────────────────────
# 🗑 삭제 (보유 + 관심 통합)
# ──────────────────────────────────────────
with st.expander(t("delete_stock")):
    if not rows:
        st.info("—")
    else:
        delete_options = {
            f"{r[_lbl_type]} · {r[_lbl_stock]} (id={r['_id']})": (r["_kind"], r["_id"])
            for r in rows
        }
        selected = st.selectbox(t("delete_target"), list(delete_options.keys()), key="del_select")
        if st.button(t("btn_delete"), type="secondary", key="del_btn"):
            kind, target_id = delete_options[selected]
            try:
                if kind == "holding":
                    db.delete_holding(target_id)
                else:
                    db.delete_watch(target_id)
                st.success(t("delete_done"))
                st.rerun()
            except Exception as e:
                st.error(f"❌ {e}")


# ──────────────────────────────────────────
# 🔄 유형 전환 (보유 ↔ 관심)
# ──────────────────────────────────────────
with st.expander(t("mystocks_convert_section")):
    if not rows:
        st.info("—")
    else:
        convert_options = {
            f"{r[_lbl_type]} · {r[_lbl_stock]} (id={r['_id']})": r
            for r in rows
        }
        sel_key = st.selectbox(
            t("mystocks_convert_target"),
            list(convert_options.keys()),
            key="convert_select",
        )
        target_row = convert_options[sel_key]
        target_kind = target_row["_kind"]
        target_code = target_row["_code"]
        target_name = target_row["_name"]

        if target_kind == "holding":
            # 보유 → 관심
            st.caption(t("mystocks_convert_to_watch"))
            if st.button(t("mystocks_convert_to_watch"), key="conv_to_watch_btn"):
                try:
                    # 원본 holding fetch (note/tags 보존 시도)
                    src = next(
                        (h for h in holdings if h["id"] == target_row["_id"]),
                        None,
                    ) or {}
                    note = src.get("note", "") or ""
                    db.add_watch(target_code, target_name, note, [])
                    db.delete_holding(target_row["_id"])
                    st.success(t("mystocks_converted"))
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ {e}")
        else:
            # 관심 → 보유 (평단/수량 필요)
            st.caption(t("mystocks_convert_to_holding"))
            with st.form("convert_to_holding_form"):
                col1, col2 = st.columns(2)
                with col1:
                    conv_avg = st.number_input(
                        t("avg_price"), min_value=1, value=10000, step=100,
                        key="conv_avg",
                    )
                with col2:
                    conv_qty = st.number_input(
                        t("quantity"), min_value=1, value=10, step=1,
                        key="conv_qty",
                    )
                col3, col4 = st.columns(2)
                with col3:
                    conv_date_unknown = st.checkbox(
                        t("purchase_date_unknown"), value=False, key="conv_date_unk",
                    )
                with col4:
                    conv_date = st.date_input(
                        t("purchase_date"), value=date.today(),
                        disabled=conv_date_unknown, key="conv_date",
                    )
                conv_submit = st.form_submit_button(
                    t("mystocks_convert_to_holding"), type="primary",
                )
                if conv_submit:
                    try:
                        src = next(
                            (w for w in watchlist if w["id"] == target_row["_id"]),
                            None,
                        ) or {}
                        note = src.get("note", "") or ""
                        use_date = None if conv_date_unknown else conv_date
                        db.add_holding(target_code, target_name, conv_avg, conv_qty, use_date, note)
                        db.delete_watch(target_row["_id"])
                        st.success(t("mystocks_converted"))
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ {e}")
