"""패턴 매칭 기반 미래 가격 예측 (키움 미래주가예측 방식).

알고리즘:
1. FinanceDataReader로 종목 과거 5년 일봉 fetch
2. 최근 N봉(default 60) 정규화 → 과거 슬라이딩 윈도우에서 Pearson correlation 계산
3. 유사도 top-k (default 3) 패턴 추출
4. 각 패턴 직후의 M봉(default 20) 가격 변화율 → 평균/min/max로 미래 경로 구성
5. 현재가에 스케일링해서 절대 가격으로 환산

한계 (정직하게):
- 과거 ≠ 미래. 패턴 반복 가정에 의존
- 단일 종목 자체 데이터만 사용 (KOSPI 전체 비교 X)
- 거시 환경 변화/이슈 반영 안 됨
- 머니트리/키움도 같은 한계
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")


# ────────────────────────────────────────────────
# 1. 과거 데이터 fetch (FDR — 인증 불필요)
# ────────────────────────────────────────────────
def _fetch_history(code: str, lookback_days: int = 1825) -> pd.DataFrame | None:
    """FDR로 종목 과거 OHLCV (default 5년 = 1825일)."""
    try:
        import FinanceDataReader as fdr
        end = datetime.now().date()
        start = end - timedelta(days=lookback_days)
        df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df is None or df.empty:
            return None
        # FDR 컬럼명: Close (대문자) — 소문자로 통일
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        return df
    except Exception:
        return None


# ────────────────────────────────────────────────
# 2. 정규화 + 슬라이딩 correlation
# ────────────────────────────────────────────────
def _normalize(arr: np.ndarray) -> np.ndarray:
    """z-score 정규화 (모양 비교용)."""
    if arr.std() == 0:
        return arr - arr.mean()
    return (arr - arr.mean()) / arr.std()


def find_similar_patterns(
    df: pd.DataFrame,
    window: int = 60,
    top_k: int = 3,
    min_gap_days: int = 90,
) -> list[dict]:
    """최근 window봉과 유사한 과거 패턴 top-k 검색.

    Args:
        df: 종가 포함 DataFrame (index=날짜)
        window: 비교 윈도우 (봉 수)
        top_k: 상위 몇 개 패턴
        min_gap_days: 패턴 간 최소 간격 (중복 방지)

    Returns:
        [{
            "start_idx": int, "end_idx": int,
            "start_date": str, "end_date": str,
            "correlation": float,
            "future_returns": np.array (다음 20봉 누적수익률 %)
        }]
    """
    if df is None or len(df) < window + 20:
        return []

    closes = df["close"].values
    n = len(closes)
    recent = closes[-window:]
    recent_norm = _normalize(recent.astype(float))

    # 슬라이딩 윈도우 correlation (최근 window는 제외)
    corrs = []
    for i in range(0, n - window - 20):
        past = closes[i:i + window].astype(float)
        past_norm = _normalize(past)
        if np.std(past) == 0:
            continue
        # Pearson correlation (정규화 후 dot product / N)
        corr = float(np.dot(recent_norm, past_norm) / window)
        corrs.append((i, corr))

    if not corrs:
        return []

    # 상관계수 내림차순 정렬
    corrs.sort(key=lambda x: -x[1])

    # top-k 추출 — 단, 서로 너무 가까운 패턴은 중복 취급
    selected = []
    for i, corr in corrs:
        if corr < 0.5:  # 최소 0.5 미만은 무의미
            break
        # 이미 선택된 패턴과 너무 가까우면 skip
        too_close = any(abs(i - s[0]) < min_gap_days for s in selected)
        if too_close:
            continue
        selected.append((i, corr))
        if len(selected) >= top_k:
            break

    # 결과 구성
    out = []
    for start_idx, corr in selected:
        end_idx = start_idx + window
        future = closes[end_idx:end_idx + 20].astype(float)
        # 첫 봉(end) 기준 누적수익률 %
        last_close_of_pattern = closes[end_idx - 1]
        future_returns = (future / last_close_of_pattern - 1) * 100
        out.append({
            "start_idx": int(start_idx),
            "end_idx": int(end_idx),
            "start_date": str(df.index[start_idx].date()),
            "end_date": str(df.index[end_idx - 1].date()),
            "correlation": round(corr, 3),
            "future_returns": future_returns.tolist(),
        })
    return out


# ────────────────────────────────────────────────
# 3. 미래 경로 투영 (평균 + 신뢰 밴드)
# ────────────────────────────────────────────────
def project_future(
    patterns: list[dict],
    current_price: float,
    n_future: int = 20,
) -> dict | None:
    """top-k 패턴의 미래 N봉 평균/범위를 현재가에 스케일링.

    Returns:
        {
            "days": [+1, +2, ..., +n],
            "avg_path": [price, ...],
            "low_path": [price, ...],     # min (보수)
            "high_path": [price, ...],    # max (낙관)
            "pattern_count": k,
            "avg_correlation": float,
        }
    """
    if not patterns:
        return None

    # 각 패턴의 future_returns (%)를 배열로 정렬 (N봉 길이)
    returns_matrix = []
    for p in patterns:
        fr = p["future_returns"][:n_future]
        if len(fr) < n_future:
            fr = fr + [fr[-1] if fr else 0.0] * (n_future - len(fr))
        returns_matrix.append(fr)

    returns_arr = np.array(returns_matrix)  # shape: (k, n_future)
    avg_returns = returns_arr.mean(axis=0)
    min_returns = returns_arr.min(axis=0)
    max_returns = returns_arr.max(axis=0)

    avg_path = (current_price * (1 + avg_returns / 100)).tolist()
    low_path = (current_price * (1 + min_returns / 100)).tolist()
    high_path = (current_price * (1 + max_returns / 100)).tolist()

    avg_corr = float(np.mean([p["correlation"] for p in patterns]))

    return {
        "days": list(range(1, n_future + 1)),
        "avg_path": avg_path,
        "low_path": low_path,
        "high_path": high_path,
        "pattern_count": len(patterns),
        "avg_correlation": round(avg_corr, 3),
    }


# ────────────────────────────────────────────────
# 4. 통합 API
# ────────────────────────────────────────────────
def predict_future_path(
    code: str,
    current_price: float | None = None,
    window: int = 60,
    n_future: int = 20,
    top_k: int = 3,
) -> dict | None:
    """패턴 매칭 기반 미래 경로 예측 통합 호출.

    Returns:
        {
            "projection": {...},   # project_future 결과
            "patterns": [...],     # 유사 패턴 메타
            "method": "pattern_match",
            "window": int,
            "n_future": int,
        }
        실패 시 None
    """
    df = _fetch_history(code, lookback_days=1825)
    if df is None or len(df) < window + 20:
        return None

    if current_price is None:
        current_price = float(df["close"].iloc[-1])

    patterns = find_similar_patterns(df, window=window, top_k=top_k)
    if not patterns:
        return None

    projection = project_future(patterns, current_price, n_future=n_future)
    if not projection:
        return None

    return {
        "projection": projection,
        "patterns": [
            {k: v for k, v in p.items() if k != "future_returns"}
            for p in patterns
        ],
        "method": "pattern_match",
        "window": window,
        "n_future": n_future,
    }


if __name__ == "__main__":
    import sys
    import json
    code = sys.argv[1] if len(sys.argv) > 1 else "005930"
    result = predict_future_path(code)
    if result:
        print(json.dumps({
            "method": result["method"],
            "patterns": result["patterns"],
            "avg_correlation": result["projection"]["avg_correlation"],
            "first_5_days_avg": result["projection"]["avg_path"][:5],
            "first_5_days_low": result["projection"]["low_path"][:5],
            "first_5_days_high": result["projection"]["high_path"][:5],
        }, ensure_ascii=False, indent=2))
    else:
        print("FAIL: no projection")
