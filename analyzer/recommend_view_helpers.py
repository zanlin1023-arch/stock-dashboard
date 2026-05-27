"""추천 종목 페이지 공통 helper.

`pages/4a_*`, `pages/4b_*`, `pages/4c_*` 세 페이지가 함께 사용한다.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from i18n import t


KST = ZoneInfo("Asia/Seoul")


# ──────────────────────────────────────────
# 세션 메타 (이모지/한글 라벨)
# ──────────────────────────────────────────
def get_session_emoji() -> dict:
    return {"morning": "🌅", "intraday": "☀️", "evening": "🌙"}


def get_session_label_kr() -> dict:
    return {
        "morning": t("rec_session_label_morning"),
        "intraday": t("rec_session_label_intraday"),
        "evening": t("rec_session_label_evening"),
    }


def get_tier_meta() -> dict:
    return {
        "large": (t("tier_large"), t("tier_large_desc")),
        "mid": (t("tier_mid"), t("tier_mid_desc")),
        "small": (t("tier_small"), t("tier_small_desc")),
    }


# ──────────────────────────────────────────
# UTC → KST 헬퍼
# ──────────────────────────────────────────
def to_kst_str(s: str) -> str:
    if not s:
        return "-"
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:19].replace("T", " ")


# ──────────────────────────────────────────
# 동종업종 비교 캐시
# ──────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _peer_data(code: str, max_peers: int = 6) -> dict:
    """동종업종 비교 데이터 (1시간 캐시)."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import sector_compare as sc
        return sc.compare_to_peers(code, max_peers=max_peers)
    except Exception:
        return {"sector_no": None, "sector_name": "", "peers": [], "self_in_peers": False}


# ──────────────────────────────────────────
# 종목 카드 렌더
# ──────────────────────────────────────────
def _stock_card(stock: dict, mode: str = "view"):
    """추천 종목 카드."""
    code = stock.get("stock_code", "")
    name = stock.get("stock_name", "")
    price = stock.get("price")
    change_pct = stock.get("change_pct")
    score = stock.get("score", 0)
    market_cap = stock.get("market_cap_eok") or 0
    foreign_5d = stock.get("foreign_5d") or 0
    inst_5d = stock.get("inst_5d") or 0
    signals = stock.get("signals") or []
    rank = stock.get("rank_in_tier", 0)

    # 섹터/테마 (캐시된 _peer_data 사용)
    sector_name = ""
    try:
        sec = _peer_data(code, max_peers=1)
        sector_name = sec.get("sector_name") or ""
    except Exception:
        pass

    won = t("rec_unit_won")
    eok = t("rec_unit_eok")

    with st.container(border=True):
        hc1, hc2, hc3 = st.columns([3, 2, 2])
        with hc1:
            st.markdown(f"### #{rank}  {name}  `{code}`")
            theme_label = sector_name or t("rec_card_no_theme")
            st.markdown(
                f"<div style='display:inline-block;padding:2px 10px;border-radius:10px;"
                f"background:#EEF3FB;color:#1B6FB0;font-size:0.85rem;font-weight:600;'>"
                f"{t('rec_card_theme')}: {theme_label}</div>",
                unsafe_allow_html=True,
            )
        with hc2:
            cs = f"{float(change_pct):+.2f}%" if change_pct else None
            st.metric(t("rec_card_price"), f"{int(float(price)):,}{won}" if price else "-", cs)
        with hc3:
            st.metric(t("rec_card_score"), f"{int(score):+}")

        dc1, dc2, dc3, dc4 = st.columns(4)
        with dc1:
            st.metric(t("rec_card_marketcap"), f"{int(market_cap):,}{eok}" if market_cap else "-")
        with dc2:
            f_color = "🟢" if foreign_5d > 0 else ("🔴" if foreign_5d < 0 else "⚪")
            st.metric(t("rec_card_foreign5d"), f"{f_color} {int(foreign_5d):+,}{eok}" if foreign_5d else "-")
        with dc3:
            i_color = "🟢" if inst_5d > 0 else ("🔴" if inst_5d < 0 else "⚪")
            st.metric(t("rec_card_inst5d"), f"{i_color} {int(inst_5d):+,}{eok}" if inst_5d else "-")
        with dc4:
            if st.button(t("rec_card_detail"), key=f"a_{mode}_{code}_{rank}", use_container_width=True):
                st.session_state["last_query"] = name
                st.switch_page("app.py")

        # 추천 이유 (signals) — expander 없이 펼친 상태로 노출
        st.markdown(
            f"<div style='margin-top:8px;padding:10px 14px;border-radius:8px;"
            f"background:#FFF9E6;border-left:4px solid #F1C40F;'>"
            f"<div style='font-weight:700;color:#7A5C00;margin-bottom:4px;'>{t('rec_card_reasons')}</div>"
            + (
                "<ul style='margin:0;padding-left:20px;color:#5A4500;'>"
                + "".join(f"<li>{sig}</li>" for sig in signals)
                + "</ul>"
                if signals
                else f"<div style='color:#8A7000;'>{t('rec_card_no_reasons')}</div>"
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        # ───── 섹터 + 관련주 비교 (지연 로딩 — expander 펼칠 때만 호출) ─────
        with st.expander(t("rec_sector_compare"), expanded=False):
            sec_full = _peer_data(code, max_peers=6)
            peers = sec_full.get("peers") or []
            sector_label = sec_full.get("sector_name") or t("rec_card_no_theme")
            if not peers:
                st.caption(t("rec_peer_unavailable"))
            else:
                st.caption(t("rec_peer_top").format(sector=sector_label, n=len(peers)))
                rows = []
                for p in peers:
                    is_self = p["code"] == code
                    rows.append({
                        t("rec_peer_col_compare"): t("rec_peer_col_self") if is_self else "",
                        t("rec_peer_col_stock"): f"{p['name']} ({p['code']})",
                        t("rec_peer_col_price"): f"{int(p['price']):,}" if p.get("price") else "-",
                        t("rec_peer_col_change"): f"{p['change_pct']:+.2f}%",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                avg = sum(p["change_pct"] for p in peers) / len(peers)
                self_chg = next(
                    (p["change_pct"] for p in peers if p["code"] == code),
                    None,
                )
                sec_color = "#E74C3C" if avg > 0 else ("#0064FF" if avg < 0 else "#7F8C8D")
                if self_chg is not None:
                    diff = self_chg - avg
                    rel_msg = (
                        f" · {t('rec_peer_self_vs_sector')} <strong>{self_chg:+.2f}%</strong> "
                        f"({t('rec_peer_sector_diff')} <strong style='color:{sec_color};'>{diff:+.2f}%p</strong>)"
                    )
                else:
                    rel_msg = ""
                st.markdown(
                    f"<div style='padding:6px 10px;border-radius:6px;background:{sec_color}10;"
                    f"border-left:3px solid {sec_color};font-size:0.85rem;'>"
                    f"{t('rec_peer_sector_avg')} <strong style='color:{sec_color};'>{avg:+.2f}%</strong>"
                    f"{rel_msg}</div>",
                    unsafe_allow_html=True,
                )


# ──────────────────────────────────────────
# 오늘 세션별 진행 상황 카드 (3개)
# ──────────────────────────────────────────
def render_session_progress(db, now: datetime):
    """오늘 세션별 자동 분석 진도 카드 3개 (morning/intraday/evening)."""
    today_str = now.strftime("%Y-%m-%d")
    today_saved_sessions = set()
    try:
        today_recs = db.list_recommendations(target_date=today_str)
        today_saved_sessions = {r.get("session") for r in today_recs if r.get("session")}
    except Exception:
        pass

    session_schedule = [
        ("🌅", "morning", 8, 0, t("rec_session_morning_desc")),
        ("☀️", "intraday", 14, 0, t("rec_session_intraday_desc")),
        ("🌙", "evening", 21, 0, t("rec_session_evening_desc")),
    ]

    st.markdown(f"##### {t('rec_session_progress')}")
    sess_cols = st.columns(3)
    for col, (emoji, sess_id, sh, sm, desc) in zip(sess_cols, session_schedule):
        sess_time = now.replace(hour=sh, minute=sm, second=0, microsecond=0)

        if sess_id in today_saved_sessions:
            status = t("rec_session_done")
            bg, border, fg = "#E8F8E8", "#27AE60", "#1E7E34"
        elif now >= sess_time:
            status = t("rec_session_pending")
            bg, border, fg = "#FFF4E6", "#E67E22", "#A04A1F"
        else:
            delta = sess_time - now
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            if hours > 0:
                status = t("rec_time_hours_min_later").format(h=hours, m=minutes)
            else:
                status = t("rec_time_min_later").format(m=minutes)
            bg, border, fg = "#F0F4FF", "#5DADE2", "#1B6FB0"

        with col:
            st.markdown(
                f"<div style='background:{bg};padding:14px;border-radius:10px;"
                f"border-left:4px solid {border};text-align:left;'>"
                f"<div style='font-size:1.3rem;font-weight:bold;color:{fg};'>"
                f"{emoji} {sess_id} <span style='font-size:0.85rem;color:#666;font-weight:normal;'>"
                f"({sh:02d}:{sm:02d} KST · {desc})</span></div>"
                f"<div style='font-size:0.95rem;color:{fg};font-weight:600;margin-top:6px;'>"
                f"{status}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.write("")


# ──────────────────────────────────────────
# 7일 추이 분석 블록
# ──────────────────────────────────────────
def render_7d_trend(db, saved_dates: list[str]):
    """최근 7일 추이 분석 (옵션). 호출 측에서 토글 후 호출."""
    st.divider()
    st.subheader(t("rec_7d_trend_title"))
    st.caption(t("rec_7d_trend_caption"))

    recent_dates = saved_dates[:7]
    by_code: dict[str, dict] = {}

    for d in recent_dates:
        day_recs = db.list_recommendations(target_date=d)
        for r in day_recs:
            code = r.get("stock_code")
            if not code:
                continue
            if code not in by_code:
                by_code[code] = {
                    "name": r.get("stock_name"),
                    "appearances": [],
                    "scores": [],
                    "tiers": set(),
                }
            by_code[code]["appearances"].append(d)
            by_code[code]["scores"].append(r.get("score") or 0)
            by_code[code]["tiers"].add(r.get("tier"))

    ranked = sorted(by_code.items(), key=lambda x: (-len(x[1]["appearances"]), -max(x[1]["scores"], default=0)))

    if ranked:
        rows = []
        for code, info in ranked[:20]:
            rows.append({
                t("rec_7d_col_stock"): f"{info['name']} ({code})",
                t("rec_7d_col_appear"): t("rec_7d_appear_format").format(n=len(info['appearances']), total=len(recent_dates)),
                t("rec_7d_col_max_score"): max(info["scores"], default=0),
                t("rec_7d_col_tier"): ", ".join(sorted(info["tiers"])),
                t("rec_7d_col_last"): max(info["appearances"]),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(t("rec_7d_insufficient"))


# ──────────────────────────────────────────
# 세션별 추천 본문 렌더 (단일 세션 고정)
# ──────────────────────────────────────────
def render_session_recommendations(db, session: str):
    """세션 단일 페이지 본문 렌더.

    Args:
        db: analyzer.db 모듈
        session: "morning" | "intraday" | "evening" (고정)
    """
    now = datetime.now(KST)
    emoji = get_session_emoji().get(session, "📊")
    label = get_session_label_kr().get(session, session)

    st.caption(
        f"🕐 {t('current_kst')}: **{now.strftime('%Y-%m-%d %H:%M')}** — "
        f"{t('current_mode')}: **{emoji} {label}**"
    )

    # 오늘 세션별 진도 카드 (3개 모두 표시 — 다른 세션 상태 알려주는 정보)
    render_session_progress(db, now)

    # 저장된 날짜 목록
    saved_dates = db.list_recommendation_dates(limit=30)

    # 상단 컨트롤 (세션은 페이지가 결정 → selectbox 제거)
    cc1, cc3 = st.columns([2, 2])

    with cc1:
        if saved_dates:
            date_options = [t("filter_latest")] + [d for d in saved_dates]
            sel_date_label = st.selectbox(t("filter_date"), date_options, key=f"rec_{session}_date")
            if sel_date_label == t("filter_latest"):
                target_date = saved_dates[0]
            else:
                target_date = sel_date_label
        else:
            st.info(t("no_saved_recs"))
            target_date = None

    with cc3:
        st.write("")
        st.write("")
        if st.button(t("btn_7d_trend"), use_container_width=True, key=f"rec_{session}_trend_btn"):
            st.session_state[f"show_trend_{session}"] = not st.session_state.get(f"show_trend_{session}", False)

    if not target_date:
        st.info(t("rec_intro_no_recs"))
        return

    # 데이터 조회 (해당 세션만)
    recs = db.list_recommendations(target_date=target_date, session=session)

    if not recs:
        st.warning(f"📅 {target_date} ({session}) — {t('rec_no_saved_for_date')}")
        return

    # 요약 카드
    total = len(recs)
    sessions_in_data = sorted({r.get("session") for r in recs if r.get("session")})

    sc1, sc2, sc3, sc4 = st.columns(4)
    sc1.metric(t("rec_date"), target_date)
    sc2.metric(t("rec_total"), f"{total}{t('rec_unit_count')}")
    sc3.metric(t("rec_session_count"), ", ".join(sessions_in_data) or "-")
    recommended_at = to_kst_str(recs[0].get("recommended_at", ""))
    sc4.metric(t("rec_analyzed_at_kst"), recommended_at)

    # 7일 추이 분석 (옵션)
    if st.session_state.get(f"show_trend_{session}"):
        render_7d_trend(db, saved_dates)

    # Tier별 카드 표시
    st.divider()

    # 세션 단일 고정 → tier별 분류
    tiered = {"large": [], "mid": [], "small": []}
    for r in recs:
        tier = r.get("tier")
        if tier in tiered:
            tiered[tier].append(r)

    tier_meta = get_tier_meta()

    st.markdown(f"## {emoji} {label}")

    has_any = False
    for tier in ["large", "mid", "small"]:
        items = tiered[tier]
        if not items:
            continue
        has_any = True
        tier_label, tier_desc = tier_meta[tier]
        st.markdown(f"### {tier_label} _({tier_desc})_")
        for stock in items:
            _stock_card(stock, mode=f"{session}_{tier}")
        st.markdown("")

    if not has_any:
        st.info(t("rec_no_saved_for_date"))

    st.divider()
    st.caption(t("rec_footer"))
