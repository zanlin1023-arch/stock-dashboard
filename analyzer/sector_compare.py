"""동종업종 비교 — 네이버 업종 페이지 기반.

특정 종목의 섹터 페이지에서 같은 업종의 상위 종목 추출 + 가격/등락률 비교.
"""
from __future__ import annotations

import re
import warnings

import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


def get_sector_no(code: str) -> str | None:
    """종목 페이지에서 업종 코드(no) 추출."""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        # 업종 링크 — sise_group_detail.naver?type=upjong&no=XXX
        a = soup.select_one("a[href*='upjong&no=']")
        if a:
            m = re.search(r"no=(\d+)", a.get("href", ""))
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


def get_sector_peers(sector_no: str, max_count: int = 10) -> list[dict]:
    """업종 페이지에서 동종 종목 리스트 추출.

    Returns: [{"code": str, "name": str, "price": float, "change_pct": float}, ...]
    """
    if not sector_no:
        return []
    url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={sector_no}"
    out = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        for tr in soup.select("table.type_5 tr"):
            tds = tr.find_all("td")
            if len(tds) < 8:
                continue
            link = tds[0].find("a")
            if not link:
                continue
            href = link.get("href", "")
            m = re.search(r"code=(\d{6})", href)
            if not m:
                continue
            code = m.group(1)
            name = link.get_text(strip=True)
            # 현재가
            try:
                price = float(tds[1].get_text(strip=True).replace(",", ""))
            except Exception:
                price = 0.0
            # 등락률
            try:
                pct_txt = tds[3].get_text(strip=True).replace("%", "").replace(",", "")
                change_pct = float(pct_txt)
                if tr.select_one(".nv01") or tr.select_one(".tah.p11.nv01"):
                    change_pct = -abs(change_pct)
            except Exception:
                change_pct = 0.0
            out.append({
                "code": code,
                "name": name,
                "price": price,
                "change_pct": change_pct,
            })
            if len(out) >= max_count:
                break
    except Exception:
        pass
    return out


def get_sector_name(sector_no: str) -> str:
    """업종명 추출."""
    if not sector_no:
        return ""
    url = f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={sector_no}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.select_one("div.h_sub h2, .sub_h h3, .top_lst h3")
        if title:
            return title.get_text(strip=True)
    except Exception:
        pass
    return ""


def compare_to_peers(code: str, max_peers: int = 10) -> dict:
    """동종업종 비교 통합 조회.

    Returns:
        {
            "sector_no": str,
            "sector_name": str,
            "peers": [...],
            "self_in_peers": bool,
        }
    """
    sector_no = get_sector_no(code)
    if not sector_no:
        return {"sector_no": None, "sector_name": "", "peers": [], "self_in_peers": False}
    sector_name = get_sector_name(sector_no)
    peers = get_sector_peers(sector_no, max_count=max_peers)
    self_in = any(p["code"] == code for p in peers)
    return {
        "sector_no": sector_no,
        "sector_name": sector_name,
        "peers": peers,
        "self_in_peers": self_in,
    }
