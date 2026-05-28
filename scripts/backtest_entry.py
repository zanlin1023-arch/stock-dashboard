"""진입 전략 백테스트 — 검토용 (적용 X).

추천 종목을 '언제 진입'하는 게 최적인지 비교:
  A) 즉시 매수      — 추천 시점 종가
  B) 눌림목 -3%     — 이후 5봉 내 -3% 닿으면 지정가 매수 (안 닿으면 미진입)
  C) 눌림목 -5%     — 이후 5봉 내 -5% 닿으면 매수
  D) 기준선 지지    — 현재가가 기준선 +2% 이내(눌림 완료)일 때만 즉시 매수

각 방식 → 진입 후 10봉 보유 수익률 + 승률 비교.
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))


def backtest_entry(code: str, lookback_days: int = 360, hold: int = 10, step: int = 3) -> list[dict]:
    import technical
    from chart_ichimoku import compute_ichimoku
    df = technical.fetch_ohlcv(code, days=lookback_days)
    df = technical.add_indicators(df)
    df = compute_ichimoku(df)
    if len(df) < 80:
        return []

    out = []
    for i in range(60, len(df) - hold - 5, step):
        entry_day = df.iloc[i]
        base_price = float(entry_day["close"])
        kijun = float(entry_day["kijun"]) if "kijun" in df.columns and entry_day["kijun"] == entry_day["kijun"] else None
        # 향후 5봉 (눌림목 체결 판정), 진입 후 hold봉 종가
        future5 = df.iloc[i + 1:i + 6]
        # A) 즉시
        a_entry = base_price
        a_exit_idx = i + hold
        a_ret = (float(df.iloc[a_exit_idx]["close"]) / a_entry - 1) * 100 if a_exit_idx < len(df) else None
        # B) -3% 지정가 (5봉 내 저가가 닿으면 체결)
        b_target = base_price * 0.97
        b_filled = any(float(r["low"]) <= b_target for _, r in future5.iterrows())
        b_ret = None
        if b_filled:
            # 체결 시점 = 처음 닿은 봉. 그 후 hold봉
            fill_offset = next((j for j, (_, r) in enumerate(future5.iterrows()) if float(r["low"]) <= b_target), None)
            exit_idx = i + 1 + fill_offset + hold
            if exit_idx < len(df):
                b_ret = (float(df.iloc[exit_idx]["close"]) / b_target - 1) * 100
        # C) -5%
        c_target = base_price * 0.95
        c_filled = any(float(r["low"]) <= c_target for _, r in future5.iterrows())
        c_ret = None
        if c_filled:
            fill_offset = next((j for j, (_, r) in enumerate(future5.iterrows()) if float(r["low"]) <= c_target), None)
            exit_idx = i + 1 + fill_offset + hold
            if exit_idx < len(df):
                c_ret = (float(df.iloc[exit_idx]["close"]) / c_target - 1) * 100
        # D) 기준선 지지 (현재가가 기준선 +2% 이내 = 눌림 완료 후 지지)
        d_ret = None
        if kijun and kijun > 0 and base_price <= kijun * 1.02 and base_price >= kijun * 0.98:
            d_exit_idx = i + hold
            if d_exit_idx < len(df):
                d_ret = (float(df.iloc[d_exit_idx]["close"]) / base_price - 1) * 100

        out.append({"a": a_ret, "b": b_ret, "c": c_ret, "d": d_ret, "b_filled": b_filled, "c_filled": c_filled})
    return out


def summarize(label: str, rets: list[float]):
    rets = [r for r in rets if r is not None]
    n = len(rets)
    if n == 0:
        print(f"  {label:<22} 표본 0")
        return
    win = sum(1 for r in rets if r > 0) / n * 100
    avg = sum(rets) / n
    med = sorted(rets)[n // 2]
    print(f"  {label:<22} 표본 {n:>4} · 승률 {win:>5.1f}% · 평균 {avg:>+6.2f}% · 중앙값 {med:>+6.2f}%")


if __name__ == "__main__":
    codes = sys.argv[1:] or ["005930", "000660", "042700", "218410", "034730", "196170", "042660", "329180"]
    print(f"진입 전략 백테스트 — {len(codes)}종목, 보유 10봉\n")
    allr = {"a": [], "b": [], "c": [], "d": []}
    fill_b = fill_c = total = 0
    for code in codes:
        try:
            rows = backtest_entry(code)
            for r in rows:
                for k in ("a", "b", "c", "d"):
                    if r[k] is not None:
                        allr[k].append(r[k])
                total += 1
                fill_b += 1 if r["b_filled"] else 0
                fill_c += 1 if r["c_filled"] else 0
        except Exception as e:
            print(f"[ERR] {code}: {e}")
    print("=" * 70)
    summarize("A) 즉시 매수", allr["a"])
    summarize("B) -3% 눌림목 지정가", allr["b"])
    summarize("C) -5% 눌림목 지정가", allr["c"])
    summarize("D) 기준선 지지 진입", allr["d"])
    print("=" * 70)
    if total:
        print(f"체결률: B(-3%) {fill_b/total*100:.0f}% · C(-5%) {fill_c/total*100:.0f}%  (미체결 = 기회 놓침)")
