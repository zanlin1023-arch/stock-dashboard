"""공시·경제 일정 캘린더.

데이터 소스:
- OpenDART: 종목 공시 (보유/관심 기준 필터)
- 한국은행/네이버: 거시 일정 (금통위, FOMC, 지표 발표) — 향후 확장
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import streamlit as st

from common import init_page, get_db, sidebar_nav, render_macro_header, nav_bar
from i18n import t

st.set_page_config(page_title="공시·경제 캘린더", page_icon="📅", layout="wide")
init_page("공시·경제 캘린더")
sidebar_nav()
render_macro_header()
nav_bar("calendar")

st.title("📅 공시 · 경제 캘린더")
st.caption("보유/관심 종목 공시 (OpenDART) + 주요 거시 일정")

db = get_db()


# ──────────────────────────────────────────
# 기간 선택
# ──────────────────────────────────────────
c1, c2, c3 = st.columns([2, 2, 2])
today = date.today()
with c1:
    start_date = st.date_input("시작일", value=today - timedelta(days=7))
with c2:
    end_date = st.date_input("종료일", value=today + timedelta(days=7))
with c3:
    show_macro = st.checkbox("거시 일정 포함", value=True)
    show_only_my = st.checkbox("내 종목만 (보유+관심)", value=True)


# ──────────────────────────────────────────
# OpenDART 공시 조회
# ──────────────────────────────────────────
@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_disclosures(codes: tuple, bgn_de: str, end_de: str) -> list[dict]:
    """OpenDartReader로 종목별 공시 목록 (fundamental.py와 동일 라이브러리)."""
    import os
    api_key = os.getenv("OPENDART_API_KEY", "")
    if not api_key:
        try:
            api_key = st.secrets["OPENDART_API_KEY"]
        except Exception:
            api_key = ""
    if not api_key:
        return []
    try:
        import OpenDartReader
    except Exception:
        return []
    dart = OpenDartReader(api_key)
    out = []
    for code in codes:
        try:
            df = dart.list(corp=code, start=bgn_de, end=end_de)
            if df is None or len(df) == 0:
                continue
            for _, row in df.iterrows():
                out.append({
                    "code": str(row.get("stock_code") or code),
                    "corp_name": row.get("corp_name") or "",
                    "title": row.get("report_nm") or "",
                    "date": str(row.get("rcept_dt", "")).replace("-", ""),
                    "rcept_no": row.get("rcept_no") or "",
                    "filer": row.get("flr_nm") or "",
                })
        except Exception:
            continue
    return out


# ──────────────────────────────────────────
# 내 종목 코드 수집
# ──────────────────────────────────────────
my_codes: list[tuple[str, str]] = []  # (code, name)
if db:
    try:
        for h in db.list_holdings():
            my_codes.append((h["stock_code"], h["stock_name"]))
    except Exception:
        pass
    try:
        for w in db.list_watchlist():
            if not any(c == w["stock_code"] for c, _ in my_codes):
                my_codes.append((w["stock_code"], w["stock_name"]))
    except Exception:
        pass


# ──────────────────────────────────────────
# 공시 조회
# ──────────────────────────────────────────
st.subheader("📰 종목 공시")

if not my_codes:
    st.info("💡 보유 또는 관심 종목을 먼저 등록하세요.")
else:
    codes_tuple = tuple(c for c, _ in my_codes)
    bgn_de = start_date.strftime("%Y%m%d")
    end_de = end_date.strftime("%Y%m%d")

    with st.spinner(f"{len(my_codes)}개 종목 공시 조회 중..."):
        disclosures = _fetch_disclosures(codes_tuple, bgn_de, end_de)

    if not disclosures:
        st.caption(f"📭 해당 기간 공시 없음 ({bgn_de} ~ {end_de})")
    else:
        # 날짜 역순 정렬
        disclosures.sort(key=lambda x: x.get("date", ""), reverse=True)

        # 날짜별 그룹
        by_date: dict[str, list[dict]] = {}
        for d in disclosures:
            dt = d.get("date") or "(미상)"
            by_date.setdefault(dt, []).append(d)

        for dt, items in by_date.items():
            dt_obj = None
            try:
                dt_obj = datetime.strptime(dt, "%Y%m%d")
                dt_label = dt_obj.strftime("%Y-%m-%d (%a)")
            except Exception:
                dt_label = dt
            expanded_flag = bool(dt_obj and dt_obj.date() >= today)
            with st.expander(f"📅 {dt_label} — {len(items)}건", expanded=expanded_flag):
                for d in items:
                    link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d.get('rcept_no')}"
                    st.markdown(
                        f"- **[{d.get('corp_name', '')}]({link})** · {d.get('title', '')}  "
                        f"<span style='color:#888;font-size:0.85rem;'>제출인: {d.get('filer', '-')}</span>",
                        unsafe_allow_html=True,
                    )


# ──────────────────────────────────────────
# 거시 일정 (정적 데이터 — 추후 API 확장)
# ──────────────────────────────────────────
if show_macro:
    st.divider()
    st.subheader("🌍 주요 거시 일정 (참고)")
    st.caption("정기 일정 안내 — 정확한 일정은 한국은행/연준 공식 발표 확인")

    macro_events = [
        ("매월 둘째주 목", "🏛 한국은행 금통위 (기준금리 결정)"),
        ("매월 둘째주 목", "🇺🇸 FOMC 회의 (3·6·9·12월 분기 중)"),
        ("매월 1·15일", "📊 KOSIS 주요 경제지표 발표"),
        ("매주 금요일 21:30 KST", "🇺🇸 미국 비농업고용지표 (월 첫 금)"),
        ("매주 목요일 21:30 KST", "🇺🇸 신규 실업수당 청구건수"),
        ("매월 셋째주 목 21:30 KST", "🇺🇸 CPI 발표 (전월 데이터)"),
    ]
    for when, what in macro_events:
        st.markdown(f"- **{when}** — {what}")

st.divider()
st.caption(
    "ℹ️ OpenDART 공시는 보유/관심 종목 한정. "
    "전체 공시는 [DART](https://dart.fss.or.kr/) 직접 검색."
)
