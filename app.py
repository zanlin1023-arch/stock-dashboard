"""메인 대시보드 — 보유 종목 종합 분석 (포트폴리오 카드)."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from common import init_page, get_db, sidebar_nav, render_macro_header
from i18n import t, td

st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_page(t("nav_dashboard"))
sidebar_nav()

# 거시경제 헤더 (모든 페이지 공통)
render_macro_header()


# ───────────────────────────────────────────────────────
# 헤더
# ───────────────────────────────────────────────────────
st.title("📊 " + t("dashboard_title"))
st.markdown(t("dashboard_subtitle"))


# ───────────────────────────────────────────────────────
# DB 체크
# ───────────────────────────────────────────────────────
db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()

holdings = db.list_holdings()
if not holdings:
    st.info(
        f"{t('dashboard_no_holdings')}\n\n"
        f"{t('home_link_holdings_hint')}"
    )
    st.stop()


# ───────────────────────────────────────────────────────
# 실시간 시세 + 분석 모듈 로드 (캐시)
# ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent / "analyzer"))


# ───────────────────────────────────────────────────────
# 보유자 관점 액션 판단 (신규 진입 판단과 분리)
#   - 입력: 손익률 + RSI + 일목 위치/TK + 종합 stance
#   - 출력: "들고 갈지 / 익절할지 / 추가매수할지 / 손절할지"
# ───────────────────────────────────────────────────────
def decide_holding_action(
    pnl_pct: float | None,
    rsi: float | None,
    cloud_pos: str | None,
    tk_bull: bool | None,
    stance: str | None,
    flow_verdict: str | None = None,
) -> tuple[str, str]:
    """보유자 액션 라벨과 색상 hex 반환.

    flow_verdict: market_context.detect_flow_reversal()의 verdict 문자열
      - "🟢 외인+기관 동반 매수" / "✅ 외국인 매수 전환"  → 강세 수급
      - "🔴 외인+기관 동반 매도" / "⚠️ 외국인 매도 전환" → 약세 수급
      - "🟡 외인/기관 분리 (혼조)"                          → 중립
    """
    p = pnl_pct if pnl_pct is not None else 0.0
    r = rsi if rsi is not None else 50.0
    bullish = stance in ("STRONG_BUY", "BUY")
    bearish = stance in ("STRONG_SELL", "SELL")
    weak_trend = cloud_pos == "below" or tk_bull is False

    # ── 1) 일목+RSI 기반 기본 액션 ──
    if p <= -10 and weak_trend:
        base = (t("holder_action_stoploss"), "#E74C3C")
    elif p >= 50 and (r >= 75 or cloud_pos == "below"):
        base = (t("holder_action_takeprofit_all"), "#C0392B")
    elif p >= 20 and r >= 70:
        base = (t("holder_action_takeprofit_part"), "#E67E22")
    elif p >= 5 and stance == "STRONG_BUY" and r < 65:
        base = (t("holder_action_addbuy_strong"), "#27AE60")
    elif p <= -5 and cloud_pos == "above" and r < 40:
        base = (t("holder_action_addbuy_oversold"), "#3498DB")
    elif p >= 0 and bullish and r < 70:
        base = (t("holder_action_hold_trend"), "#2ECC71")
    elif p < 0 and bullish:
        base = (t("holder_action_hold_wait"), "#5DADE2")
    elif bearish and p > 0:
        base = (t("holder_action_partial_exit"), "#F39C12")
    else:
        base = (t("holder_action_observe"), "#7F8C8D")

    # ── 2) 수급 보조 신호 (일목 액션은 유지, 라벨에 마크만 추가) ──
    if not flow_verdict:
        return base

    label, color = base
    fv = flow_verdict
    # 한글/번체 모두 매칭: 한글 raw + 번체 키워드
    bull_flow = (
        ("동반 매수" in fv) or ("매수 전환" in fv)
        or ("同步買入" in fv) or ("買入轉" in fv) or ("買進轉" in fv)
    )
    bear_flow = (
        ("동반 매도" in fv) or ("매도 전환" in fv)
        or ("同步賣出" in fv) or ("賣出轉" in fv)
    )

    if bull_flow and (bearish or weak_trend):
        # 일목은 약세인데 수급은 강세 → 추세 반전 가능 (보유자는 손절 보류)
        label = label + "  ·  " + t("holder_flow_reversal")
    elif bear_flow and bullish:
        # 일목 강세인데 수급은 이탈 → 익절 우호
        label = label + "  ·  " + t("holder_flow_outflow_warn")
    elif bull_flow and bullish:
        label = label + "  ·  " + t("holder_flow_align_bull")
    elif bear_flow and bearish:
        label = label + "  ·  " + t("holder_flow_align_bear")
    # 혼조는 표기 생략 (노이즈)

    return (label, color)


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_flow_summary(code: str) -> dict | None:
    """외국인/기관 수급 종합 + 세부 (30분 캐시).

    Returns:
        {
            "verdict": "🟡 외인/기관 분리 (혼조)",       # 종합
            "detail": "외인 -8,765주 ↘ · 기관 +5,432주 ↗",  # A옵션 세부 라벨
        }
    """
    try:
        import market_context as mc
        flow = mc.detect_flow_reversal(code, lookback=7)
        if not flow.get("available"):
            return None
        rf = int(flow.get("recent_foreign_net") or 0)
        ri = int(flow.get("recent_inst_net") or 0)
        f_arrow = "↗" if rf > 0 else ("↘" if rf < 0 else "→")
        i_arrow = "↗" if ri > 0 else ("↘" if ri < 0 else "→")
        detail = t("flow_detail_format", f=rf, f_arrow=f_arrow, i=ri, i_arrow=i_arrow)
        return {"verdict": flow.get("verdict"), "detail": detail}
    except Exception:
        return None


# 하위 호환 alias (혹시 다른 호출처가 있으면 verdict 문자열만 반환)
def _fetch_flow_verdict(code: str) -> str | None:
    s = _fetch_flow_summary(code)
    return s.get("verdict") if s else None


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_stock_meta(code: str, name: str) -> dict:
    """업종/테마 정보 (24시간 캐시)."""
    try:
        import enrich
        meta = enrich._enrich_via_naver(code, name)
        return {
            "sector": meta.get("sector", "") or "",
            "themes": meta.get("themes", []) or [],
        }
    except Exception:
        return {"sector": "", "themes": []}


@st.cache_data(ttl=300, show_spinner=False)
def _analyze_one(code: str, name: str) -> dict:
    """단일 종목 빠른 분석 — 현재가/RSI/일목 위치/의사결정/수급/섹터."""
    import technical
    from chart_ichimoku import (
        compute_ichimoku,
        detect_swing_points,
        compute_price_targets,
        cap_targets,
        make_decision,
    )

    try:
        df = technical.fetch_ohlcv(code, days=90)
        df = technical.add_indicators(df)
        df = compute_ichimoku(df)
        last = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else last

        price = float(last["close"])
        prev_price = float(prev["close"])
        change_pct = (price / prev_price - 1) * 100 if prev_price else 0.0
        rsi = float(last["rsi_14"]) if "rsi_14" in df.columns and last["rsi_14"] == last["rsi_14"] else None

        # 일목
        swings = detect_swing_points(df, lookback=min(80, len(df)))
        A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
        targets = compute_price_targets(A, B, C)
        # ATR cap 통일 (대시보드 target_n도 차트와 동일한 cap 적용)
        _atr_val = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns and df["atr_14"].iloc[-1] == df["atr_14"].iloc[-1] else None
        targets = cap_targets(targets, price, _atr_val)
        decision = make_decision(df, swings, targets)

        # 수급 (캐시) + 섹터/테마 (캐시)
        flow_summary = _fetch_flow_summary(code) or {}
        flow_verdict = flow_summary.get("verdict")
        flow_detail = flow_summary.get("detail")
        meta = _fetch_stock_meta(code, name)

        return {
            "code": code,
            "name": name,
            "price": price,
            "change_pct": change_pct,
            "rsi": rsi,
            "cloud_pos": decision.get("cloud_pos"),
            "stance": decision.get("stance"),
            "action": decision.get("action"),
            "target_n": targets.get("N"),
            "stop": decision.get("stop"),
            "tk_bull": decision.get("tk_bull"),
            "flow_verdict": flow_verdict,
            "flow_detail": flow_detail,
            "sector": meta.get("sector"),
            "themes": meta.get("themes", []),
            "ok": True,
        }
    except Exception as e:
        return {"code": code, "name": name, "ok": False, "error": str(e)}


with st.spinner(t("dashboard_loading")):
    analyses = []
    for h in holdings:
        a = _analyze_one(h["stock_code"], h["stock_name"])
        a["avg_price"] = float(h["avg_price"])
        a["quantity"] = int(h["quantity"])
        analyses.append(a)


# ───────────────────────────────────────────────────────
# 1단 — 포트폴리오 요약 (4 메트릭)
# ───────────────────────────────────────────────────────
total_buy = 0.0
total_eval = 0.0
for a in analyses:
    qty = a.get("quantity", 1)
    avg = a.get("avg_price", 0)
    cur = a.get("price") or avg
    total_buy += avg * qty
    total_eval += cur * qty

total_pnl = total_eval - total_buy
total_pnl_pct = (total_pnl / total_buy * 100) if total_buy else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric(t("total_buy"), f"{total_buy:,.0f}")
c2.metric(t("total_eval"), f"{total_eval:,.0f}")
c3.metric(t("total_pnl"), f"{total_pnl:+,.0f}", delta_color="normal")
c4.metric(t("pnl_pct"), f"{total_pnl_pct:+.2f}%")

st.divider()


# ───────────────────────────────────────────────────────
# 2단 — 베스트/워스트 + 종목별 비중 파이차트
# ───────────────────────────────────────────────────────
col_left, col_right = st.columns([1, 1])

# 종목별 손익률 계산
per_stock = []
for a in analyses:
    if not a.get("ok"):
        continue
    avg = a["avg_price"]
    cur = a.get("price") or avg
    qty = a.get("quantity", 1)
    pnl_pct = (cur / avg - 1) * 100 if avg else 0.0
    eval_amount = cur * qty
    buy_amount = avg * qty
    per_stock.append({
        "name": a["name"],
        "code": a["code"],
        "pnl_pct": pnl_pct,
        "eval_amount": eval_amount,
        "buy_amount": buy_amount,
        "rsi": a.get("rsi"),
        "cloud_pos": a.get("cloud_pos"),
        "stance": a.get("stance"),
        "action": a.get("action"),
        "target_n": a.get("target_n"),
        "tk_bull": a.get("tk_bull"),
        "price": a.get("price"),
        "avg_price": avg,
        "flow_verdict": a.get("flow_verdict"),
        "flow_detail": a.get("flow_detail"),
        "sector": a.get("sector"),
        "themes": a.get("themes", []),
    })

sorted_pnl = sorted(per_stock, key=lambda x: -x["pnl_pct"])

with col_left:
    st.subheader("🏆 " + t("best_worst"))
    if sorted_pnl:
        st.markdown(f"**🥇 {t('best')}**")
        for s in sorted_pnl[:3]:
            color = "🟢" if s["pnl_pct"] >= 0 else "🔴"
            st.markdown(f"  {color} **{s['name']}**  `{s['pnl_pct']:+.2f}%`")
        if len(sorted_pnl) >= 4:
            st.markdown(f"**💔 {t('worst')}**")
            for s in sorted_pnl[-2:]:
                color = "🟢" if s["pnl_pct"] >= 0 else "🔴"
                st.markdown(f"  {color} **{s['name']}**  `{s['pnl_pct']:+.2f}%`")

with col_right:
    st.subheader("🥧 " + t("portfolio_weight"))
    import pandas as pd
    _col_stock = t("home_card_col_stock")
    _col_eval = t("home_card_col_eval")
    weights = pd.DataFrame([
        {_col_stock: s["name"], _col_eval: s["eval_amount"]}
        for s in per_stock
    ]).sort_values(_col_eval, ascending=False).reset_index(drop=True)

    if not weights.empty:
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        # CJK 폰트 fallback chain — 한글 + 번체/간체 한자 모두 커버
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [
            "Malgun Gothic", "NanumGothic", "AppleGothic",
            "Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK KR",
            "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC",
            "DejaVu Sans",
        ]

        fig, ax = plt.subplots(figsize=(5, 5))
        colors = plt.cm.Pastel1(range(len(weights)))
        total = weights[_col_eval].sum()

        # 작은 조각(<5%)은 라벨/% 표시 안 함 → 겹침 방지
        def _autopct(pct):
            return f"{pct:.1f}%" if pct >= 5.0 else ""

        labels_for_pie = [
            name if (val / total * 100) >= 5.0 else ""
            for name, val in zip(weights[_col_stock], weights[_col_eval])
        ]

        wedges, texts, autotexts = ax.pie(
            weights[_col_eval],
            labels=labels_for_pie,
            autopct=_autopct,
            startangle=90,
            colors=colors,
            textprops={"fontsize": 10},
            pctdistance=0.75,
            labeldistance=1.1,
        )
        ax.axis("equal")

        # 작은 비중 종목은 범례에 모두 표시
        legend_labels = [
            f"{name}  {val/total*100:.1f}%"
            for name, val in zip(weights[_col_stock], weights[_col_eval])
        ]
        ax.legend(wedges, legend_labels, title=t("portfolio_weight"),
                  loc="center left", bbox_to_anchor=(1.0, 0.5), fontsize=9)

        st.pyplot(fig)
        plt.close(fig)

st.divider()


# ───────────────────────────────────────────────────────
# 3단 — 종목별 수익률 막대차트
# ───────────────────────────────────────────────────────
st.subheader("📊 " + t("per_stock_returns"))
if per_stock:
    import pandas as pd
    _bcol_stock = t("home_card_col_stock")
    _bcol_pnl = t("home_card_col_pnl_pct")
    bar_df = pd.DataFrame([
        {_bcol_stock: s["name"], _bcol_pnl: round(s["pnl_pct"], 2)}
        for s in sorted_pnl
    ]).set_index(_bcol_stock)
    st.bar_chart(bar_df, height=250)

st.divider()


# ───────────────────────────────────────────────────────
# 4단 — 주의 종목 자동 감지
# ───────────────────────────────────────────────────────
st.subheader("🚨 " + t("alerts"))

# 종목당 한 줄로 합침 — 같은 종목이 RSI/구름/손익 조건을 동시에 만족해도
# 여러 줄로 쪼개지지 않게 code 기준으로 묶고, 시그널은 ' · '로 병합.
# 대표 이모지는 가장 시급한 시그널(prio 낮을수록 시급) 것을 사용.
from collections import OrderedDict

_alert_map: "OrderedDict[str, dict]" = OrderedDict()

def _push_alert(stock: dict, emoji: str, msg: str, prio: int) -> None:
    key = stock.get("code") or stock["name"]
    entry = _alert_map.get(key)
    if entry is None:
        _alert_map[key] = {"name": stock["name"], "emoji": emoji, "msgs": [msg], "prio": prio}
        return
    if msg not in entry["msgs"]:
        entry["msgs"].append(msg)
    if prio < entry["prio"]:
        entry["emoji"] = emoji
        entry["prio"] = prio

for s in per_stock:
    # RSI 극단
    if s["rsi"] is not None:
        if s["rsi"] >= 80:
            _push_alert(s, "🔴", f"RSI {s['rsi']:.1f} — {t('alert_overbought')}", 2)
        elif s["rsi"] <= 25:
            _push_alert(s, "🟢", f"RSI {s['rsi']:.1f} — {t('alert_oversold')}", 4)
    # 구름 아래 + TK 데드
    if s["cloud_pos"] == "below" and not s.get("tk_bull"):
        _push_alert(s, "⚠️", t("alert_bearish_full"), 1)
    # 큰 손실
    if s["pnl_pct"] <= -10:
        _push_alert(s, "🔻", f"{t('alert_pnl_prefix')} {s['pnl_pct']:+.1f}% — {t('alert_review_stop')}", 0)
    # 큰 수익
    if s["pnl_pct"] >= 20:
        _push_alert(s, "🎯", f"{t('alert_pnl_prefix')} {s['pnl_pct']:+.1f}% — {t('alert_take_profit')}", 3)

if not _alert_map:
    st.success(t("no_alerts"))
else:
    # 시급한 종목(prio 낮음)부터 위로
    for e in sorted(_alert_map.values(), key=lambda x: x["prio"]):
        st.markdown(f"- {e['emoji']} **{e['name']}** — {' · '.join(e['msgs'])}")


st.divider()


# ───────────────────────────────────────────────────────
# 5단 — 보유 목록 미니 카드 (요약)
# ───────────────────────────────────────────────────────
st.subheader("📋 " + t("holdings_summary"))

# 보유 종목 카드 2x3 그리드
for i in range(0, len(per_stock), 3):
    cols = st.columns(3)
    for j, s in enumerate(per_stock[i:i + 3]):
        with cols[j]:
            with st.container(border=True):
                st.markdown(f"**{s['name']}**  `{s['code']}`")

                # 섹터 + 테마 태그
                sector = s.get("sector")
                themes = s.get("themes") or []
                if sector or themes:
                    chips = []
                    if sector:
                        chips.append(
                            f"<span style='background:#EAF4FB;color:#1B6FB0;"
                            f"padding:2px 8px;border-radius:10px;font-size:0.72rem;"
                            f"font-weight:600;margin-right:4px;'>🏢 {sector}</span>"
                        )
                    for th in themes[:3]:
                        chips.append(
                            f"<span style='background:#FFF4E6;color:#B5651D;"
                            f"padding:2px 8px;border-radius:10px;font-size:0.72rem;"
                            f"margin-right:4px;'>#{th}</span>"
                        )
                    st.markdown(
                        f"<div style='margin:2px 0 8px 0;line-height:1.8;'>{''.join(chips)}</div>",
                        unsafe_allow_html=True,
                    )

                if s.get("price"):
                    pnl_color = "🟢" if s["pnl_pct"] >= 0 else "🔴"
                    st.metric(
                        t("current_price"),
                        f"{int(s['price']):,}",
                        f"{s['pnl_pct']:+.2f}% {pnl_color}",
                    )
                cloud_emoji = {"above": "📈", "below": "📉", "inside": "➖"}.get(s.get("cloud_pos"), "")
                rsi_txt = f"RSI {s['rsi']:.0f}" if s.get("rsi") else ""
                tk_txt = "TK✅" if s.get("tk_bull") else "TK⚠️"
                st.caption(f"{cloud_emoji} {rsi_txt} · {tk_txt}")

                # 수급 시그널 (외국인/기관) — verdict + 세부 (A옵션)
                if s.get("flow_verdict"):
                    st.caption(f"{t('home_card_supply')}: {td(s['flow_verdict'])}")
                    if s.get("flow_detail"):
                        st.markdown(
                            f"<div style='font-size:0.78rem;color:#666;margin-left:18px;"
                            f"margin-top:-6px;margin-bottom:4px;'>{s['flow_detail']}</div>",
                            unsafe_allow_html=True,
                        )

                # 보유자 액션 (들고 갈지/익절/추가매수/손절) — 일목+RSI+수급 결합
                holder_action, holder_color = decide_holding_action(
                    pnl_pct=s.get("pnl_pct"),
                    rsi=s.get("rsi"),
                    cloud_pos=s.get("cloud_pos"),
                    tk_bull=s.get("tk_bull"),
                    stance=s.get("stance"),
                    flow_verdict=s.get("flow_verdict"),
                )
                st.markdown(
                    f"<div style='padding:6px 10px;border-radius:6px;"
                    f"background:{holder_color}15;border-left:3px solid {holder_color};"
                    f"font-size:0.85rem;color:{holder_color};font-weight:600;'>"
                    f"{holder_action}</div>",
                    unsafe_allow_html=True,
                )
                if s.get("action"):
                    st.caption(f"{t('home_card_signal')}: {td(s['action'])}")
                if st.button(t("detail_analysis"), key=f"dash_anly_{i}_{j}_{s['code']}", use_container_width=True):
                    st.session_state["last_query"] = s["name"]
                    st.switch_page("pages/5_🔬_종목_분석.py")


# 푸터
st.divider()
st.caption(
    f"⚡ {t('dashboard_footer_hint')}"
)
