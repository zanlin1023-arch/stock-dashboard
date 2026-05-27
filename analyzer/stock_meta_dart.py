"""DART OpenAPI 기반 종목 메타 정보 조회.

종목코드 → 회사명 / 업종(KSIC) / 대표자 / 홈페이지 등 회사 개황 조회.
- corpCode.xml: 종목코드 → corp_code 매핑 (1회 다운로드 + 1주일 캐시)
- company.json: corp_code → 회사 개황 (종목당 24h 캐시)
"""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import requests
import streamlit as st


DART_BASE = "https://opendart.fss.or.kr/api"
CACHE_DIR = Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)
CORP_CODE_FILE = CACHE_DIR / "corp_code.xml"


def _get_api_key() -> str:
    return os.getenv("OPENDART_API_KEY", "")


@st.cache_data(ttl=604800, show_spinner=False)  # 1주일 캐시
def _load_corp_code_map() -> dict:
    """종목코드(zfill 6) → {corp_code, corp_name} 매핑.

    파일 없으면 DART에서 zip 다운로드 → xml 추출 → 캐시.
    """
    key = _get_api_key()
    if not key:
        return {}
    try:
        if not CORP_CODE_FILE.exists():
            r = requests.get(
                f"{DART_BASE}/corpCode.xml",
                params={"crtfc_key": key},
                timeout=30,
            )
            r.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                xml_data = zf.read(zf.namelist()[0])
            CORP_CODE_FILE.write_bytes(xml_data)
        root = ET.fromstring(CORP_CODE_FILE.read_bytes())
        out: dict[str, dict] = {}
        for item in root.findall("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            name = (item.findtext("corp_name") or "").strip()
            if stock and corp and stock.isdigit():
                out[stock.zfill(6)] = {"corp_code": corp, "corp_name": name}
        return out
    except Exception:
        return {}


@st.cache_data(ttl=86400, show_spinner=False)  # 24시간 캐시
def get_company_info(stock_code: str) -> dict:
    """종목코드로 회사 개황 조회.

    Returns:
        {
            "company_name": str,
            "sector": str,        # 업종명 (KSIC)
            "induty_code": str,   # 업종 코드
            "ceo": str,           # 대표자
            "homepage": str,      # 홈페이지
            "est_date": str,      # 설립일 YYYYMMDD
            "phone": str,
            "address": str,
        }
        실패/매핑 없음 시 빈 dict
    """
    key = _get_api_key()
    if not key or not stock_code:
        return {}
    code6 = stock_code.zfill(6)
    corp_map = _load_corp_code_map()
    info = corp_map.get(code6)
    if not info:
        return {}
    corp_code = info["corp_code"]
    try:
        r = requests.get(
            f"{DART_BASE}/company.json",
            params={"crtfc_key": key, "corp_code": corp_code},
            timeout=10,
        )
        data = r.json()
        if data.get("status") != "000":
            return {}
        return {
            "company_name": data.get("corp_name") or info["corp_name"],
            "sector": (data.get("induty") or "").strip(),
            "induty_code": (data.get("induty_code") or "").strip(),
            "ceo": (data.get("ceo_nm") or "").strip(),
            "homepage": (data.get("hm_url") or "").strip(),
            "est_date": (data.get("est_dt") or "").strip(),
            "phone": (data.get("phn_no") or "").strip(),
            "address": (data.get("adres") or "").strip(),
        }
    except Exception:
        return {}


def get_sector(stock_code: str) -> str:
    """편의 함수: 종목코드 → 업종명 (없으면 빈 string)."""
    return get_company_info(stock_code).get("sector", "")
