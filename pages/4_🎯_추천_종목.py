"""신규 종목 추천 — DB 우선 조회 (날짜별 누적) + 실시간 분석 옵션."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="추천 종목", page_icon="🎯", layout="wide")
init_page("추천 종목")
sidebar_nav()
render_macro_header()
nav_bar("recommend")

st.title(t("recommend_title"))

KST = ZoneInfo("Asia/Seoul")
now = datetime.now(KST)
hour = now.hour
minute = now.minute

if hour < 9:
    default_session = "morning"
    session_label = f"🌅 {t('session_morning_label')}"
elif hour < 15 or (hour == 15 and minute < 30):
    default_session = "intraday"
    session_label = f"☀️ {t('session_intraday_label')}"
else:
    default_session = "evening"
    session_label = f"🌙 {t('session_evening_label')}"

st.caption(f"🕐 {t('current_kst')}: **{now.strftime('%Y-%m-%d %H:%M')}** — {t('current_mode')}: **{session_label}**")


# ──────────────────────────────────────────
# DB 우선 조회
# ──────────────────────────────────────────
db = get_db()
if not db:
    st.error(t("db_disconnected"))
    st.stop()

# 저장된 날짜 목록
saved_dates = db.list_recommendation_dates(limit=30)


# ──────────────────────────────────────────
# 오늘 세션별 진행 상황 (3개 자동 실행 시각)
# ──────────────────────────────────────────
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
            status = f"⏳ {hours}시간 {minutes}분 후"
        else:
            status = f"⏳ {minutes}분 후"
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
# 상단 컨트롤 (자동 분석만 — 수동 실행 버튼 제거)
# ──────────────────────────────────────────
cc1, cc2, cc3 = st.columns([2, 2, 2])

with cc1:
    if saved_dates:
        date_options = [t("filter_latest")] + [d for d in saved_dates]
        sel_date_label = st.selectbox(t("filter_date"), date_options)
        if sel_date_label == t("filter_latest"):
            target_date = saved_dates[0]
        else:
            target_date = sel_date_label
    else:
        st.info(t("no_saved_recs"))
        target_date = None

with cc2:
    session_options = [t("snapshot_all"), "🌅 morning", "☀️ intraday", "🌙 evening"]
    default_idx = {"morning": 1, "intraday": 2, "evening": 3}.get(default_session, 3)
    sel_session_label = st.selectbox(t("filter_session"), session_options, index=default_idx)
    session_map = {t("snapshot_all"): None, "🌅 morning": "morning", "☀️ intraday": "intraday", "🌙 evening": "evening"}
    sel_session = session_map[sel_session_label]

with cc3:
    st.write("")
    st.write("")
    if st.button(t("btn_7d_trend"), use_container_width=True):
        st.session_state["show_trend"] = not st.session_state.get("show_trend", False)


# ──────────────────────────────────────────
# 데이터 조회
# ──────────────────────────────────────────
if not target_date:
    st.info(
        "💡 아직 저장된 추천이 없습니다. 매일 평일 다음 시각에 자동 분석됩니다:\n\n"
        "- 🌅 **08:00 KST** — 장 시작 전 (morning)\n"
        "- ☀️ **14:00 KST** — 장 중 (intraday)\n"
        "- 🌙 **21:00 KST** — NXT 마감 후 (evening)"
    )
    st.stop()


recs = db.list_recommendations(target_date=target_date, session=sel_session)

if not recs:
    st.warning(f"📅 {target_date} ({sel_session or '전체'}) — 저장된 추천 없음")
    st.stop()


# ──────────────────────────────────────────
# 요약 카드
# ──────────────────────────────────────────
total = len(recs)
sessions_in_data = sorted({r.get("session") for r in recs if r.get("session")})

sc1, sc2, sc3, sc4 = st.columns(4)
sc1.metric("📅 추천 일자", target_date)
sc2.metric("📊 총 추천", f"{total}건")
sc3.metric("⏰ 세션", ", ".join(sessions_in_data) or "-")
# UTC → KST 변환
from datetime import datetime as _dt, timezone as _tz, timedelta as _td
_KST = _tz(_td(hours=9))
def _to_kst(s: str) -> str:
    if not s:
        return "-"
    try:
        d = _dt.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=_tz.utc)
        return d.astimezone(_KST).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:19].replace("T", " ")
recommended_at = _to_kst(recs[0].get("recommended_at", ""))
sc4.metric("🕐 분석 시각 (KST)", recommended_at)


# ──────────────────────────────────────────
# 7일 추이 분석 (옵션)
# ──────────────────────────────────────────
if st.session_state.get("show_trend"):
    st.divider()
    st.subheader("📊 7일 추천 종목 추이")
    st.caption("최근 7일간 어떤 종목이 자주 추천됐는지 + 신규/탈락 종목")

    # 최근 7일 데이터 수집
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

    # 빈도 정렬
    ranked = sorted(by_code.items(), key=lambda x: (-len(x[1]["appearances"]), -max(x[1]["scores"], default=0)))

    if ranked:
        rows = []
        for code, info in ranked[:20]:
            rows.append({
                "종목": f"{info['name']} ({code})",
                "등장 횟수": f"{len(info['appearances'])}/{len(recent_dates)}일",
                "최고 점수": max(info["scores"], default=0),
                "Tier": ", ".join(sorted(info["tiers"])),
                "최근 등장": max(info["appearances"]),
            })
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("7일치 데이터 부족")


# ──────────────────────────────────────────
# Tier별 카드 표시
# ──────────────────────────────────────────
st.divider()

# session별로 그룹
by_session = {}
for r in recs:
    s = r.get("session") or "unknown"
    by_session.setdefault(s, {"large": [], "mid": [], "small": []})
    tier = r.get("tier")
    if tier in by_session[s]:
        by_session[s][tier].append(r)


@st.cache_data(ttl=3600, show_spinner=False)
def _peer_data(code: str, max_peers: int = 6) -> dict:
    """동종업종 비교 데이터 (1시간 캐시)."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
        import sector_compare as sc
        return sc.compare_to_peers(code, max_peers=max_peers)
    except Exception:
        return {"sector_no": None, "sector_name": "", "peers": [], "self_in_peers": False}


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

    with st.container(border=True):
        hc1, hc2, hc3 = st.columns([3, 2, 2])
        with hc1:
            st.markdown(f"### #{rank}  {name}  `{code}`")
        with hc2:
            cs = f"{float(change_pct):+.2f}%" if change_pct else None
            st.metric("현재가", f"{int(float(price)):,}원" if price else "-", cs)
        with hc3:
            st.metric("추천 점수", f"{int(score):+}")

        dc1, dc2, dc3, dc4 = st.columns(4)
        with dc1:
            st.metric("시가총액", f"{int(market_cap):,}억" if market_cap else "-")
        with dc2:
            f_color = "🟢" if foreign_5d > 0 else ("🔴" if foreign_5d < 0 else "⚪")
            st.metric("외인 5일", f"{f_color} {int(foreign_5d):+,}억" if foreign_5d else "-")
        with dc3:
            i_color = "🟢" if inst_5d > 0 else ("🔴" if inst_5d < 0 else "⚪")
            st.metric("기관 5일", f"{i_color} {int(inst_5d):+,}억" if inst_5d else "-")
        with dc4:
            if st.button("🔬 상세 분석", key=f"a_{mode}_{code}_{rank}", use_container_width=True):
                st.session_state["last_query"] = name
                st.switch_page("app.py")

        if signals:
            with st.expander(f"📊 시그널 {len(signals)}개"):
                for sig in signals[:5]:
                    st.markdown(f"- {sig}")

        # ───── 섹터 + 관련주 비교 (지연 로딩 — expander 펼칠 때만 호출) ─────
        with st.expander(t("rec_sector_compare"), expanded=False):
            sec = _peer_data(code, max_peers=6)
            peers = sec.get("peers") or []
            sector_label = sec.get("sector_name") or "동종업종"
            if not peers:
                st.caption("ℹ️ 동종업종 데이터를 가져올 수 없습니다.")
            else:
                st.caption(f"📂 **{sector_label}** · 관련주 상위 {len(peers)}개")
                import pandas as pd
                rows = []
                for p in peers:
                    is_self = p["code"] == code
                    rows.append({
                        "비교": "👈 본인" if is_self else "",
                        "종목": f"{p['name']} ({p['code']})",
                        "현재가": f"{int(p['price']):,}" if p.get("price") else "-",
                        "등락률": f"{p['change_pct']:+.2f}%",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                # 섹터 평균 등락률
                avg = sum(p["change_pct"] for p in peers) / len(peers)
                self_chg = next(
                    (p["change_pct"] for p in peers if p["code"] == code),
                    None,
                )
                sec_color = "#E74C3C" if avg > 0 else ("#0064FF" if avg < 0 else "#7F8C8D")
                if self_chg is not None:
                    diff = self_chg - avg
                    rel_msg = (
                        f" · 본인 <strong>{self_chg:+.2f}%</strong> "
                        f"(섹터 대비 <strong style='color:{sec_color};'>{diff:+.2f}%p</strong>)"
                    )
                else:
                    rel_msg = ""
                st.markdown(
                    f"<div style='padding:6px 10px;border-radius:6px;background:{sec_color}10;"
                    f"border-left:3px solid {sec_color};font-size:0.85rem;'>"
                    f"📊 섹터 평균 등락률 <strong style='color:{sec_color};'>{avg:+.2f}%</strong>"
                    f"{rel_msg}</div>",
                    unsafe_allow_html=True,
                )


tier_meta = {
    "large": ("🏛 대형주", "시총 5조원 이상"),
    "mid": ("🏢 중형주", "5천억 ~ 5조원"),
    "small": ("🏠 소형주", "1천억 ~ 5천억원"),
}

session_emoji = {"morning": "🌅", "intraday": "☀️", "evening": "🌙"}
session_label_kr = {"morning": "장 시작 전", "intraday": "장 중", "evening": "장 마감 후"}

for sess in sorted(by_session.keys()):
    sess_data = by_session[sess]
    sess_total = sum(len(v) for v in sess_data.values())
    if sess_total == 0:
        continue

    emoji = session_emoji.get(sess, "📊")
    label = session_label_kr.get(sess, sess)
    st.markdown(f"## {emoji} {label}")

    for tier in ["large", "mid", "small"]:
        items = sess_data[tier]
        if not items:
            continue
        tier_label, tier_desc = tier_meta[tier]
        st.markdown(f"### {tier_label} _({tier_desc})_")
        for stock in items:
            _stock_card(stock, mode=f"{sess}_{tier}")
        st.markdown("")


# ──────────────────────────────────────────
# 푸터
# ──────────────────────────────────────────
st.divider()
st.caption(
    "⚡ DB 즉시 조회 모드 · "
    "매일 평일 자동 분석 (GitHub Actions): 🌅 08:00 / ☀️ 14:00 / 🌙 21:00 KST"
)
