"""일목균형표(Ichimoku Kinko Hyo) 전용 차트 — 머니트리 스타일.

차트 + 파동론(N/E/V 목표가) + 시간론(변곡 예측) + 의사결정 가이드.
출력: reports/{종목}_{날짜}_ichimoku.png
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import mplfinance as mpf
import numpy as np
import pandas as pd

from _utils import REPORTS_DIR, resolve_ticker
from chart_scenario import compute_ichimoku

warnings.filterwarnings("ignore")


def _setup_korean_font() -> Optional[str]:
    # Linux(Streamlit Cloud): NanumGothic, Windows: Malgun Gothic
    candidates = [
        "NanumGothic", "NanumBarunGothic", "Nanum Gothic",
        "Malgun Gothic",
        "AppleGothic", "Apple SD Gothic Neo",
        "Noto Sans CJK KR", "Noto Sans KR",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}

    # fonts-nanum 설치 후 matplotlib font cache 갱신 안 됐을 수 있음 — 재로드 시도
    if not any(c in available for c in candidates):
        try:
            font_manager._load_fontmanager(try_read_cache=False)
            available = {f.name for f in font_manager.fontManager.ttflist}
        except Exception:
            pass

    for c in candidates:
        if c in available:
            plt.rcParams["font.family"] = c
            plt.rcParams["axes.unicode_minus"] = False
            return c

    # Fallback: 시스템 ttf 직접 등록
    import glob
    for pattern in [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/*.ttf",
        "/usr/share/fonts/**/NanumGothic*.ttf",
    ]:
        for path in glob.glob(pattern, recursive=True):
            try:
                font_manager.fontManager.addfont(path)
                plt.rcParams["font.family"] = "NanumGothic"
                plt.rcParams["axes.unicode_minus"] = False
                return f"NanumGothic ({path})"
            except Exception:
                continue
    return None


_FONT = _setup_korean_font()


# ───────────────────────────────────────────────────────
# 1. 스윙 고점/저점 감지 (A/B/C 파동)
# ───────────────────────────────────────────────────────
def detect_swing_points(df: pd.DataFrame, lookback: int = 60, window: int = 5) -> dict:
    """최근 lookback 봉에서 A(시작 저점) / B(고점) / C(조정 저점) 파동 감지.

    핵심 원칙: 최근 추세의 의미있는 파동을 잡는다.
    - B = lookback 내 최고가 (현재 추세 정점)
    - A = B 이전의 최저가 (파동 시작 저점)
    - C = B 이후의 최저가 (조정 저점). B 이후 데이터 없으면 미형성 표시.

    Returns:
        {"A": {...}, "B": {...}, "C": {...}, "c_formed": bool}
    """
    if len(df) < lookback:
        lookback = len(df)
    recent = df.tail(lookback).copy()
    high = recent["high"].values
    low = recent["low"].values
    n = len(recent)

    # B: 최고가 위치
    B_idx = int(np.argmax(high))

    # A: B 이전 최저가
    if B_idx > 0:
        A_idx = int(np.argmin(low[:B_idx]))
    else:
        A_idx = 0

    # C: B 이후 최저가 (미형성 가능)
    c_formed = False
    if B_idx < n - 1:
        # B 다음 봉부터 끝까지에서 최저점
        C_offset = int(np.argmin(low[B_idx + 1:]))
        C_idx = B_idx + 1 + C_offset
        # C가 B와 큰 차이 없으면(< 3%) 조정 미형성으로 간주
        c_pullback_pct = (high[B_idx] - low[C_idx]) / high[B_idx]
        c_formed = c_pullback_pct >= 0.03
    else:
        # B가 가장 끝 봉이면 조정 자체가 없음
        C_idx = B_idx

    # C 미형성 시: 임시로 직전 단기 저점 (B 직전 5~10봉 내 저점)을 C 대안으로 사용
    if not c_formed:
        # B가 끝에 있고 조정 없음 → 추세 진행 중. C 대안 = A와 B 사이의 마지막 조정 저점
        # 간단히 (A_idx + B_idx) / 2 ~ B_idx 구간의 최저
        if B_idx > A_idx + 2:
            mid = (A_idx + B_idx) // 2
            C_alt_offset = int(np.argmin(low[mid:B_idx]))
            C_idx = mid + C_alt_offset

    base = len(df) - lookback
    return {
        "A": {"idx": base + A_idx, "price": float(low[A_idx]), "date": recent.index[A_idx]},
        "B": {"idx": base + B_idx, "price": float(high[B_idx]), "date": recent.index[B_idx]},
        "C": {"idx": base + C_idx, "price": float(low[C_idx]), "date": recent.index[C_idx]},
        "c_formed": c_formed,
    }


# ───────────────────────────────────────────────────────
# 2. N / E / V / NT 목표가 (일목 파동론)
# ───────────────────────────────────────────────────────
def compute_price_targets(A: float, B: float, C: float) -> dict:
    """일목균형표 변동폭 관측치.

    - N = C + (B - A)   : C에서 AB 상승폭만큼 추가 (가장 일반적)
    - E = 2B - A        : B 돌파 시 AB 상승폭 한번 더 (강세)
    - V = 2B - C        : B 돌파 시 조정폭만큼 추가 (BC가 작을수록 큼)
    - NT = C + (C - A)  : 약세 시나리오 (잘 안 쓰지만 참고용)
    """
    return {
        "N": C + (B - A),
        "E": 2 * B - A,
        "V": 2 * B - C,
        "NT": C + (C - A),
    }


# ───────────────────────────────────────────────────────
# 3. 시간론 — 변곡 예측 (9/17/26봉)
# ───────────────────────────────────────────────────────
def compute_time_cycles(start_idx: int, total_len: int, cycles: tuple = (9, 17, 26)) -> list[dict]:
    """파동 시작점 기준 9/17/26봉 후 시점.

    미래 변곡 예측이 목표이므로 이미 지난 시점은 다음 사이클(33, 42, 65, 76)로 자동 확장.

    Returns:
        [{"cycle": 9, "target_idx": ..., "is_future": True/False}, ...]
    """
    extended_cycles = list(cycles) + [33, 42, 51, 65, 76, 129]
    out = []
    used = set()
    for c in extended_cycles:
        if len(out) >= len(cycles):
            break
        t = start_idx + c
        # 차트에 의미있는 범위: 현재 ±35봉
        if t < total_len - 5:
            continue  # 너무 과거 (이미 지났고 의미 없음)
        if c in used:
            continue
        used.add(c)
        out.append({
            "cycle": c,
            "target_idx": t,
            "is_future": t >= total_len,
            "offset": t - (total_len - 1),
        })
    return out


# ───────────────────────────────────────────────────────
# 4. 의사결정 (지금 매수? 어디까지? 손절은?)
# ───────────────────────────────────────────────────────
def make_decision(df: pd.DataFrame, swings: dict, targets: dict) -> dict:
    """일목 + 파동 기반 의사결정 가이드."""
    last = df.iloc[-1]
    price = float(last["close"])
    tenkan = float(last["tenkan"]) if pd.notna(last.get("tenkan")) else None
    kijun = float(last["kijun"]) if pd.notna(last.get("kijun")) else None
    sa = float(last["senkou_a"]) if pd.notna(last.get("senkou_a")) else None
    sb = float(last["senkou_b"]) if pd.notna(last.get("senkou_b")) else None

    # 구름 위치
    cloud_pos = None
    if sa is not None and sb is not None:
        top, bot = max(sa, sb), min(sa, sb)
        if price > top:
            cloud_pos = "above"
        elif price < bot:
            cloud_pos = "below"
        else:
            cloud_pos = "inside"

    tk_bull = tenkan is not None and kijun is not None and tenkan > kijun
    chikou_ok = None
    if len(df) > 26:
        chikou_ok = price > float(df["close"].iloc[-27])

    rsi = None
    if "rsi_14" in df.columns and pd.notna(last.get("rsi_14")):
        rsi = float(last["rsi_14"])

    # 시그널 판단 (일목 3조건 + RSI 가드)
    if cloud_pos == "above" and tk_bull and chikou_ok:
        if rsi is not None and rsi >= 75:
            stance = "BUY"
            action = "⚠️ 과매수 진입 신중 (삼역호전 but RSI≥75)"
            action_color = "#F39C12"
        elif rsi is not None and rsi >= 70:
            stance = "BUY"
            action = "✅ 매수 우호 (삼역호전 — RSI 70+ 분할 진입)"
            action_color = "#2ECC71"
        else:
            stance = "STRONG_BUY"
            action = "🔥 강력 매수 (삼역호전)"
            action_color = "#27AE60"
    elif cloud_pos == "below" and not tk_bull and chikou_ok is False:
        stance = "STRONG_SELL"
        action = "🚨 강력 매도 (삼역역전)"
        action_color = "#E74C3C"
    elif cloud_pos == "above" and tk_bull:
        if rsi is not None and rsi >= 70:
            stance = "NEUTRAL"
            action = "➖ 관망 (구름 위지만 과매수)"
            action_color = "#7F8C8D"
        else:
            stance = "BUY"
            action = "✅ 매수 우호 (구름 위 + TK 골든)"
            action_color = "#2ECC71"
    elif cloud_pos == "below" and not tk_bull:
        stance = "SELL"
        action = "⚠️ 매도 우호 (구름 아래 + TK 데드)"
        action_color = "#E67E22"
    else:
        stance = "NEUTRAL"
        action = "➖ 관망 (방향성 불명확)"
        action_color = "#7F8C8D"

    # 목표가 (현재가 위쪽만 의미있음)
    upside_targets = sorted(
        [(k, v) for k, v in targets.items() if v > price and k != "NT"],
        key=lambda x: x[1],
    )
    # 손절: 기준선 또는 C 저점
    stop_candidates = []
    if kijun is not None:
        stop_candidates.append(("기준선", kijun))
    if swings["C"]["price"] < price:
        stop_candidates.append(("C저점", swings["C"]["price"]))
    stop = max(stop_candidates, key=lambda x: x[1]) if stop_candidates else None

    return {
        "stance": stance,
        "action": action,
        "action_color": action_color,
        "price": price,
        "cloud_pos": cloud_pos,
        "tk_bull": tk_bull,
        "chikou_ok": chikou_ok,
        "rsi": rsi,
        "upside_targets": upside_targets,
        "stop": stop,
    }


# ───────────────────────────────────────────────────────
# 4-b. 미래 추세 시나리오 (시간론 변곡점 × 파동론 N파동 × 가격론 N/V/E)
# ───────────────────────────────────────────────────────
def project_future_path(
    current_price: float,
    cycles: list[dict],
    targets: dict,
    stop: Optional[tuple] = None,
) -> list[dict]:
    """미래 변곡점에서의 예상 가격 경로 (N파동 = 상승-조정-상승 모델).

    일목 3원리 결합:
      1. 시간론: 미래 변곡점 (cycles 중 is_future=True)
      2. 파동론: N파동 = 첫 변곡=피크, 두번째=조정 골, 세번째=재상승
      3. 가격론: 피크=V/N 목표, 조정=피크-현재가의 38.2% 되돌림, 재상승=다음 목표

    Returns: [{"target_idx": 절대 idx, "cycle": int, "price": float, "label": str, "is_peak": bool}]
    """
    future_cycles = sorted(
        [c for c in cycles if c.get("is_future")],
        key=lambda c: c["target_idx"],
    )[:3]
    if not future_cycles or not targets:
        return []

    upside = sorted(
        [(k, targets[k]) for k in ("V", "N", "E") if targets.get(k, 0) > current_price],
        key=lambda x: x[1],
    )
    if not upside:
        return []

    first_label, first_target = upside[0]
    pullback_to = current_price + (first_target - current_price) * 0.382
    if stop:
        pullback_to = max(pullback_to, stop[1] * 1.02)

    if len(upside) >= 2:
        third_label, third_target = upside[1]
    else:
        third_label, third_target = first_label, first_target

    sequence = [
        (first_target, f"{first_label} 도달", True),
        (pullback_to, "V파동 조정", False),
        (third_target, f"{third_label} 도전", True),
    ]

    path = []
    for cyc, (pr, lbl, is_peak) in zip(future_cycles, sequence):
        path.append({
            "target_idx": cyc["target_idx"],
            "cycle": cyc["cycle"],
            "price": float(pr),
            "label": lbl,
            "is_peak": is_peak,
        })
    return path


# ───────────────────────────────────────────────────────
# 5. 차트 렌더링
# ───────────────────────────────────────────────────────
def _fetch_flow_for_chart(code: str, lookback: int = 30) -> tuple[list[dict], str | None, str | None]:
    """차트용 수급 데이터 + 종합 verdict + 세부 라벨 (실패 시 빈값).

    Returns: (daily, verdict, detail)
      - daily: 일별 수급 (외인/기관 매매 주식수 + 종가)
      - verdict: 종합 한 줄 (예: "🟡 외인/기관 분리 (혼조)")
      - detail: 세부 라벨 (예: "외인 -8,765주 ↘ · 기관 +5,432주 ↗")
    """
    try:
        import market_context as mc
        daily = mc.get_daily_flow(code, days=lookback)
        reversal = mc.detect_flow_reversal(code, lookback=7)
        if not reversal.get("available"):
            return (daily or []), None, None
        verdict = reversal.get("verdict")
        rf = int(reversal.get("recent_foreign_net") or 0)
        ri = int(reversal.get("recent_inst_net") or 0)
        f_arrow = "↗" if rf > 0 else ("↘" if rf < 0 else "→")
        i_arrow = "↗" if ri > 0 else ("↘" if ri < 0 else "→")
        detail = f"외인 {rf:+,}주 {f_arrow} · 기관 {ri:+,}주 {i_arrow}"
        return (daily or []), verdict, detail
    except Exception:
        return ([], None, None)


def render_ichimoku_chart(
    code: str,
    name: str,
    days: int = 180,
    out_path: Optional[Path] = None,
) -> Path:
    import technical

    df = technical.fetch_ohlcv(code, days=days)
    df = compute_ichimoku(df)

    # 시각화용: 최근 100일
    plot_df = df.tail(100).copy()
    plot_df.index.name = "Date"

    # 미래 26영업일 확장 (선행스팬 + 시간론 표시용)
    future_dates = pd.date_range(
        start=plot_df.index[-1] + timedelta(days=1),
        periods=35,
        freq="B",
    )
    future_df = pd.DataFrame(
        index=future_dates,
        columns=plot_df.columns,
        dtype=float,
    )
    # 선행스팬은 df 마지막 26봉 = 미래 26봉의 senkou_a/b
    # 이미 compute_ichimoku에서 shift(26)으로 그려져있음 → df의 tail에서 가져오기
    extended = pd.concat([plot_df, future_df])

    # 미래 영역에 선행스팬 채우기 (df의 가장 끝에서 26봉치)
    last_real_idx = len(plot_df) - 1
    # df 원본에서 미래 26봉의 senkou_a/b를 가져와야 함
    # senkou는 이미 +26 shift 돼있어서, df의 마지막 부분에 NaN 아닌 값 있음
    full_df = df.copy()
    senkou_a_future = full_df["senkou_a"].iloc[-26:].values
    senkou_b_future = full_df["senkou_b"].iloc[-26:].values
    # extended의 미래 부분 처음 26봉에 채우기
    fut_a_len = min(26, len(extended) - last_real_idx - 1)
    for i in range(fut_a_len):
        extended.iloc[last_real_idx + 1 + i, extended.columns.get_loc("senkou_a")] = senkou_a_future[i]
        extended.iloc[last_real_idx + 1 + i, extended.columns.get_loc("senkou_b")] = senkou_b_future[i]

    # 스윙 + 목표가 + 시간 사이클
    swings = detect_swing_points(df, lookback=min(80, len(df)), window=5)
    A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
    targets = compute_price_targets(A, B, C)
    # 시간 사이클은 C(조정 저점) 기준 = 새 파동 시작점
    cycles = compute_time_cycles(swings["C"]["idx"], len(df))
    decision = make_decision(df, swings, targets)
    current_price = decision["price"]

    # mplfinance 스타일
    mc = mpf.make_marketcolors(
        up="#FF3B30", down="#0064FF", edge="inherit",
        wick={"up": "#FF3B30", "down": "#0064FF"}, volume="in"
    )
    style = mpf.make_mpf_style(
        base_mpf_style="yahoo",
        marketcolors=mc,
        rc={
            "font.family": _FONT or "DejaVu Sans",
            "axes.unicode_minus": False,
            "axes.facecolor": "#FFFFFF",
            "figure.facecolor": "#FFFFFF",
        },
        gridcolor="#EEEEEE",
        gridstyle="-",
    )

    # 오버레이용 시리즈 (NaN은 자동 무시)
    apds = []
    if extended["tenkan"].notna().any():
        apds.append(mpf.make_addplot(extended["tenkan"], color="#E74C3C", width=1.2))
    if extended["kijun"].notna().any():
        apds.append(mpf.make_addplot(extended["kijun"], color="#3498DB", width=1.5))
    if extended["chikou"].notna().any():
        apds.append(mpf.make_addplot(extended["chikou"], color="#27AE60", width=1.0))

    # 외국인/기관 수급 (하단 패널) — 일목 모델과 독립된 보조 신호
    flow_daily, flow_verdict, flow_detail = _fetch_flow_for_chart(code, lookback=min(60, len(plot_df)))
    foreign_arr = np.full(len(extended), np.nan)
    inst_arr = np.full(len(extended), np.nan)
    has_flow_panel = False
    if flow_daily:
        date_to_flow = {}
        for r in flow_daily:
            try:
                d = datetime.strptime(r["date"], "%Y.%m.%d").date()
                date_to_flow[d] = (
                    float(r.get("foreign_net", 0) or 0),
                    float(r.get("inst_net", 0) or 0),
                )
            except Exception:
                continue
        for i, idx in enumerate(extended.index):
            try:
                k = idx.date()
                if k in date_to_flow:
                    foreign_arr[i], inst_arr[i] = date_to_flow[k]
            except Exception:
                continue
        if not np.isnan(foreign_arr).all() or not np.isnan(inst_arr).all():
            has_flow_panel = True
            apds.append(mpf.make_addplot(
                foreign_arr, panel=1, type="bar", color="#3498DB",
                width=0.7, ylabel="외국인(주)", alpha=0.75,
            ))
            apds.append(mpf.make_addplot(
                inst_arr, panel=1, type="bar", color="#E67E22",
                width=0.7, secondary_y=True, alpha=0.55,
            ))

    # 캔들은 실데이터 구간만, 미래는 NaN
    candle_df = extended.copy()
    plot_kwargs = dict(
        type="candle",
        addplot=apds,
        volume=False,
        style=style,
        figsize=(16, 10 if has_flow_panel else 9),
        returnfig=True,
        tight_layout=True,
        warn_too_much_data=10000,
    )
    if has_flow_panel:
        plot_kwargs["panel_ratios"] = (6, 1.4)
    fig, axes = mpf.plot(candle_df, **plot_kwargs)
    ax_main = axes[0]
    # 수급 패널: 0 기준선 추가 (매수/매도 구분)
    if has_flow_panel and len(axes) >= 3:
        for ax in axes[2:]:
            ax.axhline(0, color="#888", linewidth=0.6, linestyle="-", alpha=0.6)

    # ───── y축 범위를 합리적으로 (가까운 목표까지만, 너무 먼 건 차트 밖 화살표) ─────
    y_min_data = float(np.nanmin([plot_df["low"].min(), extended["senkou_b"].min()]))
    y_max_data = float(np.nanmax([plot_df["high"].max(), extended["senkou_a"].max()]))

    # 현재가에서 가장 가까운 목표 + 추가 여유
    sorted_t = sorted([targets["V"], targets["N"], targets["E"]])
    above_current = [t for t in sorted_t if t > current_price]
    if above_current:
        # 가까운 2개 목표는 차트 안에 보이도록, 너무 먼 건 잘림
        nearest_target = above_current[0]
        # 현재가에서 최대 +50% 또는 가까운 목표 + 10% 중 작은 값
        y_upper_candidate = min(
            nearest_target * 1.15,
            current_price * 1.6,
        )
        y_upper = max(y_max_data * 1.05, y_upper_candidate)
    else:
        y_upper = y_max_data * 1.05

    y_lower = min(y_min_data, swings["C"]["price"]) * 0.92
    ax_main.set_ylim(y_lower, y_upper)

    n_total = len(extended)
    x_idx = np.arange(n_total)

    # ───── 구름대 채우기 (미래 영역 포함) ─────
    a = extended["senkou_a"].values
    b = extended["senkou_b"].values
    valid = ~(np.isnan(a) | np.isnan(b))
    if valid.any():
        ax_main.fill_between(
            x_idx, a, b, where=(a >= b) & valid,
            color="#FFE5B4", alpha=0.60,
        )
        ax_main.fill_between(
            x_idx, a, b, where=(a < b) & valid,
            color="#D4E6F1", alpha=0.60,
        )
        ax_main.plot(x_idx, a, color="#E67E22", linewidth=0.7, alpha=0.8)
        ax_main.plot(x_idx, b, color="#5DADE2", linewidth=0.7, alpha=0.8)

    # ───── 현재가 라인 ─────
    today_x = last_real_idx
    ax_main.axvline(today_x, color="#888", linestyle="--", linewidth=0.8, alpha=0.6)
    ax_main.text(
        today_x, ax_main.get_ylim()[1], " 오늘",
        fontsize=8, va="top", ha="left", color="#555",
    )

    # ───── A / B / C 라벨 ─────
    plot_base_idx = len(df) - len(plot_df)  # plot_df 시작이 df의 어디인지
    for label, sw, color in [
        ("A", swings["A"], "#7F8C8D"),
        ("B", swings["B"], "#E74C3C"),
        ("C", swings["C"], "#3498DB"),
    ]:
        rel_idx = sw["idx"] - plot_base_idx
        if 0 <= rel_idx < len(plot_df):
            offset = -0.02 * (ax_main.get_ylim()[1] - ax_main.get_ylim()[0])
            y_pos = sw["price"] + (offset if label == "B" else -offset)
            ax_main.scatter([rel_idx], [sw["price"]], color=color, s=80, zorder=5,
                          edgecolors="white", linewidths=1.5)
            ax_main.text(
                rel_idx, y_pos,
                f"{label}\n{sw['price']:,.0f}",
                fontsize=9, ha="center",
                va="top" if label == "B" else "bottom",
                color=color, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                         edgecolor=color, alpha=0.9),
            )

    # ───── N / E / V 목표가 라벨 (우측 끝) ─────
    # 우선순위: V(1차 익절) < N(표준 목표) < E(강세 목표)
    target_x = n_total - 1
    target_meta = {
        "V": {"color": "#8E44AD", "desc": "1차 익절", "rank": "★"},
        "N": {"color": "#E74C3C", "desc": "표준 목표", "rank": "★★"},
        "E": {"color": "#C0392B", "desc": "강세 목표", "rank": "★★★"},
    }
    sorted_targets = sorted(
        [(k, targets[k]) for k in ["V", "N", "E"]],
        key=lambda x: x[1], reverse=True,
    )
    y_top = ax_main.get_ylim()[1]
    for k, v in sorted_targets:
        meta = target_meta[k]
        pct = (v / current_price - 1) * 100
        if v > y_top:
            # 차트 영역 밖 → 상단에 화살표 + 라벨
            ax_main.text(
                target_x, y_top * 0.98,
                f" ↑ {k} {meta['rank']} {v:,.0f} ({pct:+.1f}%) {meta['desc']}",
                fontsize=9, va="top", ha="left",
                color=meta["color"], fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                         edgecolor=meta["color"], alpha=0.95, linestyle="--"),
            )
        else:
            ax_main.axhline(v, color=meta["color"], linestyle=":", linewidth=1.0, alpha=0.7,
                           xmin=today_x / n_total, xmax=1.0)
            ax_main.text(
                target_x, v,
                f" {k} {meta['rank']} {v:,.0f} ({pct:+.1f}%) {meta['desc']}",
                fontsize=10, va="center", ha="left",
                color=meta["color"], fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                         edgecolor=meta["color"], alpha=0.95),
            )

    # 현재가 라벨
    ax_main.text(
        target_x, current_price,
        f" ● 현재 {current_price:,.0f}",
        fontsize=10, va="center", ha="left",
        color="#000", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.25", facecolor="#FFFACD",
                 edgecolor="#000", alpha=0.95),
    )

    # 손절선
    if decision["stop"]:
        stop_name, stop_val = decision["stop"]
        pct = (stop_val / current_price - 1) * 100
        ax_main.axhline(stop_val, color="#2C3E50", linestyle="--", linewidth=1.0, alpha=0.7,
                       xmin=today_x / n_total, xmax=1.0)
        ax_main.text(
            target_x, stop_val,
            f" 🛡 손절 {stop_val:,.0f} ({pct:+.1f}%) {stop_name}",
            fontsize=9.5, va="center", ha="left",
            color="#2C3E50", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                     edgecolor="#2C3E50", alpha=0.95),
        )

    # ───── 시간 사이클 ▼ (시간론 — C 저점 기준) ─────
    # 정통 일목 수치: 9 / 17 / 26 / 33 / 42 / 51 / 65 / 76 / 129
    cycle_colors = {
        9: "#E74C3C", 17: "#F39C12", 26: "#2980B9",
        33: "#E67E22", 42: "#16A085", 51: "#8E44AD",
        65: "#34495E", 76: "#7F8C8D", 129: "#2C3E50",
    }
    y_max = ax_main.get_ylim()[1]
    y_min = ax_main.get_ylim()[0]
    y_range = y_max - y_min

    # 마커 위치: 차트 하단 5% 지점 (캔들 안 가리게)
    marker_y = y_min + 0.04 * y_range
    label_y = y_min + 0.08 * y_range

    # 기준선 가로선 (시간 패널 구분)
    ax_main.axhline(marker_y, color="#DDD", linewidth=0.5, alpha=0.5,
                   xmin=0, xmax=1)

    for cyc in cycles:
        rel_idx = cyc["target_idx"] - plot_base_idx
        if 0 <= rel_idx < n_total:
            color = cycle_colors[cyc["cycle"]]
            is_future = cyc["is_future"]
            # 과거(이미 지남)는 회색 처리, 미래는 진한 색
            fill_color = color if is_future else "#BBB"
            edge_color = color
            alpha_val = 1.0 if is_future else 0.5

            # 큰 ▼ 마커 (하단)
            ax_main.scatter([rel_idx], [marker_y],
                          marker="v", color=fill_color, s=220, zorder=6,
                          edgecolors=edge_color, linewidths=2.0, alpha=alpha_val)

            # 봉 수 (큰 글씨)
            ax_main.text(
                rel_idx, marker_y,
                f"{cyc['cycle']}",
                fontsize=10, ha="center", va="center",
                color="white", fontweight="bold",
            )

            # 라벨: 날짜 + 봉수 (마커 위)
            label_date = extended.index[rel_idx].strftime("%m/%d")
            label_text = f"{cyc['cycle']}봉\n{label_date}"
            if is_future:
                label_text = f"▼ {label_text}"

            ax_main.text(
                rel_idx, label_y,
                label_text,
                fontsize=8.5, ha="center", va="bottom",
                color=color if is_future else "#888",
                fontweight="bold" if is_future else "normal",
                bbox=dict(
                    boxstyle="round,pad=0.2",
                    facecolor="white",
                    edgecolor=color if is_future else "#CCC",
                    alpha=0.95,
                ),
            )

    # 시간론 시작점 표시 (C 저점에서 화살표)
    c_rel_idx = swings["C"]["idx"] - plot_base_idx
    if 0 <= c_rel_idx < n_total:
        ax_main.annotate(
            "시간론 起点 (C)", xy=(c_rel_idx, marker_y),
            xytext=(c_rel_idx, marker_y - 0.04 * y_range),
            fontsize=8, ha="center", color="#555",
            arrowprops=dict(arrowstyle="->", color="#555", lw=0.8),
        )

    # ───── 미래 추세 시나리오 (N파동: 상승-조정-재상승) ─────
    future_path = project_future_path(
        current_price=current_price,
        cycles=cycles,
        targets=targets,
        stop=decision.get("stop"),
    )
    # 차트 좌표로 변환 + 범위 필터
    chart_path = []
    for p in future_path:
        rel_idx = p["target_idx"] - plot_base_idx
        if 0 <= rel_idx < n_total:
            chart_path.append({**p, "rel_idx": rel_idx})
    if chart_path:
        xs = [today_x] + [p["rel_idx"] for p in chart_path]
        ys = [current_price] + [p["price"] for p in chart_path]
        ax_main.plot(
            xs, ys,
            linestyle=":", linewidth=1.8, color="#2C3E50",
            marker="o", markersize=6,
            markerfacecolor="#2C3E50", markeredgecolor="white",
            markeredgewidth=1.2,
            zorder=6,
            label="예상 경로",
        )
        for p in chart_path:
            try:
                date_str = extended.index[p["rel_idx"]].strftime("%m/%d")
            except Exception:
                date_str = f"+{p['cycle']}봉"
            pct = (p["price"] / current_price - 1) * 100
            color = "#C0392B" if p["is_peak"] else "#2980B9"
            va = "bottom" if p["is_peak"] else "top"
            offset_y = (0.03 if p["is_peak"] else -0.03) * y_range
            ax_main.text(
                p["rel_idx"], p["price"] + offset_y,
                f"{date_str}\n{p['price']:,.0f} ({pct:+.1f}%)\n{p['label']}",
                fontsize=8, ha="center", va=va,
                color=color, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                          edgecolor=color, alpha=0.92, linestyle="--"),
            )

    # ───── 의사결정 박스 (좌측 상단) ─────
    info_lines = [
        f"📌 {decision['action']}",
        "",
        f"현재가: {current_price:,.0f}",
    ]
    cloud_txt = {
        "above": "구름 위 (강세 영역)",
        "below": "구름 아래 (약세 영역)",
        "inside": "구름 안 (횡보)",
    }.get(decision["cloud_pos"], "—")
    info_lines.append(f"위치: {cloud_txt}")
    info_lines.append(f"TK: {'전환 > 기준 ✅' if decision['tk_bull'] else '전환 < 기준 ⚠️'}")
    if decision["chikou_ok"] is not None:
        info_lines.append(f"후행: {'26일전 위 ✅' if decision['chikou_ok'] else '26일전 아래 ⚠️'}")

    if decision["upside_targets"]:
        info_lines.append("")
        c_note = " ⚠ C 미형성" if not swings.get("c_formed", True) else ""
        info_lines.append(f"🎯 목표가 (파동론){c_note}:")
        desc_map = {"V": "1차 익절", "N": "표준 목표", "E": "강세 목표"}
        for k, v in decision["upside_targets"][:3]:
            d = desc_map.get(k, "")
            info_lines.append(f"  {k} {v:,.0f} ({(v/current_price-1)*100:+.1f}%) — {d}")
    else:
        info_lines.append("")
        info_lines.append("🎯 목표가: 현재가가 B(고점) 위 → 신규 파동 진행 중")
        info_lines.append("   (조정 후 새 C 확인 후 재계산 권장)")

    if decision["stop"]:
        info_lines.append("")
        stop_name, stop_val = decision["stop"]
        info_lines.append(f"🛡 손절: {stop_name} {stop_val:,.0f} ({(stop_val/current_price-1)*100:+.1f}%)")

    # 수급 보조 신호 (일목 모델과 독립) — verdict + 세부 라벨 (A옵션)
    if flow_verdict:
        info_lines.append("")
        info_lines.append(f"💹 수급 (7일): {flow_verdict}")
        if flow_detail:
            info_lines.append(f"   {flow_detail}")

    # 매매 가이드 (가까운 목표부터 순서대로 분할 익절)
    if decision["upside_targets"]:
        # 가까운 순 = upside_targets는 이미 가격 오름차순
        ordered = sorted(decision["upside_targets"], key=lambda x: x[1])
        info_lines.append("")
        info_lines.append("📖 활용법 (가까운 순):")
        labels = ["1차 분할 익절 (1/3)", "2차 분할 익절 (1/3)", "전량 익절 / 추세 종료"]
        for (k, v), lbl in zip(ordered[:3], labels):
            info_lines.append(f"  {k} {v:,.0f} → {lbl}")

    ax_main.text(
        0.01, 0.98, "\n".join(info_lines),
        transform=ax_main.transAxes,
        fontsize=10, va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="white",
                 edgecolor=decision["action_color"], linewidth=2.0, alpha=0.96),
    )

    # ───── 범례 (우측 하단) ─────
    legend_text = (
        "━ 전환선 (9)   ━ 기준선 (26)\n"
        "━ 후행스팬 (-26)\n"
        "▓ 구름 (선행스팬 A/B, +26)\n"
        "▼ 시간 변곡 (9/17/26봉)"
    )
    ax_main.text(
        0.99, 0.02, legend_text,
        transform=ax_main.transAxes,
        fontsize=8.5, va="bottom", ha="right",
        color="#555",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                 edgecolor="#CCCCCC", alpha=0.9),
    )

    # 타이틀 (제목 + 부제를 figure-level로 합쳐 axes title과 겹치지 않게)
    today_str = datetime.now().strftime("%Y-%m-%d")
    fig.suptitle(
        f"{name} ({code}) — 일목균형표 종합 분석   {today_str}",
        fontsize=14, fontweight="bold", y=1.015,
    )
    fig.text(
        0.5, 0.975,
        "Calculate the Future, Don't Guess It — 가격(N/E/V) × 시간(9/17/26봉) × 파동(N파동 시나리오)",
        fontsize=9, color="#888", ha="center", va="top",
    )
    ax_main.set_title("")  # axes title 제거 (suptitle과 겹침 방지)

    # 저장
    if out_path is None:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        out_path = REPORTS_DIR / f"{name}_{date_str}_ichimoku.png"

    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="일목균형표 종합 분석 차트 (머니트리 스타일)")
    parser.add_argument("ticker", help="종목명 또는 종목코드")
    parser.add_argument("--days", type=int, default=180, help="조회 기간(일) — 기본 180")
    parser.add_argument("--out", type=str, default=None, help="출력 경로")
    args = parser.parse_args()

    code, name = resolve_ticker(args.ticker)
    out_path = Path(args.out) if args.out else None
    saved = render_ichimoku_chart(code, name, days=args.days, out_path=out_path)
    print(f"✅ 일목균형표 차트 저장: {saved}")

    # 콘솔 요약
    import technical
    df = technical.fetch_ohlcv(code, days=args.days)
    df = compute_ichimoku(df)
    swings = detect_swing_points(df, lookback=min(80, len(df)))
    targets = compute_price_targets(swings["A"]["price"], swings["B"]["price"], swings["C"]["price"])
    decision = make_decision(df, swings, targets)

    print()
    print(f"📊 {name} ({code}) 일목 종합")
    print(f"  현재가: {decision['price']:,.0f}")
    print(f"  파동: A={swings['A']['price']:,.0f} → B={swings['B']['price']:,.0f} → C={swings['C']['price']:,.0f}")
    print(f"  목표가:")
    for k in ["N", "E", "V"]:
        v = targets[k]
        pct = (v / decision['price'] - 1) * 100
        print(f"    {k} = {v:,.0f} ({pct:+.1f}%)")
    print(f"  판단: {decision['action']}")
    if decision["stop"]:
        n, v = decision["stop"]
        print(f"  손절: {n} {v:,.0f} ({(v/decision['price']-1)*100:+.1f}%)")
