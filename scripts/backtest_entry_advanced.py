"""진입 전략 심화 백테스트 — 검토용 (적용 X).

3가지 분석 동시:
  [1] 신호등 — 기준선(Kijun) 대비 현재가 위치 구간별 즉시매수 10봉 성과
       🟢 ±2% (눌림완료) / 🟡 +2~7% / 🔴 +7%↑(과열) / 🔵 기준선 아래
  [2] 분할매수 — 1차40%(즉시) + 2차30%(-3%) + 3차30%(-5%) 평단/수익 vs 즉시100%
  [3] 추세 proxy 점수 — (구름위 + 정배열 + RSI구간)별 즉시매수 성과
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


def analyze_code(code: str, lookback_days: int = 360, hold: int = 10, step: int = 2):
    import technical
    from chart_ichimoku import compute_ichimoku
    df = technical.fetch_ohlcv(code, days=lookback_days)
    df = technical.add_indicators(df)
    df = compute_ichimoku(df)
    if len(df) < 80:
        return None

    res = {
        "signal": defaultdict(list),   # 신호등 구간 → 수익률
        "split": [],                   # (분할 수익, 즉시 수익)
        "trend": defaultdict(list),    # 추세점수 → 수익률
    }
    for i in range(60, len(df) - hold - 6, step):
        row = df.iloc[i]
        base = float(row["close"])
        exit_idx = i + hold
        if exit_idx >= len(df):
            continue
        exit_price = float(df.iloc[exit_idx]["close"])
        immediate_ret = (exit_price / base - 1) * 100

        kijun = float(row["kijun"]) if row.get("kijun") == row.get("kijun") else None
        # ── [1] 신호등 (기준선 대비) ──
        if kijun and kijun > 0:
            gap = (base / kijun - 1) * 100
            if gap < -2:
                zone = "🔵 기준선아래"
            elif gap <= 2:
                zone = "🟢 ±2%(눌림완료)"
            elif gap <= 7:
                zone = "🟡 +2~7%"
            else:
                zone = "🔴 +7%↑(과열)"
            res["signal"][zone].append(immediate_ret)

        # ── [2] 분할매수 ──
        future5 = df.iloc[i + 1:i + 6]
        b_target, c_target = base * 0.97, base * 0.95
        b_fill = any(float(r["low"]) <= b_target for _, r in future5.iterrows())
        c_fill = any(float(r["low"]) <= c_target for _, r in future5.iterrows())
        # 분할 평단: 1차 즉시(40%) 항상 + 2차 -3%(30%) 체결시 + 3차 -5%(30%) 체결시
        w_sum, cost = 0.40, 0.40 * base
        if b_fill:
            w_sum += 0.30; cost += 0.30 * b_target
        if c_fill:
            w_sum += 0.30; cost += 0.30 * c_target
        avg_cost = cost / w_sum
        split_ret = (exit_price / avg_cost - 1) * 100
        res["split"].append((split_ret, immediate_ret))

        # ── [3] 추세 proxy 점수 ──
        score = 0
        sa = row.get("senkou_a"); sb = row.get("senkou_b")
        if sa == sa and sb == sb:
            top = max(sa, sb)
            if base > top:
                score += 1  # 구름 위
        # 정배열 (5>20>60)
        if all(c in df.columns for c in ["sma_5", "sma_20", "sma_60"]):
            if row["sma_5"] > row["sma_20"] > row["sma_60"]:
                score += 1
        # RSI 50~70 (강세 비과열)
        rsi = row.get("rsi_14")
        if rsi == rsi and 50 <= rsi <= 70:
            score += 1
        res["trend"][score].append(immediate_ret)

    return res


def _stats(rets):
    rets = [r for r in rets if r is not None]
    n = len(rets)
    if n == 0:
        return None
    win = sum(1 for r in rets if r > 0) / n * 100
    avg = sum(rets) / n
    med = sorted(rets)[n // 2]
    return n, win, avg, med


if __name__ == "__main__":
    codes = sys.argv[1:] or [
        "005930", "000660", "042700", "218410", "034730", "196170", "042660",
        "329180", "222800", "095340", "005380", "066570", "035420", "000270",
        "105560", "207940", "247540", "086520", "042000", "277810", "348340",
        "240810", "138040", "012450", "010140",
    ]
    print(f"진입 심화 백테스트 — {len(codes)}종목, 보유 10봉\n")
    sig = defaultdict(list)
    split_pairs = []
    trend = defaultdict(list)
    for code in codes:
        try:
            r = analyze_code(code)
            if not r:
                continue
            for z, lst in r["signal"].items():
                sig[z].extend(lst)
            split_pairs.extend(r["split"])
            for s, lst in r["trend"].items():
                trend[s].extend(lst)
        except Exception as e:
            print(f"[ERR] {code}: {e}")

    print("=" * 72)
    print("[1] 신호등 — 기준선 대비 현재가 위치별 즉시매수 10봉 성과")
    print("-" * 72)
    for z in ["🟢 ±2%(눌림완료)", "🟡 +2~7%", "🔴 +7%↑(과열)", "🔵 기준선아래"]:
        s = _stats(sig.get(z, []))
        if s:
            print(f"  {z:<18} 표본 {s[0]:>4} · 승률 {s[1]:>5.1f}% · 평균 {s[2]:>+6.2f}% · 중앙 {s[3]:>+6.2f}%")

    print("\n" + "=" * 72)
    print("[2] 분할매수(1차40%즉시+2차30%-3%+3차30%-5%) vs 즉시100%")
    print("-" * 72)
    split_rets = [p[0] for p in split_pairs]
    imm_rets = [p[1] for p in split_pairs]
    for label, rets in [("분할매수", split_rets), ("즉시 100%", imm_rets)]:
        s = _stats(rets)
        if s:
            print(f"  {label:<12} 표본 {s[0]:>4} · 승률 {s[1]:>5.1f}% · 평균 {s[2]:>+6.2f}% · 중앙 {s[3]:>+6.2f}%")

    print("\n" + "=" * 72)
    print("[3] 추세 proxy 점수(구름위+정배열+RSI50~70, 0~3점)별 즉시매수")
    print("-" * 72)
    for s_val in [3, 2, 1, 0]:
        s = _stats(trend.get(s_val, []))
        if s:
            print(f"  {s_val}점 표본 {s[0]:>4} · 승률 {s[1]:>5.1f}% · 평균 {s[2]:>+6.2f}% · 중앙 {s[3]:>+6.2f}%")
