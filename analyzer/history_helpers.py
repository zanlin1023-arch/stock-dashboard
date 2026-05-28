"""분석 히스토리 페이지 공통 helper.

`pages/3a_*`, `pages/3b_*`, `pages/3c_*` 세 페이지가 함께 사용한다.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
import streamlit as st

from i18n import t, td


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


def _add_business_days(start_date, days: int):
    """주말 제외하고 영업일 더하기 (한국 공휴일은 미반영, 근사치)."""
    d = start_date
    added = 0
    while added < days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 0=월~4=금
            added += 1
    return d


def _cycle_to_date(utc_iso: str, cycle) -> str:
    """분석 시점(UTC ISO) + cycle 영업일 → 'MM/DD' (KST 기준).

    cycle 없거나 변환 실패 시 빈 string.
    """
    try:
        c = int(cycle or 0)
        if c <= 0:
            return ""
        s = (utc_iso or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        base = dt.astimezone(KST).date()
        target = _add_business_days(base, c)
        return f"{target.month}/{target.day}"
    except Exception:
        return ""


def _render_table(records: list[dict], holdings_map: dict | None = None):
    """공통 테이블 렌더 — 미래 경로 + 수급 컬럼.

    Args:
        holdings_map: {stock_code: avg_price} — 보유 평단가 (보유 페이지에서만 전달)
                       전달 시 V/N/E/1·2·3차에 평단 대비 % 추가 표시
    """
    rows = []
    for r in records:
        # raw_data에서 future_path / flow 추출
        raw = r.get("raw_data") or {}
        fp = raw.get("future_path") or []
        flow = raw.get("flow") or {}
        price_now = float(r.get("price") or 0)

        _candle = t("hist_candle_unit")
        analyzed_at_iso = r.get("analyzed_at", "")
        # 보유 평단가 lookup
        _avg = None
        if holdings_map and r.get("stock_code"):
            _avg = holdings_map.get(r["stock_code"])
            try:
                _avg = float(_avg) if _avg else None
            except (TypeError, ValueError):
                _avg = None

        def _avg_suffix(price_val: float) -> str:
            """평단 대비 % suffix (보유 종목만)."""
            if _avg and _avg > 0 and price_val:
                pct_avg = (float(price_val) / _avg - 1) * 100
                return f" | 평단 {pct_avg:+.1f}%"
            return ""

        def _fmt_future(p: dict, ref_price: float, ref_label: str) -> str:
            """ref_price 대비 % + 평단 대비 %(보유시) 표시."""
            pct = (p.get("price", 0) / ref_price - 1) * 100 if ref_price else 0
            date_str = _cycle_to_date(analyzed_at_iso, p.get("cycle"))
            date_prefix = f"📅 {date_str} · " if date_str else ""
            return (
                f"{date_prefix}+{p.get('cycle')}{_candle} · {p.get('label', '')} "
                f"{p.get('price', 0):,.0f} ({ref_label} {pct:+.1f}%{_avg_suffix(p.get('price', 0))})"
            )

        # 1차: 현재가 대비 / 2차(조정): 1차 대비 (음수가 맞음) / 3차: 현재가 대비
        future_1st = _fmt_future(fp[0], price_now, "현재가") if fp else "-"
        future_2nd = (
            _fmt_future(fp[1], fp[0].get("price", price_now), "1차 대비")
            if len(fp) >= 2 else "-"
        )
        future_3rd = _fmt_future(fp[2], price_now, "현재가") if len(fp) >= 3 else "-"

        # 수급 verdict (짧게)
        flow_short = flow.get("verdict", "-") or "-"

        # 일목 V/N/E 목표가 + 손절 (현재가 대비 % + 평단 대비 %)
        def _fmt_target(val):
            if not val:
                return "-"
            pct = (float(val) / price_now - 1) * 100 if price_now else 0
            return f"{float(val):,.0f} ({pct:+.1f}%{_avg_suffix(val)})"

        # 패턴 매칭 시점별 예측 가격 (raw_data.pattern_match.projection)
        pm_data = raw.get("pattern_match") or {}
        proj = pm_data.get("projection") or {}
        pm_days = proj.get("days") or []
        pm_avg = proj.get("avg_path") or []

        def _fmt_pattern(target_day: int) -> str:
            """target_day(예: 5/10/15/20봉) 시점의 패턴 매칭 평균 예측가."""
            for i, d in enumerate(pm_days):
                if d == target_day and i < len(pm_avg):
                    price = float(pm_avg[i])
                    date_str = _cycle_to_date(analyzed_at_iso, target_day)
                    date_prefix = f"📅 {date_str} · " if date_str else ""
                    pct = (price / price_now - 1) * 100 if price_now else 0
                    return f"{date_prefix}{price:,.0f} ({pct:+.1f}%)"
            return "-"

        # 보유 평단가 + 현재가 대비 손익 (보유 페이지에서만)
        row_dict = {
            t("hist_col_analyzed_at"): _to_kst_str(r.get("analyzed_at", ""), with_label=False),
            t("hist_col_stock"): f"{r.get('stock_name', '')} ({r.get('stock_code', '')})",
            t("hist_col_price"): f"{r['price']:,.0f}" if r.get("price") else "-",
        }
        if _avg:
            # 평단가 + 분석 시점 가격 대비 손익
            pnl = (price_now / _avg - 1) * 100 if price_now and _avg else 0
            row_dict[t("hist_col_avg_price")] = f"{_avg:,.0f}"
            row_dict[t("hist_col_pnl")] = f"{pnl:+.1f}%"
        row_dict.update({
            t("hist_col_rsi"): f"{r['rsi_14']:.1f}" if r.get("rsi_14") else "-",
            t("hist_col_cloud"): {
                "above": t("hist_cloud_above"),
                "below": t("hist_cloud_below"),
                "inside": t("hist_cloud_inside"),
            }.get(r.get("cloud_position", ""), "-"),
            t("hist_col_decision"): td(r.get("decision_action", "-") or "-"),
            # 🔬 패턴 매칭 시점별 예측 가격 (실데이터 기반 — 일목 V/N/E 공식 대체)
            t("hist_col_pattern_5d"): _fmt_pattern(5),
            t("hist_col_pattern_10d"): _fmt_pattern(10),
            t("hist_col_pattern_15d"): _fmt_pattern(15),
            t("hist_col_pattern_20d"): _fmt_pattern(20),
            # 일목 시간 사이클 (참고용)
            t("hist_col_future_1st"): future_1st,
            t("hist_col_future_2nd"): future_2nd,
            t("hist_col_future_3rd"): future_3rd,
            t("hist_col_stop"): _fmt_target(r.get("stop_loss")),
            t("hist_col_flow"): td(flow_short),
        })
        rows.append(row_dict)
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

        with st.expander(f"📅 {when_kst}  ·  {td(action)}", expanded=False):
            st.markdown(t("hist_future_path_header"))
            if fp:
                has_any = True
                analyzed_iso = r.get("analyzed_at", "")
                for p in fp:
                    role = t("hist_future_peak") if p.get("is_peak") else t("hist_future_pullback")
                    pct = (p.get("price", 0) / float(r.get("price") or 1) - 1) * 100 if r.get("price") else 0
                    target_date = _cycle_to_date(analyzed_iso, p.get("cycle"))
                    date_prefix = f"📅 **{target_date}** · " if target_date else ""
                    st.markdown(
                        "- " + date_prefix + t(
                            "hist_future_path_item",
                            role=role,
                            label=p.get("label", ""),
                            cycle=p.get("cycle"),
                            price=p.get("price", 0),
                            pct=pct,
                        )
                    )
            else:
                st.caption(t("hist_future_no_data"))

            st.markdown(t("hist_flow_header"))
            if flow.get("verdict"):
                has_any = True
                st.markdown(f"- {t('hist_flow_summary')}: **{td(flow['verdict'])}**")
                for sig in (flow.get("signals") or [])[:3]:
                    st.caption(f"  · {td(sig)}")
            else:
                st.caption(t("hist_flow_no_data"))

            future_cycles = [c for c in cycles_data if c.get("is_future")]
            if future_cycles:
                has_any = True
                st.markdown(t("hist_cycle_header"))
                for c in future_cycles[:5]:
                    st.caption(t("hist_cycle_item", cycle=c.get("cycle")))

            if swings_data:
                a, b, c = swings_data.get("A"), swings_data.get("B"), swings_data.get("C")
                if a and b and c:
                    st.markdown(t("hist_swing_header"))
                    st.caption(
                        t(
                            "hist_swing_item",
                            a=a.get("price", 0),
                            b=b.get("price", 0),
                            c=c.get("price", 0),
                        )
                    )

            # 패턴 매칭 (키움 방식)
            pm_data = raw.get("pattern_match") or {}
            proj = pm_data.get("projection") or {}
            patterns_list = pm_data.get("patterns") or []
            if proj:
                has_any = True
                st.markdown(t("hist_pattern_header"))
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
                    st.markdown("- " + t("hist_pattern_similar", pc=pc, r=avg_corr))
                    st.markdown("- " + t("hist_pattern_avg", val=last_avg, pct=pct))
                    st.caption(t("hist_pattern_lowhigh", low=last_low, high=last_high))
                if patterns_list:
                    pattern_dates = " · ".join(
                        f"{p.get('start_date', '?')}~{p.get('end_date', '?')} (r={p.get('correlation')})"
                        for p in patterns_list[:3]
                    )
                    st.caption(f"{t('hist_pattern_matched_periods')}: {pattern_dates}")

    if not has_any:
        st.info(t("hist_rawdata_note"))


def _render_auto_section(records: list[dict], key_prefix: str,
                         caption_msg: str, empty_msg: str,
                         records_title: str,
                         holdings_map: dict | None = None):
    """자동 스냅샷 섹션 공통 렌더 (보유/관심 둘 다 사용).

    holdings_map: {stock_code: avg_price} — 보유 페이지에서만 전달 → 평단 대비 % 표시
    """
    st.caption(caption_msg)
    if not records:
        st.info(empty_msg)
        return

    # 종목 + 날짜 필터
    codes_x = sorted({(r["stock_code"], r["stock_name"]) for r in records}, key=lambda x: x[1])
    dates_x = sorted(
        {r.get("analyzed_date") for r in records if r.get("analyzed_date")},
        reverse=True,
    )
    options_x = [t("filter_all")] + [f"{name} ({code})" for code, name in codes_x]
    options_d = [t("filter_all")] + list(dates_x)

    fc1, fc2 = st.columns(2)
    with fc1:
        sel_x = st.selectbox(t("filter_stock"), options_x, key=f"hist_{key_prefix}_stock")
    with fc2:
        sel_d = st.selectbox(t("filter_date"), options_d, key=f"hist_{key_prefix}_date")

    filtered = records
    if sel_x != t("filter_all"):
        sel_code_x = sel_x.split("(")[-1].rstrip(")")
        filtered = [r for r in filtered if r["stock_code"] == sel_code_x]
    if sel_d != t("filter_all"):
        filtered = [r for r in filtered if r.get("analyzed_date") == sel_d]

    # 통계
    unique_codes = {r["stock_code"] for r in filtered}
    unique_dates = {r.get("analyzed_date") for r in filtered if r.get("analyzed_date")}
    a1, a2, a3 = st.columns(3)
    a1.metric(t("hist_metric_snapshots"), f"{len(filtered)}")
    a2.metric(t("hist_metric_stocks"), f"{len(unique_codes)}")
    a3.metric(t("hist_metric_days"), f"{len(unique_dates)}")

    st.divider()
    st.subheader(f"{records_title} ({len(filtered)})")
    _render_table(filtered, holdings_map=holdings_map)

    # 종목별 상세 (자동은 시계열 추이가 핵심)
    if sel_x != t("filter_all") and filtered:
        st.divider()
        sel_code = sel_x.split("(")[-1].rstrip(")")
        sel_name = sel_x.split(" (")[0]
        st.subheader(f"📈 {sel_x} {t('hist_auto_detail_title')}")

        # ⚠️ 차트와 raw_data 시점 mismatch 안내
        latest_analyzed = filtered[0].get("analyzed_at", "")
        latest_kst = _to_kst_str(latest_analyzed, with_label=False)
        st.warning(t("hist_chart_mismatch_warn", when=latest_kst))

        # 일목 차트 (최신)
        with st.spinner(t("hist_chart_loading")):
            try:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from chart_ichimoku import render_ichimoku_chart
                chart_path = render_ichimoku_chart(sel_code, sel_name, days=180)
                if chart_path and chart_path.exists():
                    from common import render_zoomable_image
                    render_zoomable_image(str(chart_path), alt="일목 차트")
            except Exception as e:
                st.error(f"{t('hist_chart_fail')}: {e}")

        # 추이 차트 (2건 이상)
        if len(filtered) >= 2:
            _tc_time = t("hist_trend_col_time")
            _tc_price = t("hist_trend_col_price")
            _tc_rsi = t("hist_trend_col_rsi")
            _tc_target = t("hist_trend_col_target_n")
            _tc_tenkan = t("hist_trend_col_tenkan")
            _tc_kijun = t("hist_trend_col_kijun")
            trend_df = pd.DataFrame([
                {
                    _tc_time: r["analyzed_at"][:10],
                    _tc_price: float(r["price"]) if r.get("price") else None,
                    _tc_rsi: float(r["rsi_14"]) if r.get("rsi_14") else None,
                    _tc_target: float(r["target_n"]) if r.get("target_n") else None,
                    _tc_tenkan: float(r["tenkan"]) if r.get("tenkan") else None,
                    _tc_kijun: float(r["kijun"]) if r.get("kijun") else None,
                }
                for r in filtered if r.get("price")
            ]).sort_values(_tc_time)
            if not trend_df.empty:
                tab1, tab2, tab3 = st.tabs([t("hist_tab_price_target"), t("hist_tab_rsi"), t("hist_tab_ichimoku5")])
                with tab1:
                    st.line_chart(trend_df.set_index(_tc_time)[[_tc_price, _tc_target]])
                with tab2:
                    st.line_chart(trend_df.set_index(_tc_time)[_tc_rsi])
                    st.caption(t("hist_rsi_caption"))
                with tab3:
                    if trend_df[[_tc_tenkan, _tc_kijun]].notna().any().any():
                        st.line_chart(trend_df.set_index(_tc_time)[[_tc_price, _tc_tenkan, _tc_kijun]])
                    else:
                        st.info(t("hist_ichimoku5_pending"))
        else:
            st.info(t("hist_trend_need_more", n=len(filtered)))

        # raw_data 펼침
        st.markdown(t("hist_raw_daily_title"))
        _render_raw_data_expanders(filtered, limit=10)


def _render_manual_section(manual_records: list[dict]):
    """수동 (일회성 깊은 분석) 섹션 렌더."""
    st.caption(t("hist_manual_caption"))

    if not manual_records:
        st.info(t("hist_manual_empty"))
        return

    codes_manual = sorted({(r["stock_code"], r["stock_name"]) for r in manual_records}, key=lambda x: x[1])
    dates_manual = sorted(
        {r.get("analyzed_date") for r in manual_records if r.get("analyzed_date")},
        reverse=True,
    )
    options_manual = [t("filter_all")] + [f"{name} ({code})" for code, name in codes_manual]
    options_dm = [t("filter_all")] + list(dates_manual)

    mc1, mc2 = st.columns(2)
    with mc1:
        sel_manual = st.selectbox(t("filter_stock"), options_manual, key="hist_manual_stock")
    with mc2:
        sel_dm = st.selectbox(t("filter_date"), options_dm, key="hist_manual_date")

    filtered_manual = manual_records
    if sel_manual != t("filter_all"):
        sel_code_m = sel_manual.split("(")[-1].rstrip(")")
        filtered_manual = [r for r in filtered_manual if r["stock_code"] == sel_code_m]
    if sel_dm != t("filter_all"):
        filtered_manual = [r for r in filtered_manual if r.get("analyzed_date") == sel_dm]

    # 통계 — 수동은 판단 분포가 의미 있음
    stances = [r.get("decision_stance") for r in filtered_manual if r.get("decision_stance")]
    buy_count = sum(1 for s in stances if s in ("STRONG_BUY", "BUY"))
    sell_count = sum(1 for s in stances if s in ("STRONG_SELL", "SELL"))

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
        with st.spinner(t("hist_chart_loading")):
            try:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from chart_ichimoku import render_ichimoku_chart
                chart_path = render_ichimoku_chart(sel_code_m, sel_name_m, days=180)
                if chart_path and chart_path.exists():
                    from common import render_zoomable_image
                    render_zoomable_image(str(chart_path), alt="일목 차트")
            except Exception as e:
                st.error(f"{t('hist_chart_fail')}: {e}")

        # raw_data 펼침
        st.markdown(t("hist_raw_manual_title"))
        _render_raw_data_expanders(filtered_manual, limit=10)


def load_history_records(db) -> dict:
    """analysis_history 전체 조회 + 보유/관심/수동으로 분류해 반환.

    Returns:
        dict: {
            "auto_hold": [...],
            "auto_watch": [...],
            "manual": [...],
            "empty": bool,  # 전체가 비어있는지
        }
    """
    client = db.get_client()
    if not client:
        return {"auto_hold": [], "auto_watch": [], "manual": [], "empty": True, "client_fail": True}

    res = client.table("analysis_history").select("*").order("analyzed_at", desc=True).limit(500).execute()
    all_records = res.data or []

    if not all_records:
        return {"auto_hold": [], "auto_watch": [], "manual": [], "empty": True}

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
    # manual은 보유/관심 외 종목만 (보유/관심이면 자동 카테고리로 자동 분류됨)
    manual_records = [
        r for r in all_records
        if r.get("snapshot_type") != "scheduled"
        and r.get("stock_code") not in holding_codes
        and r.get("stock_code") not in watch_codes
    ]

    return {
        "auto_hold": auto_hold_records,
        "auto_watch": auto_watch_records,
        "manual": manual_records,
        "empty": False,
    }
