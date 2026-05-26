"""종목 메타 정보 자동 수집 — 업종/테마/메모 자동 채우기.

우선순위:
1. Claude (Anthropic) — 한국어 처리 최강, 한 줄 설명 + 테마 풍부
2. 네이버 금융 스크래핑 (무료 fallback)
3. FDR StockListing (캐시 — 시장 정보)
"""
from __future__ import annotations

import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup


# ───────────────────────────────────────────────────────
# 통합 함수 (외부 진입점)
# ───────────────────────────────────────────────────────
def enrich_stock(code: str, name: str) -> dict:
    """종목 메타 정보 자동 수집.

    Returns:
        {
            "market": "KOSPI",
            "sector": "반도체",
            "themes": ["AI 반도체", "HBM"],
            "memo": "한 줄 요약",
            "source": "claude" | "naver" | "fdr" | "fallback",
        }
    """
    # 1) Claude API 사용 가능 시 (한국어 최강)
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return _enrich_via_claude(code, name)
        except Exception:
            pass

    # 2) 네이버 금융 크롤링
    try:
        return _enrich_via_naver(code, name)
    except Exception:
        pass

    # 3) FDR fallback
    try:
        return _enrich_via_fdr(code, name)
    except Exception:
        pass

    return {
        "market": "",
        "sector": "",
        "themes": [],
        "memo": "",
        "source": "fallback",
    }


# ───────────────────────────────────────────────────────
# 1. Claude (Anthropic) — 한국어 최강
# ───────────────────────────────────────────────────────
def _enrich_via_claude(code: str, name: str) -> dict:
    """Anthropic Claude API로 회사 요약 + 테마 자동 생성."""
    import json

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    # 네이버 기본 정보 먼저 (Claude 컨텍스트 + 정확도 향상)
    base = {}
    try:
        base = _enrich_via_naver(code, name)
    except Exception:
        pass

    prompt = f"""한국 주식 종목 '{name}' (종목코드 {code})에 대해 정확하고 간결한 정보를 한국어로 작성하세요.

기존 수집 정보:
- 업종: {base.get('sector') or '미확인'}
- 테마: {base.get('themes') or []}

다음 JSON 형식으로만 답변하세요 (다른 설명 없이):
{{
  "memo": "회사가 무엇을 하는지 30자 이내 한 줄 요약",
  "themes": ["핵심 투자 테마 3-5개", "예: AI 반도체", "HBM", "2차전지"],
  "sector": "주력 업종 (예: 반도체, 자동차 부품)"
}}

주의: 종목명 그대로 사용하지 말고 '무엇을 하는 회사인지' 핵심을 담을 것."""

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",  # 빠르고 저렴
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=20,
    )
    r.raise_for_status()
    text = r.json()["content"][0]["text"].strip()

    # JSON 추출 (```json ... ``` 또는 순수 JSON)
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    parsed = json.loads(text)

    return {
        "market": base.get("market", ""),
        "sector": parsed.get("sector") or base.get("sector", ""),
        "themes": (parsed.get("themes") or base.get("themes", []))[:5],
        "memo": (parsed.get("memo") or "")[:80],
        "source": "claude",
    }


# ───────────────────────────────────────────────────────
# 2. 네이버 금융 (무료, 업종+테마)
# ───────────────────────────────────────────────────────
def _enrich_via_naver(code: str, name: str) -> dict:
    """네이버 종목 페이지에서 업종 + 테마 수집."""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.naver.com/",
    }
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    # 네이버는 페이지마다 인코딩 다름 — content 바이트에서 직접 디코딩
    raw = r.content
    for enc in ("utf-8", "euc-kr", "cp949"):
        try:
            html = raw.decode(enc)
            if "삼성" in html or "코스피" in html or "kospi" in html.lower() or "<title>" in html.lower():
                break
        except UnicodeDecodeError:
            continue
    else:
        html = r.text
    soup = BeautifulSoup(html, "html.parser")

    out = {
        "market": "",
        "sector": "",
        "themes": [],
        "memo": "",
        "source": "naver",
    }

    # 시장 (KOSPI/KOSDAQ)
    market_tag = soup.select_one(".description img")
    if market_tag and market_tag.get("alt"):
        alt = market_tag["alt"].upper()
        if "KOSPI" in alt:
            out["market"] = "KOSPI"
        elif "KOSDAQ" in alt:
            out["market"] = "KOSDAQ"

    # 업종 (예: "반도체와반도체장비")
    industry_link = soup.select_one("#wrap .trade_compare a, .description .upjong a")
    if industry_link:
        out["sector"] = industry_link.get_text(strip=True)

    # 종목 테마 — coinfo 페이지에서 가져오기
    try:
        themes = _fetch_naver_themes(code)
        out["themes"] = themes[:5]
    except Exception:
        pass

    # 한 줄 메모 = 업종 + 첫 테마 1-2개
    parts = []
    if out["sector"]:
        parts.append(out["sector"])
    if out["themes"]:
        parts.append(" / ".join(out["themes"][:2]))
    out["memo"] = " · ".join(parts)[:60]

    return out


def _fetch_naver_themes(code: str) -> list[str]:
    """종목 테마 페이지에서 테마명 추출."""
    url = f"https://finance.naver.com/item/coinfo.naver?code={code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    r.encoding = "euc-kr"
    soup = BeautifulSoup(r.text, "html.parser")

    themes: list[str] = []
    # 테마 링크는 보통 wics/wi/theme 형태 페이지로 연결됨
    for a in soup.select("a"):
        href = a.get("href", "")
        if "theme" in href.lower() or "wics" in href.lower():
            text = a.get_text(strip=True)
            if 1 < len(text) < 20 and text not in themes:
                themes.append(text)
        if len(themes) >= 5:
            break

    return themes


# ───────────────────────────────────────────────────────
# 3. FDR fallback
# ───────────────────────────────────────────────────────
def _enrich_via_fdr(code: str, name: str) -> dict:
    """FDR StockListing 캐시에서 시장 정보만."""
    from pathlib import Path
    import pandas as pd

    cache_path = Path(__file__).parent / "data" / "krx_listing.csv"
    if not cache_path.exists():
        raise FileNotFoundError("krx_listing.csv 없음")

    df = pd.read_csv(cache_path, dtype={"Code": str})
    df["Code"] = df["Code"].astype(str).str.zfill(6)
    row = df[df["Code"] == code]
    if len(row) == 0:
        raise ValueError(f"종목 없음: {code}")

    row = row.iloc[0]
    market = str(row.get("Market", "")).strip() if "Market" in row else ""
    return {
        "market": market,
        "sector": "",
        "themes": [],
        "memo": market or "",
        "source": "fdr",
    }
