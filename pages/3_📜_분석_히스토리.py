"""분석 히스토리 — Supabase analysis_history 테이블 조회."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

from common import init_page, get_db, nav_bar, sidebar_nav, render_macro_header
from i18n import t

st.set_page_config(page_title="분석 히스토리", page_icon="📜", layout="wide")
init_page("분석 히스토리")
sidebar_nav()
render_macro_header()
nav_bar("history")


# Supabase TIMESTAMPTZ는 UTC로 저장됨 → KST(+9h)로 변환해 표시
KST = timezone(timedelta(hours=9))


def _to_kst_str(utc_iso: str, with_label: bool = True) -> str:
    """ISO 8601 UTC 문자열 → 'YYYY-MM-DD HH:MM:SS KST'."""
    if not utc_iso:
        return ""
    try:
        s = utc_iso.replace("Z", "+00:00")
        # Supabase는 마이크로초 6자리 + tz, fromisoformat이 처리 가능
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        kst = dt.astimezone(KST)
        return kst.strftime("%Y-%m-%d %H:%M:%S" + (" KST" if with_label else ""))
    except Exception:
        # fallback
        return utc_iso[:19].replace("T", " ")

st.title(t("history_title"))

db = get_db()
if db is None:
    st.error(t("db_disconnected"))
    st.stop()


# ──────────────────────────────────────────
# 종목 필터 (또는 전체)
# ──────────────────────────────────────────
client = db.get_client()
if not client:
    st.error("DB 클라이언트 로드 실패")
    st.stop()

# 전체 데이터 조회
res = client.table("analysis_history").select("*").order("analyzed_at", desc=True).limit(500).execute()
all_records = res.data or []

if not all_records:
    st.info(t("history_empty"))
    st.stop()


# ──────────────────────────────────────────
# 💼 자동 보유 / ⭐ 자동 관심 / 👤 수동 일회성 — 3-way 분류
# 카테고리 라디오는 사이드바(common._render_history_subnav)에 표시됨
# ──────────────────────────────────────────
# 보유/관심 종목 코드 셋 (자동 스냅샷을 보유/관심으로 분류)
holding_codes: set[str] = set()
watch_codes: set[str] = set()
try:
    for h in db.list_holdings():
        holding_codes.add(h["stock_code"])
except Exception:
    pass
try:
    for w in db.list_watchlist():
        watch_codes.add(w["stock_code"])
except Exception:
    pass

scheduled = [r for r in all_records if r.get("snapshot_type") == "scheduled"]
# 보유에 있으면 보유, 아니면 관심에 있으면 관심, 둘 다 아니면 보유로 fallback (구버전 데이터)
auto_hold_records = [r for r in scheduled if r["stock_code"] in holding_codes]
auto_watch_records = [
    r for r in scheduled
    if r["stock_code"] not in holding_codes and r["stock_code"] in watch_codes
]
# 보유에서 빠졌고 관심에도 없는 옛 자동 기록은 보유 탭에 표시 (orphan)
orphan_auto = [
    r for r in scheduled
    if r["stock_code"] not in holding_codes and r["stock_code"] not in watch_codes
]
auto_hold_records += orphan_auto
manual_records = [r for r in all_records if r.get("snapshot_type") != "scheduled"]

# 사이드바 라디오용 카운트 전달 (분석 히스토리 페이지일 때 sidebar_nav가 다시 렌더되며 사용)
st.session_state["_hist_counts"] = {
    "auto_hold": len(auto_hold_records),
    "auto_watch": len(auto_watch_records),
    "manual": len(manual_records),
}

# 현재 카테고리 결정 — 이모지로 분기 (한글/중문 모두 같은 이모지 prefix)
category = st.session_state.get("hist_category", "")
if not category:
    cat_mode = "hold"  # 기본
elif category.startswith("⭐"):
    cat_mode = "watch"
elif category.startswith("👤"):
    cat_mode = "manual"
else:
    cat_mode = "hold"


def _render_table(records: list[dict]):
    """공통 테이블 렌더 — 미래 경로(future_path) + 수급(flow) 컬럼 포함."""
    rows = []
    for r in records:
        # raw_data에서 future_path / flow 추출
        raw = r.get("raw_data") or {}
        fp = raw.get("future_path") or []
        flow = raw.get("flow") or {}
        price_now = float(r.get("price") or 0)

        # 미래 1차 (첫 피크)
        future_1st = "-"
        if fp:
            p = fp[0]
            pct = (p.get("price", 0) / price_now - 1) * 100 if price_now else 0
            future_1st = (
                f"+{p.get('cycle')}봉 · {p.get('label', '')} "
                f"{p.get('price', 0):,.0f} ({pct:+.1f}%)"
            )

        # 미래 2차 (조정)
        future_2nd = "-"
        if len(fp) >= 2:
            p = fp[1]
            pct = (p.get("price", 0) / price_now - 1) * 100 if price_now else 0
            future_2nd = (
                f"+{p.get('cycle')}봉 · {p.get('label', '')} "
                f"{p.get('price', 0):,.0f} ({pct:+.1f}%)"
            )

        # 미래 3차 (재상승)
        future_3rd = "-"
        if len(fp) >= 3:
            p = fp[2]
            pct = (p.get("price", 0) / price_now - 1) * 100 if price_now else 0
            future_3rd = (
                f"+{p.get('cycle')}봉 · {p.get('label', '')} "
                f"{p.get('price', 0):,.0f} ({pct:+.1f}%)"
            )

        # 수급 verdict (짧게)
        flow_short = flow.get("verdict", "-") or "-"

        rows.append({
            "분석시각 (KST)": _to_kst_str(r.get("analyzed_at", ""), with_label=False),
            "종목": f"{r.get('stock_name', '')} ({r.get('stock_code', '')})",
            "현재가": f"{r['price']:,.0f}" if r.get("price") else "-",
            "RSI": f"{r['rsi_14']:.1f}" if r.get("rsi_14") else "-",
            "구름": {
                "above": "위 ↑", "below": "아래 ↓", "inside": "안 ↔",
            }.get(r.get("cloud_position", ""), "-"),
            "판단": r.get("decision_action", "-") or "-",
            "🔺 1차 (피크)": future_1st,
            "🔻 2차 (조정)": future_2nd,
            "🔺 3차 (재상승)": future_3rd,
            "💹 수급": flow_short,
            "N목표": f"{r['target_n']:,.0f}" if r.get("target_n") else "-",
            "손절": f"{r['stop_loss']:,.0f}" if r.get("stop_loss") else "-",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_raw_data_expanders(records: list[dict], limit: int = 5):
    """raw_data (future_path/flow/cycles/swings) expander 형태로 표시."""
    has_any = False
    for r in records[:limit]:
        raw = r.get("raw_data") or {}
        fp = raw.get("future_path") or []
        flow = raw.get("flow") or {}
        cycles_data = raw.get("cycles") or []
        swings_data = raw.get("swings") or {}

        when_kst = _to_kst_str(r.get("analyzed_at", ""))
        action = r.get("decision_action", "-") or "-"

        with st.expander(f"📅 {when_kst}  ·  {action}", expanded=False):
            st.markdown("**📈 미래 추세 예측 (N파동 시나리오)**")
            if fp:
                has_any = True
                for p in fp:
                    role = "🔺 피크" if p.get("is_peak") else "🔻 조정"
                    pct = (p.get("price", 0) / float(r.get("price") or 1) - 1) * 100 if r.get("price") else 0
                    st.markdown(
                        f"- {role} · **{p.get('label', '')}** "
                        f"({p.get('cycle')}봉 후) → "
                        f"**{p.get('price', 0):,.0f}원** ({pct:+.1f}%)"
                    )
            else:
                st.caption("ℹ️ 미래 경로 데이터 없음")

            st.markdown("**💹 외국인/기관 수급 (7일)**")
            if flow.get("verdict"):
                has_any = True
                st.markdown(f"- 종합: **{flow['verdict']}**")
                for sig in (flow.get("signals") or [])[:3]:
                    st.caption(f"  · {sig}")
            else:
                st.caption("ℹ️ 수급 데이터 없음")

            future_cycles = [c for c in cycles_data if c.get("is_future")]
            if future_cycles:
                has_any = True
                st.markdown("**⏰ 다음 시간 변곡점 (일목 시간론)**")
                for c in future_cycles[:5]:
                    st.caption(f"  · +{c.get('cycle')}봉 후")

            if swings_data:
                a, b, c = swings_data.get("A"), swings_data.get("B"), swings_data.get("C")
                if a and b and c:
                    st.markdown("**🔄 스윙 포인트**")
                    st.caption(
                        f"  A: {a.get('price', 0):,.0f} · "
                        f"B: {b.get('price', 0):,.0f} · "
                        f"C: {c.get('price', 0):,.0f}"
                    )

            # 패턴 매칭 (키움 방식)
            pm_data = raw.get("pattern_match") or {}
            proj = pm_data.get("projection") or {}
            patterns_list = pm_data.get("patterns") or []
            if proj:
                has_any = True
                st.markdown("**🔍 패턴 매칭 (과거 유사 패턴 기반 미래 예측)**")
                pc = proj.get("pattern_count", 0)
                avg_corr = proj.get("avg_correlation", 0)
                avg_path = proj.get("avg_path") or []
                low_path = proj.get("low_path") or []
                high_path = proj.get("high_path") or []
                price_now = float(r.get("price") or 1)
                if avg_path:
                    last_avg = avg_path[-1]
                    last_low = low_path[-1] if low_path else last_avg
                    last_high = high_path[-1] if high_path else last_avg
                    pct = (last_avg / price_now - 1) * 100
                    st.markdown(
                        f"- 유사 패턴 **{pc}개** (평균 상관계수 r={avg_corr})"
                    )
                    st.markdown(
                        f"- 20봉 후 평균: **{last_avg:,.0f}원** ({pct:+.1f}%)"
                    )
                    st.caption(
                        f"  · 보수(low): {last_low:,.0f} · 낙관(high): {last_high:,.0f}"
                    )
                if patterns_list:
                    pattern_dates = " · ".join(
                        f"{p.get('start_date', '?')}~{p.get('end_date', '?')} (r={p.get('correlation')})"
                        for p in patterns_list[:3]
                    )
                    st.caption(f"  · 매칭 구간: {pattern_dates}")

    if not has_any:
        st.info(
            "💡 future_path / flow / cycles 데이터는 코드 업데이트 (2026-05-26) 이후 "
            "분석부터 raw_data에 저장됩니다."
        )


def _render_auto_section(records: list[dict], key_prefix: str,
                         caption_msg: str, empty_msg: str,
                         records_title: str):
    """자동 스냅샷 섹션 공통 렌더 (보유/관심 둘 다 사용)."""
    st.caption(caption_msg)
    if not records:
        st.info(empty_msg)
        return

    # 종목 필터
    codes_x = sorted({(r["stock_code"], r["stock_name"]) for r in records}, key=lambda x: x[1])
    options_x = [t("filter_all")] + [f"{name} ({code})" for code, name in codes_x]
    sel_x = st.selectbox(t("filter_stock"), options_x, key=f"hist_{key_prefix}_stock")

    filtered = records
    if sel_x != t("filter_all"):
        sel_code_x = sel_x.split("(")[-1].rstrip(")")
        filtered = [r for r in filtered if r["stock_code"] == sel_code_x]

    # 통계
    unique_codes = {r["stock_code"] for r in filtered}
    unique_dates = {r.get("analyzed_date") for r in filtered if r.get("analyzed_date")}
    a1, a2, a3 = st.columns(3)
    a1.metric(t("hist_metric_snapshots"), f"{len(filtered)}")
    a2.metric(t("hist_metric_stocks"), f"{len(unique_codes)}")
    a3.metric(t("hist_metric_days"), f"{len(unique_dates)}")

    st.divider()
    st.subheader(f"{records_title} ({len(filtered)})")
    _render_table(filtered)

    # 종목별 상세 (자동은 시계열 추이가 핵심)
    if sel_x != t("filter_all") and filtered:
        st.divider()
        sel_code = sel_x.split("(")[-1].rstrip(")")
        sel_name = sel_x.split(" (")[0]
        st.subheader(f"📈 {sel_x} {t('hist_auto_detail_title')}")

        # ⚠️ 차트와 raw_data 시점 mismatch 안내
        latest_analyzed = filtered[0].get("analyzed_at", "")
        latest_kst = _to_kst_str(latest_analyzed, with_label=False)
        st.warning(
            f"⚠️ **차트는 오늘 기준** · **raw_data는 분석 시점({latest_kst}) 기준** — "
            f"미래 경로/사이클은 분석 당시 예측이라 현재 차트와 일치하지 않을 수 있음"
        )

        # 일목 차트 (최신)
        with st.spinner("🔍 최신 일목균형표 차트 생성 중..."):
            try:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
                from chart_ichimoku import render_ichimoku_chart
                chart_path = render_ichimoku_chart(sel_code, sel_name, days=180)
                if chart_path and chart_path.exists():
                    st.image(str(chart_path), use_container_width=True)
            except Exception as e:
                st.error(f"⚠️ 차트 실패: {e}")

        # 추이 차트 (2건 이상)
        if len(filtered) >= 2:
            trend_df = pd.DataFrame([
                {
                    "시각": r["analyzed_at"][:10],
                    "현재가": float(r["price"]) if r.get("price") else None,
                    "RSI": float(r["rsi_14"]) if r.get("rsi_14") else None,
                    "N목표": float(r["target_n"]) if r.get("target_n") else None,
                    "전환선": float(r["tenkan"]) if r.get("tenkan") else None,
                    "기준선": float(r["kijun"]) if r.get("kijun") else None,
                }
                for r in filtered if r.get("price")
            ]).sort_values("시각")
            if not trend_df.empty:
                tab1, tab2, tab3 = st.tabs(["💰 가격 + 목표가", "📊 RSI", "🌥 일목 5선"])
                with tab1:
                    st.line_chart(trend_df.set_index("시각")[["현재가", "N목표"]])
                with tab2:
                    st.line_chart(trend_df.set_index("시각")["RSI"])
                    st.caption("70+ 과매수 / 30- 과매도 / 50 중립")
                with tab3:
                    if trend_df[["전환선", "기준선"]].notna().any().any():
                        st.line_chart(trend_df.set_index("시각")[["현재가", "전환선", "기준선"]])
                    else:
                        st.info("일목 데이터가 누적되면 표시")
        else:
            st.info(f"💡 추이 차트는 같은 종목 자동 분석 2회 이상 누적되면 표시됩니다. 현재 {len(filtered)}건.")

        # raw_data 펼침
        st.markdown("#### 🗂 일자별 누적 raw_data")
        _render_raw_data_expanders(filtered, limit=10)


# ══════════════════════════════════════════
# 💼 자동 (보유 일일 스냅샷)
# ══════════════════════════════════════════
if cat_mode == "hold":
    _render_auto_section(
        records=auto_hold_records,
        key_prefix="auto_hold",
        caption_msg=t("hist_auto_caption"),
        empty_msg=t("hist_auto_empty"),
        records_title=t("hist_auto_records_title"),
    )

# ══════════════════════════════════════════
# ⭐ 자동 (관심 일일 스냅샷)
# ══════════════════════════════════════════
elif cat_mode == "watch":
    _render_auto_section(
        records=auto_watch_records,
        key_prefix="auto_watch",
        caption_msg=t("hist_watch_caption"),
        empty_msg=t("hist_watch_empty"),
        records_title=t("hist_watch_records_title"),
    )


# ══════════════════════════════════════════
# 👤 수동 (일회성 깊은 분석)
# ══════════════════════════════════════════
else:
    st.caption(t("hist_manual_caption"))

    if not manual_records:
        st.info(t("hist_manual_empty"))
    else:
        codes_manual = sorted({(r["stock_code"], r["stock_name"]) for r in manual_records}, key=lambda x: x[1])
        options_manual = [t("filter_all")] + [f"{name} ({code})" for code, name in codes_manual]
        sel_manual = st.selectbox(t("filter_stock"), options_manual, key="hist_manual_stock")

        filtered_manual = manual_records
        if sel_manual != t("filter_all"):
            sel_code_m = sel_manual.split("(")[-1].rstrip(")")
            filtered_manual = [r for r in filtered_manual if r["stock_code"] == sel_code_m]

        # 통계 — 수동은 판단 분포가 의미 있음
        stances = [r.get("decision_stance") for r in filtered_manual if r.get("decision_stance")]
        buy_count = sum(1 for s in stances if s in ("STRONG_BUY", "BUY"))
        sell_count = sum(1 for s in stances if s in ("STRONG_SELL", "SELL"))
        neutral_count = sum(1 for s in stances if s == "NEUTRAL")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric(t("hist_metric_total"), f"{len(filtered_manual)}")
        m2.metric(t("hist_metric_stocks"), f"{len({r['stock_code'] for r in filtered_manual})}")
        m3.metric(t("hist_metric_buy"), f"{buy_count}")
        m4.metric(t("hist_metric_sell"), f"{sell_count}")

        st.divider()
        st.subheader(f"{t('hist_manual_records_title')} ({len(filtered_manual)})")
        _render_table(filtered_manual)

        # 종목별 상세 (수동 탭 — 일회성이라 raw_data 펼침이 핵심)
        if sel_manual != t("filter_all") and filtered_manual:
            st.divider()
            sel_code_m = sel_manual.split("(")[-1].rstrip(")")
            sel_name_m = sel_manual.split(" (")[0]
            st.subheader(f"🔬 {sel_manual} {t('hist_manual_detail_title')}")

            # 일목 차트 (최신 시점 기준 실시간 생성)
            with st.spinner("🔍 최신 일목균형표 차트 생성 중..."):
                try:
                    import sys
                    from pathlib import Path
                    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analyzer"))
                    from chart_ichimoku import render_ichimoku_chart
                    chart_path = render_ichimoku_chart(sel_code_m, sel_name_m, days=180)
                    if chart_path and chart_path.exists():
                        st.image(str(chart_path), use_container_width=True)
                except Exception as e:
                    st.error(f"⚠️ 차트 실패: {e}")

            # raw_data 펼침
            st.markdown("#### 🗂 누적 분석 데이터 (DB raw_data)")
            _render_raw_data_expanders(filtered_manual, limit=10)
