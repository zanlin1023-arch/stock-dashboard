"""추세 지속 가능성 평가: ADX, 거래량 동행성, 다이버전스, 정배열 유지, 신고가, 과거 패턴."""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

from technical import add_indicators, fetch_ohlcv

warnings.filterwarnings("ignore")


def calc_adx(df: pd.DataFrame, period: int = 14) -> float | None:
    """ADX (Average Directional Index): 추세 강도. 25↑ 강한 추세."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up = high.diff()
    down = -low.diff()

    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down

    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)

    # Wilder's smoothing (단순 EMA로 근사)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr

    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    adx = dx.ewm(alpha=1 / period, adjust=False).mean()

    val = adx.iloc[-1]
    return float(val) if pd.notna(val) else None


def volume_concordance(df: pd.DataFrame, days: int = 20) -> float | None:
    """최근 N일 상승일 거래량 합 / 하락일 거래량 합."""
    recent = df.tail(days).copy()
    diff = recent["close"].diff()
    up_vol = recent.loc[diff > 0, "volume"].sum()
    down_vol = recent.loc[diff < 0, "volume"].sum()
    if down_vol == 0:
        return None
    return float(up_vol / down_vol)


def detect_divergence(df: pd.DataFrame, lookback: int = 30) -> str | None:
    """가격-RSI 다이버전스 감지."""
    recent = df.tail(lookback).dropna(subset=["rsi_14"]).copy()
    if len(recent) < 10:
        return None

    half = len(recent) // 2
    early = recent.iloc[:half]
    late = recent.iloc[half:]

    early_price_hi = early["close"].max()
    late_price_hi = late["close"].max()
    early_rsi_hi = early["rsi_14"].max()
    late_rsi_hi = late["rsi_14"].max()

    # 약세 다이버전스: 가격은 신고가, RSI는 못 따라옴
    if late_price_hi > early_price_hi * 1.01 and late_rsi_hi < early_rsi_hi - 3:
        return "bearish"

    early_price_lo = early["close"].min()
    late_price_lo = late["close"].min()
    early_rsi_lo = early["rsi_14"].min()
    late_rsi_lo = late["rsi_14"].min()

    # 강세 다이버전스: 가격은 신저가, RSI는 더 높음
    if late_price_lo < early_price_lo * 0.99 and late_rsi_lo > early_rsi_lo + 3:
        return "bullish"

    return None


def aligned_days(df: pd.DataFrame) -> int:
    """현재까지 정배열(5>20>60) 유지 연속 일수."""
    if "sma_5" not in df.columns:
        return 0
    days = 0
    for i in range(len(df) - 1, -1, -1):
        r = df.iloc[i]
        if pd.notna(r["sma_5"]) and pd.notna(r["sma_20"]) and pd.notna(r["sma_60"]):
            if r["sma_5"] > r["sma_20"] > r["sma_60"]:
                days += 1
            else:
                break
        else:
            break
    return days


def count_new_highs(df: pd.DataFrame, window: int = 60) -> int:
    """최근 N일 중 직전까지의 신고가를 갱신한 일수."""
    recent = df.tail(window).copy()
    if len(recent) < 2:
        return 0
    expanding_max = recent["close"].expanding().max()
    new_highs = (recent["close"] == expanding_max) & (recent["close"] > recent["close"].shift(1))
    return int(new_highs.sum())


def historical_rsi_pattern(df: pd.DataFrame, current_rsi: float, forward: int = 5) -> dict | None:
    """현재 RSI ±3 구간의 과거 사례 → forward일 후 수익률 분포."""
    if current_rsi is None:
        return None

    clean = df.dropna(subset=["rsi_14", "close"]).reset_index(drop=True)
    if len(clean) < forward + 10:
        return None

    similar = clean[
        (clean["rsi_14"] >= current_rsi - 3) & (clean["rsi_14"] <= current_rsi + 3)
    ]
    # 마지막 forward일은 제외 (forward 가능 데이터 없음)
    valid_idx = [i for i in similar.index if i + forward < len(clean) and i < len(clean) - forward - 1]
    if len(valid_idx) < 3:
        return None

    returns = []
    for i in valid_idx:
        start = clean.iloc[i]["close"]
        end = clean.iloc[i + forward]["close"]
        if start > 0:
            returns.append((end / start - 1) * 100)

    if not returns:
        return None

    return {
        "n_samples": len(returns),
        "mean": float(np.mean(returns)),
        "median": float(np.median(returns)),
        "win_rate": float(sum(1 for r in returns if r > 0) / len(returns) * 100),
        "max_gain": float(max(returns)),
        "max_loss": float(min(returns)),
    }


FORWARD_WINDOWS = [5, 10, 20, 60]  # 1주, 2주, 한달, 3달

# Phase 1 — 통계 신뢰성 임계값 (업계 표준: López de Prado)
SAMPLE_MIN_OUTPUT = 10    # 이하면 결과 표시 안 함
SAMPLE_MIN_RELIABLE = 30  # 이하면 통계 신뢰성 경고
SAMPLE_RELIABLE = 100     # 이상이면 신뢰


def calc_atr(df: pd.DataFrame, period: int = 14) -> float | None:
    """ATR(Average True Range) — Wilder의 변동성 지표.

    손절선 표준: 진입가 - (2~3 × ATR)
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()
    val = atr.iloc[-1]
    return float(val) if pd.notna(val) else None


def detect_trend_bias(df: pd.DataFrame) -> dict:
    """1년 종목 수익률 ±100% 이상 → 추세 편향 경고."""
    clean = df["close"].dropna()
    if len(clean) < 250:
        days = len(clean)
    else:
        days = 250
    if days < 60:
        return {"flag": False, "reason": "데이터 부족"}
    period_return = (clean.iloc[-1] / clean.iloc[-days] - 1) * 100
    if period_return > 100:
        return {
            "flag": True,
            "direction": "up",
            "period_return": float(period_return),
            "warning": f"⚠️ 1년 수익률 {period_return:+.1f}% (폭등주) — 백테스팅 결과 **상승 방향으로 부풀려짐**. 평균 수익률은 미래 예측이 아닌 '과거 추세의 반영'.",
        }
    if period_return < -50:
        return {
            "flag": True,
            "direction": "down",
            "period_return": float(period_return),
            "warning": f"⚠️ 1년 수익률 {period_return:+.1f}% (하락주) — 백테스팅 결과 **하락 방향으로 부풀려짐**.",
        }
    return {"flag": False, "period_return": float(period_return)}


def threshold_backtest(df: pd.DataFrame, rsi_threshold: float, windows: list[int] = None) -> dict | None:
    """절대 RSI 임계값 백테스팅 (예: RSI 80+, 85+, 90+).

    각 window마다:
      - end_return: window일 후 수익률
      - max_drawdown: window 내 최대 낙폭 (저점까지)
      - max_runup: window 내 최대 상승폭 (고점까지)
    """
    if windows is None:
        windows = FORWARD_WINDOWS
    clean = df.dropna(subset=["rsi_14", "close"]).reset_index(drop=True)
    if len(clean) < max(windows) + 10:
        return None

    high_rsi_idx = clean.index[clean["rsi_14"] >= rsi_threshold].tolist()
    valid = [i for i in high_rsi_idx if i + max(windows) < len(clean)]
    if len(valid) < 3:
        return {"threshold": rsi_threshold, "n_samples": len(valid), "windows": {}, "insufficient": True}

    out = {"threshold": rsi_threshold, "n_samples": len(valid), "windows": {}, "insufficient": False}

    for w in windows:
        end_returns = []
        mdds = []
        runups = []
        for i in valid:
            start = clean.iloc[i]["close"]
            slice_ = clean.iloc[i + 1:i + 1 + w]
            if slice_.empty or start <= 0:
                continue
            end_returns.append((slice_.iloc[-1]["close"] / start - 1) * 100)
            mdds.append((slice_["close"].min() / start - 1) * 100)
            runups.append((slice_["close"].max() / start - 1) * 100)

        if not end_returns:
            continue

        out["windows"][w] = {
            "end_return_mean": float(np.mean(end_returns)),
            "end_return_median": float(np.median(end_returns)),
            "win_rate": float(sum(1 for r in end_returns if r > 0) / len(end_returns) * 100),
            "mdd_mean": float(np.mean(mdds)),
            "mdd_median": float(np.median(mdds)),
            "mdd_worst": float(min(mdds)),
            "runup_mean": float(np.mean(runups)),
            "runup_median": float(np.median(runups)),
            "runup_best": float(max(runups)),
        }
    return out


def _select_threshold(df: pd.DataFrame, current_rsi: float) -> dict | None:
    """현재 RSI에 맞는 임계값 선택 + 백테스팅. 표본 부족 시 자동 fallback."""
    # 현재 RSI에서 점차 낮은 임계값으로 fallback
    if current_rsi >= 90:
        candidates = [90, 85, 80, 70, 60, 50]
    elif current_rsi >= 80:
        candidates = [80, 70, 60, 50, 40]
    elif current_rsi >= 70:
        candidates = [70, 60, 50, 40]
    elif current_rsi >= 50:
        candidates = [60, 50, 40, 30]
    elif current_rsi >= 30:
        candidates = [50, 40, 30]
    else:
        candidates = [40, 30, 20]

    best = None
    for t in candidates:
        bt = threshold_backtest(df, t)
        if bt and not bt.get("insufficient") and bt["n_samples"] >= 5:
            return bt  # 표본 5개 이상이면 즉시 채택
        if bt and not best:
            best = bt
    return best


def actionable_thresholds(df: pd.DataFrame, current_price: float, current_rsi: float, label: str = "", atr: float | None = None) -> dict:
    """단일 기간 백테스팅 → 권고가/손절가 산출.

    Phase 1 개선:
      - 표본 크기 경고 (n<10 미출력 / n<30 경고 / n<100 부분신뢰)
      - 중앙값 우선 (평균은 참고)
      - ATR 기반 손절선 추가 (업계 표준)
    """
    if current_rsi is None or current_price <= 0:
        return {}

    best = _select_threshold(df, current_rsi)
    if not best or best.get("insufficient"):
        return {"unavailable": True, "reason": f"{label} 표본 부족 (n={best.get('n_samples', 0) if best else 0})"}

    n = best["n_samples"]
    if n < SAMPLE_MIN_OUTPUT:
        return {"unavailable": True, "reason": f"{label} 표본 {n}개 — 통계 무효 (최소 10개 필요)"}

    # 신뢰도 라벨
    if n >= SAMPLE_RELIABLE:
        reliability = ("✅ 신뢰", f"n={n} ≥ 100, 업계 표준 충족")
    elif n >= SAMPLE_MIN_RELIABLE:
        reliability = ("🟡 중간", f"n={n} (30~100), 추론 가능하나 신뢰구간 넓음")
    else:
        reliability = ("🚨 낮음", f"n={n} (<30), **통계 추론 불가**, 참고용으로만")

    w20 = best["windows"].get(20, {})

    out = {
        "label": label,
        "source_threshold": best["threshold"],
        "n_samples": n,
        "reliability_label": reliability[0],
        "reliability_note": reliability[1],
        "windows_stats": best["windows"],
    }

    # 평균-중앙값 괴리 검사 (한달 기준)
    if w20:
        mean_run = w20["runup_mean"]
        median_run = w20["runup_median"]
        # 격차가 2배 이상이면 경고
        if abs(median_run) > 0.5 and abs(mean_run / median_run) > 2.5:
            out["mean_median_warning"] = (
                f"⚠️ 한달 상승폭 평균({mean_run:+.1f}%)이 중앙값({median_run:+.1f}%) 대비 큼 "
                f"— 극단치에 끌려간 평균. **중앙값을 신뢰**하세요."
            )

    # 분할 매수 가격대 (한달=20일 MDD 기준) — 중앙값 우선
    if w20:
        out["buy_zones"] = [
            (round(current_price * (1 + w20["mdd_median"] / 100), -2),
             f"한달 중앙값 MDD ({w20['mdd_median']:+.1f}%) — **1차 분할 매수** ⭐"),
            (round(current_price * (1 + w20["mdd_mean"] / 100), -2),
             f"한달 평균 MDD ({w20['mdd_mean']:+.1f}%) — 참고"),
            (round(current_price * (1 + w20["mdd_worst"] / 100), -2),
             f"한달 최악 MDD ({w20['mdd_worst']:+.1f}%) — 극단 시나리오"),
        ]

        # 익절선: 중앙값을 1차(현실적), 평균을 2차(낙관적, 참고)
        out["target_zones"] = [
            (round(current_price * (1 + w20["runup_median"] / 100), -2),
             f"한달 중앙값 상승 ({w20['runup_median']:+.1f}%) — **1차 익절** ⭐"),
            (round(current_price * (1 + w20["runup_mean"] / 100), -2),
             f"한달 평균 상승 ({w20['runup_mean']:+.1f}%) — 2차 (낙관)"),
            (round(current_price * (1 + w20["runup_best"] / 100), -2),
             f"한달 최고 상승 ({w20['runup_best']:+.1f}%) — 극단 강세"),
        ]

    # ATR 기반 손절선 (업계 표준 — Wilder)
    if atr is not None:
        atr_pct = atr / current_price * 100
        out["stop_loss_atr"] = {
            "atr_value": atr,
            "atr_pct": atr_pct,
            "tight": round(current_price - 2 * atr, -2),    # 보수 (단타)
            "loose": round(current_price - 3 * atr, -2),    # 여유 (스윙)
            "tight_pct": -2 * atr_pct,
            "loose_pct": -3 * atr_pct,
        }

    # 보조: 한달 최악 MDD 손절선 (참고용 — 너무 깊으니 ATR 우선)
    if w20:
        out["stop_loss_mdd"] = {
            "price": round(current_price * (1 + w20["mdd_worst"] / 100), -2),
            "pct": w20["mdd_worst"],
        }

    return out


def actionable_dual(df_full: pd.DataFrame, current_price: float, current_rsi: float) -> dict:
    """단기(최근 1년 / 250 영업일) + 중기(전체 2년) 양쪽 백테스팅 + ATR + 추세편향."""
    short_df = df_full.tail(250).reset_index(drop=True)
    mid_df = df_full.reset_index(drop=True)

    # ATR — 전체 데이터로 계산
    atr = calc_atr(df_full, period=14)
    # 추세 편향 검사
    bias = detect_trend_bias(df_full)

    return {
        "short": actionable_thresholds(short_df, current_price, current_rsi, label="단기 (최근 1년)", atr=atr),
        "mid": actionable_thresholds(mid_df, current_price, current_rsi, label="중기 (2년)", atr=atr),
        "atr": atr,
        "trend_bias": bias,
    }


def evaluate(code: str, name: str) -> dict[str, Any]:
    df = fetch_ohlcv(code, days=730)  # 2년치로 확대 (백테스팅 표본 확보)
    df = add_indicators(df)

    items: list[tuple[str, int, str]] = []
    score = 0

    # 1. ADX
    adx = calc_adx(df)
    if adx is not None:
        if adx > 40:
            items.append(("ADX", +20, f"ADX {adx:.1f} — 매우 강한 추세"))
            score += 20
        elif adx > 25:
            items.append(("ADX", +10, f"ADX {adx:.1f} — 강한 추세"))
            score += 10
        elif adx > 15:
            items.append(("ADX", 0, f"ADX {adx:.1f} — 보통 추세"))
        else:
            items.append(("ADX", -10, f"ADX {adx:.1f} — 추세 부재"))
            score -= 10

    # 2. 거래량 동행성
    vc = volume_concordance(df)
    if vc is not None:
        if vc > 1.5:
            items.append(("거래량 동행", +15, f"상승일/하락일 거래량 = {vc:.2f} — 강한 매수세"))
            score += 15
        elif vc > 1.0:
            items.append(("거래량 동행", +5, f"비율 {vc:.2f} — 매수 우위"))
            score += 5
        elif vc < 0.7:
            items.append(("거래량 동행", -10, f"비율 {vc:.2f} — 매도 우위"))
            score -= 10

    # 3. 다이버전스
    div = detect_divergence(df)
    if div == "bearish":
        items.append(("다이버전스", -20, "약세 다이버전스 — 가격↑ RSI↓ (추세 약화)"))
        score -= 20
    elif div == "bullish":
        items.append(("다이버전스", +20, "강세 다이버전스 — 가격↓ RSI↑ (반등 가능)"))
        score += 20
    else:
        items.append(("다이버전스", 0, "특이 다이버전스 없음"))

    # 4. 정배열 유지 일수
    ad = aligned_days(df)
    if ad >= 30:
        items.append(("정배열 지속", +15, f"{ad}일 — 안정적 상승 추세"))
        score += 15
    elif ad >= 10:
        items.append(("정배열 지속", +10, f"{ad}일 — 추세 형성"))
        score += 10
    elif ad >= 3:
        items.append(("정배열 지속", +5, f"{ad}일 — 초기 정배열"))
        score += 5
    elif ad == 0:
        items.append(("정배열 지속", -5, "정배열 미형성"))
        score -= 5

    # 5. 신고가 갱신
    nh = count_new_highs(df, 60)
    if nh > 12:
        items.append(("신고가 빈도", +15, f"60일 중 {nh}회 신고가 — 강한 모멘텀"))
        score += 15
    elif nh > 5:
        items.append(("신고가 빈도", +5, f"60일 중 {nh}회 신고가"))
        score += 5
    elif nh == 0:
        items.append(("신고가 빈도", -5, "60일 신고가 없음"))
        score -= 5

    # 6. 과거 RSI 유사 패턴
    last_rsi = df["rsi_14"].dropna().iloc[-1] if not df["rsi_14"].dropna().empty else None
    pattern = historical_rsi_pattern(df, last_rsi, forward=5)
    if pattern:
        m = pattern["mean"]
        if m > 2:
            items.append((
                "과거 5일 패턴",
                +10,
                f"RSI {last_rsi:.0f} 유사구간 후 5일 평균 {m:+.2f}% / 승률 {pattern['win_rate']:.0f}% (n={pattern['n_samples']})",
            ))
            score += 10
        elif m < -2:
            items.append((
                "과거 5일 패턴",
                -10,
                f"RSI {last_rsi:.0f} 유사구간 후 5일 평균 {m:+.2f}% / 승률 {pattern['win_rate']:.0f}% (n={pattern['n_samples']})",
            ))
            score -= 10
        else:
            items.append((
                "과거 5일 패턴",
                0,
                f"RSI {last_rsi:.0f} 유사구간 후 5일 평균 {m:+.2f}% / 승률 {pattern['win_rate']:.0f}% (n={pattern['n_samples']})",
            ))

    # 자체 백테스팅 — 단기(1년) + 중기(2년) 양쪽 권고가/손절가 산출
    current_price = float(df.iloc[-1]["close"])
    actions_dual = actionable_dual(df, current_price, last_rsi)

    return {
        "code": code,
        "name": name,
        "total_score": max(-100, min(100, score)),
        "items": items,
        "adx": adx,
        "volume_concordance": vc,
        "divergence": div,
        "aligned_days": ad,
        "new_highs_60d": nh,
        "historical_pattern": pattern,
        "current_rsi": float(last_rsi) if last_rsi is not None else None,
        "current_price": current_price,
        "actionable_dual": actions_dual,
    }


def verdict(score: int) -> tuple[str, str]:
    if score >= 50:
        return ("🟢 강한 지속력", "추세 지속 신호 우세 — 모멘텀 살아있음, 추격 매수도 고려 가능")
    if score >= 20:
        return ("🟢 지속 우세", "추세 유지 가능성 높음 — 조정 시 분할 진입 검토")
    if score >= -10:
        return ("🟡 혼조", "지속/반전 시그널 혼재 — 변동성 주의, 신규 진입 신중")
    if score >= -40:
        return ("🟠 약화", "추세 약화 신호 — 반전 가능성 증가, 보유 시 일부 차익 실현 검토")
    return ("🔴 반전 우세", "강한 반전 시그널 — 추가 상승 기대 어려움")


def to_markdown(result: dict) -> str:
    label, comment = verdict(result["total_score"])
    lines = [
        "## 📈 추세 지속 가능성 평가",
        "",
        f"### 종합: {label} (총점 **{result['total_score']:+d}**)",
        f"_{comment}_",
        "",
        "### 핵심 지표",
        "| 지표 | 값 | 해석 |",
        "|------|-----|------|",
    ]

    if result["adx"] is not None:
        adx_v = result["adx"]
        adx_int = "매우 강함" if adx_v > 40 else ("강함" if adx_v > 25 else ("보통" if adx_v > 15 else "약함"))
        lines.append(f"| ADX | {adx_v:.1f} | {adx_int} |")

    if result["volume_concordance"] is not None:
        vc = result["volume_concordance"]
        vc_int = "매수세 강함" if vc > 1.5 else ("매수 우위" if vc > 1.0 else "매도 우위")
        lines.append(f"| 상승일/하락일 거래량 | {vc:.2f} | {vc_int} |")

    div_str = {"bearish": "⚠️ 약세 다이버전스", "bullish": "✅ 강세 다이버전스"}.get(
        result["divergence"], "특이 신호 없음"
    )
    lines.append(f"| 다이버전스 | - | {div_str} |")
    lines.append(f"| 정배열 유지 | {result['aligned_days']}일 | {'안정' if result['aligned_days'] >= 30 else ('형성중' if result['aligned_days'] >= 10 else '미형성')} |")
    lines.append(f"| 60일 신고가 횟수 | {result['new_highs_60d']}회 | {'강한 모멘텀' if result['new_highs_60d'] > 12 else ('모멘텀 있음' if result['new_highs_60d'] > 5 else '약함')} |")

    if result.get("historical_pattern"):
        p = result["historical_pattern"]
        lines.append(
            f"| 과거 RSI {result['current_rsi']:.0f} 후 5일 | "
            f"평균 {p['mean']:+.2f}% / 중앙값 {p['median']:+.2f}% / 승률 {p['win_rate']:.0f}% | "
            f"표본 {p['n_samples']}개 (최대 {p['max_gain']:+.1f}% / 최소 {p['max_loss']:+.1f}%) |"
        )

    lines += ["", "### 가산/감점 내역", "| 항목 | 점수 | 사유 |", "|------|------|------|"]
    for nm, pts, reason in result["items"]:
        lines.append(f"| {nm} | {pts:+d} | {reason} |")

    # 자체 백테스팅 기반 권고 (단기 1년 + 중기 2년)
    dual = result.get("actionable_dual") or {}

    # 추세 편향 경고 (가장 먼저 — 전체 결과 해석에 영향)
    bias = dual.get("trend_bias") or {}
    if bias.get("flag"):
        lines += ["", "### ⚠️ 추세 편향 경고", "", f"> {bias['warning']}"]

    # ATR 기반 손절선 (업계 표준 — 종목별 변동성 자동 반영)
    atr = dual.get("atr")
    short_actions = dual.get("short") or {}
    if atr is not None and short_actions.get("stop_loss_atr"):
        atr_info = short_actions["stop_loss_atr"]
        current_price = result.get("current_price", 0)
        lines += [
            "",
            "### 🛡️ ATR 기반 손절선 (업계 표준 — Wilder)",
            "",
            f"_ATR(14) = **{atr_info['atr_value']:,.0f}원** ({atr_info['atr_pct']:.2f}% / 일평균 변동성)_",
            "",
            f"| 손절 유형 | 가격 | 하락폭 | 용도 |",
            f"|-----------|------|--------|------|",
            f"| **단타 손절 (2×ATR)** | **{atr_info['tight']:,.0f}원** | {atr_info['tight_pct']:+.2f}% | 짧게 끊기 |",
            f"| **스윙 손절 (3×ATR)** | **{atr_info['loose']:,.0f}원** | {atr_info['loose_pct']:+.2f}% | 한달 보유 |",
        ]
        if short_actions.get("stop_loss_mdd"):
            mdd = short_actions["stop_loss_mdd"]
            lines.append(
                f"| 한달 최악 MDD (참고) | {mdd['price']:,.0f}원 | {mdd['pct']:+.2f}% | 극단 시나리오 |"
            )

    for key, header in [("short", "🎯 단기 백테스팅 (최근 1년 데이터 — 단타 우선)"),
                        ("mid", "🎯 중기 백테스팅 (2년 데이터 — 안정성 우선)")]:
        actions = dual.get(key) or {}
        if not actions or actions.get("unavailable"):
            lines += ["", f"### {header}", "", f"_{actions.get('reason', '데이터 부족')}_ "]
            continue

        # 신뢰도 표시
        rel_label = actions.get("reliability_label", "?")
        rel_note = actions.get("reliability_note", "")
        lines += [
            "",
            f"### {header}",
            f"_RSI {actions.get('source_threshold', '?')}+ 사례 **n={actions.get('n_samples', 0)}** | 신뢰도: {rel_label} ({rel_note})_",
        ]

        # 평균-중앙값 괴리 경고
        if actions.get("mean_median_warning"):
            lines += ["", actions["mean_median_warning"]]

        # 기간별 통계표 (5일/10일/한달/3달)
        ws = actions.get("windows_stats") or {}
        if ws:
            lines += [
                "",
                "**기간별 통계:**",
                "| 기간 | 평균 수익률 | **중앙값** ⭐ | 승률 | 평균 MDD | 최악 MDD | 중앙값 상승폭 |",
                "|------|------|------|------|----------|----------|------------|",
            ]
            label_map = {5: "1주(5일)", 10: "2주(10일)", 20: "**한달(20일)**", 60: "3달(60일)"}
            for w in [5, 10, 20, 60]:
                s = ws.get(w)
                if not s:
                    continue
                lines.append(
                    f"| {label_map[w]} | {s['end_return_mean']:+.2f}% | **{s['end_return_median']:+.2f}%** | "
                    f"{s['win_rate']:.0f}% | {s['mdd_mean']:+.2f}% | {s['mdd_worst']:+.2f}% | "
                    f"**{s['runup_median']:+.2f}%** |"
                )

        # 매수 권고가
        if actions.get("buy_zones"):
            lines += ["", "**분할 매수 가격대 (한달 조정폭 기반 — 중앙값 우선):**"]
            for price, lbl in actions["buy_zones"]:
                lines.append(f"- {price:,.0f}원 — {lbl}")

        # 익절선 (중앙값 우선)
        if actions.get("target_zones"):
            lines += ["", "**익절 가격대 (한달 상승폭 기반 — 중앙값 우선):**"]
            for price, lbl in actions["target_zones"]:
                lines.append(f"- {price:,.0f}원 — {lbl}")

    lines += [
        "",
        "---",
        "> ⚠️ **추세 지표는 후행적** — 거시 충격, 실적 발표, 정책 변화는 미반영.",
        "> 📊 **백테스팅 기준 (Phase 1 적용)**:",
        ">   - 손절선 = ATR(14) × 2~3 (업계 표준, 종목별 변동성 자동 반영)",
        ">   - 권고가는 **중앙값 우선** (평균은 극단치 영향 받음)",
        ">   - 표본 n<30이면 신뢰도 낮음, n<10이면 미출력",
        ">   - 1년 수익률 ±100% 종목은 추세 편향으로 결과 부풀림",
        "> 💡 **단기(1년)** = 현재 환경 반영 / **중기(2년)** = 표본 풍부 — 결과 다르면 단기 우선, 중기로 검증.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    from _utils import resolve_ticker

    q = sys.argv[1] if len(sys.argv) > 1 else "005930"
    code, name = resolve_ticker(q)
    r = evaluate(code, name)
    print(to_markdown(r))
