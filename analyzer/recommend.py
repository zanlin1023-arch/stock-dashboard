"""신규 종목 추천 — 매번 실시간 시장 데이터로 동적 후보 수집.

핵심 원칙:
1. 고정 리스트 없음 — 매번 시장에서 활성 종목 자동 수집
2. 4가지 소스 통합: 거래대금/상승률/거래량/시가총액 상위
3. ETF/ETN/우선주 자동 제외 → 일반 주식만
4. 시가총액별 Tier 자동 분류 (대형/중형/소형)
5. 사용자 보유 종목만 제외 (분석 요청 종목은 후보 유지)
"""
from __future__ import annotations

import re
import warnings
from typing import Any

import requests
from bs4 import BeautifulSoup

import market_context as mc

warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


# =========================================================
# 자동 제외 (보유 종목만)
# =========================================================

EXCLUDED_HOLDINGS = {
    "032820",  # 우리기술
    "080220",  # 제주반도체
    "347700",  # 스피어
    "389500",  # 에스비비테크
    "119830",  # 아이텍
    "006910",  # 보성파워텍
    "108490",  # 로보티즈
    "229640",  # LS에코에너지
}


# ETF/ETN/우선주 식별
ETF_KEYWORDS = [
    "KODEX", "TIGER", "KBSTAR", "ARIRANG", "HANARO", "SOL", "KOSEF",
    "KOACT", "ACE", "KIWOOM", "WOORI", "FOCUS", "TIMEFOLIO", "MASTER",
    "인버스", "레버리지", "선물", "ETN", "ETF", "Plus", "ATTACK",
    "VWAP", "WTI", "PLUS",
]


def is_normal_stock(name: str, code: str) -> bool:
    """ETF/ETN/우선주/스팩 등 제외 → 일반 주식만 True."""
    if not name or not code:
        return False
    # 우선주 (이름 끝에 '우')
    if name.endswith("우") or name.endswith("우B"):
        return False
    # ETF/ETN 키워드
    for kw in ETF_KEYWORDS:
        if kw in name:
            return False
    # 스팩
    if "스팩" in name or "SPAC" in name.upper():
        return False
    # 코드 6자리 숫자만
    if not re.fullmatch(r"\d{6}", code):
        return False
    return True


# =========================================================
# 1. 동적 후보 수집 (4가지 소스)
# =========================================================

def _scrape_stock_list(url: str, max_count: int = 50) -> list[tuple[str, str]]:
    """네이버 시세 페이지 스크래핑 → [(종목명, 코드)]."""
    out = []
    seen = set()
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        # 네이버 sise 페이지는 EUC-KR 인코딩 사용
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a.tltle"):
            name = a.get_text(strip=True)
            href = a.get("href", "")
            if "code=" not in href:
                continue
            code = href.split("code=")[-1].split("&")[0]
            if not is_normal_stock(name, code):
                continue
            if code in seen:
                continue
            seen.add(code)
            out.append((name, code))
            if len(out) >= max_count:
                break
    except Exception:
        pass
    return out


def collect_active_stocks(top_n: int = 40) -> dict[str, list]:
    """4가지 소스 × 2개 시장 = 8개 페이지에서 활성 종목 수집.

    매번 호출 시 시장 현재 상태로 새로 가져옴.
    """
    sources = [
        ("거래대금", "sise_quant.naver"),       # 거래대금 상위
        ("상승률", "sise_rise.naver"),          # 상승률 상위
        ("거래량", "sise_quant_vol.naver"),     # 거래량 상위
        ("시가총액", "sise_market_sum.naver"),  # 시가총액 상위 (대형주 보강)
    ]
    markets = [("KOSPI", "0"), ("KOSDAQ", "1")]

    candidates = {}  # code: {"name": ..., "sources": [...]}
    for src_name, path in sources:
        for mkt_name, sosok in markets:
            url = f"https://finance.naver.com/sise/{path}?sosok={sosok}"
            stocks = _scrape_stock_list(url, max_count=top_n)
            for name, code in stocks:
                if code not in candidates:
                    candidates[code] = {"name": name, "sources": [], "market": mkt_name}
                candidates[code]["sources"].append(f"{mkt_name}-{src_name}")

    return candidates


# =========================================================
# 2. 시가총액 + Tier 분류
# =========================================================

def get_stock_info(code: str) -> dict:
    """종목 정보 — 모바일 API(시세) + PC 메인(시가총액) 결합."""
    info = {"name": "", "close": 0, "change_pct": "0", "market_cap_eok": 0}

    # 1. 모바일 API: 시세
    try:
        r = requests.get(
            f"https://m.stock.naver.com/api/stock/{code}/basic",
            headers=HEADERS, timeout=5,
        )
        d = r.json()

        def _f(v):
            try:
                if isinstance(v, str):
                    return float(v.replace(",", "").replace("원", ""))
                return float(v)
            except (ValueError, TypeError):
                return 0

        info["name"] = d.get("stockName", "")
        info["close"] = _f(d.get("closePrice"))
        info["change_pct"] = d.get("fluctuationsRatio", "0")
    except Exception:
        pass

    # 2. PC 메인: 시가총액 (네이버 모바일 API에는 없음)
    try:
        r = requests.get(
            f"https://finance.naver.com/item/main.naver",
            params={"code": code},
            headers=HEADERS, timeout=5,
        )
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        cap_em = soup.select_one("em#_market_sum")
        if cap_em:
            txt = cap_em.parent.get_text(separator=" ", strip=True) if cap_em.parent else cap_em.get_text(strip=True)
            # "1,543조 4,176억원" 또는 "5,234억원"
            jo_match = re.search(r"([\d,]+)\s*조", txt)
            eok_match = re.search(r"([\d,]+)\s*억", txt)
            jo = int(jo_match.group(1).replace(",", "")) if jo_match else 0
            eok = int(eok_match.group(1).replace(",", "")) if eok_match else 0
            info["market_cap_eok"] = jo * 10000 + eok  # 조 → 만억 환산
    except Exception:
        pass

    return info


def classify_tier(market_cap_eok: int) -> str:
    """시가총액(억원) → Tier."""
    if market_cap_eok >= 50_000:  # 5조+
        return "large"
    elif market_cap_eok >= 5_000:  # 5천억~5조
        return "mid"
    elif market_cap_eok >= 500:  # 500억~5천억
        return "small"
    return "tiny"  # 500억 미만 (제외)


# =========================================================
# 3. 종목 평가 (일별 흐름 + 수급 + 점수)
# =========================================================

def evaluate_stock(code: str, name: str, market_cap_eok: int, price: float = 0, change_pct: str = "0") -> dict:
    """종목 종합 평가 — 펀더 점수 + 모멘텀 점수 둘 다 계산."""
    # 일별 흐름 (선행 시그널) - 일별 데이터 1회 호출
    daily = mc.get_daily_flow(code, days=10)
    reversal = mc.detect_flow_reversal(code, lookback=7)
    verdict = reversal.get("verdict", "?") if reversal.get("available") else "?"

    # 일별 데이터에서 누적 직접 계산
    f5 = sum(r.get("foreign_net", 0) for r in daily[:5])
    i5 = sum(r.get("inst_net", 0) for r in daily[:5])
    f_streak = 0
    for r in daily:
        if r.get("foreign_net", 0) > 0:
            f_streak += 1
        else:
            break
    if daily and daily[0].get("close"):
        f5 = f5 * daily[0]["close"] / 1e8
        i5 = i5 * daily[0]["close"] / 1e8

    # 모멘텀 점수 (try momentum_signal.py)
    momentum_buy_score = 0
    momentum_signals = []
    try:
        import momentum_signal as ms
        buy_result = ms.detect_buy_signals(code, name)
        if buy_result.get("available"):
            momentum_buy_score = buy_result.get("score", 0)
            momentum_signals = buy_result.get("signals", [])
    except Exception:
        pass

    # 점수 계산
    score = 0
    if "동반 매수" in verdict:
        score += 30
    elif "매수 전환" in verdict:
        score += 20
    elif "매도 전환" in verdict:
        score -= 20
    elif "동반 매도" in verdict:
        score -= 30

    # 시총별 매수 금액 임계값
    if market_cap_eok >= 50_000:
        threshold = 500  # 대형주: 500억+
    elif market_cap_eok >= 5_000:
        threshold = 100  # 중형주: 100억+
    else:
        threshold = 30   # 소형주: 30억+

    if f5 > threshold:
        score += 10
    if i5 > threshold:
        score += 10
    if f_streak >= 5:
        score += 15
    elif f_streak >= 3:
        score += 5

    # 추천 이유 시그널 모음 (사람이 읽을 수 있는 형태)
    signals: list[str] = []
    if "동반 매수" in verdict:
        signals.append("🟢 외인+기관 동반 매수")
    elif "매수 전환" in verdict:
        signals.append("🟢 수급 매수 전환")
    elif "동반 매도" in verdict:
        signals.append("🔴 외인+기관 동반 매도")
    elif "매도 전환" in verdict:
        signals.append("🔴 수급 매도 전환")
    if f_streak >= 5:
        signals.append(f"🔥 외인 {f_streak}일 연속 순매수")
    elif f_streak >= 3:
        signals.append(f"📈 외인 {f_streak}일 순매수")
    if f5 > threshold:
        signals.append(f"💰 외인 5일 +{int(f5):,}억 매수 (임계 {threshold}억↑)")
    if i5 > threshold:
        signals.append(f"🏦 기관 5일 +{int(i5):,}억 매수 (임계 {threshold}억↑)")
    for s in momentum_signals:
        if isinstance(s, (list, tuple)) and len(s) >= 2:
            region = str(s[0])
            label = str(s[1])
            sc = s[2] if len(s) > 2 else None
            detail = str(s[3]) if len(s) > 3 and s[3] else ""
            region_emoji = "🌍" if "글로벌" in region else "🇰🇷"
            sc_str = f" (+{int(sc)}점)" if isinstance(sc, (int, float)) and sc else ""
            detail_str = f" — {detail}" if detail else ""
            text = f"{region_emoji} {label}{detail_str}{sc_str}"
            if text not in signals:
                signals.append(text)
        elif isinstance(s, str) and s and s not in signals:
            signals.append(s)
    foreign_5d_eok = int(round(f5))
    inst_5d_eok = int(round(i5))

    # 섹터/테마 (1회만 — 캐시 활용)
    sector_name = ""
    try:
        import sector_compare as _sc
        sec = _sc.compare_to_peers(code, max_peers=1)
        sector_name = sec.get("sector_name") or ""
    except Exception:
        pass

    return {
        "name": name,
        "code": code,
        "price": price,
        "change_pct": change_pct,
        "market_cap_eok": market_cap_eok,
        "tier": classify_tier(market_cap_eok),
        "verdict": verdict,
        "f5": f5,
        "i5": i5,
        "f_streak": f_streak,
        "score": score,
        "momentum_score": momentum_buy_score,
        "total_score": score + (momentum_buy_score * 0.5),
        "signals": signals,
        "foreign_5d": foreign_5d_eok,
        "inst_5d": inst_5d_eok,
        "sector_name": sector_name,
    }


# =========================================================
# 4. 메인 추천 함수
# =========================================================

def recommend(top_n_per_tier: int = 3, exclude: set | None = None,
              n_per_source: int = 20) -> dict:
    """매번 시장 현재 상태로 동적 추천.

    1. 4가지 소스에서 활성 종목 수집 (~150개)
    2. ETF/우선주 자동 제외
    3. 보유 종목 제외
    4. 종목별 평가
    5. Tier별 상위 N개 반환
    """
    excluded = exclude if exclude is not None else EXCLUDED_HOLDINGS

    print(f"[*] 동적 후보 수집 중 (시장 현재 상태)...")
    candidates = collect_active_stocks(top_n=n_per_source)
    print(f"[*] {len(candidates)}개 활성 종목 발견")

    # 보유 종목 제외
    candidates = {c: v for c, v in candidates.items() if c not in excluded}
    print(f"[*] 보유 제외 후 {len(candidates)}개")

    # 종목별 평가 — get_stock_info는 1회만 호출
    print(f"[*] 일별 흐름 + 수급 분석 중 ({len(candidates)}개)...")
    evaluated = []
    processed = 0
    for code, info in candidates.items():
        try:
            stock_info = get_stock_info(code)
            mc_eok = stock_info.get("market_cap_eok", 0)
            if mc_eok < 500:  # 500억 미만 제외
                continue
            result = evaluate_stock(
                code, info["name"], mc_eok,
                price=stock_info.get("close", 0),
                change_pct=stock_info.get("change_pct", "0"),
            )
            result["sources"] = info["sources"]
            evaluated.append(result)
            processed += 1
            if processed % 20 == 0:
                print(f"   진행: {processed}개")
        except Exception:
            continue

    # Tier별 분류 + 정렬
    by_tier = {"large": [], "mid": [], "small": []}
    for r in evaluated:
        tier = r["tier"]
        if tier in by_tier:
            by_tier[tier].append(r)

    # 종합 점수(펀더 + 모멘텀 50%) 기준으로 정렬
    for tier in by_tier:
        by_tier[tier].sort(key=lambda x: -x.get("total_score", x.get("score", 0)))

    return {
        "large": by_tier["large"][:top_n_per_tier],
        "mid": by_tier["mid"][:top_n_per_tier],
        "small": by_tier["small"][:top_n_per_tier],
        "total_scanned": len(candidates),
    }


# =========================================================
# Markdown 출력
# =========================================================

def to_markdown(results: dict) -> str:
    lines = ["# 🎯 신규 종목 추천 — 실시간 동적 수집", ""]
    lines.append(f"_총 {results.get('total_scanned', 0)}개 활성 종목 스캔 (거래대금/상승률/거래량/시가총액 상위)_")
    lines.append("")

    tier_labels = {
        "large": ("🏛️ 대형주 (시총 5조+)", "안정성 우선"),
        "mid": ("🏢 중형주 (시총 5천억~5조)", "균형 (성장+안정)"),
        "small": ("🏠 소형주 (시총 500억~5천억)", "변동성 큼, 수익률 ↑"),
    }

    for tier_key in ["large", "mid", "small"]:
        label, desc = tier_labels[tier_key]
        stocks = results.get(tier_key, [])
        lines += ["", f"## {label}", f"_{desc}_", ""]

        if not stocks:
            lines.append("- (추천 종목 없음)")
            continue

        lines += [
            "| 순위 | 종목 | 코드 | 현재가 | 오늘 | 시총(억) | 시그널 | 외인 5일 | 펀더 점수 | 모멘텀 점수 |",
            "|------|------|------|--------|------|---------|--------|---------|---------|---------|",
        ]
        for i, s in enumerate(stocks, 1):
            short_verdict = s["verdict"].replace("매수 시그널", "").replace("약세 시그널", "").replace("강세 시그널", "").strip()[:25]
            mom_score = s.get("momentum_score", 0)
            lines.append(
                f"| {i} | **{s['name']}** | {s['code']} | {s['price']:,.0f} | "
                f"{s['change_pct']}% | {s['market_cap_eok']:,} | {short_verdict} | "
                f"{s['f5']:+.0f}억 ({s['f_streak']}일) | **{s['score']:+d}** | **{mom_score:+d}** |"
            )

    all_results = results.get("large", []) + results.get("mid", []) + results.get("small", [])
    if all_results:
        lines += [
            "",
            "## 📊 종합 통계",
            f"- 스캔된 활성 종목: {results.get('total_scanned', 0)}개",
            f"- 추천 종목: {len(all_results)}개",
            f"- 동반 매수: {sum(1 for s in all_results if '동반 매수' in s['verdict'])}개",
            f"- 매수 전환: {sum(1 for s in all_results if '매수 전환' in s['verdict'])}개",
            f"- 매도 시그널: {sum(1 for s in all_results if '매도' in s['verdict'])}개",
        ]

    lines += [
        "",
        "---",
        "> 🔄 매번 호출 시 시장 현재 상태로 동적 수집 (고정 리스트 없음)",
        "> 📊 4개 소스 × 2개 시장: 거래대금/상승률/거래량/시가총액 상위",
        "> 🚫 ETF/ETN/우선주/스팩 자동 제외",
        "> 💼 보유 종목 자동 제외 (분석 요청 종목은 포함)",
        "> ⚠️ 점수: 동반매수(+30) / 매수전환(+20) / 외인5일(+10) / 기관5일(+10) / 연속매수(+15)",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(f"🔍 신규 종목 추천 스캔 중 (Tier별 상위 {top_n}개)...")
    print()
    results = recommend(top_n_per_tier=top_n)
    print(to_markdown(results))
