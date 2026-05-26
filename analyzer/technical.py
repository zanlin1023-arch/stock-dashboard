"""기술적 분석: 이동평균, RSI, MACD, 볼린저밴드 + 시그널 감지."""
from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

from _utils import date_range, date_range_iso, fmt_num, fmt_pct

warnings.filterwarnings("ignore")


def fetch_ohlcv(code: str, days: int = 180) -> pd.DataFrame:
    """OHLCV 조회. FDR 우선, pykrx 폴백."""
    # FDR 우선 (가벼움, setuptools 의존성 없음)
    try:
        import FinanceDataReader as fdr
        start_iso, end_iso = date_range_iso(days)
        df = fdr.DataReader(code, start_iso, end_iso)
        if df is not None and not df.empty:
            df = df.rename(
                columns={
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume",
                }
            )
            keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            return df[keep]
    except Exception:
        pass

    # pykrx 폴백 (설치돼있을 때만)
    try:
        from pykrx import stock
        start, end = date_range(days)
        df = stock.get_market_ohlcv(start, end, code)
        if df is not None and not df.empty:
            return df.rename(
                columns={"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}
            )
    except Exception:
        pass

    raise ValueError(f"OHLCV 데이터 없음: {code}")


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # 이동평균
    for n in (5, 20, 60, 120):
        out[f"sma_{n}"] = out["close"].rolling(n).mean()

    # RSI(14)
    delta = out["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    out["rsi_14"] = 100 - 100 / (1 + rs)

    # MACD(12, 26, 9)
    ema12 = out["close"].ewm(span=12, adjust=False).mean()
    ema26 = out["close"].ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    # 볼린저 밴드(20, 2)
    sma20 = out["close"].rolling(20).mean()
    std20 = out["close"].rolling(20).std()
    out["bb_upper"] = sma20 + 2 * std20
    out["bb_lower"] = sma20 - 2 * std20

    # 일목균형표 (Ichimoku Kinko Hyo) — 9/26/52
    high, low, close = out["high"], out["low"], out["close"]
    out["tenkan"] = (high.rolling(9).max() + low.rolling(9).min()) / 2
    out["kijun"] = (high.rolling(26).max() + low.rolling(26).min()) / 2
    out["senkou_a"] = ((out["tenkan"] + out["kijun"]) / 2).shift(26)
    out["senkou_b"] = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    out["chikou"] = close.shift(-26)
    # 현시점 기준 구름대 (26일 전 계산값이 오늘에 도달)
    out["cloud_top"] = out[["senkou_a", "senkou_b"]].max(axis=1)
    out["cloud_bot"] = out[["senkou_a", "senkou_b"]].min(axis=1)

    return out


def detect_signals(df: pd.DataFrame) -> list[str]:
    sigs = []
    if len(df) < 2:
        sigs.append("⚠️ 시그널 판정 데이터 부족 (상장 초기 또는 거래정지 영향)")
        return sigs
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # 골든/데드 크로스 (5일선이 20일선을 돌파)
    if prev["sma_5"] <= prev["sma_20"] and last["sma_5"] > last["sma_20"]:
        sigs.append("✅ **골든크로스** (5일선이 20일선 상향 돌파)")
    if prev["sma_5"] >= prev["sma_20"] and last["sma_5"] < last["sma_20"]:
        sigs.append("⚠️ **데드크로스** (5일선이 20일선 하향 돌파)")

    # RSI 과매수/과매도
    if last["rsi_14"] >= 70:
        sigs.append(f"⚠️ **RSI 과매수** ({last['rsi_14']:.1f})")
    elif last["rsi_14"] <= 30:
        sigs.append(f"✅ **RSI 과매도** ({last['rsi_14']:.1f}) — 반등 가능")

    # MACD 시그널 교차
    if prev["macd"] <= prev["macd_signal"] and last["macd"] > last["macd_signal"]:
        sigs.append("✅ **MACD 골든크로스** (매수 시그널)")
    if prev["macd"] >= prev["macd_signal"] and last["macd"] < last["macd_signal"]:
        sigs.append("⚠️ **MACD 데드크로스** (매도 시그널)")

    # 볼린저 밴드 이탈
    if last["close"] > last["bb_upper"]:
        sigs.append("⚠️ **볼린저 상단 이탈** (과열 가능)")
    if last["close"] < last["bb_lower"]:
        sigs.append("✅ **볼린저 하단 이탈** (저점 가능)")

    # 추세
    if last["sma_5"] > last["sma_20"] > last["sma_60"]:
        sigs.append("📈 정배열 (단기>중기>장기) — 상승 추세")
    elif last["sma_5"] < last["sma_20"] < last["sma_60"]:
        sigs.append("📉 역배열 (단기<중기<장기) — 하락 추세")

    # 일목균형표
    if pd.notna(last.get("tenkan")) and pd.notna(last.get("kijun")):
        # TK 크로스
        if prev["tenkan"] <= prev["kijun"] and last["tenkan"] > last["kijun"]:
            sigs.append("✅ **일목 전환선↗기준선** (TK 골든크로스)")
        if prev["tenkan"] >= prev["kijun"] and last["tenkan"] < last["kijun"]:
            sigs.append("⚠️ **일목 전환선↘기준선** (TK 데드크로스)")

        # 구름대 위치
        if pd.notna(last.get("cloud_top")) and pd.notna(last.get("cloud_bot")):
            if last["close"] > last["cloud_top"]:
                cloud_pos = "above"
                sigs.append("📈 일목 **구름 위** (강세 영역)")
            elif last["close"] < last["cloud_bot"]:
                cloud_pos = "below"
                sigs.append("📉 일목 **구름 아래** (약세 영역)")
            else:
                cloud_pos = "inside"
                sigs.append("➖ 일목 구름 안 (방향 모호, 횡보)")

            # 구름 돌파
            if prev["close"] <= prev["cloud_top"] and last["close"] > last["cloud_top"]:
                sigs.append("✅ **일목 구름 상향 돌파** (강력 매수 시그널)")
            if prev["close"] >= prev["cloud_bot"] and last["close"] < last["cloud_bot"]:
                sigs.append("⚠️ **일목 구름 하향 이탈** (강력 매도 시그널)")

            # 후행스팬 확인 (26일 전 캔들 위/아래)
            chikou_ok = None
            if len(df) > 26:
                price_26d_ago = df["close"].iloc[-27]
                chikou_ok = last["close"] > price_26d_ago

            # 삼역호전/삼역역전
            tk_bull = last["tenkan"] > last["kijun"]
            if cloud_pos == "above" and tk_bull and chikou_ok is True:
                sigs.append("🔥 **일목 삼역호전(三役好転)** — 강력 매수 (구름위+TK골든+후행양호)")
            tk_bear = last["tenkan"] < last["kijun"]
            if cloud_pos == "below" and tk_bear and chikou_ok is False:
                sigs.append("🚨 **일목 삼역역전(三役逆転)** — 강력 매도 (구름아래+TK데드+후행약세)")

    if not sigs:
        sigs.append("➖ 특이 시그널 없음 — 횡보 추세")
    return sigs


def analyze(code: str, name: str) -> dict[str, Any]:
    df = fetch_ohlcv(code, days=180)
    df = add_indicators(df)
    last = df.iloc[-1]
    first = df.iloc[0]

    period_return = (last["close"] / first["close"] - 1) * 100
    daily_return = (last["close"] / df.iloc[-2]["close"] - 1) * 100 if len(df) > 1 else 0
    high_52w = df["close"].max()
    low_52w = df["close"].min()

    return {
        "code": code,
        "name": name,
        "current_price": int(last["close"]),
        "daily_return": daily_return,
        "period_return_180d": period_return,
        "high_180d": int(high_52w),
        "low_180d": int(low_52w),
        "volume": int(last["volume"]),
        "sma_5": float(last["sma_5"]) if pd.notna(last["sma_5"]) else None,
        "sma_20": float(last["sma_20"]) if pd.notna(last["sma_20"]) else None,
        "sma_60": float(last["sma_60"]) if pd.notna(last["sma_60"]) else None,
        "sma_120": float(last["sma_120"]) if pd.notna(last["sma_120"]) else None,
        "rsi_14": float(last["rsi_14"]) if pd.notna(last["rsi_14"]) else None,
        "macd": float(last["macd"]) if pd.notna(last["macd"]) else None,
        "macd_signal_line": float(last["macd_signal"]) if pd.notna(last["macd_signal"]) else None,
        "bb_upper": float(last["bb_upper"]) if pd.notna(last["bb_upper"]) else None,
        "bb_lower": float(last["bb_lower"]) if pd.notna(last["bb_lower"]) else None,
        "tenkan": float(last["tenkan"]) if pd.notna(last["tenkan"]) else None,
        "kijun": float(last["kijun"]) if pd.notna(last["kijun"]) else None,
        "senkou_a": float(last["senkou_a"]) if pd.notna(last["senkou_a"]) else None,
        "senkou_b": float(last["senkou_b"]) if pd.notna(last["senkou_b"]) else None,
        "cloud_top": float(last["cloud_top"]) if pd.notna(last["cloud_top"]) else None,
        "cloud_bot": float(last["cloud_bot"]) if pd.notna(last["cloud_bot"]) else None,
        "signals": detect_signals(
            df.dropna(
                subset=["sma_5", "sma_20", "sma_60", "rsi_14", "macd", "macd_signal", "bb_upper", "bb_lower"]
            )
        ),
    }


def to_markdown(result: dict) -> str:
    lines = [
        f"## 🔬 기술적 분석",
        "",
        f"| 지표 | 값 |",
        f"|------|-----|",
        f"| 현재가 | {fmt_num(result['current_price'])}원 |",
        f"| 전일 대비 | {fmt_pct(result['daily_return'])} |",
        f"| 180일 수익률 | {fmt_pct(result['period_return_180d'])} |",
        f"| 180일 최고 | {fmt_num(result['high_180d'])}원 |",
        f"| 180일 최저 | {fmt_num(result['low_180d'])}원 |",
        f"| 거래량 | {fmt_num(result['volume'])}주 |",
        "",
        f"### 이동평균",
        f"| 기간 | 값 |",
        f"|------|-----|",
        f"| 5일 | {fmt_num(result['sma_5'])}원 |",
        f"| 20일 | {fmt_num(result['sma_20'])}원 |",
        f"| 60일 | {fmt_num(result['sma_60'])}원 |",
        f"| 120일 | {fmt_num(result['sma_120'])}원 |",
        "",
        f"### 모멘텀 지표",
        f"- RSI(14): **{fmt_num(result['rsi_14'])}**",
        f"- MACD: {fmt_num(result['macd'])} / Signal: {fmt_num(result['macd_signal_line'])}",
        f"- 볼린저 밴드: {fmt_num(result['bb_lower'])} ~ {fmt_num(result['bb_upper'])}",
        "",
        f"### 일목균형표 (Ichimoku)",
        f"- 전환선(9): **{fmt_num(result['tenkan'])}** / 기준선(26): **{fmt_num(result['kijun'])}**",
        f"- 구름대: {fmt_num(result['cloud_bot'])} ~ {fmt_num(result['cloud_top'])}",
        f"- 선행스팬 A: {fmt_num(result['senkou_a'])} / B: {fmt_num(result['senkou_b'])}",
        "",
        f"### 시그널",
    ]
    for s in result["signals"]:
        lines.append(f"- {s}")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    code = sys.argv[1] if len(sys.argv) > 1 else "005930"
    from _utils import resolve_ticker

    code, name = resolve_ticker(code)
    r = analyze(code, name)
    print(to_markdown(r))
