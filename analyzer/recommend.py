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

def _get_us_movers() -> list[dict]:
    """미장 주요 종목 어제 등락률."""
    import FinanceDataReader as fdr
    import datetime as dt
    tickers = {
        "NVDA": "엔비디아", "AMD": "AMD", "TSM": "TSMC",
        "AAPL": "애플", "MSFT": "마이크로소프트", "GOOGL": "구글",
        "AMZN": "아마존", "META": "메타", "TSLA": "테슬라",
        "JPM": "JP모건", "XOM": "엑손모빌",
    }
    end = dt.date.today()
    start = end - dt.timedelta(days=10)
    movers = []
    for sym, name in tickers.items():
        try:
            df = fdr.DataReader(sym, start, end)
            if len(df) >= 2:
                close = float(df.iloc[-1]["Close"])
                prev = float(df.iloc[-2]["Close"])
                chg = (close / prev - 1) * 100
                movers.append({"ticker": sym, "name": name, "change": chg})
        except Exception:
            pass
    return movers


def _claude_sector_mapping(movers: list[dict]) -> dict:
    """Claude API로 미장 강세/약세 종목 → 한국 동조 섹터 매핑.

    Returns:
        {"strong": ["반도체", ...], "weak": ["통신서비스", ...]}
        실패/키 없음 시 빈 dict
    """
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or not movers:
        return {}
    strong = [m for m in movers if m["change"] >= 1.5]
    weak = [m for m in movers if m["change"] <= -1.5]
    if not strong and not weak:
        return {}
    s_str = ", ".join(f"{m['name']} +{m['change']:.1f}%" for m in strong) if strong else "(없음)"
    w_str = ", ".join(f"{m['name']} {m['change']:.1f}%" for m in weak) if weak else "(없음)"
    prompt = f"""미장 어제 종가 기준 주요 종목 등락:
- 강세 종목: {s_str}
- 약세 종목: {w_str}

이 흐름이 오늘 한국 코스피/코스닥에서 동조할 가능성이 높은 섹터를 매핑해줘.
- 한국 KSIC 업종명 기준 (예: "반도체와반도체장비", "자동차", "조선", "제약")
- 강세 미장 종목 → 한국 강세 후보 섹터
- 약세 미장 종목 → 한국 약세 후보 섹터
- 각 최대 5개

오직 JSON만 응답: {{"strong": ["섹터1", "섹터2"], "weak": ["섹터3"]}}"""
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""
        import json, re
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "strong": list(data.get("strong") or [])[:5],
                "weak": list(data.get("weak") or [])[:5],
            }
    except Exception as e:
        print(f"[WARN] Claude API 섹터 매핑 실패: {e}")
    return {}


def _claude_news_analysis() -> dict:
    """Claude API로 당일 시장 뉴스 → 한국 수혜/리스크 섹터 매핑.

    네이버 메인 뉴스 헤드라인 → Claude Haiku가 섹터 영향 분석.
    Returns: {"strong": [...], "weak": [...]} / 키 없거나 실패 시 {}
    """
    import os
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return {}
    try:
        news = mc.get_market_news(limit=12) or []
        titles = [n.get("title", "") for n in news if n.get("title")]
        if len(titles) < 3:
            return {}
        headlines = "\n".join(f"- {t}" for t in titles[:12])
        prompt = f"""오늘 한국 증시 주요 뉴스 헤드라인:
{headlines}

이 뉴스들이 오늘 한국 코스피/코스닥 섹터에 미칠 영향을 분석해줘.
- 전쟁/지정학/유가/금리/규제/실적 등 거시·이벤트 관점
- 수혜 섹터 (오를 가능성) / 리스크 섹터 (내릴 가능성)
- 한국 KSIC 업종명 기준 (예: "반도체와반도체장비", "방위산업", "정유", "항공운송")
- 각 최대 4개, 뉴스에 근거 없으면 빈 배열

오직 JSON만: {{"strong": ["섹터1"], "weak": ["섹터2"]}}"""
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text if resp.content else ""
        import json, re
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return {
                "strong": list(data.get("strong") or [])[:4],
                "weak": list(data.get("weak") or [])[:4],
            }
    except Exception as e:
        print(f"[WARN] Claude 뉴스 분석 실패: {e}")
    return {}


def get_overnight_context() -> dict:
    """morning 추천용 — 미장 종합 지수 + 환율 + Claude 섹터 매핑.

    Returns:
        {
            "available": bool,
            "global_score": int,
            "fx_krw": float,
            "fx_change_pct": float,
            "strong_sectors": list[str],   # Claude 매핑 강세 섹터
            "weak_sectors": list[str],     # Claude 매핑 약세 섹터
            "details": list[str],
        }
    """
    out = {
        "available": False, "global_score": 0,
        "fx_krw": 0, "fx_change_pct": 0,
        "wti_change": 0, "vix": 0, "vix_change": 0, "bond10y_change": 0,
        "vix_gate": 0,  # VIX 공포 게이트 (전 종목 페널티)
        "strong_sectors": [], "weak_sectors": [],
        "news_strong": [], "news_weak": [],  # Claude 뉴스 분석
        "details": [],
    }
    try:
        import FinanceDataReader as fdr
        import datetime as dt
        end = dt.date.today()
        start = end - dt.timedelta(days=10)

        # 미장 (어제 종가 + 전날 대비 % 평균)
        global_pcts = []
        for sym, label in [("IXIC", "나스닥"), ("US500", "S&P500"), ("DJI", "다우")]:
            try:
                df = fdr.DataReader(sym, start, end)
                if len(df) >= 2:
                    close = float(df.iloc[-1]["Close"])
                    prev = float(df.iloc[-2]["Close"])
                    chg = (close / prev - 1) * 100
                    global_pcts.append((label, chg))
            except Exception:
                pass
        if global_pcts:
            avg_global = sum(p for _, p in global_pcts) / len(global_pcts)
            # 미장 종합 점수 (-15 ~ +15)
            if avg_global >= 1.5:
                out["global_score"] = 15
                out["details"].append(f"🌍 미장 강세 (평균 +{avg_global:.2f}%) → 갭상승 가능")
            elif avg_global >= 0.5:
                out["global_score"] = 8
                out["details"].append(f"🌍 미장 상승 (+{avg_global:.2f}%)")
            elif avg_global <= -1.5:
                out["global_score"] = -15
                out["details"].append(f"🌍 미장 약세 ({avg_global:.2f}%) → 갭하락 우려")
            elif avg_global <= -0.5:
                out["global_score"] = -8
                out["details"].append(f"🌍 미장 하락 ({avg_global:.2f}%)")
            else:
                out["details"].append(f"🌍 미장 횡보 ({avg_global:+.2f}%)")

        # 환율 (USD/KRW)
        try:
            fx_df = fdr.DataReader("USD/KRW", start, end)
            if len(fx_df) >= 2:
                fx_close = float(fx_df.iloc[-1]["Close"])
                fx_prev = float(fx_df.iloc[-2]["Close"])
                fx_chg = (fx_close / fx_prev - 1) * 100
                out["fx_krw"] = fx_close
                out["fx_change_pct"] = fx_chg
                if fx_chg >= 0.3:
                    out["details"].append(f"💱 원화 약세 ({fx_close:,.0f}원, +{fx_chg:.2f}%) → 수출주 우대")
                elif fx_chg <= -0.3:
                    out["details"].append(f"💱 원화 강세 ({fx_close:,.0f}원, {fx_chg:.2f}%) → 내수주 우대")
                else:
                    out["details"].append(f"💱 환율 안정 ({fx_close:,.0f}원, {fx_chg:+.2f}%)")
        except Exception:
            pass

        # ── [A] 거시 지표: 유가(WTI) / VIX / 미국채 10년 ──
        def _chg(sym):
            try:
                d = fdr.DataReader(sym, start, end)
                if len(d) >= 2:
                    c, p = float(d.iloc[-1]["Close"]), float(d.iloc[-2]["Close"])
                    return c, (c / p - 1) * 100
            except Exception:
                pass
            return None, None

        # 유가 (정유/조선 ↑ vs 항공/운송 ↓)
        _, wti_chg = _chg("CL=F")
        if wti_chg is not None:
            out["wti_change"] = wti_chg
            if wti_chg >= 3:
                out["details"].append(f"🛢 유가 급등 (+{wti_chg:.1f}%) → 정유/조선 우대")
            elif wti_chg <= -3:
                out["details"].append(f"🛢 유가 급락 ({wti_chg:.1f}%) → 항공/운송 우대")

        # 미국채 10년 (성장주 ↓ vs 금융 ↑)
        _, bond_chg = _chg("US10YT")
        if bond_chg is not None:
            out["bond10y_change"] = bond_chg
            if bond_chg >= 2:
                out["details"].append(f"📈 美금리 급등 (+{bond_chg:.1f}%) → 성장주 부담/금융 우대")
            elif bond_chg <= -2:
                out["details"].append(f"📉 美금리 급락 ({bond_chg:.1f}%) → 성장주 우대")

        # ── [C] VIX 공포 게이트 ──
        vix_val, vix_chg = _chg("VIX")
        if vix_val is not None:
            out["vix"] = vix_val
            out["vix_change"] = vix_chg or 0
            if vix_val >= 30:
                out["vix_gate"] = -15
                out["details"].append(f"😱 VIX {vix_val:.1f} 극공포 → 전 종목 -15 (대형주 방어)")
            elif vix_val >= 25:
                out["vix_gate"] = -10
                out["details"].append(f"⚠️ VIX {vix_val:.1f} 공포 → 전 종목 -10 (보수 모드)")
            elif vix_val >= 20:
                out["vix_gate"] = -5
                out["details"].append(f"VIX {vix_val:.1f} 경계 → 전 종목 -5")

        # ── 🤖 [Claude] 미장 → 한국 섹터 동조 매핑 ──
        try:
            us_movers = _get_us_movers()
            mapping = _claude_sector_mapping(us_movers)
            if mapping:
                out["strong_sectors"] = mapping.get("strong", [])
                out["weak_sectors"] = mapping.get("weak", [])
                if out["strong_sectors"]:
                    out["details"].append(f"🤖 Claude 미장 매핑 강세: {', '.join(out['strong_sectors'])}")
                if out["weak_sectors"]:
                    out["details"].append(f"🤖 Claude 미장 매핑 약세: {', '.join(out['weak_sectors'])}")
        except Exception:
            pass

        # ── 🤖 [B] Claude 당일 뉴스 분석 → 리스크/수혜 섹터 ──
        try:
            news_map = _claude_news_analysis()
            if news_map:
                out["news_strong"] = news_map.get("strong", [])
                out["news_weak"] = news_map.get("weak", [])
                if out["news_strong"]:
                    out["details"].append(f"📰 뉴스 수혜 섹터: {', '.join(out['news_strong'])}")
                if out["news_weak"]:
                    out["details"].append(f"📰 뉴스 리스크 섹터: {', '.join(out['news_weak'])}")
        except Exception:
            pass

        out["available"] = bool(out["details"])
    except Exception:
        pass
    return out


# 수출주/내수주 섹터 키워드 (환율 영향)
_EXPORT_KEYWORDS = ("반도체", "자동차", "조선", "철강", "화학", "전자", "디스플레이", "정보통신")
_DOMESTIC_KEYWORDS = ("유통", "금융", "은행", "보험", "통신서비스", "건설", "음식료", "유틸리티")


def _apply_overnight_bonus(stock: dict, ctx: dict) -> dict:
    """morning 추천 시 미장/환율 기반 보너스 점수 적용."""
    if not ctx.get("available"):
        return stock
    bonus = 0
    extra_signals = []

    # 미장 종합 점수 (모든 종목 공통)
    g_score = ctx.get("global_score", 0)
    if g_score:
        bonus += g_score
        if g_score > 0:
            extra_signals.append(f"🌍 미장 강세 보너스 +{g_score}")
        elif g_score < 0:
            extra_signals.append(f"🌍 미장 약세 페널티 {g_score}")

    # 환율 → 수출/내수 가중치
    sector = (stock.get("sector_name") or "")
    fx_chg = ctx.get("fx_change_pct", 0)
    if fx_chg >= 0.3:
        if any(k in sector for k in _EXPORT_KEYWORDS):
            bonus += 8
            extra_signals.append(f"💱 원화 약세 + 수출 섹터 +8")
        elif any(k in sector for k in _DOMESTIC_KEYWORDS):
            bonus -= 5
            extra_signals.append(f"💱 원화 약세 + 내수 섹터 -5")
    elif fx_chg <= -0.3:
        if any(k in sector for k in _DOMESTIC_KEYWORDS):
            bonus += 8
            extra_signals.append(f"💱 원화 강세 + 내수 섹터 +8")
        elif any(k in sector for k in _EXPORT_KEYWORDS):
            bonus -= 5
            extra_signals.append(f"💱 원화 강세 + 수출 섹터 -5")

    # 🤖 Claude 매핑 — 미장 강세/약세 종목 → 한국 동조 섹터 보너스
    for strong_sec in ctx.get("strong_sectors", []):
        if strong_sec and strong_sec in sector:
            bonus += 12
            extra_signals.append(f"🎯 {strong_sec} (미장 동조 강세) +12")
            break
    for weak_sec in ctx.get("weak_sectors", []):
        if weak_sec and weak_sec in sector:
            bonus -= 10
            extra_signals.append(f"⚠ {weak_sec} (미장 동조 약세) -10")
            break

    # [A] 유가 → 정유/조선 vs 항공/운송
    wti = ctx.get("wti_change", 0)
    if wti >= 3:
        if any(k in sector for k in ("정유", "조선", "에너지", "화학")):
            bonus += 8; extra_signals.append(f"🛢 유가 급등 + 정유/조선 +8")
        elif any(k in sector for k in ("항공", "운송", "해운")):
            bonus -= 6; extra_signals.append(f"🛢 유가 급등 + 항공/운송 -6")
    elif wti <= -3:
        if any(k in sector for k in ("항공", "운송", "해운")):
            bonus += 6; extra_signals.append(f"🛢 유가 급락 + 항공/운송 +6")

    # [A] 美금리 → 성장주 vs 금융
    bond = ctx.get("bond10y_change", 0)
    if bond >= 2:
        if any(k in sector for k in ("제약", "바이오", "소프트웨어", "인터넷", "게임")):
            bonus -= 8; extra_signals.append(f"📈 美금리 급등 + 성장주 -8")
        elif any(k in sector for k in ("은행", "금융", "보험", "증권")):
            bonus += 5; extra_signals.append(f"📈 美금리 급등 + 금융 +5")
    elif bond <= -2:
        if any(k in sector for k in ("제약", "바이오", "소프트웨어", "인터넷", "게임")):
            bonus += 6; extra_signals.append(f"📉 美금리 급락 + 성장주 +6")

    # [B] Claude 뉴스 분석 → 수혜/리스크 섹터
    for ns in ctx.get("news_strong", []):
        if ns and ns in sector:
            bonus += 10; extra_signals.append(f"📰 {ns} (뉴스 수혜) +10")
            break
    for nw in ctx.get("news_weak", []):
        if nw and nw in sector:
            bonus -= 10; extra_signals.append(f"📰 {nw} (뉴스 리스크) -10")
            break

    # [C] VIX 공포 게이트 — 전 종목 페널티 (대형주는 절반 방어)
    vix_gate = ctx.get("vix_gate", 0)
    if vix_gate < 0:
        mc_eok = stock.get("market_cap_eok", 0)
        gate = vix_gate // 2 if mc_eok >= 50_000 else vix_gate  # 대형주 방어
        bonus += gate
        extra_signals.append(f"😱 VIX 게이트 {gate} (시총 {'대형방어' if mc_eok>=50000 else '일반'})")

    if bonus:
        stock["score"] = int(stock.get("score", 0)) + bonus
        stock["total_score"] = float(stock.get("total_score", 0)) + bonus
        stock["overnight_bonus"] = bonus
        sigs = list(stock.get("signals") or [])
        sigs.extend(extra_signals)
        stock["signals"] = sigs
    return stock


def recommend(top_n_per_tier: int = 3, exclude: set | None = None,
              n_per_source: int = 20, session: str = "evening") -> dict:
    """매번 시장 현재 상태로 동적 추천.

    1. 4가지 소스에서 활성 종목 수집 (~150개)
    2. ETF/우선주 자동 제외
    3. 보유 종목 제외
    4. 종목별 평가
    5. (morning 한정) 미장/환율 보너스 점수 적용
    6. Tier별 상위 N개 반환
    """
    excluded = exclude if exclude is not None else EXCLUDED_HOLDINGS
    # morning + evening 모두 거시 반영. 단 미장 종합(global_score)은 morning만 유효
    overnight_ctx = {"available": False}
    if session in ("morning", "evening"):
        overnight_ctx = get_overnight_context()
        if session == "evening":
            overnight_ctx["global_score"] = 0  # evening(21시)엔 당일 미장 미개장

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
            # morning/evening 거시 보너스 적용 (미장/환율/유가/VIX/금리/뉴스)
            if overnight_ctx.get("available"):
                result = _apply_overnight_bonus(result, overnight_ctx)
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

    # 최소 점수 컷오프 — tier 강제 채우기로 저점수/음수 종목이 추천되던 문제 해결
    # tier를 못 채워도 '질 우선' (후보 부족 시 추천 수 적어짐 = 정직)
    MIN_SCORE = 10

    def _cut(lst):
        return [
            s for s in lst
            if s.get("total_score", s.get("score", 0)) >= MIN_SCORE
        ][:top_n_per_tier]

    return {
        "large": _cut(by_tier["large"]),
        "mid": _cut(by_tier["mid"]),
        "small": _cut(by_tier["small"]),
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
