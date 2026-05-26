"""메인 대시보드 — 보유 종목 종합 분석 (포트폴리오 카드)."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from common import init_page, get_db, sidebar_nav
from i18n import t

st.set_page_config(
    page_title="Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_page("대시보드")
sidebar_nav()


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
        f"👉 [💼 보유 종목 페이지](/💼_보유_종목)에서 종목을 추가하면 여기서 종합 분석이 표시됩니다."
    )
    st.stop()


# ───────────────────────────────────────────────────────
# 실시간 시세 + 분석 모듈 로드 (캐시)
# ───────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent / "analyzer"))


@st.cache_data(ttl=300, show_spinner=False)
def _analyze_one(code: str, name: str) -> dict:
    """단일 종목 빠른 분석 — 현재가/RSI/일목 위치/의사결정."""
    import technical
    from chart_ichimoku import (
        compute_ichimoku,
        detect_swing_points,
        compute_price_targets,
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
        decision = make_decision(df, swings, targets)

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
    weights = pd.DataFrame([
        {"종목": s["name"], "평가금액": s["eval_amount"]}
        for s in per_stock
    ]).sort_values("평가금액", ascending=False).reset_index(drop=True)

    if not weights.empty:
        import matplotlib.pyplot as plt
        from matplotlib import font_manager

        for fn in ["Malgun Gothic", "NanumGothic", "AppleGothic"]:
            try:
                if any(f.name == fn for f in font_manager.fontManager.ttflist):
                    plt.rcParams["font.family"] = fn
                    break
            except Exception:
                pass

        fig, ax = plt.subplots(figsize=(5, 5))
        colors = plt.cm.Pastel1(range(len(weights)))
        total = weights["평가금액"].sum()

        # 작은 조각(<5%)은 라벨/% 표시 안 함 → 겹침 방지
        def _autopct(pct):
            return f"{pct:.1f}%" if pct >= 5.0 else ""

        labels_for_pie = [
            name if (val / total * 100) >= 5.0 else ""
            for name, val in zip(weights["종목"], weights["평가금액"])
        ]

        wedges, texts, autotexts = ax.pie(
            weights["평가금액"],
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
            for name, val in zip(weights["종목"], weights["평가금액"])
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
    bar_df = pd.DataFrame([
        {"종목": s["name"], "수익률(%)": round(s["pnl_pct"], 2)}
        for s in sorted_pnl
    ]).set_index("종목")
    st.bar_chart(bar_df, height=250)

st.divider()


# ───────────────────────────────────────────────────────
# 4단 — 주의 종목 자동 감지
# ───────────────────────────────────────────────────────
st.subheader("🚨 " + t("alerts"))
alerts = []
for s in per_stock:
    # RSI 극단
    if s["rsi"] is not None:
        if s["rsi"] >= 80:
            alerts.append(("🔴", s["name"], f"RSI {s['rsi']:.1f} — {t('alert_overbought')}"))
        elif s["rsi"] <= 25:
            alerts.append(("🟢", s["name"], f"RSI {s['rsi']:.1f} — {t('alert_oversold')}"))
    # 구름 아래 + TK 데드
    if s["cloud_pos"] == "below" and not s.get("tk_bull"):
        alerts.append(("⚠️", s["name"], t("alert_bearish_full")))
    # 큰 손실
    if s["pnl_pct"] <= -10:
        alerts.append(("🔻", s["name"], f"손익 {s['pnl_pct']:+.1f}% — {t('alert_review_stop')}"))
    # 큰 수익
    if s["pnl_pct"] >= 20:
        alerts.append(("🎯", s["name"], f"손익 {s['pnl_pct']:+.1f}% — {t('alert_take_profit')}"))

if not alerts:
    st.success(t("no_alerts"))
else:
    for emoji, name, msg in alerts:
        st.markdown(f"- {emoji} **{name}** — {msg}")


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
                if s.get("action"):
                    st.caption(f"💡 {s['action']}")
                if st.button(f"🔬 " + t("detail_analysis"), key=f"dash_anly_{s['code']}", use_container_width=True):
                    st.session_state["last_query"] = s["name"]
                    st.switch_page("pages/5_🔬_종목_분석.py")


# 푸터
st.divider()
st.caption(
    f"⚡ {t('dashboard_footer_hint')}"
)
