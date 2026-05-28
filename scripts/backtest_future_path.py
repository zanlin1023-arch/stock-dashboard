"""project_future_path 백테스팅 — 과거 데이터로 1차/2차/3차 예측 vs 실제 비교.

방법:
1. 과거 lookback_days 기간의 OHLCV 데이터 수집
2. 5일 간격으로 각 시점에서 project_future_path() 실행
3. 그 시점부터 9/17/26봉(또는 매핑된 cycle) 후 실제 가격과 비교
4. 적중률 (예측 가격에 high가 도달했는지) + 평균 오차

사용:
    py scripts/backtest_future_path.py 005930              # 단일 종목
    py scripts/backtest_future_path.py 005930 042700 218410  # 여러 종목
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))


def backtest_code(code: str, lookback_days: int = 360, step: int = 5) -> dict:
    """단일 종목 백테스팅."""
    import technical
    from chart_ichimoku import (
        compute_ichimoku, detect_swing_points, compute_price_targets,
        compute_time_cycles, make_decision, project_future_path,
    )
    df = technical.fetch_ohlcv(code, days=lookback_days)
    df = technical.add_indicators(df)
    df = compute_ichimoku(df)

    results = []
    min_idx = 80  # 최소 80봉 필요 (swing/일목/ATR 안정)
    max_test_idx = len(df) - 30  # 미래 30봉 여유

    for end_idx in range(min_idx, max_test_idx, step):
        past_df = df.iloc[:end_idx]
        try:
            swings = detect_swing_points(past_df, lookback=min(80, len(past_df)))
            A = swings["A"]["price"]
            B = swings["B"]["price"]
            C = swings["C"]["price"]
            targets = compute_price_targets(A, B, C)
            current = float(past_df.iloc[-1]["close"])
            atr = float(past_df["atr_14"].iloc[-1]) if "atr_14" in past_df.columns else None
            cycles = compute_time_cycles(swings["C"]["idx"], len(past_df))
            decision = make_decision(past_df, swings, targets)
            path = project_future_path(
                current, cycles, targets, decision.get("stop"),
                swings=swings, atr_value=atr,
            )
            if not path:
                continue
        except Exception:
            continue

        for p in path:
            offset = p["target_idx"] - (end_idx - 1)
            actual_idx = end_idx + offset - 1
            if actual_idx >= len(df) or actual_idx < 0:
                continue
            # cycle 시점 ± 2봉 윈도우로 실제 최고/최저 (정확히 도달 시점 측정)
            win_lo = max(end_idx, actual_idx - 2)
            win_hi = min(len(df) - 1, actual_idx + 2)
            window = df.iloc[win_lo:win_hi + 1]
            actual_high = float(window["high"].max())
            actual_low = float(window["low"].min())
            actual_close = float(df.iloc[actual_idx]["close"])
            predicted = p["price"]
            is_peak = p.get("is_peak", True)
            # 도달 여부: 피크는 high가 predicted 넘으면 도달, 조정은 low가 predicted 닿으면 도달
            if is_peak:
                reached = actual_high >= predicted
                # 도달 시 오버슛/언더슛 %
                err = (actual_high - predicted) / predicted * 100
            else:
                reached = actual_low <= predicted
                err = (actual_low - predicted) / predicted * 100
            close_err = (actual_close - predicted) / predicted * 100
            results.append({
                "end_date": past_df.index[-1].strftime("%Y-%m-%d"),
                "label": p["label"],
                "cycle": p["cycle"],
                "is_peak": is_peak,
                "current": current,
                "predicted": predicted,
                "predicted_pct": (predicted / current - 1) * 100,
                "actual_high": actual_high,
                "actual_low": actual_low,
                "actual_close": actual_close,
                "reached": reached,
                "extreme_err_pct": err,         # high/low 기준 오차
                "close_err_pct": close_err,     # close 기준 오차
            })

    # 통계 — 라벨/cycle별 그룹
    from collections import defaultdict
    groups = defaultdict(list)
    for r in results:
        key = f"{r['cycle']}봉 ({'피크' if r['is_peak'] else '조정'})"
        groups[key].append(r)

    summary = {}
    for key, items in groups.items():
        n = len(items)
        if n == 0:
            continue
        reached_n = sum(1 for r in items if r["reached"])
        close_errs = [r["close_err_pct"] for r in items]
        avg_close_err = sum(close_errs) / n
        median_close_err = sorted(close_errs)[n // 2]
        summary[key] = {
            "n": n,
            "reached_rate": reached_n / n * 100,
            "avg_close_err_pct": avg_close_err,
            "median_close_err_pct": median_close_err,
        }

    return {"code": code, "n_total": len(results), "summary": summary, "raw": results}


def print_summary(code: str, result: dict):
    name = result["code"]
    n = result["n_total"]
    print(f"\n{'=' * 70}")
    print(f"📊 {name} 백테스트 — 총 {n}개 예측 검증")
    print(f"{'=' * 70}")
    print(f"{'시점':<20s} {'표본':>5s} {'적중률':>8s} {'평균 오차':>10s} {'중앙값':>10s}")
    print(f"{'-' * 70}")
    for key in sorted(result["summary"].keys(), key=lambda x: int(x.split("봉")[0])):
        s = result["summary"][key]
        print(
            f"{key:<20s} {s['n']:>5d} {s['reached_rate']:>7.1f}% "
            f"{s['avg_close_err_pct']:>+9.2f}% {s['median_close_err_pct']:>+9.2f}%"
        )
    print(f"\n💡 적중률 = 예측 가격에 high/low가 닿은 비율")
    print(f"💡 오차 % = (실제 close - 예측) / 예측 — 음수면 예측이 더 높음 (과대 예측)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        # 기본: 보유 종목 일부
        args = ["005930", "000660", "042700", "218410"]
    print(f"백테스트 대상: {args}")
    all_results = []
    for code in args:
        try:
            r = backtest_code(code, lookback_days=360, step=5)
            print_summary(code, r)
            all_results.append(r)
        except Exception as e:
            print(f"[ERROR] {code}: {e}")
    # 전체 종목 합산 통계
    if len(all_results) > 1:
        print(f"\n{'=' * 70}")
        print(f"🎯 전체 합산 — {len(all_results)}개 종목")
        print(f"{'=' * 70}")
        from collections import defaultdict
        combined = defaultdict(list)
        for r in all_results:
            for raw in r["raw"]:
                key = f"{raw['cycle']}봉 ({'피크' if raw['is_peak'] else '조정'})"
                combined[key].append(raw)
        print(f"{'시점':<20s} {'표본':>5s} {'적중률':>8s} {'평균 오차':>10s} {'중앙값':>10s}")
        print(f"{'-' * 70}")
        for key in sorted(combined.keys(), key=lambda x: int(x.split("봉")[0])):
            items = combined[key]
            n = len(items)
            reached_rate = sum(1 for r in items if r["reached"]) / n * 100
            errs = [r["close_err_pct"] for r in items]
            print(
                f"{key:<20s} {n:>5d} {reached_rate:>7.1f}% "
                f"{sum(errs)/n:>+9.2f}% {sorted(errs)[n//2]:>+9.2f}%"
            )
