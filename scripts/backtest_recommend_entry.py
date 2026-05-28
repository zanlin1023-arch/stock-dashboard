"""추천(고점수) 종목 한정 진입 재검증 — 검토용 (적용 X).

과거 재현 가능한 '글로벌 모멘텀 점수'(신고가+거래량+RSI+MACD+정배열)로
각 시점 추천 후보를 재현 → 고점수 vs 저점수 종목의 진입 전략 성과 비교.

핵심 질문: "추천 로직이 고르는 강세(고점수) 종목이 단기 진입에서 정말 불리한가?"
  → 고점수 종목: 즉시 vs 눌림 vs 기준선
  → 저점수 종목: 동일 비교
"""
from __future__ import annotations

import sys
from pathlib import Path
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))


def _global_momentum_score(df, i: int) -> int:
    """i 시점까지의 데이터로 글로벌 모멘텀 점수 (0~100) — 과거 재현용.

    momentum_signal.detect_buy_signals의 글로벌 룰만 (수급 제외).
    """
    import pandas as pd
    window = df.iloc[:i + 1]
    if len(window) < 30:
        return 0
    last = window.iloc[-1]
    prev_20 = window.tail(20)
    score = 0
    # 20일 신고가 + 거래량
    high_20 = prev_20["close"].max()
    avg_vol = window.tail(20)["volume"].iloc[:-1].mean()
    vol_ratio = last["volume"] / avg_vol if avg_vol > 0 else 0
    if last["close"] >= high_20 * 0.99:
        score += 30 if vol_ratio >= 1.5 else 15
    elif vol_ratio >= 3:
        score += 20
    elif vol_ratio >= 1.5:
        score += 10
    # RSI
    rsi = last.get("rsi_14")
    if rsi == rsi:
        if rsi > 60: score += 20
        elif rsi > 50: score += 15
        elif rsi < 30: score += 10
    # MACD
    if "macd" in window.columns and len(window) >= 2:
        m, s = last["macd"], last["macd_signal"]
        mp, sp = window.iloc[-2]["macd"], window.iloc[-2]["macd_signal"]
        if m == m and s == s:
            if m > s and mp <= sp: score += 15
            elif m > s: score += 5
    # 정배열
    s5, s20, s60 = last.get("sma_5"), last.get("sma_20"), last.get("sma_60")
    if all(x == x for x in [s5, s20, s60]) and s5 > s20 > s60:
        score += 15
    return score


def analyze_code(code: str, lookback_days: int = 360, hold: int = 10, step: int = 2):
    import technical
    from chart_ichimoku import compute_ichimoku
    df = technical.fetch_ohlcv(code, days=lookback_days)
    df = technical.add_indicators(df)
    df = compute_ichimoku(df)
    if len(df) < 80:
        return None

    # tier: 고점수(>=50) / 중(30~49) / 저(<30)
    out = defaultdict(lambda: {"immediate": [], "pull3": [], "pull5": [], "kijun": []})
    for i in range(60, len(df) - hold - 6, step):
        score = _global_momentum_score(df, i)
        tier = "high" if score >= 50 else ("mid" if score >= 30 else "low")
        row = df.iloc[i]
        base = float(row["close"])
        exit_idx = i + hold
        if exit_idx >= len(df):
            continue
        exit_price = float(df.iloc[exit_idx]["close"])
        imm = (exit_price / base - 1) * 100
        out[tier]["immediate"].append(imm)
        # 눌림 -3/-5%
        future5 = df.iloc[i + 1:i + 6]
        for tag, mult in [("pull3", 0.97), ("pull5", 0.95)]:
            target = base * mult
            offs = next((j for j, (_, r) in enumerate(future5.iterrows()) if float(r["low"]) <= target), None)
            if offs is not None:
                ex = i + 1 + offs + hold
                if ex < len(df):
                    out[tier][tag].append((float(df.iloc[ex]["close"]) / target - 1) * 100)
        # 기준선 ±2%
        kijun = row.get("kijun")
        if kijun == kijun and kijun > 0 and abs(base / kijun - 1) <= 0.02:
            out[tier]["kijun"].append(imm)
    return out


def _stats(rets):
    rets = [r for r in rets if r is not None]
    n = len(rets)
    if n == 0:
        return "표본 0"
    win = sum(1 for r in rets if r > 0) / n * 100
    avg = sum(rets) / n
    return f"표본 {n:>4} · 승률 {win:>5.1f}% · 평균 {avg:>+6.2f}%"


if __name__ == "__main__":
    codes = sys.argv[1:] or [
        "005930", "000660", "042700", "218410", "034730", "196170", "042660",
        "329180", "222800", "095340", "005380", "066570", "035420", "000270",
        "105560", "207940", "247540", "086520", "042000", "277810", "348340",
        "240810", "138040", "012450", "010140", "028260", "005490", "011200",
    ]
    print(f"추천(고점수) 진입 재검증 — {len(codes)}종목, 보유 10봉\n")
    agg = defaultdict(lambda: defaultdict(list))
    for code in codes:
        try:
            r = analyze_code(code)
            if not r:
                continue
            for tier, methods in r.items():
                for m, lst in methods.items():
                    agg[tier][m].extend(lst)
        except Exception as e:
            print(f"[ERR] {code}: {e}")

    tier_label = {"high": "🔥 고점수(≥50)", "mid": "➖ 중점수(30~49)", "low": "❄ 저점수(<30)"}
    for tier in ["high", "mid", "low"]:
        print("=" * 72)
        print(f"{tier_label[tier]} 종목")
        print("-" * 72)
        for m, label in [("immediate", "즉시 매수"), ("pull3", "-3% 눌림"),
                          ("pull5", "-5% 눌림"), ("kijun", "기준선 ±2%")]:
            print(f"  {label:<14} {_stats(agg[tier][m])}")
