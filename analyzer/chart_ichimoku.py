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


# matplotlib 한국 폰트에 이모지 글리프 없음 → 깨짐(☒) 방지용 기호 대체
_EMOJI_MAP = {
    "📌": "▣", "🎯": "◆", "🛡": "▽", "💹": "■", "🔍": "※", "📖": "▤",
    "🔥": "★", "✅": "○", "⚠️": "!", "⚠": "!", "🚨": "!!", "➖": "—",
    "📈": "↑", "📉": "↓", "🟢": "[+]", "🔴": "[-]", "🟡": "[~]",
    "📊": "■", "💰": "$", "🏦": "[기관]", "🌍": "[G]", "🇰🇷": "[K]",
    "📅": "", "💡": "*",
}


def _safe_emoji(text: str) -> str:
    """matplotlib에서 깨지는 이모지를 한국 폰트 지원 기호로 치환."""
    if not text:
        return text
    for emo, sym in _EMOJI_MAP.items():
        text = text.replace(emo, sym)
    return text


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


def cap_targets(targets: dict, current_price: float, atr: float | None = None) -> dict:
    """V/N/E를 ATR cap(현재가+3×ATR)으로 제한. 비현실적 목표 차단 (전 경로 일관용).

    차트(make_decision)·page5 카드·DB 저장·히트맵·대시보드가 모두 동일한 cap된
    목표가를 쓰도록, raw compute_price_targets 결과를 직접 표시/저장하는 모든 경로에서
    이 헬퍼를 거치게 한다. atr 없거나 0 이하면 원본 그대로(복사본) 반환.
    """
    if not atr or atr <= 0:
        return dict(targets)
    cap = current_price + 3 * float(atr)
    out = {}
    for k, v in targets.items():
        try:
            fv = float(v)
            out[k] = min(fv, cap) if fv > current_price else fv
        except (TypeError, ValueError):
            out[k] = v
    return out


# ───────────────────────────────────────────────────────
# 2-c. 주봉 추세 필터 (장기 방향 — 일봉 신호 보강용, 2026-05 추가)
# ───────────────────────────────────────────────────────
def get_weekly_trend(code: str) -> dict:
    """일봉을 주봉으로 리샘플 → 주봉 일목 구름 위치로 장기 추세 판단.

    추세 순응 원칙: 일봉 매수 신호가 주봉 추세와 같으면 신뢰↑(가산), 반대면 위험(감점).

    Returns:
        {"trend": "above"/"inside"/"below"/None, "bonus": +10/0/-10, "label": str}
        - above: 장기 상승 (주봉 구름 위) → 일봉 매수 신호 +10
        - below: 장기 하락 (주봉 구름 아래) → 일봉 매수 신호 -10 (역추세 위험)
        - inside: 횡보 (구름 안) → 0
    """
    out = {"trend": None, "bonus": 0, "label": "—"}
    try:
        import technical
        # 주봉 52주 일목엔 1년+ 필요 → 2년치 일봉
        df = technical.fetch_ohlcv(code, days=730)
        if df is None or len(df) < 60:
            return out
        # 일봉 → 주봉 리샘플 (금요일 종가 기준)
        wk = df.resample("W").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna()
        if len(wk) < 30:
            return out
        high, low, close = wk["high"], wk["low"], wk["close"]
        # 주봉 일목 (9/26/52주)
        tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
        kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
        price = float(close.iloc[-1])
        sa = senkou_a.iloc[-1]
        sb = senkou_b.iloc[-1]
        if sa != sa or sb != sb:  # NaN (데이터 부족)
            return out
        top, bot = max(sa, sb), min(sa, sb)
        if price > top:
            out.update(trend="above", bonus=10, label="🟢 장기 상승 (주봉 구름 위)")
        elif price < bot:
            out.update(trend="below", bonus=-10, label="🔴 장기 하락 (주봉 구름 아래)")
        else:
            out.update(trend="inside", bonus=0, label="➖ 장기 횡보 (주봉 구름 안)")
    except Exception:
        pass
    return out


# ───────────────────────────────────────────────────────
# 3. 시간론 — 변곡 예측 (9/17/26봉)
# ───────────────────────────────────────────────────────
def compute_time_cycles(start_idx: int, total_len: int, cycles: tuple = (9, 17, 26)) -> list[dict]:
    """A 방식 (2026-05): **현재 시점 기준** 9/17/26봉 후 (= 약 2주/3.5주/5주 후).

    기존엔 start_idx(C 조정저점)부터 카운트 → C가 오래된 종목은 9/17/26봉이 이미 지나
    42/51/65봉으로 밀려 2~3개월 후 먼 미래가 됐음. 현재 기준으로 고정해 항상 가깝게.
    (start_idx는 호환성 위해 시그니처 유지하나 미사용)

    Returns: [{"cycle": 9, "target_idx": 현재+9, "is_future": True}, ...]
    """
    base = total_len - 1  # 현재(마지막 봉) 기준
    return [
        {
            "cycle": c,
            "target_idx": base + c,
            "is_future": True,
            "offset": c,
        }
        for c in cycles
    ]


# ───────────────────────────────────────────────────────
# 4. 의사결정 (지금 매수? 어디까지? 손절은?)
# ───────────────────────────────────────────────────────
def _cloud_pos(price: float, sa, sb) -> str | None:
    """현재가의 구름 대비 위치 (above/inside/below)."""
    if sa is None or sb is None or pd.isna(sa) or pd.isna(sb):
        return None
    top, bot = max(float(sa), float(sb)), min(float(sa), float(sb))
    if price > top:
        return "above"
    if price < bot:
        return "below"
    return "inside"


def classify_ichimoku_stance(cloud_pos, tk_bull, chikou_ok, rsi):
    """일목 3조건(구름·TK·후행스팬) + RSI 가드 → (stance, action, color).

    make_decision(상세 페이지)과 ichimoku_signal(리스트 뷰)이 공유하는 단일 판정기.
    삼역호전 = 구름 위 + 전환선>기준선 + 후행스팬 우위 → STRONG_BUY.
    """
    if cloud_pos == "above" and tk_bull and chikou_ok:
        if rsi is not None and rsi >= 75:
            return "BUY", "⚠️ 과매수 진입 신중 (삼역호전 but RSI≥75)", "#F39C12"
        if rsi is not None and rsi >= 70:
            return "BUY", "✅ 매수 우호 (삼역호전 — RSI 70+ 분할 진입)", "#2ECC71"
        return "STRONG_BUY", "🔥 강력 매수 (삼역호전)", "#27AE60"
    if cloud_pos == "below" and not tk_bull and chikou_ok is False:
        return "STRONG_SELL", "🚨 강력 매도 (삼역역전)", "#E74C3C"
    if cloud_pos == "above" and tk_bull:
        if rsi is not None and rsi >= 70:
            return "NEUTRAL", "➖ 관망 (구름 위지만 과매수)", "#7F8C8D"
        return "BUY", "✅ 매수 우호 (구름 위 + TK 골든)", "#2ECC71"
    if cloud_pos == "below" and not tk_bull:
        return "SELL", "⚠️ 매도 우호 (구름 아래 + TK 데드)", "#E67E22"
    return "NEUTRAL", "➖ 관망 (방향성 불명확)", "#7F8C8D"


def ichimoku_signal(df: pd.DataFrame) -> dict:
    """리스트(추천/관심) 표시용 컴팩트 일목 시그널 — 목표가/손절 없이 매수신호만.

    Returns:
        {stance, fresh, cloud_pos}
        - stance: STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL / NA
        - fresh: 오늘 구름을 상향 돌파(어제는 구름 위 아님) + TK 골든 → 이미지의 'Buy Signal' 순간
    """
    if df is None or len(df) < 27:
        return {"stance": "NA", "fresh": False, "cloud_pos": None}
    last = df.iloc[-1]
    price = float(last["close"])
    cloud_pos = _cloud_pos(price, last.get("senkou_a"), last.get("senkou_b"))
    tk_bull = (
        pd.notna(last.get("tenkan")) and pd.notna(last.get("kijun"))
        and float(last["tenkan"]) > float(last["kijun"])
    )
    chikou_ok = price > float(df["close"].iloc[-27])
    rsi = float(last["rsi_14"]) if "rsi_14" in df.columns and pd.notna(last.get("rsi_14")) else None
    stance, _, _ = classify_ichimoku_stance(cloud_pos, tk_bull, chikou_ok, rsi)

    # 매수돌파(fresh) = 최근 3봉 내 구름 상향 돌파 + 현재 구름 위 + TK골든.
    # [이전] 딱 어제→오늘 1봉 전환만 잡아 사실상 안 떴음(돌파 당일만 포착).
    # [변경] 직전 3봉(어제~3일전) 중 구름 아래/안이었다가 오늘 위면 '막 돌파'로 인정.
    recent_not_above = any(
        _cloud_pos(
            float(df.iloc[i]["close"]),
            df.iloc[i].get("senkou_a"), df.iloc[i].get("senkou_b"),
        ) in ("inside", "below")
        for i in range(-4, -1)
    )
    fresh = cloud_pos == "above" and tk_bull and recent_not_above

    # 과열 경고: RSI ≥ 70. 26봉 보유 백테스트(28종목·2015표본)에서 과매수는
    # 승률 53.7% / 평균 +7.8%로, 정상(68.3% / +11.7%)·과매도(71.4% / +13.6%) 대비
    # 뚜렷이 열위 → 추천/리스트에 ⚠️ 표시만(점수 미반영, 검증된 랭킹 유지).
    #
    # [미도입] 상대강도(RS, 종목 20일 수익 − 코스피)는 같은 백테스트에서 26봉 forward
    #   상관 -0.02(우위 0). 단일 거래일엔 되돌림으로 음의 상관(-0.48)이 떠도 장기 예측력
    #   없음 → 필터/점수에 넣지 않음.
    # [향후 후보] 과매도(RSI < 30)가 26봉 최고 성과(+13.6%, 71.4%) — 역발상 진입 신호로
    #   활용 검토 가능(현재 미적용).
    overheated = rsi is not None and rsi >= 70

    # [캔들 패턴 미도입 — 백테스트 결과 기록]
    # 망치(hammer)·유성(shooting star) 등 캔들 패턴 edge를 검증함.
    #  - 28종목(n105): 망치 26봉 70.5% / +12.2% 로 강세 edge처럼 보였음.
    #  - 100종목(n377)으로 확대 재검증: baseline(5봉55.3%/10봉58.1%/26봉63.5%·+11.0%) 대비
    #    망치 5·10봉 이하, 26봉 수익 오히려 낮음(+9.6%) → edge 소멸(소표본 noise).
    #    유성도 100종목선 약세 신호 실패. 장악·삼병·도지도 edge 없음.
    #  → 캔들 패턴은 점수·표시 모두 미적용. (RS와 동일 결론: 작은 표본 edge는 확대 시 사라짐.)
    return {
        "stance": stance, "fresh": fresh, "cloud_pos": cloud_pos,
        "overheated": overheated, "rsi": rsi,
    }


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

    # 시그널 판단 (일목 3조건 + RSI 가드) — 리스트 뷰와 공용 분류기
    stance, action, action_color = classify_ichimoku_stance(cloud_pos, tk_bull, chikou_ok, rsi)

    # ATR (목표가 cap + 손절 검증용)
    atr = None
    if "atr_14" in df.columns and pd.notna(df["atr_14"].iloc[-1]):
        atr = float(df["atr_14"].iloc[-1])

    # 목표가 (현재가 위 + ATR cap으로 비현실적 V/N/E 차단 — v7 일관)
    atr_cap = price + 3 * atr if atr else None
    upside_targets = []
    for k, v in sorted(
        [(k, v) for k, v in targets.items() if v > price and k != "NT"],
        key=lambda x: x[1],
    ):
        capped = min(v, atr_cap) if atr_cap else v
        upside_targets.append((k, capped))

    # 손절: 현재가 *아래* 지지선만 (기준선이 현재가 위면 저항이지 손절 아님)
    stop_candidates = []
    if kijun is not None and kijun < price:
        stop_candidates.append(("기준선", kijun))
    if swings["C"]["price"] < price:
        stop_candidates.append(("C저점", swings["C"]["price"]))
    stop = max(stop_candidates, key=lambda x: x[1]) if stop_candidates else None
    # 현재가 아래 지지선이 없으면 ATR 2배 손절 (업계 표준)
    if stop is None and atr:
        stop = ("ATR 2배", price - 2 * atr)

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
    swings: Optional[dict] = None,
    atr_value: Optional[float] = None,
) -> list[dict]:
    """미래 변곡점 예상 가격 경로 (N파동 = 상승-조정-상승).

    개선 적용 (2026-05):
      A. **B 돌파 가드**: 현재가가 B(최근 피크) 미돌파 시 label에 "(가설)" 표시
         V/N/E 공식은 B 돌파 후에만 active (2nd Skies / TradingView 일목 이론)
      B. **ATR cap**: V/N/E가 현재가 + 3×ATR 초과 시 cap → 비현실적 목표 차단
      C. **Deep pullback**: 조정 38.2% → 50% (일목/피보나치 표준 더 가까움)

    Args:
        swings: {"A": {price}, "B": {price}, "C": {price}} — B 돌파 판정용
        atr_value: ATR(14) — V/N/E 상한 캡 (없으면 캡 없음)
    """
    future_cycles = sorted(
        [c for c in cycles if c.get("is_future")],
        key=lambda c: c["target_idx"],
    )[:3]
    if not future_cycles or not targets:
        return []

    # B 돌파 여부 (V/N/E의 신뢰도)
    b_broken = True
    if swings and swings.get("B"):
        try:
            b_price = float(swings["B"].get("price", 0))
            b_broken = current_price >= b_price
        except (TypeError, ValueError):
            b_broken = True

    # ATR cap (v5: 2×ATR → 1.5×ATR, 더 보수적 — 적중률 85% 목표)
    atr_cap = None
    if atr_value and atr_value > 0:
        atr_cap = current_price + 1.5 * float(atr_value)

    def _cap(val: float) -> float:
        if atr_cap is not None and val > atr_cap:
            return atr_cap
        return val

    upside_raw = sorted(
        [(k, targets[k]) for k in ("V", "N", "E") if targets.get(k, 0) > current_price],
        key=lambda x: x[1],
    )
    # v3: ATR cap만 적용, buffer는 시점별 가변 (1차=단기 보수, 3차=장기 완화)
    upside = [(k, _cap(v)) for k, v in upside_raw]
    if not upside:
        return []

    # active/가설 라벨 suffix
    confidence = "" if b_broken else " (가설)"

    # v7: 26봉도 단기 취급 (적중률 90% 목표)
    def _buffer_for_cycle(c: int) -> float:
        if c <= 26:
            return 0.88  # 단기~중기: 강하게 보수
        return 0.92      # 장기 (v5와 동일)

    # raw 1차/3차 (cap 적용, buffer 미적용)
    first_label, first_raw_capped = upside[0]
    if len(upside) >= 2:
        third_label, third_raw_capped = upside[1]
    else:
        third_label = first_label
        third_raw_capped = first_raw_capped

    # pullback은 1차 raw 기준 50% (cycle 무관)
    pullback_to = current_price + (first_raw_capped * 0.92 - current_price) * 0.5
    if stop:
        pullback_to = max(pullback_to, stop[1] * 1.02)

    sequence = [
        (first_raw_capped, f"{first_label} 도달{confidence}", True),
        (pullback_to, "V파동 조정", False),
        (third_raw_capped, f"{third_label} 도전{confidence}", True),
    ]

    path = []
    for cyc, (raw_val, lbl, is_peak) in zip(future_cycles, sequence):
        if is_peak:
            buf = _buffer_for_cycle(cyc["cycle"])
            pr = raw_val * buf
            # 피크(도달 목표)는 최소 현재가 +1% 보장 — buffer×cap로 음수 목표 방지
            pr = max(pr, current_price * 1.01)
        else:
            pr = raw_val  # 임시 (아래에서 1차 최종가 기준 재계산)
        path.append({
            "target_idx": cyc["target_idx"],
            "cycle": cyc["cycle"],
            "price": float(pr),
            "label": lbl,
            "is_peak": is_peak,
        })

    # 2차(조정) 재정렬 — 1차 최종가 기준 50% 되돌림 (항상 1차보다 낮게 → "조정" 라벨 정직)
    if len(path) >= 2 and not path[1]["is_peak"]:
        first_final = path[0]["price"]
        if first_final > current_price:
            # 정상: 1차가 현재가 위 → 조정 = 1차~현재가 50% 되돌림 (1차보다 낮음)
            pb = current_price + (first_final - current_price) * 0.5
            if stop:
                pb = max(pb, stop[1] * 1.02)
            # 단, pullback이 1차 넘으면 안 됨 (안전)
            pb = min(pb, first_final * 0.97)
            path[1]["price"] = float(pb)
            path[1]["label"] = "V파동 조정"
        else:
            # 1차가 현재가 이하(보수적) → '조정' 의미 없음 → 약보합 라벨
            path[1]["price"] = float(current_price * 0.98)
            path[1]["label"] = "약보합/횡보"

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

    # 미래 영역에 선행스팬 채우기 — '원본(unshifted)' 스팬의 최근 26봉을 앞으로.
    # [이전 버그] df.senkou_a/b는 이미 26봉 shift된 값이라 그 끝 26개를 쓰면
    #   ~27봉 과거 스팬이 미래에 들어가 구름이 추세를 못 따라감(우상향이 우하향처럼 보임).
    # [수정] 전환·기준선과 52일 고저로 원본 스팬을 재계산해 최근 26봉을 미래로.
    #   (과거 구름은 shift된 df 값을 그대로 써서 정확, 미래만 원본 엣지로 연결 → 연속)
    last_real_idx = len(plot_df) - 1
    full_df = df.copy()
    _raw_a = (full_df["tenkan"] + full_df["kijun"]) / 2
    _raw_b = (full_df["high"].rolling(52).max() + full_df["low"].rolling(52).min()) / 2
    senkou_a_future = _raw_a.iloc[-26:].values
    senkou_b_future = _raw_b.iloc[-26:].values
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
        # 양운(A≥B)=상승 초록 / 음운(A<B)=하락 빨강. 한국식 빨강(상승)캔들과
        # 겹치는 음운은 채도 낮은 파스텔로 가독성 확보.
        ax_main.fill_between(
            x_idx, a, b, where=(a >= b) & valid,
            color="#B7E4C7", alpha=0.55,
        )
        ax_main.fill_between(
            x_idx, a, b, where=(a < b) & valid,
            color="#F5B7B1", alpha=0.55,
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

    # y축 자동 확장: V/N/E + 손절이 모두 차트 안에 들어오도록 (사용자 요청)
    y_bottom, y_top = ax_main.get_ylim()
    extreme_top = max([v for _, v in sorted_targets] + [y_top])
    extreme_bot_candidates = [v for _, v in sorted_targets] + [y_bottom]
    if decision.get("stop"):
        extreme_top = max(extreme_top, decision["stop"][1])
        extreme_bot_candidates.append(decision["stop"][1])
    extreme_bot = min(extreme_bot_candidates)
    new_top = extreme_top * 1.05 if extreme_top > y_top else y_top
    new_bot = extreme_bot * 0.95 if extreme_bot < y_bottom else y_bottom
    ax_main.set_ylim(new_bot, new_top)
    y_top = new_top
    # 라벨 겹침 방지: 텍스트 y 위치를 최소 간격(차트 높이 6%) 확보하며 위→아래 배치
    _y_range = y_top - new_bot
    _min_gap = _y_range * 0.06
    _last_label_y = None  # 직전 라벨 y (위에서부터 내려옴)
    for k, v in sorted_targets:  # 내림차순 (E→N→V)
        meta = target_meta[k]
        pct = (v / current_price - 1) * 100
        if v > y_top:
            ax_main.text(
                target_x, y_top * 0.98,
                f" ↑ {k} {meta['rank']} {v:,.0f} ({pct:+.1f}%) {meta['desc']}",
                fontsize=9, va="top", ha="left",
                color=meta["color"], fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white",
                         edgecolor=meta["color"], alpha=0.95, linestyle="--"),
            )
        else:
            # 점선은 실제 가격 v 위치
            ax_main.axhline(v, color=meta["color"], linestyle=":", linewidth=1.0, alpha=0.7,
                           xmin=today_x / n_total, xmax=1.0)
            # 라벨 텍스트는 겹치지 않게 y 분산
            label_y = v
            if _last_label_y is not None and (_last_label_y - label_y) < _min_gap:
                label_y = _last_label_y - _min_gap
            _last_label_y = label_y
            ax_main.text(
                target_x, label_y,
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
            f" ▽ 손절 {stop_val:,.0f} ({pct:+.1f}%) {stop_name}",
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

    # 시간 사이클 마커는 '시간 정보만' (일목 시간론 원리)
    # 가격 예측은 패턴 매칭 (파란 영역) + 우측 V/N/E 라벨로 통일 → 충돌 방지

    for cyc in cycles:
        rel_idx = cyc["target_idx"] - plot_base_idx
        if 0 <= rel_idx < n_total:
            color = cycle_colors[cyc["cycle"]]
            is_future = cyc["is_future"]
            fill_color = color if is_future else "#BBB"
            edge_color = color
            alpha_val = 1.0 if is_future else 0.5

            ax_main.scatter([rel_idx], [marker_y],
                          marker="v", color=fill_color, s=220, zorder=6,
                          edgecolors=edge_color, linewidths=2.0, alpha=alpha_val)

            ax_main.text(
                rel_idx, marker_y,
                f"{cyc['cycle']}",
                fontsize=10, ha="center", va="center",
                color="white", fontweight="bold",
            )

            # 라벨: 봉수 + 날짜만 (가격 X — 두 예측 로직 충돌 방지)
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

    # ───── 미래 추세 예측 (패턴 매칭 우선, 실패 시 N파동 fallback) ─────
    pattern_result = None
    try:
        import pattern_match
        pattern_result = pattern_match.predict_future_path(
            code=code, current_price=current_price,
            window=60, n_future=20, top_k=3,
        )
    except Exception:
        pattern_result = None

    if pattern_result and pattern_result.get("projection"):
        # 패턴 매칭 방식 — 평균 경로 + low/high 신뢰 밴드
        proj = pattern_result["projection"]
        # 미래 20봉을 today_x 기준 1봉씩 → rel_idx 변환 (extended가 35봉 미래 보유)
        future_rel = [today_x + d for d in proj["days"]]
        future_rel_in_range = [(i, rel) for i, rel in enumerate(future_rel) if rel < n_total]
        if future_rel_in_range:
            valid_x = [today_x] + [rel for _, rel in future_rel_in_range]
            valid_avg = [current_price] + [proj["avg_path"][i] for i, _ in future_rel_in_range]
            valid_low = [current_price] + [proj["low_path"][i] for i, _ in future_rel_in_range]
            valid_high = [current_price] + [proj["high_path"][i] for i, _ in future_rel_in_range]

            # 신뢰 밴드 (low~high 음영)
            ax_main.fill_between(
                valid_x, valid_low, valid_high,
                color="#3498DB", alpha=0.12, zorder=4,
                label="패턴 매칭 범위",
            )
            # 평균 경로 (실선)
            ax_main.plot(
                valid_x, valid_avg,
                linestyle="-", linewidth=1.8, color="#1B6FB0",
                marker="o", markersize=4,
                markerfacecolor="#1B6FB0", markeredgecolor="white",
                markeredgewidth=0.8, alpha=0.9, zorder=5,
                label="패턴 평균",
            )
            # low/high 경계선 (얇은 점선)
            ax_main.plot(valid_x, valid_low, linestyle=":", linewidth=0.8,
                         color="#1B6FB0", alpha=0.5, zorder=4)
            ax_main.plot(valid_x, valid_high, linestyle=":", linewidth=0.8,
                         color="#1B6FB0", alpha=0.5, zorder=4)

            # 마지막(20일 후) 라벨
            last_idx = future_rel_in_range[-1][1]
            last_avg = valid_avg[-1]
            last_low = valid_low[-1]
            last_high = valid_high[-1]
            avg_pct = (last_avg / current_price - 1) * 100
            try:
                end_date = extended.index[last_idx].strftime("%m/%d")
            except Exception:
                end_date = f"+{proj['days'][-1]}봉"
            n_pat = proj.get("pattern_count", 0)
            avg_corr = proj.get("avg_correlation", 0)
            ax_main.text(
                last_idx, last_avg,
                f"  {end_date} 평균\n"
                f"  {last_avg:,.0f} ({avg_pct:+.1f}%)\n"
                f"  범위: {last_low:,.0f}~{last_high:,.0f}\n"
                f"  유사 패턴 {n_pat}개 (r={avg_corr})",
                fontsize=8, va="center", ha="left",
                color="#1B6FB0", fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor="#1B6FB0", alpha=0.95),
            )
    else:
        # Fallback: 일목 N파동 시나리오 (편향 있음, 패턴 데이터 부족 시)
        _atr_val = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns and pd.notna(df["atr_14"].iloc[-1]) else None
        future_path = project_future_path(
            current_price=current_price,
            cycles=cycles,
            targets=targets,
            stop=decision.get("stop"),
            swings=swings,
            atr_value=_atr_val,
        )
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
                markeredgewidth=1.2, zorder=6,
                label="일목 N파동 (fallback)",
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

    # 패턴 매칭 결과 (있을 때만) — 키움/머니트리 방식 정직성
    if pattern_result and pattern_result.get("projection"):
        proj = pattern_result["projection"]
        avg_last = proj["avg_path"][-1] if proj.get("avg_path") else current_price
        avg_pct = (avg_last / current_price - 1) * 100
        info_lines.append("")
        info_lines.append(
            f"🔍 패턴매칭 (과거 유사 {proj.get('pattern_count')}개, r={proj.get('avg_correlation')})"
        )
        info_lines.append(
            f"   20봉 후 평균 {avg_last:,.0f} ({avg_pct:+.1f}%)"
        )

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
        0.01, 0.98, _safe_emoji("\n".join(info_lines)),
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
    # 범례 위치: 좌측 상단 (우측 하단은 ▼ 시간 사이클 마커와 겹침)
    ax_main.text(
        0.01, 0.02, legend_text,
        transform=ax_main.transAxes,
        fontsize=8.5, va="bottom", ha="left",
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
