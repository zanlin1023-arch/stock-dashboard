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
) -> dict:
    """분석 결과를 히스토리에 저장."""
    client = get_client()
    if not client:
        return {}

    record = {
        "stock_code": stock_code,
        "stock_name": stock_name,
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
        },
    }
    res = client.table("analysis_history").insert(record).execute()
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
