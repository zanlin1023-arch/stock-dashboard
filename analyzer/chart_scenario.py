"""시나리오 차트 생성: 캔들 + 일목균형표 + 매물대 + 백테 기반 매수/익절/손절 라벨.

Tatons 스타일 차트를 우리 백테스팅 데이터 + ATR + Volume Profile로 자동 생성.
출력: reports/{종목}_{날짜}_chart.png
"""
from __future__ import annotations

import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import font_manager
import mplfinance as mpf
import numpy as np
import pandas as pd

from _utils import REPORTS_DIR, resolve_ticker

warnings.filterwarnings("ignore")


# 한글 폰트 설정 (Windows: Malgun Gothic)
def _setup_korean_font():
    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for c in candidates:
        if c in available:
            plt.rcParams["font.family"] = c
            plt.rcParams["axes.unicode_minus"] = False
            return c
    return None


_FONT = _setup_korean_font()


# ───────────────────────────────────────────────────────
# 1. 일목균형표 (Ichimoku Cloud)
# ───────────────────────────────────────────────────────
def compute_ichimoku(df: pd.DataFrame) -> pd.DataFrame:
    """일목균형표 5선 계산.

    - 전환선 (Tenkan): 9일 최고/최저 평균
    - 기준선 (Kijun): 26일 최고/최저 평균
    - 선행스팬1 (Senkou A): (전환+기준)/2, 26일 앞으로
    - 선행스팬2 (Senkou B): 52일 최고/최저 평균, 26일 앞으로
    - 후행스팬 (Chikou): 종가를 26일 뒤로
    """
    out = df.copy()
    high = out["high"]
    low = out["low"]
    close = out["close"]

    out["tenkan"] = (high.rolling(9).max() + low.rolling(9).min()) / 2
    out["kijun"] = (high.rolling(26).max() + low.rolling(26).min()) / 2
    out["senkou_a"] = ((out["tenkan"] + out["kijun"]) / 2).shift(26)
    out["senkou_b"] = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    out["chikou"] = close.shift(-26)
    return out


# ───────────────────────────────────────────────────────
# 2. Volume Profile (매물대 감지)
# ───────────────────────────────────────────────────────
def detect_volume_profile(df: pd.DataFrame, n_bins: int = 30, top_n: int = 3) -> list[dict]:
    """가격대별 거래량 누적 → 상위 N개 매물대 가격대 반환.

    Returns:
        [{"price": 가격중심, "volume": 누적거래량, "low": 구간하한, "high": 구간상한}, ...]
    """
    if len(df) < 20:
        return []
    prices = df["close"].values
    volumes = df["volume"].values
    pmin, pmax = prices.min(), prices.max()
    if pmax == pmin:
        return []
    bins = np.linspace(pmin, pmax, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    bin_volumes = np.zeros(n_bins)
    for p, v in zip(prices, volumes):
        idx = min(int((p - pmin) / (pmax - pmin) * n_bins), n_bins - 1)
        bin_volumes[idx] += v
    # 상위 N개
    top_idx = np.argsort(bin_volumes)[::-1][:top_n]
    result = []
    for i in top_idx:
        result.append({
            "price": float(bin_centers[i]),
            "volume": float(bin_volumes[i]),
            "low": float(bins[i]),
            "high": float(bins[i + 1]),
        })
    return sorted(result, key=lambda x: x["price"])


# ───────────────────────────────────────────────────────
# 3. 백테스팅 기반 가격대 계산 (analyze.py momentum 결과 활용)
# ───────────────────────────────────────────────────────
def compute_price_zones(code: str, current_price: float, atr: float, df: pd.DataFrame) -> dict:
    """백테스팅 + ATR로 매수/익절/손절 가격대 계산.

    Returns:
        {
          "buy_1": (가격, 라벨), "buy_2": ..., "buy_3": ...,
          "sell_1": (가격, 라벨), "sell_2": ...,
          "stop_day": (가격, 라벨), "stop_swing": ...,
        }
    """
    import momentum

    zones = {}
    # ATR 손절선
    if atr:
        zones["stop_day"] = (round(current_price - 2 * atr, -2), "단타 손절 (2×ATR)")
        zones["stop_swing"] = (round(current_price - 3 * atr, -2), "스윙 손절 (3×ATR)")

    # 백테스팅 한달 윈도우
    rsi_last = float(df["rsi_14"].iloc[-1]) if "rsi_14" in df.columns and pd.notna(df["rsi_14"].iloc[-1]) else None
    if rsi_last is not None:
        bt = momentum._select_threshold(df, rsi_last)
        if bt and not bt.get("insufficient"):
            w20 = bt["windows"].get(20, {})
            n = bt.get("n_samples", 0)
            if w20 and n >= 10:
                # 매수: 한달 평균 MDD / 중앙값 MDD (조정폭 기반)
                mdd_med = w20.get("mdd_median", 0)
                mdd_avg = w20.get("mdd_mean", 0)
                mdd_worst = w20.get("mdd_worst", 0)
                buy_1 = round(current_price * (1 + mdd_med / 100), -2)
                buy_2 = round(current_price * (1 + mdd_avg / 100), -2)
                buy_3 = round(current_price * (1 + mdd_worst / 100), -2)
                zones["buy_1"] = (buy_1, "1차 매수 (한달 중앙값 MDD)")
                zones["buy_2"] = (buy_2, "2차 매수 (한달 평균 MDD)")
                zones["buy_3"] = (buy_3, "3차 매수 (한달 최악 MDD)")
                # 익절: 한달 평균/중앙값 상승폭
                run_med = w20.get("runup_median", 0)
                run_avg = w20.get("runup_mean", 0)
                run_best = w20.get("runup_best", 0)
                sell_1 = round(current_price * (1 + run_med / 100), -2)
                sell_2 = round(current_price * (1 + run_avg / 100), -2)
                sell_3 = round(current_price * (1 + run_best / 100), -2)
                zones["sell_1"] = (sell_1, "1차 익절 (한달 중앙값)")
                zones["sell_2"] = (sell_2, "2차 익절 (한달 평균)")
                zones["sell_3"] = (sell_3, "차익실현 매물 (극단)")
    return zones


# ───────────────────────────────────────────────────────
# 4. 차트 렌더링
# ───────────────────────────────────────────────────────
def render_scenario_chart(
    code: str,
    name: str,
    days: int = 180,
    avg_price: Optional[float] = None,
    out_path: Optional[Path] = None,
) -> Path:
    """시나리오 차트 생성."""
    import technical
    import momentum

    df = technical.fetch_ohlcv(code, days=days)
    df = technical.add_indicators(df)
    df = compute_ichimoku(df)

    # 시각화용: 최근 90일 (가독성↑)
    plot_df = df.tail(90).copy()
    plot_df.index.name = "Date"

    current_price = float(plot_df["close"].iloc[-1])
    atr = momentum.calc_atr(df, period=14)
    zones = compute_price_zones(code, current_price, atr, df)
    # 매물대는 최근 90일 데이터로 계산 (먼 과거 가격대 영향 최소화)
    profile = detect_volume_profile(plot_df, n_bins=20, top_n=3)

    # mplfinance 스타일
    mc = mpf.make_marketcolors(
        up="#FF3B30", down="#0064FF", edge="inherit", wick={"up": "#FF3B30", "down": "#0064FF"}, volume="in"
    )
    style = mpf.make_mpf_style(
        base_mpf_style="yahoo",
        marketcolors=mc,
        rc={
            "font.family": _FONT or "DejaVu Sans",
            "axes.unicode_minus": False,
            "axes.facecolor": "#FAFAFA",
            "figure.facecolor": "#FFFFFF",
        },
        gridcolor="#E5E5E5",
        gridstyle="--",
    )

    # 일목 + 이평선 오버레이
    apds = []
    if plot_df["tenkan"].notna().any():
        apds.append(mpf.make_addplot(plot_df["tenkan"], color="#FF6B35", width=1.0))
    if plot_df["kijun"].notna().any():
        apds.append(mpf.make_addplot(plot_df["kijun"], color="#004E89", width=1.2))
    if plot_df["sma_5"].notna().any():
        apds.append(mpf.make_addplot(plot_df["sma_5"], color="#888888", width=0.6, linestyle=":"))
    if plot_df["sma_20"].notna().any():
        apds.append(mpf.make_addplot(plot_df["sma_20"], color="#AAAAAA", width=0.6, linestyle=":"))

    # RSI 패널
    if plot_df["rsi_14"].notna().any():
        apds.append(mpf.make_addplot(plot_df["rsi_14"], panel=2, color="#9B59B6", width=1.0, ylabel="RSI"))
        apds.append(mpf.make_addplot([70] * len(plot_df), panel=2, color="#E74C3C", width=0.5, linestyle="--"))
        apds.append(mpf.make_addplot([30] * len(plot_df), panel=2, color="#27AE60", width=0.5, linestyle="--"))

    # 차트 그리기
    fig, axes = mpf.plot(
        plot_df,
        type="candle",
        addplot=apds,
        volume=True,
        style=style,
        figsize=(14, 9),
        panel_ratios=(6, 1.5, 1.5),
        returnfig=True,
        tight_layout=True,
        warn_too_much_data=10000,
    )

    ax_main = axes[0]

    # ───── 일목 구름대 채우기 ─────
    x_idx = np.arange(len(plot_df))
    a = plot_df["senkou_a"].values
    b = plot_df["senkou_b"].values
    valid = ~(np.isnan(a) | np.isnan(b))
    if valid.any():
        ax_main.fill_between(
            x_idx, a, b, where=(a >= b) & valid, color="#A8E6CF", alpha=0.25, label="구름 양"
        )
        ax_main.fill_between(
            x_idx, a, b, where=(a < b) & valid, color="#FFAAA5", alpha=0.25, label="구름 음"
        )

    # ───── 매물대 가로 영역 ─────
    n = len(plot_df)
    for i, p in enumerate(profile):
        ax_main.axhspan(p["low"], p["high"], color="#FFB347", alpha=0.10, zorder=0)
        ax_main.text(
            n - 1, p["price"],
            f" ({i+1}) 매물대 {p['price']:,.0f}",
            fontsize=8, va="center", ha="left",
            color="#D35400", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="#D35400", alpha=0.85),
        )

    # ───── 백테 기반 가격 라벨 ─────
    def _label_zone(price, text, color, dash=False):
        ax_main.axhline(price, color=color, linestyle="--" if dash else "-", linewidth=0.9, alpha=0.7)
        ax_main.text(
            -3, price, f"{text}\n{price:,.0f} ({(price/current_price-1)*100:+.1f}%)",
            fontsize=8, va="center", ha="right",
            color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color, alpha=0.9),
        )

    # 매수 라인 (파란계열)
    for key, color in [("buy_1", "#0064FF"), ("buy_2", "#3D8BFD"), ("buy_3", "#5DADE2")]:
        if key in zones:
            price, label = zones[key]
            _label_zone(price, label, color, dash=False)
    # 익절 라인 (빨강/주황계열) — sell_3는 차트 범위 벗어날 수 있어 생략
    for key, color in [("sell_1", "#FF3B30"), ("sell_2", "#FF6B35")]:
        if key in zones:
            price, label = zones[key]
            _label_zone(price, label, color, dash=True)
    # 손절 라인 (회색/검정)
    if "stop_day" in zones:
        _label_zone(zones["stop_day"][0], zones["stop_day"][1], "#2C3E50", dash=True)
    if "stop_swing" in zones:
        _label_zone(zones["stop_swing"][0], zones["stop_swing"][1], "#7F8C8D", dash=True)

    # ───── 평단가 (보유 진단 모드) ─────
    if avg_price is not None:
        pnl = (current_price / avg_price - 1) * 100
        ax_main.axhline(avg_price, color="#9B59B6", linestyle="-", linewidth=1.5, alpha=0.9)
        ax_main.text(
            -3, avg_price, f"📍 평단가 {avg_price:,.0f}\n손익 {pnl:+.1f}%",
            fontsize=9, va="center", ha="right",
            color="#9B59B6", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#F5EEFB", edgecolor="#9B59B6", alpha=0.95),
        )

    # ───── 현재가 강조 ─────
    ax_main.axhline(current_price, color="#000000", linestyle="-", linewidth=0.8, alpha=0.5)
    ax_main.text(
        n - 1, current_price, f"  현재가 {current_price:,.0f}",
        fontsize=9, va="center", ha="left",
        color="white", fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#000000", alpha=0.85),
    )

    # ───── 시나리오 화살표 (향후 5~10봉 예상) ─────
    # 단순 룰: 현재가 → 가까운 매수선 또는 익절선으로 점선 화살표
    if "sell_1" in zones:
        target = zones["sell_1"][0]
        ax_main.annotate(
            "",
            xy=(n + 8, target),
            xytext=(n - 1, current_price),
            arrowprops=dict(arrowstyle="->", color="#FF3B30", lw=1.5, linestyle="--", alpha=0.7),
        )
        ax_main.text(
            n + 8, target, f"  강세 시나리오\n  {target:,.0f}",
            fontsize=8, color="#FF3B30", fontweight="bold", va="center", ha="left",
        )
    if "buy_1" in zones:
        target = zones["buy_1"][0]
        ax_main.annotate(
            "",
            xy=(n + 8, target),
            xytext=(n - 1, current_price),
            arrowprops=dict(arrowstyle="->", color="#0064FF", lw=1.5, linestyle="--", alpha=0.7),
        )
        ax_main.text(
            n + 8, target, f"  약세 시나리오\n  {target:,.0f}",
            fontsize=8, color="#0064FF", fontweight="bold", va="center", ha="left",
        )

    # ───── X축 확장 (시나리오 공간) ─────
    ax_main.set_xlim(-15, n + 20)

    # ───── Y축 범위 동적 조정 (백테 매수/익절 + 평단가 모두 표시) ─────
    y_candidates = [plot_df["low"].min(), plot_df["high"].max(), current_price]
    for key in ("buy_1", "buy_2", "buy_3", "sell_1", "sell_2", "stop_day", "stop_swing"):
        if key in zones:
            y_candidates.append(zones[key][0])
    if avg_price is not None:
        y_candidates.append(avg_price)
    y_min = min(y_candidates) * 0.97
    y_max = max(y_candidates) * 1.03
    ax_main.set_ylim(y_min, y_max)

    # ───── 제목 + 워터마크 ─────
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    fig.suptitle(
        f"{name} ({code}) — 시나리오 차트  |  {today}",
        fontsize=14, fontweight="bold", y=0.985,
    )
    # 워터마크
    fig.text(
        0.5, 0.5, "stock-analysis-ujim",
        fontsize=40, color="#AAAAAA", alpha=0.06,
        ha="center", va="center", rotation=30, fontweight="bold",
    )
    fig.text(
        0.99, 0.005, f"© ujim stock-analysis | {today}",
        fontsize=7, color="#888888", ha="right", va="bottom",
    )

    # 저장
    if out_path is None:
        REPORTS_DIR.mkdir(exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = name.replace("/", "_")
        out_path = REPORTS_DIR / f"{safe_name}_{date_str}_chart.png"
    fig.savefig(out_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out_path


# ───────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="종목별 시나리오 차트 생성 (Tatons 스타일)")
    parser.add_argument("query", help="종목명 또는 코드")
    parser.add_argument("--avg-price", type=float, default=None, help="평단가 (보유 진단)")
    parser.add_argument("--days", type=int, default=180, help="데이터 기간 (기본 180일)")
    args = parser.parse_args()

    code, name = resolve_ticker(args.query)
    print(f"[*] 시나리오 차트 생성 중: {name} ({code})")
    path = render_scenario_chart(code, name, days=args.days, avg_price=args.avg_price)
    print(f"[✓] 차트 저장: {path}")
