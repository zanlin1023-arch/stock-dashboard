"""Supabase 연동 — 보유종목 / 관심종목 / 분석 히스토리 CRUD."""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

from supabase import Client, create_client


# ───────────────────────────────────────────────────────
# Client 싱글톤
# ───────────────────────────────────────────────────────
_client: Optional[Client] = None


def get_client() -> Optional[Client]:
    """Supabase client 반환. URL/KEY 없으면 None."""
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip() or os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
    if not url or not key:
        return None
    _client = create_client(url, key)
    return _client


def is_db_available() -> bool:
    return get_client() is not None


# ───────────────────────────────────────────────────────
# 보유 종목 (holdings)
# ───────────────────────────────────────────────────────
def list_holdings() -> list[dict]:
    """보유 종목 전체 조회."""
    client = get_client()
    if not client:
        return []
    res = client.table("holdings").select("*").order("purchase_date", desc=True).execute()
    return res.data or []


def add_holding(
    stock_code: str,
    stock_name: str,
    avg_price: float,
    quantity: int,
    purchase_date: Optional[date] = None,
    note: str = "",
) -> dict:
    client = get_client()
    if not client:
        raise RuntimeError("Supabase 미설정 (SUPABASE_URL/KEY 누락)")
    data = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "avg_price": float(avg_price),
        "quantity": int(quantity),
        "purchase_date": (purchase_date or date.today()).isoformat(),
        "note": note,
    }
    res = client.table("holdings").insert(data).execute()
    return res.data[0] if res.data else {}


def delete_holding(holding_id: int) -> None:
    client = get_client()
    if not client:
        return
    client.table("holdings").delete().eq("id", holding_id).execute()


def update_holding(holding_id: int, **fields) -> dict:
    client = get_client()
    if not client:
        raise RuntimeError("Supabase 미설정")
    res = client.table("holdings").update(fields).eq("id", holding_id).execute()
    return res.data[0] if res.data else {}


# ───────────────────────────────────────────────────────
# 관심 종목 (watchlist)
# ───────────────────────────────────────────────────────
def list_watchlist() -> list[dict]:
    client = get_client()
    if not client:
        return []
    res = client.table("watchlist").select("*").order("added_at", desc=True).execute()
    return res.data or []


def add_watch(stock_code: str, stock_name: str, note: str = "", tags: Optional[list[str]] = None) -> dict:
    client = get_client()
    if not client:
        raise RuntimeError("Supabase 미설정")
    data = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "note": note,
        "tags": tags or [],
    }
    # upsert (중복 시 갱신)
    res = client.table("watchlist").upsert(data, on_conflict="stock_code").execute()
    return res.data[0] if res.data else {}


def delete_watch(watch_id: int) -> None:
    client = get_client()
    if not client:
        return
    client.table("watchlist").delete().eq("id", watch_id).execute()


# ───────────────────────────────────────────────────────
# 분석 히스토리 (analysis_history)
# ───────────────────────────────────────────────────────
def save_analysis(
    stock_code: str,
    stock_name: str,
    technical: dict,
    decision: dict,
    targets: dict,
    swings: Optional[dict] = None,
    snapshot_type: str = "manual",  # 'manual' or 'scheduled'
    cycles: Optional[list] = None,
    future_path: Optional[list] = None,
    flow: Optional[dict] = None,
    pattern_match: Optional[dict] = None,
    target_date: Optional[str] = None,  # 'YYYY-MM-DD' (None이면 오늘 — backfill용)
) -> dict:
    """분석 결과를 히스토리에 저장 (같은 날 같은 종목+타입은 덮어쓰기).

    추가 인자 (raw_data JSONB에만 저장 — 스키마 변경 불필요):
      - cycles: 시간 변곡 마커 리스트 (과거+미래)
      - future_path: 미래 추세 예상 경로 (N파동 시나리오)
      - flow: {"verdict": str, "daily": list[dict]} 외국인/기관 수급
      - pattern_match: {"projection":{...}, "patterns":[...]} 키움 방식 패턴 매칭
    """
    from datetime import date as _date
    client = get_client()
    if not client:
        return {}

    record = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "snapshot_type": snapshot_type,
        "analyzed_date": target_date or _date.today().isoformat(),
        "price": _safe_num(technical.get("current_price")),
        "rsi_14": _safe_num(technical.get("rsi_14")),
        "macd": _safe_num(technical.get("macd")),
        "tenkan": _safe_num(technical.get("tenkan")),
        "kijun": _safe_num(technical.get("kijun")),
        "senkou_a": _safe_num(technical.get("senkou_a")),
        "senkou_b": _safe_num(technical.get("senkou_b")),
        "cloud_position": decision.get("cloud_pos"),
        "decision_stance": decision.get("stance"),
        "decision_action": decision.get("action"),
        "target_v": _safe_num(targets.get("V")),
        "target_n": _safe_num(targets.get("N")),
        "target_e": _safe_num(targets.get("E")),
        "stop_loss": _safe_num(decision.get("stop", (None, None))[1] if decision.get("stop") else None),
        "raw_data": {
            "technical": _json_safe(technical),
            "decision": _json_safe(decision),
            "targets": _json_safe(targets),
            "swings": _json_safe(swings) if swings else None,
            "cycles": _json_safe(cycles) if cycles else None,
            "future_path": _json_safe(future_path) if future_path else None,
            "flow": _json_safe(flow) if flow else None,
            "pattern_match": _json_safe(pattern_match) if pattern_match else None,
        },
    }
    # 같은 날짜+종목+타입 중복 시 UPDATE (UNIQUE 제약 활용)
    res = client.table("analysis_history").upsert(
        record, on_conflict="stock_code,analyzed_date,snapshot_type"
    ).execute()
    return res.data[0] if res.data else {}


def get_history(stock_code: str, limit: int = 30) -> list[dict]:
    client = get_client()
    if not client:
        return []
    res = (
        client.table("analysis_history")
        .select("*")
        .eq("stock_code", stock_code)
        .order("analyzed_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ───────────────────────────────────────────────────────
# 추천 종목 (recommendations) — 날짜별 누적
# ───────────────────────────────────────────────────────
def save_recommendations(results: dict, session: str = "evening", target_date: str | None = None) -> int:
    """recommend.recommend() 결과를 DB에 저장.

    Args:
        results: {"large": [...], "mid": [...], "small": [...]}
        session: 'morning' / 'intraday' / 'evening'
        target_date: 'YYYY-MM-DD' (None이면 오늘)

    Returns:
        저장된 행 수
    """
    from datetime import date as _date
    client = get_client()
    if not client:
        return 0

    today = target_date or _date.today().isoformat()
    rows = []
    for tier in ["large", "mid", "small"]:
        for rank, stock in enumerate(results.get(tier, []), 1):
            rows.append({
                "recommended_date": today,
                "session": session,
                "tier": tier,
                "rank_in_tier": rank,
                "stock_code": stock.get("code"),
                "stock_name": stock.get("name"),
                "score": int(round(float(stock.get("score") or 0))) or None,
                "price": int(float(stock.get("price") or 0)) or None,
                "change_pct": _safe_num(stock.get("change_pct")),
                "market_cap_eok": int(stock.get("market_cap_eok") or 0) or None,
                "foreign_5d": int(stock.get("foreign_5d") or 0) or None,
                "inst_5d": int(stock.get("inst_5d") or 0) or None,
                "signals": _json_safe(stock.get("signals") or []),
            })
    if not rows:
        return 0
    # upsert (같은 날짜+세션+tier+종목 중복 방지)
    client.table("recommendations").upsert(
        rows, on_conflict="recommended_date,session,tier,stock_code"
    ).execute()
    return len(rows)


def list_recommendations(
    target_date: str | None = None,
    session: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """추천 종목 조회.

    Args:
        target_date: 'YYYY-MM-DD' (None이면 가장 최근 날짜)
        session: 'morning' / 'intraday' / 'evening' (None이면 모두)
    """
    client = get_client()
    if not client:
        return []

    if target_date is None:
        # 가장 최근 추천 날짜
        res = (
            client.table("recommendations")
            .select("recommended_date")
            .order("recommended_date", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            return []
        target_date = res.data[0]["recommended_date"]

    q = (
        client.table("recommendations")
        .select("*")
        .eq("recommended_date", target_date)
    )
    if session:
        q = q.eq("session", session)
    res = q.order("tier").order("rank_in_tier").limit(limit).execute()
    return res.data or []


def list_recommendation_dates(limit: int = 30) -> list[str]:
    """저장된 추천 날짜 목록 (최근 N개)."""
    client = get_client()
    if not client:
        return []
    res = (
        client.table("recommendations")
        .select("recommended_date")
        .order("recommended_date", desc=True)
        .limit(1000)
        .execute()
    )
    dates = sorted({r["recommended_date"] for r in (res.data or [])}, reverse=True)
    return dates[:limit]


# ───────────────────────────────────────────────────────
# 유틸
# ───────────────────────────────────────────────────────
def _safe_num(x) -> Optional[float]:
    if x is None:
        return None
    try:
        v = float(x)
        return v if v == v else None  # NaN 체크
    except (TypeError, ValueError):
        return None


def _json_safe(obj: Any) -> Any:
    """JSON 직렬화 불가능한 객체를 안전하게 변환."""
    if obj is None:
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(x) for x in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (int, float, str, bool)):
        return obj
    return str(obj)  # fallback
