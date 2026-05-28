"""추천 종목 페이지 공통 helper.

`pages/4a_*`, `pages/4b_*`, `pages/4c_*` 세 페이지가 함께 사용한다.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from i18n import t, td


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
# 단타 / 장기 관점 분류
# ──────────────────────────────────────────
# 단기 모멘텀 시그널 키워드 (단타)
_SHORT_KW = (
    "폭등", "거래량", "신고가", "RSI 강세", "ADX 강한", "ADX 매우 강한",
    "동행성", "5일 +", "5일 폭등",
)
# 추세 형성 시그널 키워드 (장기)
_LONG_KW = (
    "정배열", "MACD 골든", "MACD 상승", "동반 매수", "연속 순매수", "연속 매수",
    "매수 전환", "60일 신고가", "RSI 양호", "RSI 강세 (>50)",
)


def classify_horizon(signals: list, change_pct=None) -> tuple[str, int, int]:
    """시그널 + 등락률 기반으로 단타/장기 관점 분류.

    Returns:
        (라벨 키, short_score, long_score)
        라벨 키: rec_horizon_short / rec_horizon_long / rec_horizon_both / rec_horizon_neutral
    """
    short_score = 0
    long_score = 0
    for s in signals or []:
        s = str(s)
        for kw in _SHORT_KW:
            if kw in s:
                short_score += 1
        for kw in _LONG_KW:
            if kw in s:
                long_score += 1
    # 등락률 큰 (>5%) 종목은 단타 가중
    try:
        chg = float(change_pct) if change_pct is not None else 0
        if abs(chg) >= 5:
            short_score += 2
        elif abs(chg) >= 3:
            short_score += 1
    except (TypeError, ValueError):
        pass

    # 분류 임계값
    s_strong = short_score >= 3
    l_strong = long_score >= 3
    if s_strong and l_strong:
        return ("rec_horizon_both", short_score, long_score)
    if s_strong:
        return ("rec_horizon_short", short_score, long_score)
    if l_strong:
        return ("rec_horizon_long", short_score, long_score)
    # 약한 시그널 — 더 큰 쪽
    if short_score > long_score and short_score >= 1:
        return ("rec_horizon_short", short_score, long_score)
    if long_score > short_score and long_score >= 1:
        return ("rec_horizon_long", short_score, long_score)
    return ("rec_horizon_neutral", short_score, long_score)


# ──────────────────────────────────────────
# 강세 테마 집계
# ──────────────────────────────────────────
def compute_hot_themes(recs: list[dict], top_n: int = 5) -> list[dict]:
    """추천 종목들의 sector 집계 → 강세 테마 상위 N개 (DART 업종 우선)."""
    from collections import defaultdict
    bucket: dict[str, dict] = defaultdict(lambda: {"changes": [], "stocks": []})
    for r in recs:
        code = r.get("stock_code")
        if not code:
            continue
        sector_name = _resolve_sector(code)
        if not sector_name:
            continue
        try:
            chg = float(r.get("change_pct") or 0)
        except (TypeError, ValueError):
            chg = 0
        bucket[sector_name]["changes"].append(chg)
        bucket[sector_name]["stocks"].append(r.get("stock_name", "?"))
    items = []
    for theme, info in bucket.items():
        n = len(info["changes"])
        avg = sum(info["changes"]) / n if n else 0
        items.append({
            "theme": theme,
            "count": n,
            "avg_change": avg,
            "stocks": info["stocks"],
        })
    # 등장 종목 수 우선, 같으면 평균 등락률
    items.sort(key=lambda x: (-x["count"], -x["avg_change"]))
    return items[:top_n]


def render_hot_themes(recs: list[dict]):
    """상단 강세 테마 박스 — sector 데이터 부족 시 등락률 상위 종목 fallback."""
    themes = compute_hot_themes(recs, top_n=5)

    if themes:
        # 정상: 테마 chip 렌더
        chip_html = []
        for th in themes:
            avg = th["avg_change"]
            color = "#E74C3C" if avg > 0 else ("#1F77D4" if avg < 0 else "#7F8C8D")
            stocks_preview = " · ".join(th["stocks"][:3])
            chip_html.append(
                f"<span style='display:inline-block;margin:3px 4px;padding:6px 12px;"
                f"background:{color}15;border:1px solid {color}40;border-radius:14px;"
                f"font-size:0.82rem;color:#333;'>"
                f"<strong style='color:{color};'>{th['theme']}</strong> "
                f"<span style='color:#777;font-size:0.75rem;'>{th['count']}{t('rec_hot_themes_stocks')} · "
                f"{t('rec_hot_themes_avg')} <strong style='color:{color};'>{avg:+.2f}%</strong></span>"
                f"<div style='font-size:0.7rem;color:#999;margin-top:2px;'>{stocks_preview}</div>"
                f"</span>"
            )
        st.markdown(
            f"<div style='padding:12px 14px;background:#FFF9E6;border-left:4px solid #F1C40F;"
            f"border-radius:8px;margin:8px 0;'>"
            f"<div style='font-weight:700;color:#7A5C00;margin-bottom:6px;'>"
            f"{t('rec_hot_themes_title')}</div>"
            f"<div>{''.join(chip_html)}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # Fallback: sector 데이터 부족 시 등락률 상위 종목 chip
    movers = []
    for r in recs:
        try:
            chg = float(r.get("change_pct") or 0)
        except (TypeError, ValueError):
            chg = 0
        if chg > 0:
            movers.append((r.get("stock_name", "?"), r.get("stock_code", ""), chg))
    movers.sort(key=lambda x: -x[2])
    movers = movers[:6]
    if not movers:
        return  # 빈 박스 숨김 (메시지도 노출 안 함)

    chip_html = []
    for name, code, chg in movers:
        color = "#E74C3C"
        chip_html.append(
            f"<span style='display:inline-block;margin:3px 4px;padding:6px 12px;"
            f"background:{color}15;border:1px solid {color}40;border-radius:14px;"
            f"font-size:0.82rem;color:#333;'>"
            f"<strong>{name}</strong> "
            f"<span style='color:{color};font-weight:600;'>{chg:+.2f}%</span>"
            f"<span style='color:#999;font-size:0.7rem;margin-left:4px;'>{code}</span>"
            f"</span>"
        )
    st.markdown(
        f"<div style='padding:12px 14px;background:#FFF9E6;border-left:4px solid #F1C40F;"
        f"border-radius:8px;margin:8px 0;'>"
        f"<div style='font-weight:700;color:#7A5C00;margin-bottom:6px;'>"
        f"🔥 오늘 강세 종목 <span style='font-weight:400;color:#999;font-size:0.75rem;'>"
        f"(테마 매핑 부족 → 등락률 상위 표시)</span></div>"
        f"<div>{''.join(chip_html)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────
# 섹터 해석 (DART → 네이버 → peer fallback)
# ──────────────────────────────────────────
@st.cache_data(ttl=86400, show_spinner=False)
def _scrape_naver_sector(code: str) -> str:
    """네이버 PC 종목 페이지에서 업종 조회 (24h 캐시).

    예: https://finance.naver.com/item/main.naver?code=005930
    → <a href="...sise_group_detail.naver...">반도체와반도체장비</a>
    """
    if not code:
        return ""
    try:
        import requests
        from bs4 import BeautifulSoup
        r = requests.get(
            f"https://finance.naver.com/item/main.naver?code={code}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=6,
        )
        if r.status_code != 200:
            return ""
        # raw bytes를 EUC-KR로 BeautifulSoup에 직접 전달 (r.text 사용 시 깨짐)
        soup = BeautifulSoup(r.content, "html.parser", from_encoding="euc-kr")
        a = soup.select_one('a[href*="sise_group_detail.naver"]')
        if a:
            sector = a.get_text(strip=True)
            if sector:
                return sector
    except Exception:
        pass
    return ""


def _resolve_sector(code: str) -> str:
    """종목 sector 결정 — 네이버 PC가 가장 안정적이라 1차로.

    DART는 induty(업종명)가 비어있는 경우 많음 (induty_code만 있음).
    """
    # 1차: 네이버 PC 종목 페이지 (가장 안정, 한글 업종명 확실)
    s = _scrape_naver_sector(code)
    if s:
        return s
    # 2차: DART
    try:
        from analyzer.stock_meta_dart import get_sector as _dart_sector
        s = _dart_sector(code)
        if s:
            return s
    except Exception:
        pass
    # 3차: peer_data
    try:
        return _peer_data(code, max_peers=1).get("sector_name") or ""
    except Exception:
        return ""


def diagnose_sector(code: str) -> dict:
    """sector 조회 진단 (사용자 디버그용)."""
    diag = {"code": code}
    # DART
    try:
        from analyzer.stock_meta_dart import _get_api_key, _load_corp_code_map, get_company_info
        diag["dart_key_set"] = bool(_get_api_key())
        diag["dart_key_len"] = len(_get_api_key() or "")
        cmap = _load_corp_code_map()
        diag["dart_corp_map_size"] = len(cmap)
        diag["dart_code_in_map"] = code.zfill(6) in cmap
        info = get_company_info(code)
        diag["dart_company_info"] = info
    except Exception as e:
        diag["dart_error"] = str(e)
    # 네이버
    diag["naver_sector"] = _scrape_naver_sector(code)
    return diag


def prefetch_meta(codes: list[str], max_workers: int = 10):
    """DART/peer 메타를 병렬로 미리 캐시 워밍업.

    페이지 첫 로딩 시 종목별 직렬 호출 (~15초) → 병렬 (~2-3초)로 단축.
    """
    if not codes:
        return
    from concurrent.futures import ThreadPoolExecutor

    def _warm(c: str):
        try:
            from analyzer.stock_meta_dart import get_company_info
            get_company_info(c)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(_warm, codes))


# ──────────────────────────────────────────
# 일목 매수 시그널 (추천/관심 공용)
# ──────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_ichimoku_signal(code: str) -> dict:
    """종목 코드 → 컴팩트 일목 시그널 {stance, fresh, cloud_pos} (15분 캐시)."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import technical
        from chart_scenario import compute_ichimoku
        from chart_ichimoku import ichimoku_signal
        df = technical.fetch_ohlcv(code, days=180)
        df = technical.add_indicators(df)
        df = compute_ichimoku(df)
        return ichimoku_signal(df)
    except Exception:
        return {"stance": "NA", "fresh": False, "cloud_pos": None}


def prefetch_ichimoku(codes: list[str], max_workers: int = 8) -> None:
    """일목 시그널 캐시 병렬 워밍업 (리스트 첫 로딩 단축)."""
    if not codes:
        return
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        list(ex.map(get_ichimoku_signal, codes))


def ichimoku_badge(sig: dict) -> str:
    """일목 시그널 dict → 표시용 짧은 배지 (언어별). 과열(RSI≥70)이면 ⚠️ 덧붙임."""
    if not sig:
        return "—"
    if sig.get("fresh"):
        base = t("ichimoku_fresh")
    else:
        base = {
            "STRONG_BUY": t("ichimoku_strong_buy"),
            "BUY": t("ichimoku_buy"),
            "NEUTRAL": t("ichimoku_neutral"),
            "SELL": t("ichimoku_sell"),
            "STRONG_SELL": t("ichimoku_strong_sell"),
        }.get(sig.get("stance"), "—")
    if sig.get("overheated"):
        base = f"{base} {t('ichimoku_overheated')}"
    return base


def ichimoku_sort_key(sig: dict) -> int:
    """돌파/강매수 종목이 위로 오도록 정렬 키 (작을수록 위)."""
    if not sig:
        return 9
    if sig.get("fresh"):
        return 0
    return {
        "STRONG_BUY": 1, "BUY": 2, "NEUTRAL": 5, "SELL": 6, "STRONG_SELL": 7,
    }.get(sig.get("stance"), 8)


# ──────────────────────────────────────────
# 시장 레짐 (지수 일목)
# ──────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_market_regime_cached() -> dict:
    """코스피/코스닥 지수 일목 레짐 (15분 캐시)."""
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import market_context as mc
        return mc.get_market_regime()
    except Exception:
        return {}


def render_market_regime():
    """추천 페이지 상단 시장 레짐 배너 — 국내(코스피/코스닥) + 미장(S&P500/나스닥).

    지수가 구름 아래면 개별 매수신호 신뢰도가 낮으니 신중 안내.
    """
    reg = get_market_regime_cached()

    def _fmt(n: str) -> str:
        r = reg[n]
        return f"**{n}** {r['label']} {r.get('change', 0):+.1f}%"

    kr = [_fmt(n) for n in ("KOSPI", "KOSDAQ") if reg.get(n)]
    us = [_fmt(n) for n in ("S&P500", "NASDAQ") if reg.get(n)]
    if not kr and not us:
        return
    bear_kr = sum(1 for n in ("KOSPI", "KOSDAQ") if reg.get(n, {}).get("pos") == "below")
    lines = [f"**{t('market_regime_title')}**"]
    if kr:
        lines.append("🇰🇷 " + "  ·  ".join(kr))
    if us:
        lines.append("🇺🇸 " + "  ·  ".join(us))
    body = "\n\n".join(lines)
    if bear_kr == 2:
        st.error(f"{body}\n\n→ {t('market_regime_caution')}")
    elif bear_kr == 1:
        st.warning(body)
    else:
        st.info(body)


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
                + "".join(f"<li>{td(sig)}</li>" for sig in signals)
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
        ("🌙", "evening", 21, 0, t("rec_session_evening_desc")),
    ]

    st.markdown(f"##### {t('rec_session_progress')}")
    sess_cols = st.columns(2)
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

    # 시장 레짐 (코스피/코스닥 지수 일목) — 개별 신호 신뢰도 가늠용
    render_market_regime()

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

    # DART 메타 병렬 prefetch (첫 로딩 ~15초 → 2-3초)
    with st.spinner("📡 회사 정보 조회 중..."):
        prefetch_meta([r.get("stock_code", "") for r in recs if r.get("stock_code")])

    # 요약 카드
    total = len(recs)
    sessions_in_data = sorted({r.get("session") for r in recs if r.get("session")})

    # st.metric은 값 폰트가 커서(~2.25rem) 컴팩트 커스텀 카드로 대체
    recommended_at = to_kst_str(recs[0].get("recommended_at", ""))
    _metrics = [
        (t("rec_date"), str(target_date)),
        (t("rec_total"), f"{total}{t('rec_unit_count')}"),
        (t("rec_session_count"), ", ".join(sessions_in_data) or "-"),
        (t("rec_analyzed_at_kst"), recommended_at),
    ]
    for _col, (_lbl, _val) in zip(st.columns(4), _metrics):
        _col.markdown(
            f"<div style='line-height:1.3'>"
            f"<div style='font-size:0.72rem;color:#8a8a8a'>{_lbl}</div>"
            f"<div style='font-size:1.05rem;font-weight:700;color:#262730'>{_val}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # 7일 추이 분석 (옵션)
    if st.session_state.get(f"show_trend_{session}"):
        render_7d_trend(db, saved_dates)

    # 강세 테마 박스 (테이블 위)
    st.divider()
    render_hot_themes(recs)

    # 디버그: 테마 조회 진단 (첫 종목 기준)
    with st.expander("🔧 테마 조회 진단 (DART/네이버 상태)", expanded=False):
        if recs:
            sample_code = recs[0].get("stock_code", "")
            sample_name = recs[0].get("stock_name", "")
            st.caption(f"샘플: {sample_name} ({sample_code})")
            diag = diagnose_sector(sample_code)
            st.json(diag)

    # 컴팩트 정렬 테이블 + 종목 상세 펼침
    st.markdown(f"## {emoji} {label}")
    render_recommendations_table(recs, session)

    st.divider()
    st.caption(t("rec_footer"))


# ──────────────────────────────────────────
# 시안 B — 컴팩트 정렬 테이블 + 상세 펼침
# ──────────────────────────────────────────
def render_recommendations_table(recs: list[dict], session: str):
    """추천 종목 컴팩트 테이블 + 종목 선택 시 상세 펼침."""
    if not recs:
        st.info(t("rec_no_saved_for_date"))
        return

    # 컬럼명 (lang 일관성 위해 캐시)
    _c_rank = t("rec_tbl_col_rank")
    _c_stock = t("rec_tbl_col_stock")
    _c_tier = t("rec_tbl_col_tier")
    _c_theme = t("rec_tbl_col_theme")
    _c_price = t("rec_tbl_col_price")
    _c_change = t("rec_tbl_col_change")
    _c_score = t("rec_tbl_col_score")
    _c_horizon = t("rec_tbl_col_horizon")
    _c_foreign = t("rec_tbl_col_foreign5d")
    _c_inst = t("rec_tbl_col_inst5d")
    _c_reason = t("rec_tbl_col_reason")
    _c_ichimoku = t("ichimoku_col")

    tier_meta = get_tier_meta()
    tier_short = {"large": tier_meta["large"][0], "mid": tier_meta["mid"][0], "small": tier_meta["small"][0]}

    # 일목 시그널 병렬 워밍업 (캐시) → 루프에서 즉시 조회
    prefetch_ichimoku([r.get("stock_code") for r in recs if r.get("stock_code")])

    fresh_breakouts: list[str] = []
    rows = []
    for r in recs:
        code = r.get("stock_code")
        ichi = get_ichimoku_signal(code) if code else {}
        if ichi.get("fresh"):
            fresh_breakouts.append(r.get("stock_name", "") or code)
        sig = r.get("signals") or []
        h_key, _, _ = classify_horizon(sig, change_pct=r.get("change_pct"))
        sector = _resolve_sector(code)
        try:
            chg = float(r.get("change_pct") or 0)
        except (TypeError, ValueError):
            chg = 0
        # 핵심 이유: 첫 2개만, 없으면 "데이터 부족" 표시
        if sig:
            key_reasons = " · ".join(td(str(s)) for s in sig[:2])
        else:
            # signals 없는 종목 — 등락률 + 외인/기관 기반 fallback
            fb_parts = []
            if chg >= 5:
                fb_parts.append(f"📈 당일 +{chg:.1f}%")
            elif chg <= -3:
                fb_parts.append(f"📉 당일 {chg:.1f}%")
            f5 = int(r.get("foreign_5d") or 0)
            i5 = int(r.get("inst_5d") or 0)
            if f5 > 0:
                fb_parts.append(f"외인 +{f5}억")
            if i5 > 0:
                fb_parts.append(f"기관 +{i5}억")
            key_reasons = " · ".join(fb_parts) if fb_parts else f"⚠ {t('rec_card_no_reasons')}"
        tier = r.get("tier", "")
        rows.append({
            "_tier_order": {"large": 0, "mid": 1, "small": 2}.get(tier, 3),
            "_ichimoku_order": ichimoku_sort_key(ichi),
            _c_rank: r.get("rank_in_tier", 0),
            _c_stock: f"{r.get('stock_name', '')} ({code})",
            _c_ichimoku: ichimoku_badge(ichi),
            _c_tier: tier_short.get(tier, tier),
            _c_theme: sector or "—",
            _c_price: int(float(r.get("price") or 0)) if r.get("price") else 0,
            _c_change: chg,
            _c_score: int(r.get("score") or 0),
            _c_horizon: t(h_key),
            _c_foreign: int(r.get("foreign_5d") or 0),
            _c_inst: int(r.get("inst_5d") or 0),
            _c_reason: key_reasons,
        })

    # 돌파(삼역호전) 종목 상단 강조 요약줄
    if fresh_breakouts:
        st.success(f"{t('ichimoku_breakout_today')}: " + ", ".join(fresh_breakouts))

    # 돌파/강매수 → 상단, 그다음 tier·순위
    df = (
        pd.DataFrame(rows)
        .sort_values(["_ichimoku_order", "_tier_order", _c_rank])
        .drop(["_ichimoku_order", "_tier_order"], axis=1)
        .reset_index(drop=True)
    )

    # 행 클릭 → 선택 → 아래에 상세 펼침
    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            _c_price: st.column_config.NumberColumn(format="%d"),
            _c_change: st.column_config.NumberColumn(format="%+.2f%%"),
            _c_score: st.column_config.NumberColumn(format="%+d"),
            _c_foreign: st.column_config.NumberColumn(format="%+d 억"),
            _c_inst: st.column_config.NumberColumn(format="%+d 억"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key=f"rec_{session}_table",
    )

    st.caption(f"💡 {t('rec_horizon_hint')} · {t('rec_detail_select')}")

    # 선택된 행 → 상세 펼침
    sel_rec = None
    try:
        sel_rows = event.selection.rows  # type: ignore[attr-defined]
    except Exception:
        sel_rows = []
    if sel_rows:
        sel_idx = sel_rows[0]
        if 0 <= sel_idx < len(df):
            sel_label = df.iloc[sel_idx][_c_stock]
            sel_code = sel_label.split("(")[-1].rstrip(")")
            sel_rec = next((r for r in recs if r.get("stock_code") == sel_code), None)

    if sel_rec:
        st.markdown("---")
        _render_stock_detail(sel_rec, session)


def _render_stock_detail(stock: dict, session: str):
    """선택된 종목 상세: 관점 + 추천 이유 전체 + 동종업종 비교."""
    code = stock.get("stock_code", "")
    name = stock.get("stock_name", "")
    price = stock.get("price")
    change_pct = stock.get("change_pct")
    score = stock.get("score", 0)
    market_cap = stock.get("market_cap_eok") or 0
    foreign_5d = stock.get("foreign_5d") or 0
    inst_5d = stock.get("inst_5d") or 0
    signals = stock.get("signals") or []
    h_key, short_score, long_score = classify_horizon(signals, change_pct=change_pct)
    sector = _resolve_sector(code) or t("rec_card_no_theme")
    # DART 회사 정보 (sector 외 추가 메타)
    try:
        from analyzer.stock_meta_dart import get_company_info
        company = get_company_info(code) or {}
    except Exception:
        company = {}
    won = t("rec_unit_won")
    eok = t("rec_unit_eok")

    with st.container(border=True):
        # 헤더
        hc1, hc2, hc3 = st.columns([3, 2, 2])
        with hc1:
            st.markdown(f"### {name}  `{code}`")
            st.markdown(
                f"<div style='display:inline-block;padding:2px 10px;border-radius:10px;"
                f"background:#EEF3FB;color:#1B6FB0;font-size:0.85rem;font-weight:600;margin-right:6px;'>"
                f"{t('rec_card_theme')}: {sector}</div>"
                f"<div style='display:inline-block;padding:2px 10px;border-radius:10px;"
                f"background:#FFF4E6;color:#B5651D;font-size:0.85rem;font-weight:600;'>"
                f"{t('rec_detail_horizon_label')}: {t(h_key)} "
                f"<span style='color:#888;font-weight:400;'>(단타 {short_score} · 장기 {long_score})</span></div>",
                unsafe_allow_html=True,
            )
        with hc2:
            cs = f"{float(change_pct):+.2f}%" if change_pct else None
            st.metric(t("rec_card_price"), f"{int(float(price)):,}{won}" if price else "-", cs)
        with hc3:
            st.metric(t("rec_card_score"), f"{int(score):+}")

        # 보조 지표
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
            if st.button(t("rec_card_detail"), key=f"detail_btn_{session}_{code}", use_container_width=True):
                st.session_state["last_query"] = name
                st.switch_page("app.py")

        # DART 회사 정보 (있을 때만)
        if company:
            info_parts = []
            if company.get("ceo"):
                info_parts.append(f"👤 {company['ceo']}")
            if company.get("est_date") and len(company["est_date"]) == 8:
                d = company["est_date"]
                info_parts.append(f"📅 {d[:4]}.{d[4:6]}.{d[6:]} 설립")
            if company.get("homepage"):
                hp = company["homepage"]
                info_parts.append(f"🌐 <a href='{hp}' target='_blank' style='color:#1B6FB0;'>{hp.replace('http://', '').replace('https://', '').rstrip('/')[:40]}</a>")
            info_line = " · ".join(info_parts) if info_parts else ""
            company_name = company.get("company_name", name)
            st.markdown(
                f"<div style='margin-top:6px;padding:10px 14px;border-radius:8px;"
                f"background:#F0F7FF;border-left:4px solid #1B6FB0;'>"
                f"<div style='font-weight:700;color:#1B6FB0;margin-bottom:3px;'>"
                f"🏢 회사 정보</div>"
                f"<div style='font-size:0.88rem;color:#333;'><strong>{company_name}</strong> · {sector}</div>"
                + (f"<div style='font-size:0.78rem;color:#666;margin-top:2px;'>{info_line}</div>" if info_line else "")
                + "</div>",
                unsafe_allow_html=True,
            )

        # 추천 이유 (전체)
        st.markdown(
            f"<div style='margin-top:8px;padding:10px 14px;border-radius:8px;"
            f"background:#FFF9E6;border-left:4px solid #F1C40F;'>"
            f"<div style='font-weight:700;color:#7A5C00;margin-bottom:4px;'>"
            f"{t('rec_detail_all_reasons')}</div>"
            + (
                "<ul style='margin:0;padding-left:20px;color:#5A4500;'>"
                + "".join(f"<li>{td(sig)}</li>" for sig in signals)
                + "</ul>"
                if signals
                else f"<div style='color:#8A7000;'>{t('rec_card_no_reasons')}</div>"
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        # 동종업종 비교
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
                self_chg = next((p["change_pct"] for p in peers if p["code"] == code), None)
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
