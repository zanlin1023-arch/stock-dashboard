"""모멘텀 매수/매도 시그널 감지 — 시장 조사 검증된 룰 기반.

# 🌐 글로벌 검증 룰 (어느 시장에도 적용)
─────────────────────────────────────────────
[매수 시그널]
1. 20일 신고가 + 거래량 폭증
   - Schwab: https://www.schwab.com/learn/story/3-strength-indicators-assessing-stock-momentum
   - TradingView: https://www.tradingview.com/scripts/volumebreakout/
2. 거래량 폭증 (평소 3배+) — TradingView, FortexTester
3. RSI(14) > 50 (모멘텀 게이팅)
   - FortexTester: https://forextester.com/blog/momentum-trading-strategies/
4. MACD 골든크로스
   - TradingView: https://www.tradingview.com/scripts/macd/

[매도 시그널]
1. MACD 데드크로스
   - StockGro: https://www.stockgro.club/blogs/trading/macd-trading-strategy/
   - OANDA: https://www.oanda.com/us-en/learn/indicators-oscillators/determining-entry-and-exit-points-with-macd/
2. 20일 EMA 하향 이탈 — StockGro, OANDA
3. RSI 60+ 후 50 이탈 — FortexTester
4. RSI 다이버전스 (가격↑ RSI↓)
   - Schwab: https://www.schwab.com/learn/story/identifying-trend-reversals-with-rsi
5. 상승일 거래량 감소 — TradingSim, Altrady
6. ATR 트레일링 손절 (2~3×ATR)
   - Trade That Swing: https://tradethatswing.com/trend-trading-strategy-for-high-momentum-stocks-atr-based/

# 🇰🇷 한국 특화 룰 (한국 시장에서만)
─────────────────────────────────────────────
[매수/매도]
- 외인+기관 동반 매수/매도, 매수↔매도 전환
  - FnGuide: https://comp.fnguide.com/SVO/WooriRenewal/SupplyTrend.asp
  - 자체 일별 흐름 감지 (market_context.detect_flow_reversal)
- 3일 횡보 정리
  - 나무위키 단타매매: https://namu.wiki/w/%EC%A3%BC%EC%8B%9D%ED%88%AC%EC%9E%90/%EB%8B%A8%ED%83%80%EB%A7%A4%EB%A7%A4%20%EA%B8%B0%EB%B2%95

# 💰 손익비 표준
─────────────────────────────────────────────
- 단타: 손절 -2% / 익절 +4% (Risk:Reward 1:2) — 한국 실전 룰
- 스윙: 3×ATR 손절 / 한달 백테 중앙값 익절 (1:2~1:3)
- 업계 표준: 최소 1:1.5
"""
from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

import market_context as mc
from technical import add_indicators, fetch_ohlcv

warnings.filterwarnings("ignore")


def detect_buy_signals(code: str, name: str = "") -> dict:
    """모멘텀 매수 시그널 종합 평가 — 글로벌 + 한국 룰.

    각 시그널마다 출처(글로벌/한국) 명시.
    """
    df = fetch_ohlcv(code, days=120)
    df = add_indicators(df)

    if len(df) < 30:
        return {"available": False, "reason": "데이터 부족"}

    last = df.iloc[-1]
    prev_5 = df.tail(5)
    prev_20 = df.tail(20)

    signals = []  # [(category, name, score, reason)]
    score = 0

    # ────────────────────────────────
    # 🌐 글로벌 검증 룰
    # ────────────────────────────────

    # G1. 20일 신고가 + 거래량 폭증 (가장 강력, +30) [Schwab, TradingView]
    high_20 = prev_20["close"].max()
    avg_vol_20 = df.tail(20)["volume"].iloc[:-1].mean()
    vol_ratio = last["volume"] / avg_vol_20 if avg_vol_20 > 0 else 0

    if last["close"] >= high_20 * 0.99:  # 20일 최고가 도달
        if vol_ratio >= 1.5:
            signals.append(("글로벌", "20일 신고가 + 거래량 폭증", +30,
                          f"신고가 {high_20:,.0f}원 도달 + 거래량 {vol_ratio:.1f}배"))
            score += 30
        else:
            signals.append(("글로벌", "20일 신고가 (거래량 부족)", +15,
                          f"신고가 도달 but 거래량 {vol_ratio:.1f}배"))
            score += 15
    else:
        # G2. 거래량 폭증 단독 (+20) [TradingView, FortexTester]
        if vol_ratio >= 3:
            signals.append(("글로벌", "거래량 폭증 (3배+)", +20, f"거래량 {vol_ratio:.1f}배"))
            score += 20
        elif vol_ratio >= 1.5:
            signals.append(("글로벌", "거래량 증가", +10, f"거래량 {vol_ratio:.1f}배"))
            score += 10

    # G3. RSI(14) > 50 모멘텀 게이팅 [FortexTester]
    rsi = last.get("rsi_14")
    if rsi is not None and pd.notna(rsi):
        if rsi > 60:
            signals.append(("글로벌", "RSI 강세 (>60)", +20, f"RSI {rsi:.1f}"))
            score += 20
        elif rsi > 50:
            signals.append(("글로벌", "RSI 양호 (>50)", +15, f"RSI {rsi:.1f}"))
            score += 15
        elif rsi < 30:
            signals.append(("글로벌", "RSI 과매도 (반등 가능)", +10, f"RSI {rsi:.1f}"))
            score += 10

    # G4. MACD 골든크로스 [TradingView, StockGro]
    if "macd" in df.columns and "macd_signal" in df.columns:
        macd_now = df.iloc[-1]["macd"]
        signal_now = df.iloc[-1]["macd_signal"]
        macd_prev = df.iloc[-2]["macd"] if len(df) >= 2 else macd_now
        signal_prev = df.iloc[-2]["macd_signal"] if len(df) >= 2 else signal_now
        if pd.notna(macd_now) and pd.notna(signal_now):
            if macd_now > signal_now and macd_prev <= signal_prev:
                signals.append(("글로벌", "MACD 골든크로스", +15, "당일 발생"))
                score += 15
            elif macd_now > signal_now:
                signals.append(("글로벌", "MACD 상승 추세", +5, "골든 유지"))
                score += 5

    # G5. 정배열 형성 (단기/중기/장기) [Schwab, TradingView]
    sma5 = last.get("sma_5")
    sma20 = last.get("sma_20")
    sma60 = last.get("sma_60")
    if all(pd.notna(x) for x in [sma5, sma20, sma60]):
        if sma5 > sma20 > sma60:
            signals.append(("글로벌", "정배열 (5>20>60)", +15, "상승 추세 형성"))
            score += 15

    # ────────────────────────────────
    # 🇰🇷 한국 특화 룰
    # ────────────────────────────────

    # K1. 외인+기관 동반 매수 (가장 강력, +30) [FnGuide, 자체]
    try:
        reversal = mc.detect_flow_reversal(code, lookback=7)
        if reversal.get("available"):
            verdict = reversal["verdict"]
            if "동반 매수" in verdict:
                signals.append(("한국", "외인+기관 동반 매수", +30, verdict))
                score += 30
            elif "매수 전환" in verdict:
                signals.append(("한국", "외국인 매수 전환", +20, verdict))
                score += 20
    except Exception:
        pass

    # K2. 외국인 연속 매수 5일+ (강한 매집 시그널) [한국 단타 실전]
    try:
        daily = mc.get_daily_flow(code, days=10)
        if daily:
            streak = 0
            for r in daily:
                if r.get("foreign_net", 0) > 0:
                    streak += 1
                else:
                    break
            if streak >= 5:
                signals.append(("한국", f"외국인 {streak}일 연속 매수", +20, "강한 매집 패턴"))
                score += 20
            elif streak >= 3:
                signals.append(("한국", f"외국인 {streak}일 연속 매수", +10, "매집 진행 중"))
                score += 10
    except Exception:
        pass

    # K3. 60일 신고가 빈도 (강한 모멘텀) [한국 실전]
    if len(df) >= 60:
        recent_60 = df.tail(60)
        rolling_max = recent_60["close"].cummax()
        new_highs = (recent_60["close"] == rolling_max).sum()
        if new_highs >= 15:
            signals.append(("한국", "60일 신고가 매우 강함", +15, f"{new_highs}회 갱신"))
            score += 15
        elif new_highs >= 10:
            signals.append(("한국", "60일 신고가 빈도 높음", +10, f"{new_highs}회 갱신"))
            score += 10
        elif new_highs >= 5:
            signals.append(("한국", "60일 신고가 양호", +5, f"{new_highs}회"))
            score += 5

    # K4. ADX 강한 추세 (한국 단타 활용 지표)
    try:
        from momentum import calc_adx
        adx = calc_adx(df)
        if adx is not None:
            if adx >= 40:
                signals.append(("한국", f"ADX 매우 강한 추세 ({adx:.1f})", +15, "단기 모멘텀 강력"))
                score += 15
            elif adx >= 25:
                signals.append(("한국", f"ADX 강한 추세 ({adx:.1f})", +10, "추세 형성"))
                score += 10
    except Exception:
        pass

    # K5. 단기 강한 상승 (5일 +5% 이상) [한국 모멘텀]
    five_day_return = (last["close"] / prev_5.iloc[0]["close"] - 1) * 100
    if five_day_return > 10:
        signals.append(("한국", "5일 폭등 (+10%↑)", +15, f"{five_day_return:+.1f}%"))
        score += 15
    elif five_day_return > 5:
        signals.append(("한국", "5일 강한 상승", +10, f"{five_day_return:+.1f}%"))
        score += 10
    elif five_day_return > 2:
        signals.append(("한국", "5일 양호 상승", +5, f"{five_day_return:+.1f}%"))
        score += 5

    # K6. 거래량 동행성 (한국 단타 — 매수일 거래량이 매도일보다 많음)
    if len(df) >= 20:
        recent_20 = df.tail(20).copy()
        recent_20["diff"] = recent_20["close"].diff()
        up_vol = recent_20.loc[recent_20["diff"] > 0, "volume"].sum()
        down_vol = recent_20.loc[recent_20["diff"] < 0, "volume"].sum()
        if down_vol > 0:
            vc_ratio = up_vol / down_vol
            if vc_ratio >= 3:
                signals.append(("한국", "거래량 동행성 강함", +10, f"상승일/하락일 {vc_ratio:.1f}배"))
                score += 10
            elif vc_ratio >= 1.5:
                signals.append(("한국", "거래량 동행성 양호", +5, f"비율 {vc_ratio:.1f}"))
                score += 5

    # 종합 등급
    if score >= 80:
        grade = "🟢🟢🟢 매우 강력한 매수 시그널"
    elif score >= 50:
        grade = "🟢 강한 매수 시그널"
    elif score >= 30:
        grade = "🟡 약한 매수 시그널"
    else:
        grade = "⚪ 매수 시그널 부족"

    return {
        "available": True,
        "score": score,
        "grade": grade,
        "signals": signals,
        "current_price": float(last["close"]),
        "rsi": float(rsi) if rsi is not None and pd.notna(rsi) else None,
    }


def detect_sell_signals(code: str, name: str = "") -> dict:
    """모멘텀 매도 시그널 종합 평가."""
    df = fetch_ohlcv(code, days=120)
    df = add_indicators(df)

    if len(df) < 30:
        return {"available": False, "reason": "데이터 부족"}

    last = df.iloc[-1]
    signals = []
    score = 0

    # 🌐 G1. 20일 EMA 하향 이탈 (가장 명확) [StockGro, OANDA]
    sma20 = last.get("sma_20")
    if sma20 is not None and pd.notna(sma20):
        if last["close"] < sma20:
            prev_close = df.iloc[-2]["close"] if len(df) >= 2 else last["close"]
            prev_sma = df.iloc[-2]["sma_20"] if len(df) >= 2 else sma20
            if prev_close >= prev_sma:
                signals.append(("글로벌", "20일선 하향 이탈", -30, f"종가 {last['close']:,.0f} < SMA20 {sma20:,.0f}"))
                score -= 30
            else:
                signals.append(("글로벌", "20일선 아래 지속", -15, f"종가 < SMA20"))
                score -= 15

    # 🌐 G2. MACD 데드크로스 [TradingView, StockGro]
    if "macd" in df.columns and "macd_signal" in df.columns:
        macd_now = df.iloc[-1]["macd"]
        signal_now = df.iloc[-1]["macd_signal"]
        macd_prev = df.iloc[-2]["macd"] if len(df) >= 2 else macd_now
        signal_prev = df.iloc[-2]["macd_signal"] if len(df) >= 2 else signal_now
        if pd.notna(macd_now) and pd.notna(signal_now):
            if macd_now < signal_now and macd_prev >= signal_prev:
                signals.append(("글로벌", "MACD 데드크로스", -25, "당일 발생"))
                score -= 25

    # 🌐 G3. RSI 50 이탈 (60+ 유지 후) [FortexTester]
    rsi = last.get("rsi_14")
    if rsi is not None and pd.notna(rsi):
        recent_rsi = df.tail(10)["rsi_14"].dropna()
        if len(recent_rsi) >= 3:
            max_recent = recent_rsi.max()
            if max_recent > 60 and rsi < 50:
                signals.append(("글로벌", "RSI 60+ 후 50 이탈", -20, f"최근 최고 {max_recent:.1f} → 현재 {rsi:.1f}"))
                score -= 20
            elif rsi < 40:
                signals.append(("글로벌", "RSI 약세 (<40)", -10, f"RSI {rsi:.1f}"))
                score -= 10

    # 🌐 G4. RSI 다이버전스 [Schwab — Identifying Trend Reversals With RSI]
    if rsi is not None and pd.notna(rsi) and len(df) >= 20:
        recent_20 = df.tail(20)
        half = len(recent_20) // 2
        early = recent_20.iloc[:half]
        late = recent_20.iloc[half:]
        if late["close"].max() > early["close"].max() * 1.01:
            if late["rsi_14"].max() < early["rsi_14"].max() - 3:
                signals.append(("글로벌", "RSI 다이버전스 (정점)", -25, "가격↑ RSI↓"))
                score -= 25

    # 🌐 G5. 상승일 거래량 감소 (모멘텀 약화) [TradingSim, Altrady]
    if len(df) >= 10:
        recent_10 = df.tail(10).copy()
        recent_10["price_chg"] = recent_10["close"].diff()
        up_days = recent_10[recent_10["price_chg"] > 0]
        if len(up_days) >= 3:
            up_vol_mean = up_days["volume"].mean()
            total_vol_mean = recent_10["volume"].mean()
            if up_vol_mean < total_vol_mean * 0.8:
                signals.append(("글로벌", "상승일 거래량 약함", -15, "모멘텀 약화"))
                score -= 15

    # 🇰🇷 K1. 외인/기관 매도 전환 [FnGuide]
    try:
        reversal = mc.detect_flow_reversal(code, lookback=7)
        if reversal.get("available"):
            verdict = reversal["verdict"]
            if "동반 매도" in verdict:
                signals.append(("한국", "외인+기관 동반 매도", -30, verdict))
                score -= 30
            elif "매도 전환" in verdict:
                signals.append(("한국", "외국인 매도 전환", -25, verdict))
                score -= 25
    except Exception:
        pass

    # 🇰🇷 K2. 3일 횡보 정리 [나무위키 단타매매]
    last_3 = df.tail(3)["close"]
    if len(last_3) == 3:
        range_pct = (last_3.max() / last_3.min() - 1) * 100
        if range_pct < 2:
            signals.append(("한국", "3일 횡보 (정체)", -10, f"변동폭 {range_pct:.1f}%"))
            score -= 10

    # 🇰🇷 K3. 역배열 (5<20<60) [한국 단타 실전]
    sma5 = last.get("sma_5")
    sma60 = last.get("sma_60")
    if all(pd.notna(x) for x in [sma5, sma20, sma60]):
        if sma5 < sma20 < sma60:
            signals.append(("한국", "역배열 (5<20<60)", -20, "하락 추세 형성"))
            score -= 20

    # 종합 등급
    if score <= -60:
        grade = "🔴🔴🔴 즉시 매도 시그널"
    elif score <= -30:
        grade = "🔴 매도 시그널"
    elif score <= -15:
        grade = "🟡 약한 매도 시그널"
    else:
        grade = "⚪ 매도 시그널 부족"

    return {
        "available": True,
        "score": score,
        "grade": grade,
        "signals": signals,
        "current_price": float(last["close"]),
    }


def detect_signals(code: str, name: str = "") -> dict:
    """매수/매도 시그널 종합."""
    buy = detect_buy_signals(code, name)
    sell = detect_sell_signals(code, name)

    # 종합 판단
    if not buy.get("available") or not sell.get("available"):
        return {"available": False, "reason": "데이터 부족"}

    net_score = buy["score"] + sell["score"]
    if net_score >= 50:
        verdict = "🟢 강한 매수 우세"
    elif net_score >= 20:
        verdict = "🟡 매수 우세 (신중)"
    elif net_score >= -20:
        verdict = "⚪ 중립"
    elif net_score >= -50:
        verdict = "🟠 매도 우세"
    else:
        verdict = "🔴 강한 매도 우세"

    return {
        "available": True,
        "buy": buy,
        "sell": sell,
        "net_score": net_score,
        "verdict": verdict,
    }


def to_markdown(result: dict, code: str = "", name: str = "") -> str:
    if not result.get("available"):
        return f"_시그널 분석 불가: {result.get('reason', '?')}_"

    buy = result.get("buy", {})
    sell = result.get("sell", {})

    lines = [
        f"## 🎯 모멘텀 매수/매도 시그널 — {name} ({code})",
        "",
        f"### 종합: {result['verdict']} (Net 점수 {result['net_score']:+d})",
        f"_매수 점수: **{buy.get('score', 0):+d}** / 매도 점수: **{sell.get('score', 0):+d}**_",
        "",
    ]

    # 매수 시그널 (글로벌/한국 분류)
    lines += [
        f"### 🟢 매수 시그널 — {buy.get('grade', '')}",
        "",
        "| 분류 | 시그널 | 점수 | 상세 |",
        "|------|--------|------|------|",
    ]
    buy_signals = buy.get("signals", [])
    # 글로벌 먼저, 한국 나중에 정렬
    global_signals = [s for s in buy_signals if (len(s) >= 4 and s[0] == "글로벌")]
    korea_signals = [s for s in buy_signals if (len(s) >= 4 and s[0] == "한국")]
    other_signals = [s for s in buy_signals if (len(s) < 4 or s[0] not in ["글로벌", "한국"])]

    for sig in global_signals:
        cat, nm, pts, reason = sig
        lines.append(f"| 🌐 {cat} | {nm} | {pts:+d} | {reason} |")
    for sig in korea_signals:
        cat, nm, pts, reason = sig
        lines.append(f"| 🇰🇷 {cat} | {nm} | {pts:+d} | {reason} |")
    for sig in other_signals:
        if len(sig) >= 3:
            nm, pts, reason = sig[-3], sig[-2], sig[-1]
            lines.append(f"| - | {nm} | {pts:+d} | {reason} |")
    if not buy_signals:
        lines.append("| - | (매수 시그널 없음) | - | - |")

    # 매도 시그널 (글로벌/한국 분류)
    lines += [
        "",
        f"### 🔴 매도 시그널 — {sell.get('grade', '')}",
        "",
        "| 분류 | 시그널 | 점수 | 상세 |",
        "|------|--------|------|------|",
    ]
    sell_signals = sell.get("signals", [])
    global_sell = [s for s in sell_signals if (len(s) >= 4 and s[0] == "글로벌")]
    korea_sell = [s for s in sell_signals if (len(s) >= 4 and s[0] == "한국")]
    other_sell = [s for s in sell_signals if (len(s) < 4 or s[0] not in ["글로벌", "한국"])]

    for sig in global_sell:
        cat, nm, pts, reason = sig
        lines.append(f"| 🌐 {cat} | {nm} | {pts:+d} | {reason} |")
    for sig in korea_sell:
        cat, nm, pts, reason = sig
        lines.append(f"| 🇰🇷 {cat} | {nm} | {pts:+d} | {reason} |")
    for sig in other_sell:
        if len(sig) >= 3:
            nm, pts, reason = sig[-3], sig[-2], sig[-1]
            lines.append(f"| - | {nm} | {pts:+d} | {reason} |")
    if not sell_signals:
        lines.append("| - | (매도 시그널 없음) | - | - |")

    lines += [
        "",
        "---",
        "> 📚 **글로벌 검증 룰**: Schwab + TradingView + OANDA + StockGro + FortexTester + Trade That Swing",
        "> 🇰🇷 **한국 특화 룰**: FnGuide (외인+기관 동반 순매수), 나무위키 (단타 매매)",
        "> 💰 **손익비**: 단타 1:2 (손절 -2%, 익절 +4%) / 스윙 1:2~1:3 (3×ATR 손절)",
        "> ⚠️ 매수+매도 시그널 동시 발생 시 신중 진입 + 빠른 익절",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from _utils import resolve_ticker

    q = sys.argv[1] if len(sys.argv) > 1 else "005930"
    code, name = resolve_ticker(q)
    r = detect_signals(code, name)
    print(to_markdown(r, code, name))
