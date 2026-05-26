"""기본적 분석: PER/PBR/ROE/부채비율 + 재무제표 추이 + 증권사 컨센서스."""
from __future__ import annotations

import re
import warnings
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

from _utils import fmt_num, fmt_pct, get_dart_key

FNGUIDE_URL = "http://comp.fnguide.com/SVO2/asp/SVD_Main.asp"
NAVER_RESEARCH_LIST = "https://finance.naver.com/research/company_list.naver"
NAVER_RESEARCH_DETAIL = "https://finance.naver.com/research/company_read.naver"


def fetch_broker_targets(code: str, limit: int = 10) -> list[dict]:
    """네이버 금융 리서치 페이지에서 개별 증권사 목표가 + 투자의견 수집."""
    out = []
    try:
        list_resp = requests.get(
            NAVER_RESEARCH_LIST,
            params={"searchType": "itemCode", "itemCode": code},
            headers=HEADERS,
            timeout=10,
        )
        list_resp.encoding = list_resp.apparent_encoding or "utf-8"
        list_soup = BeautifulSoup(list_resp.text, "html.parser")
    except Exception:
        return out

    rows = list_soup.select("table.type_1 tr")
    candidates = []
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) < 5:
            continue
        title_a = tds[1].find("a") if len(tds) > 1 else None
        if not title_a:
            continue
        href = title_a.get("href", "")
        nid_match = re.search(r"nid=(\d+)", href)
        if not nid_match:
            continue
        nid = nid_match.group(1)
        broker = tds[2].get_text(strip=True) if len(tds) > 2 else ""
        date = tds[4].get_text(strip=True) if len(tds) > 4 else ""
        title = title_a.get_text(strip=True)
        candidates.append({"nid": nid, "broker": broker, "date": date, "title": title})
        if len(candidates) >= limit * 2:  # 여유있게
            break

    # 각 리포트 상세 페이지에서 목표가 추출
    for c in candidates:
        if len(out) >= limit:
            break
        try:
            detail_resp = requests.get(
                NAVER_RESEARCH_DETAIL,
                params={"nid": c["nid"]},
                headers=HEADERS,
                timeout=8,
            )
            detail_resp.encoding = detail_resp.apparent_encoding or "utf-8"
            detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
            text = detail_soup.get_text(separator=" ", strip=True)

            # "목표가 330,000 | 투자의견 Buy" 패턴
            target_match = re.search(r"목표가\s*([\d,]+)", text)
            opinion_match = re.search(r"투자의견\s*([A-Za-z가-힣\s/]+?)(?:\s|\||$)", text)

            if target_match:
                target = int(target_match.group(1).replace(",", ""))
                opinion = opinion_match.group(1).strip() if opinion_match else "-"
                out.append({
                    "broker": c["broker"],
                    "date": c["date"],
                    "title": c["title"],
                    "target_price": target,
                    "opinion": opinion,
                    "url": f"{NAVER_RESEARCH_DETAIL}?nid={c['nid']}",
                })
        except Exception:
            continue

    return out


def fetch_broker_consensus(code: str) -> dict[str, Any] | None:
    """FnGuide에서 증권사 컨센서스 (목표주가/투자의견/EPS/PER) 추출."""
    try:
        resp = requests.get(
            FNGUIDE_URL,
            params={"gicode": f"A{code.zfill(6)}", "cID": "", "MenuYn": "Y", "ReportGB": "", "NewMenuID": "Y", "stkGb": "701"},
            headers=HEADERS,
            timeout=10,
        )
        resp.encoding = resp.apparent_encoding or "utf-8"
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)

    # "투자의견 목표주가 EPS PER 추정기관수" 다음에 숫자들이 옴
    pattern = re.search(
        r"투자의견\s*목표주가\s*EPS\s*PER\s*추정기관수\s+(\d+\.?\d*)\s+([\d,]+)\s+([\d,]+)\s+([\d.\-]+)\s+(\d+)",
        text,
    )
    if not pattern:
        return None

    try:
        opinion = float(pattern.group(1))
        target_price = int(pattern.group(2).replace(",", ""))
        eps_est = int(pattern.group(3).replace(",", ""))
        per_est = float(pattern.group(4).replace(",", "").replace("-", "0"))
        n_brokers = int(pattern.group(5))
    except (ValueError, AttributeError):
        return None

    # 투자의견 라벨
    opinion_labels = {
        5: "매수 (Buy)",
        4: "비중확대 (O/Weight)",
        3: "중립 (Neutral)",
        2: "비중축소 (U/Weight)",
        1: "매도 (Sell)",
    }
    nearest = round(opinion)
    opinion_label = opinion_labels.get(nearest, f"{opinion:.1f}/5")

    return {
        "target_price": target_price,
        "investment_opinion": opinion,
        "opinion_label": opinion_label,
        "eps_estimate": eps_est,
        "per_estimate": per_est,
        "n_brokers": n_brokers,
        "source": "FnGuide",
    }

warnings.filterwarnings("ignore")

NAVER_MAIN_URL = "https://finance.naver.com/item/main.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


def _parse_num(text: str | None) -> float | None:
    if not text:
        return None
    s = text.strip().replace(",", "")
    if not s or s in ("-", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(\.\d+)?", s)
        return float(m.group(0)) if m else None


def fetch_naver_ratios(code: str) -> dict[str, Any]:
    """네이버 금융 메인 페이지에서 PER/PBR/EPS/BPS/배당수익률/시총 추출."""
    try:
        resp = requests.get(NAVER_MAIN_URL, params={"code": code}, headers=HEADERS, timeout=10)
        resp.encoding = resp.apparent_encoding or "utf-8"
        resp.raise_for_status()
    except Exception:
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")

    def _em(sid: str) -> float | None:
        em = soup.select_one(f"em#{sid}")
        return _parse_num(em.get_text() if em else None)

    # 시가총액: "1,543조 4,176억원" 형식 파싱
    market_cap = None
    cap_em = soup.select_one("em#_market_sum")
    if cap_em:
        parent_txt = cap_em.parent.get_text(separator=" ", strip=True) if cap_em.parent else cap_em.get_text(strip=True)
        # "1,543조 4,176억원"에서 조와 억 추출
        jo_match = re.search(r"([\d,]+)\s*조", parent_txt)
        eok_match = re.search(r"([\d,]+)\s*억", parent_txt)
        jo = int(jo_match.group(1).replace(",", "")) if jo_match else 0
        eok = int(eok_match.group(1).replace(",", "")) if eok_match else 0
        market_cap = jo * 1_000_000_000_000 + eok * 100_000_000  # 원 단위
        if market_cap == 0:
            # fallback: 그냥 숫자만 있는 경우 (억원 단위로 가정)
            m = re.search(r"[\d,]+", parent_txt)
            if m:
                try:
                    market_cap = int(m.group(0).replace(",", "")) * 100_000_000
                except ValueError:
                    market_cap = None

    return {
        "as_of": datetime.now().strftime("%Y%m%d"),
        "per": _em("_per"),
        "pbr": _em("_pbr"),
        "eps": _em("_eps"),
        "bps": _em("_bps"),
        "div_yield": _em("_dvr"),
        "dps": None,
        "market_cap": market_cap,
        "shares": None,
        "source": "naver",
    }


def fetch_market_ratios(code: str) -> dict[str, Any]:
    """pykrx로 PER/PBR/배당수익률/시총 조회 (가장 최근 영업일)."""
    from pykrx import stock

    # 종목별 시계열 조회 (최근 30일 중 가장 최근 영업일 자동 선택)
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=30)).strftime("%Y%m%d")

    try:
        df_fund = stock.get_market_fundamental_by_date(start, end, code)
    except Exception:
        df_fund = None

    if df_fund is None or df_fund.empty:
        return {}

    last = df_fund.iloc[-1]
    as_of = df_fund.index[-1].strftime("%Y%m%d") if hasattr(df_fund.index[-1], "strftime") else str(df_fund.index[-1])

    # 시가총액
    market_cap = None
    shares = None
    try:
        df_cap = stock.get_market_cap_by_date(start, end, code)
        if df_cap is not None and not df_cap.empty:
            cap_row = df_cap.iloc[-1]
            market_cap = int(cap_row["시가총액"])
            shares = int(cap_row["상장주식수"])
    except Exception:
        pass

    def _f(v):
        try:
            v = float(v)
            return v if v != 0 else None
        except Exception:
            return None

    return {
        "as_of": as_of,
        "per": _f(last.get("PER")),
        "pbr": _f(last.get("PBR")),
        "eps": _f(last.get("EPS")),
        "bps": _f(last.get("BPS")),
        "div_yield": _f(last.get("DIV")),
        "dps": _f(last.get("DPS")),
        "market_cap": market_cap,
        "shares": shares,
    }


def fetch_financials(code: str) -> dict[str, Any]:
    """OpenDART에서 최근 3년 재무제표 추출."""
    import OpenDartReader

    dart = OpenDartReader(get_dart_key())
    current_year = datetime.now().year

    rows = []
    for y in range(current_year - 3, current_year + 1):
        try:
            fs = dart.finstate(code, y)
            if fs is None or len(fs) == 0:
                continue
            fs = fs[fs["fs_div"] == "CFS"] if "fs_div" in fs.columns else fs
            rows.append((y, fs))
        except Exception:
            continue

    if not rows:
        return {"available": False}

    def get_amount(fs_df: pd.DataFrame, account_keywords: list[str]) -> float | None:
        for kw in account_keywords:
            mask = fs_df["account_nm"].str.contains(kw, na=False)
            sub = fs_df[mask]
            if len(sub) > 0:
                amt = sub.iloc[0].get("thstrm_amount", "0")
                try:
                    return float(str(amt).replace(",", ""))
                except Exception:
                    continue
        return None

    series = []
    for year, fs in rows:
        revenue = get_amount(fs, ["매출액", "수익(매출액)", "영업수익"])
        op_income = get_amount(fs, ["영업이익"])
        net_income = get_amount(fs, ["당기순이익"])
        assets = get_amount(fs, ["자산총계"])
        equity = get_amount(fs, ["자본총계"])
        liabilities = get_amount(fs, ["부채총계"])
        series.append({
            "year": year,
            "revenue": revenue,
            "operating_income": op_income,
            "net_income": net_income,
            "assets": assets,
            "equity": equity,
            "liabilities": liabilities,
            "operating_margin": (op_income / revenue * 100) if revenue and op_income else None,
            "net_margin": (net_income / revenue * 100) if revenue and net_income else None,
            "roe": (net_income / equity * 100) if equity and net_income else None,
            "debt_ratio": (liabilities / equity * 100) if equity and liabilities else None,
        })

    # 매출 성장률
    for i in range(1, len(series)):
        prev_rev = series[i-1]["revenue"]
        curr_rev = series[i]["revenue"]
        if prev_rev and curr_rev:
            series[i]["revenue_growth"] = (curr_rev / prev_rev - 1) * 100
        else:
            series[i]["revenue_growth"] = None

    return {"available": True, "years": series}


def analyze(code: str, name: str) -> dict[str, Any]:
    ratios = fetch_market_ratios(code)
    if not ratios or not ratios.get("per"):
        ratios = fetch_naver_ratios(code)
    fin = fetch_financials(code)
    consensus = fetch_broker_consensus(code)
    broker_targets = fetch_broker_targets(code, limit=10)
    return {
        "code": code,
        "name": name,
        "ratios": ratios,
        "financials": fin,
        "consensus": consensus,
        "broker_targets": broker_targets,
    }


def _fmt_market_cap(v) -> str:
    if not v:
        return "-"
    jo = v // 1_000_000_000_000
    eok = (v % 1_000_000_000_000) // 100_000_000
    if jo > 0:
        return f"{jo:,}조 {eok:,}억원"
    return f"{eok:,}억원"


def to_markdown(result: dict) -> str:
    r = result.get("ratios") or {}
    f = result.get("financials") or {}
    c = result.get("consensus")

    lines = [
        "## 📊 기본적 분석",
        "",
    ]

    # 증권사 컨센서스 (있으면 가장 먼저)
    if c:
        target = c["target_price"]
        lines += [
            "### 🎯 증권사 컨센서스 (FnGuide 평균)",
            "",
            f"| 항목 | 값 |",
            f"|------|-----|",
            f"| **평균 목표주가** | **{target:,}원** |",
            f"| 투자의견 | {c['opinion_label']} ({c['investment_opinion']:.1f}/5) |",
            f"| 추정 EPS | {c['eps_estimate']:,}원 |",
            f"| 추정 PER | {c['per_estimate']:.2f}배 |",
            f"| 추정 기관 수 | {c['n_brokers']}개 |",
            "",
        ]

    # 개별 증권사 목표가 리스트
    targets = result.get("broker_targets") or []
    if targets:
        # 통계
        prices = [t["target_price"] for t in targets if t.get("target_price")]
        if prices:
            avg_target = sum(prices) / len(prices)
            min_target = min(prices)
            max_target = max(prices)
            lines += [
                f"### 📑 개별 증권사 목표가 ({len(targets)}개 — 네이버 리서치)",
                "",
                f"- 최고: **{max_target:,}원** / 최저: **{min_target:,}원** / 평균: **{avg_target:,.0f}원**",
                "",
                "| 작성일 | 증권사 | 목표가 | 의견 | 리포트 제목 |",
                "|--------|--------|--------|------|-------------|",
            ]
            for t in targets:
                title_short = t["title"][:35] + "…" if len(t["title"]) > 35 else t["title"]
                lines.append(
                    f"| {t['date']} | {t['broker']} | {t['target_price']:,}원 | {t['opinion']} | "
                    f"[{title_short}]({t['url']}) |"
                )
            lines.append("")

    lines += [
        f"### 시장 지표 (기준일: {r.get('as_of', '-')})",
        f"| 지표 | 값 |",
        f"|------|-----|",
        f"| 시가총액 | {_fmt_market_cap(r.get('market_cap'))} |",
        f"| PER | {fmt_num(r.get('per'))}배 |",
        f"| PBR | {fmt_num(r.get('pbr'))}배 |",
        f"| EPS | {fmt_num(r.get('eps'))}원 |",
        f"| BPS | {fmt_num(r.get('bps'))}원 |",
        f"| 배당수익률 | {fmt_num(r.get('div_yield'))}% |",
        f"| 주당배당금 | {fmt_num(r.get('dps'))}원 |",
        "",
    ]

    if not f.get("available"):
        lines.append("> ⚠️ 재무제표 데이터 없음 (OpenDART)")
        return "\n".join(lines)

    years = f["years"]
    lines += [
        "### 재무제표 추이 (단위: 억원)",
        "| 항목 | " + " | ".join(str(y["year"]) for y in years) + " |",
        "|------|" + "|".join(["-----"] * len(years)) + "|",
    ]

    def row(label: str, key: str, divisor: float = 1e8, suffix: str = ""):
        vals = []
        for y in years:
            v = y.get(key)
            vals.append(fmt_num(v / divisor) if v is not None else "-")
        return f"| {label} | " + " | ".join(vals) + " |"

    lines.append(row("매출액", "revenue"))
    lines.append(row("영업이익", "operating_income"))
    lines.append(row("당기순이익", "net_income"))
    lines.append(row("자산총계", "assets"))
    lines.append(row("자본총계", "equity"))
    lines.append(row("부채총계", "liabilities"))

    lines += ["", "### 수익성/안정성"]
    lines.append("| 항목 | " + " | ".join(str(y["year"]) for y in years) + " |")
    lines.append("|------|" + "|".join(["-----"] * len(years)) + "|")

    def pct_row(label: str, key: str):
        vals = []
        for y in years:
            v = y.get(key)
            vals.append(f"{v:.2f}%" if v is not None else "-")
        return f"| {label} | " + " | ".join(vals) + " |"

    lines.append(pct_row("영업이익률", "operating_margin"))
    lines.append(pct_row("순이익률", "net_margin"))
    lines.append(pct_row("ROE", "roe"))
    lines.append(pct_row("부채비율", "debt_ratio"))
    lines.append(pct_row("매출 성장률", "revenue_growth"))

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    from _utils import resolve_ticker

    q = sys.argv[1] if len(sys.argv) > 1 else "005930"
    code, name = resolve_ticker(q)
    r = analyze(code, name)
    print(to_markdown(r))
