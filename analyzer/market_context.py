"""시장 컨텍스트: 지수/시장수급/섹터정합성/뉴스 — 단타용 시장 분위기 파악."""
from __future__ import annotations

import time
import warnings
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
}


def _business_day(days_back: int = 0) -> str:
    d = datetime.now() - timedelta(days=days_back)
    while d.weekday() >= 5:  # 주말 스킵
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


# =========================================================
# 1. 지수 동향 (KOSPI/KOSDAQ + 환율)
# =========================================================

def _classify_regime(close: pd.Series) -> tuple[float, float, str, float | None]:
    """이동평균 + RSI 기반 추세 분류."""
    last = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else last
    sma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else sma20

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = float((100 - 100 / (1 + rs)).iloc[-1]) if len(close) >= 14 else None

    if last > sma20 > sma60:
        regime = "🟢 강세 정배열"
    elif last < sma20 < sma60:
        regime = "🔴 약세 역배열"
    elif last > sma20:
        regime = "🟡 단기 강세 (중기 혼조)"
    else:
        regime = "🟡 단기 약세 (중기 혼조)"
    return sma20, sma60, regime, rsi_val


def _fetch_naver_realtime_index(name: str) -> dict | None:
    """네이버 모바일 API로 실시간 지수 (장중 실시간)."""
    try:
        r = requests.get(
            f"https://m.stock.naver.com/api/index/{name}/basic",
            headers=HEADERS, timeout=10,
        )
        d = r.json()

        def _f(v):
            if v is None or v == "":
                return None
            try:
                return float(str(v).replace(",", ""))
            except (ValueError, TypeError):
                return None

        close = _f(d.get("closePrice"))
        chg_pct = _f(d.get("fluctuationsRatio"))
        if close is None:
            return None
        return {
            "close": close,
            "change_pct": chg_pct or 0,
            "as_of": d.get("localTradedAt"),
            "source": "Naver Mobile (실시간)",
        }
    except Exception:
        return None


def get_index_status() -> dict[str, Any]:
    """코스피/코스닥 오늘 상태 + 추세 분류.

    가격/등락률: 네이버 모바일 API (실시간, 약 1분 지연)
    추세 분류 (SMA/RSI): FinanceDataReader (일봉)
    """
    out: dict[str, Any] = {}
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=120)

    for name, fdr_code in [("KOSPI", "KS11"), ("KOSDAQ", "KQ11")]:
        # 1. 네이버 모바일 API로 실시간 가격
        rt = _fetch_naver_realtime_index(name)

        # 2. FinanceDataReader로 추세 분류용 과거 데이터
        sma20, sma60, regime, rsi_val = None, None, "?", None
        try:
            import FinanceDataReader as fdr
            df = fdr.DataReader(fdr_code, start_dt, end_dt)
            if df is not None and not df.empty:
                close = df["Close"].copy()
                # 실시간 가격이 있으면 마지막 값을 실시간으로 갱신 (장중 RSI 보정)
                if rt and rt.get("close"):
                    if str(df.index[-1])[:10] != end_dt.strftime("%Y-%m-%d"):
                        # 오늘 일봉 미반영이면 추가
                        close.loc[end_dt] = rt["close"]
                    else:
                        close.iloc[-1] = rt["close"]
                sma20, sma60, regime, rsi_val = _classify_regime(close)
                if not rt:
                    # 실시간 실패 시 일봉 마지막 값 사용
                    last = float(close.iloc[-1])
                    prev = float(close.iloc[-2]) if len(close) >= 2 else last
                    rt = {
                        "close": last,
                        "change_pct": (last / prev - 1) * 100 if prev > 0 else 0,
                        "as_of": str(df.index[-1])[:10],
                        "source": "FinanceDataReader (일봉)",
                    }
        except Exception:
            pass

        if rt:
            out[name] = {
                "close": rt["close"],
                "change_pct": rt["change_pct"],
                "sma20": sma20,
                "sma60": sma60,
                "rsi": rsi_val,
                "regime": regime,
                "as_of": rt["as_of"],
                "source": rt["source"],
            }
    if out:
        return out

    # pykrx fallback (있을 때만)
    try:
        from pykrx import stock
    except Exception:
        return out
    end = _business_day()
    start = start_dt.strftime("%Y%m%d")
    for name, code in [("KOSPI", "1001"), ("KOSDAQ", "2001")]:
        try:
            df = stock.get_index_ohlcv(start, end, code)
            if df is None or df.empty:
                continue
            close = df["종가"]
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) >= 2 else last
            sma20, sma60, regime, rsi_val = _classify_regime(close)
            out[name] = {
                "close": last,
                "change_pct": (last / prev - 1) * 100 if prev > 0 else 0,
                "sma20": sma20,
                "sma60": sma60,
                "rsi": rsi_val,
                "regime": regime,
                "as_of": str(df.index[-1])[:10],
                "source": "pykrx",
            }
        except Exception:
            continue
    return out


def get_usd_krw() -> dict | None:
    """원/달러 환율 (네이버 금융 스크래핑)."""
    try:
        r = requests.get("https://finance.naver.com/marketindex/", headers=HEADERS, timeout=10)
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        # USD/KRW
        h_usd = soup.select_one("a.head.usd .value")
        h_chg = soup.select_one("a.head.usd .change")
        if h_usd:
            return {
                "rate": h_usd.get_text(strip=True),
                "change": h_chg.get_text(strip=True) if h_chg else "",
            }
    except Exception:
        return None
    return None


def get_market_regime() -> dict:
    """국내(코스피/코스닥) + 미장(S&P500/나스닥) 지수의 일목 구름 레짐.

    지수가 일목 구름 위/안/아래 어디 있는지로 강세/횡보/약세 판정.
    한국 시장은 미장에 크게 동조하므로 미장도 함께 본다.
    Returns: {"KOSPI": {"pos","label","close","group"}, ...}  (실패 항목은 누락)
    """
    import datetime as _dt
    out: dict = {}
    try:
        import FinanceDataReader as fdr
        from chart_scenario import compute_ichimoku
    except Exception:
        return out

    end = _dt.date.today()
    start = end - _dt.timedelta(days=420)  # 52+26봉 + 여유 (휴장 포함)
    for name, code, group in [
        ("KOSPI", "KS11", "kr"), ("KOSDAQ", "KQ11", "kr"),
        ("S&P500", "US500", "us"), ("NASDAQ", "IXIC", "us"),
    ]:
        try:
            df = fdr.DataReader(code, start, end)
            if df is None or df.empty:
                continue
            df = df.rename(columns={
                "Open": "open", "High": "high", "Low": "low",
                "Close": "close", "Volume": "volume",
            })
            df = compute_ichimoku(df)
            last = df.iloc[-1]
            price = float(last["close"])
            sa, sb = last.get("senkou_a"), last.get("senkou_b")
            if pd.isna(sa) or pd.isna(sb):
                continue
            top, bot = max(float(sa), float(sb)), min(float(sa), float(sb))
            prev_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else price
            chg = (price / prev_close - 1) * 100 if prev_close else 0.0
            if price > top:
                pos = "above"
                # 구름 top 대비 +2% 미만이면 '근접·약'(겨우 걸친 상태) — 하루 급락에 깨질 수 있음
                gap = (price / top - 1) * 100 if top else 0.0
                label = "🟢 구름 위 (강세)" if gap >= 2 else "🟢 구름 위 (근접·약)"
            elif price < bot:
                pos, label = "below", "🔴 구름 아래 (약세)"
            else:
                pos, label = "inside", "🟡 구름 안 (횡보)"
            out[name] = {"pos": pos, "label": label, "close": price,
                         "change": chg, "group": group}
        except Exception:
            continue
    return out


# =========================================================
# 2. 오늘의 시장 주도 종목 (상승률/거래대금)
# =========================================================

def get_top_movers(market: str = "KOSPI", n: int = 10) -> dict:
    """오늘 상승률/하락률 상위 N개."""
    try:
        from pykrx import stock
    except Exception:
        return {}

    end = _business_day()
    start = _business_day(days_back=2)
    try:
        df = stock.get_market_price_change(start, end, market=market)
        if df is None or df.empty:
            return {}
        df = df.reset_index()
        # 컬럼명: 종목명, 시가, 종가, 변동폭, 등락률, 거래량, 거래대금
        sorted_df = df.sort_values("등락률", ascending=False)
        gainers = sorted_df.head(n)[["티커", "종목명", "등락률", "종가", "거래대금"]].to_dict("records")
        losers = sorted_df.tail(n).iloc[::-1][["티커", "종목명", "등락률", "종가", "거래대금"]].to_dict("records")
        # 거래대금 상위
        by_value = df.sort_values("거래대금", ascending=False).head(n)
        top_value = by_value[["티커", "종목명", "등락률", "종가", "거래대금"]].to_dict("records")
        return {"gainers": gainers, "losers": losers, "top_value": top_value}
    except Exception:
        return {}


# =========================================================
# 3. 종목별 외국인/기관 수급
# =========================================================

def _parse_int_amount(s: str) -> int:
    """'+12,345' / '-1,234' → int. 빈 값/None은 0."""
    if not s:
        return 0
    s = s.replace(",", "").replace(" ", "").strip()
    if not s or s == "-":
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0


def get_foreign_inst_flow(code: str, days: int = 20) -> dict | None:
    """종목별 일별 외국인/기관 순매수 추이. pykrx 실패 시 네이버 스크래핑."""
    # pykrx 우선 시도
    try:
        from pykrx import stock
        end = _business_day()
        start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")
        df = stock.get_market_trading_value_by_date(start, end, code)
        if df is not None and not df.empty:
            df = df.tail(days)
            return _summarize_flow_df(df, "외국인합계", "기관합계", "개인")
    except Exception:
        pass

    # 네이버 스크래핑 fallback
    return _fetch_naver_flow(code, days)


def _summarize_flow_df(df: pd.DataFrame, col_foreign: str, col_inst: str, col_indiv: str) -> dict:
    foreign_total = int(df[col_foreign].sum()) if col_foreign in df.columns else 0
    inst_total = int(df[col_inst].sum()) if col_inst in df.columns else 0
    indiv_total = int(df[col_indiv].sum()) if col_indiv in df.columns else 0

    last_5 = df.tail(5)
    foreign_5d = int(last_5[col_foreign].sum()) if col_foreign in last_5.columns else 0
    inst_5d = int(last_5[col_inst].sum()) if col_inst in last_5.columns else 0

    def _streak(series):
        c = 0
        for v in series.iloc[::-1]:
            if v > 0:
                c += 1
            else:
                break
        return c

    return {
        "foreign_20d": foreign_total,
        "institution_20d": inst_total,
        "individual_20d": indiv_total,
        "foreign_5d": foreign_5d,
        "institution_5d": inst_5d,
        "foreign_buy_streak": _streak(df[col_foreign]) if col_foreign in df.columns else 0,
        "institution_buy_streak": _streak(df[col_inst]) if col_inst in df.columns else 0,
        "days": len(df),
    }


def get_daily_flow(code: str, days: int = 10, retries: int = 2) -> list[dict]:
    """일별 외국인/기관 매매 추이 (네이버 스크래핑).

    반환: 최근 N일 일별 데이터 [최신순]
    - date, close, change, volume, foreign_net (주), inst_net (주)

    빈 응답(네이버 throttle 등)이면 지수 backoff로 최대 retries회 재시도.
    대량 연속 스캔(스냅샷/추천)에서 수급 누락을 줄임.
    """
    rows: list[dict] = []
    for attempt in range(retries + 1):
        rows = []
        for page in range(1, 3):
            try:
                r = requests.get(
                    "https://finance.naver.com/item/frgn.naver",
                    params={"code": code, "page": page},
                    headers=HEADERS, timeout=10,
                )
                r.encoding = r.apparent_encoding or "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")
                for tr in soup.select("table.type2 tr"):
                    tds = tr.find_all("td")
                    if len(tds) < 9:
                        continue
                    date_str = tds[0].get_text(strip=True)
                    if not date_str or "." not in date_str:
                        continue
                    try:
                        close = _parse_int_amount(tds[1].get_text(strip=True))
                        change = tds[2].get_text(strip=True)  # "하락1,290" 또는 "상승500"
                        foreign_net = _parse_int_amount(tds[5].get_text(strip=True))
                        inst_net = _parse_int_amount(tds[6].get_text(strip=True))
                        rows.append({
                            "date": date_str,
                            "close": close,
                            "change_str": change,
                            "foreign_net": foreign_net,
                            "inst_net": inst_net,
                        })
                    except Exception:
                        continue
            except Exception:
                continue
        if rows:
            break
        if attempt < retries:
            time.sleep(0.6 * (attempt + 1))  # 0.6s → 1.2s backoff
    return rows[:days]


def detect_flow_reversal(code: str, lookback: int = 7, daily: list[dict] | None = None) -> dict:
    """수급 전환 감지: 최근 N일 외국인/기관 매매 패턴 분석.

    감지하는 패턴:
    - 매수 지속 (최근 N일 매수 우세)
    - 매도 지속 (최근 N일 매도 우세)
    - 매수 → 매도 전환 (앞 절반 매수, 뒤 절반 매도)
    - 매도 → 매수 전환 (앞 절반 매도, 뒤 절반 매수)

    daily 전달 시 추가 네트워크 호출 없이 재사용 (lookback 길이로 슬라이스).
    """
    if daily is None:
        daily = get_daily_flow(code, days=lookback)
    else:
        daily = daily[:lookback]
    if len(daily) < 4:
        return {"available": False, "reason": "데이터 부족"}

    # 최근 N일을 절반으로 나눠 비교
    half = len(daily) // 2
    recent = daily[:half]   # 최근 (앞쪽이 최신)
    earlier = daily[half:]  # 이전

    def _sum_net(rows, col):
        return sum(r.get(col, 0) for r in rows)

    recent_foreign = _sum_net(recent, "foreign_net")
    earlier_foreign = _sum_net(earlier, "foreign_net")
    recent_inst = _sum_net(recent, "inst_net")
    earlier_inst = _sum_net(earlier, "inst_net")

    total_foreign = recent_foreign + earlier_foreign
    total_inst = recent_inst + earlier_inst

    # 외국인 패턴 감지
    signals = []
    foreign_pattern = None
    inst_pattern = None

    # 최근 N일 매수 추세 (연속성)
    foreign_streak_buy = 0
    foreign_streak_sell = 0
    for r in daily:
        if r["foreign_net"] > 0:
            foreign_streak_buy += 1
            foreign_streak_sell = 0
        else:
            foreign_streak_sell += 1
            foreign_streak_buy = 0
        if foreign_streak_buy >= 3 or foreign_streak_sell >= 3:
            break

    inst_streak_buy = 0
    inst_streak_sell = 0
    for r in daily:
        if r["inst_net"] > 0:
            inst_streak_buy += 1
            inst_streak_sell = 0
        else:
            inst_streak_sell += 1
            inst_streak_buy = 0
        if inst_streak_buy >= 3 or inst_streak_sell >= 3:
            break

    # 외국인 패턴
    if earlier_foreign > 0 and recent_foreign < 0:
        foreign_pattern = "🔴 매수 → 매도 전환"
        signals.append(f"외국인 매수→매도 전환 (이전 {earlier_foreign:+,}주 → 최근 {recent_foreign:+,}주)")
    elif earlier_foreign < 0 and recent_foreign > 0:
        foreign_pattern = "🟢 매도 → 매수 전환"
        signals.append(f"외국인 매도→매수 전환 (이전 {earlier_foreign:+,}주 → 최근 {recent_foreign:+,}주)")
    elif total_foreign > 0:
        foreign_pattern = "🟢 매수 지속"
        signals.append(f"외국인 누적 +{total_foreign:,}주 매수")
    else:
        foreign_pattern = "🔴 매도 지속"
        signals.append(f"외국인 누적 {total_foreign:,}주 매도")

    # 기관 패턴
    if earlier_inst > 0 and recent_inst < 0:
        inst_pattern = "🔴 매수 → 매도 전환"
        signals.append(f"기관 매수→매도 전환 (이전 {earlier_inst:+,}주 → 최근 {recent_inst:+,}주)")
    elif earlier_inst < 0 and recent_inst > 0:
        inst_pattern = "🟢 매도 → 매수 전환"
        signals.append(f"기관 매도→매수 전환 (이전 {earlier_inst:+,}주 → 최근 {recent_inst:+,}주)")
    elif total_inst > 0:
        inst_pattern = "🟢 매수 지속"
    else:
        inst_pattern = "🔴 매도 지속"

    # 종합 등급
    if "전환" in foreign_pattern and "🔴" in foreign_pattern:
        verdict = "⚠️ 외국인 매도 전환 — 단기 약세 시그널"
    elif "전환" in foreign_pattern and "🟢" in foreign_pattern:
        verdict = "✅ 외국인 매수 전환 — 단기 강세 시그널"
    elif "🟢" in foreign_pattern and "🟢" in inst_pattern:
        verdict = "🟢 외인+기관 동반 매수 — 강력한 매수 시그널"
    elif "🔴" in foreign_pattern and "🔴" in inst_pattern:
        verdict = "🔴 외인+기관 동반 매도 — 강한 약세 시그널"
    else:
        verdict = "🟡 외인/기관 분리 (혼조)"

    return {
        "available": True,
        "daily": daily,
        "recent_foreign_net": recent_foreign,
        "earlier_foreign_net": earlier_foreign,
        "recent_inst_net": recent_inst,
        "earlier_inst_net": earlier_inst,
        "foreign_pattern": foreign_pattern,
        "inst_pattern": inst_pattern,
        "signals": signals,
        "verdict": verdict,
    }


def to_markdown_daily_flow(reversal: dict, target_name: str = "") -> str:
    """일별 흐름 + 수급 전환 분석 Markdown."""
    if not reversal.get("available"):
        return ""

    lines = [
        f"### 📅 {target_name} 일별 수급 흐름 (선행 신호)",
        "",
        f"**{reversal['verdict']}**",
        "",
    ]
    for s in reversal["signals"]:
        lines.append(f"- {s}")

    # 일별 표
    daily = reversal.get("daily", [])
    if daily:
        lines += [
            "",
            "| 날짜 | 종가 | 등락 | 외국인 (주) | 기관 (주) |",
            "|------|------|------|------------|----------|",
        ]
        for r in daily[:7]:
            f_str = f"{r['foreign_net']:+,}"
            i_str = f"{r['inst_net']:+,}"
            f_em = "🟢" if r['foreign_net'] > 0 else ("🔴" if r['foreign_net'] < 0 else "⚪")
            i_em = "🟢" if r['inst_net'] > 0 else ("🔴" if r['inst_net'] < 0 else "⚪")
            lines.append(f"| {r['date']} | {r['close']:,} | {r['change_str']} | {f_em} {f_str} | {i_em} {i_str} |")

    return "\n".join(lines)


def _fetch_naver_flow(code: str, days: int = 20) -> dict | None:
    """네이버 금융 종목 외국인/기관 페이지 스크래핑."""
    rows = []
    for page in range(1, 4):  # 3페이지 (약 30일)
        try:
            r = requests.get(
                "https://finance.naver.com/item/frgn.naver",
                params={"code": code, "page": page},
                headers=HEADERS,
                timeout=10,
            )
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for tr in soup.select("table.type2 tr"):
                tds = tr.find_all("td")
                if len(tds) < 7:
                    continue
                date_str = tds[0].get_text(strip=True)
                if not date_str or "." not in date_str:
                    continue
                try:
                    foreign_net = _parse_int_amount(tds[5].get_text(strip=True)) * 1  # 주 단위
                    inst_net = _parse_int_amount(tds[6].get_text(strip=True)) * 1
                    close_price = _parse_int_amount(tds[1].get_text(strip=True))
                    rows.append({
                        "date": date_str,
                        "close": close_price,
                        "foreign_net": foreign_net * close_price,  # 원 단위 환산 (주×종가)
                        "inst_net": inst_net * close_price,
                    })
                except Exception:
                    continue
        except Exception:
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows[:days])
    if df.empty:
        return None

    foreign_5d = int(df.head(5)["foreign_net"].sum())
    inst_5d = int(df.head(5)["inst_net"].sum())
    foreign_total = int(df["foreign_net"].sum())
    inst_total = int(df["inst_net"].sum())

    def _streak(series):
        c = 0
        for v in series:
            if v > 0:
                c += 1
            else:
                break
        return c

    return {
        "foreign_20d": foreign_total,
        "institution_20d": inst_total,
        "individual_20d": -(foreign_total + inst_total),  # 추정
        "foreign_5d": foreign_5d,
        "institution_5d": inst_5d,
        "foreign_buy_streak": _streak(df["foreign_net"]),
        "institution_buy_streak": _streak(df["inst_net"]),
        "days": len(df),
        "source": "Naver",
    }


# =========================================================
# 4. 섹터 정합성 (종목 vs 동종 섹터)
# =========================================================

_SECTOR_CACHE: pd.DataFrame | None = None


def _load_sector_listing() -> pd.DataFrame | None:
    global _SECTOR_CACHE
    if _SECTOR_CACHE is not None:
        return _SECTOR_CACHE
    try:
        import FinanceDataReader as fdr
        listing = fdr.StockListing("KRX")
        # 컬럼 다를 수 있음 — Code/Symbol, Name, Sector, Industry
        _SECTOR_CACHE = listing
        return listing
    except Exception:
        return None


def get_sector_for(code: str) -> str | None:
    listing = _load_sector_listing()
    if listing is None:
        return None
    code_col = "Code" if "Code" in listing.columns else "Symbol"
    if code_col not in listing.columns:
        return None
    row = listing[listing[code_col].astype(str).str.zfill(6) == code.zfill(6)]
    if row.empty:
        return None
    for col in ("Sector", "Industry", "업종", "Industry_kor"):
        if col in row.columns:
            val = row.iloc[0].get(col)
            if pd.notna(val) and str(val).strip():
                return str(val)
    return None


def compare_to_sector(code: str) -> dict | None:
    """종목 등락률 vs 섹터 평균."""
    try:
        from pykrx import stock
    except Exception:
        return None

    sector = get_sector_for(code)
    if not sector:
        return None

    listing = _load_sector_listing()
    if listing is None:
        return None
    code_col = "Code" if "Code" in listing.columns else "Symbol"
    sector_cols = [c for c in ("Sector", "Industry", "업종") if c in listing.columns]
    if not sector_cols:
        return None
    same_sector = listing[listing[sector_cols[0]].astype(str) == sector]
    if len(same_sector) < 3:
        return None

    end = _business_day()
    start = _business_day(days_back=2)
    try:
        df = stock.get_market_price_change(start, end, market="ALL")
        df = df.reset_index()
        peer_codes = same_sector[code_col].astype(str).str.zfill(6).tolist()
        peers = df[df["티커"].astype(str).str.zfill(6).isin(peer_codes)]
        if peers.empty:
            return None
        avg_change = float(peers["등락률"].mean())
        median_change = float(peers["등락률"].median())
        target = peers[peers["티커"].astype(str).str.zfill(6) == code.zfill(6)]
        target_change = float(target["등락률"].iloc[0]) if not target.empty else None

        return {
            "sector": sector,
            "peer_count": len(peers),
            "sector_avg_change": avg_change,
            "sector_median_change": median_change,
            "target_change": target_change,
            "relative_strength": (target_change - avg_change) if target_change is not None else None,
        }
    except Exception:
        return None


# =========================================================
# 5. 시장 메인 뉴스 헤드라인
# =========================================================

def get_market_news(limit: int = 10) -> list[dict]:
    """네이버 금융 메인 뉴스 헤드라인."""
    try:
        r = requests.get("https://finance.naver.com/", headers=HEADERS, timeout=10)
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        return [{"error": f"네이버 메인 조회 실패: {e}"}]

    out = []
    seen = set()
    for a in soup.select('a[href*="news"]'):
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if not title or len(title) < 10:
            continue
        if title[:20] in seen:
            continue
        seen.add(title[:20])
        if href.startswith("/"):
            href = "https://finance.naver.com" + href
        out.append({"title": title, "url": href})
        if len(out) >= limit:
            break
    return out


# =========================================================
# 종합 분석 + Markdown 출력
# =========================================================

def analyze(target_code: str | None = None) -> dict:
    """모든 시장 컨텍스트 한번에 수집."""
    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "indices": get_index_status(),
        "usd_krw": get_usd_krw(),
        "kospi_top": get_top_movers("KOSPI", n=10),
        "kosdaq_top": get_top_movers("KOSDAQ", n=10),
        "news": get_market_news(limit=8),
        "target_flow": get_foreign_inst_flow(target_code) if target_code else None,
        "target_sector": compare_to_sector(target_code) if target_code else None,
    }


def _fmt_billion(v: int | None) -> str:
    if v is None:
        return "-"
    if abs(v) >= 1_000_000_000_000:
        return f"{v / 1_000_000_000_000:+.2f}조원"
    if abs(v) >= 100_000_000:
        return f"{v / 100_000_000:+.0f}억원"
    return f"{v:,}원"


def to_markdown(ctx: dict, target_code: str | None = None, target_name: str = "") -> str:
    lines = ["## 🌐 시장 컨텍스트", ""]
    lines.append(f"_기준: {ctx.get('as_of', '-')}_ ")
    lines.append("")

    # 1. 지수 + 환율
    indices = ctx.get("indices") or {}
    if indices:
        lines += ["### 📊 지수 동향", "", "| 지수 | 종가 | 등락 | RSI | 추세 |", "|------|------|------|------|------|"]
        for name, d in indices.items():
            rsi_str = f"{d['rsi']:.1f}" if d.get("rsi") is not None else "-"
            lines.append(f"| {name} | {d['close']:,.2f} | {d['change_pct']:+.2f}% | {rsi_str} | {d['regime']} |")

    usd = ctx.get("usd_krw")
    if usd:
        lines += ["", f"**원/달러**: {usd['rate']} ({usd['change']})"]

    # 2. 시장 주도 종목
    for mkt_key, mkt_label in [("kospi_top", "KOSPI"), ("kosdaq_top", "KOSDAQ")]:
        movers = ctx.get(mkt_key) or {}
        if not movers:
            continue
        lines += ["", f"### 🚀 {mkt_label} 오늘 주도주", ""]

        if movers.get("top_value"):
            lines += ["**거래대금 상위 5:**"]
            for m in movers["top_value"][:5]:
                lines.append(
                    f"- {m['종목명']} ({m['티커']}) — {m['종가']:,.0f}원 ({m['등락률']:+.2f}%) "
                    f"— 거래대금 {m['거래대금'] / 100_000_000:,.0f}억"
                )

        if movers.get("gainers"):
            lines += ["", "**상승률 상위 5:**"]
            for m in movers["gainers"][:5]:
                lines.append(f"- {m['종목명']} ({m['티커']}) — {m['종가']:,.0f}원 ({m['등락률']:+.2f}%)")

        if movers.get("losers"):
            lines += ["", "**하락률 상위 5:**"]
            for m in movers["losers"][:5]:
                lines.append(f"- {m['종목명']} ({m['티커']}) — {m['종가']:,.0f}원 ({m['등락률']:+.2f}%)")

    # 3. 종목별 외국인/기관 수급
    flow = ctx.get("target_flow")
    if flow and target_code:
        lines += ["", f"### 💰 {target_name or target_code} 외국인/기관 수급", ""]
        lines += ["| 기간 | 외국인 순매수 | 기관 순매수 | 개인 |", "|------|------|------|------|"]
        lines.append(f"| 최근 5일 | {_fmt_billion(flow['foreign_5d'])} | {_fmt_billion(flow['institution_5d'])} | - |")
        lines.append(f"| 최근 20일 | {_fmt_billion(flow['foreign_20d'])} | {_fmt_billion(flow['institution_20d'])} | {_fmt_billion(flow['individual_20d'])} |")
        lines += ["", f"- 외국인 연속 매수일: **{flow['foreign_buy_streak']}일**", f"- 기관 연속 매수일: **{flow['institution_buy_streak']}일**"]

        # 시그널 해석
        signals = []
        if flow["foreign_5d"] > 0 and flow["institution_5d"] > 0:
            signals.append("🟢 외국인+기관 동반 순매수 — 강력한 매수 시그널")
        elif flow["foreign_5d"] > 0:
            signals.append("🟢 외국인 순매수")
        elif flow["institution_5d"] > 0:
            signals.append("🟢 기관 순매수")
        elif flow["foreign_5d"] < 0 and flow["institution_5d"] < 0:
            signals.append("🔴 외국인+기관 동반 순매도 — 약세 시그널")
        if flow["foreign_buy_streak"] >= 3:
            signals.append(f"⭐ 외국인 {flow['foreign_buy_streak']}일 연속 매수")
        if signals:
            lines += ["", "**수급 시그널:**"] + [f"- {s}" for s in signals]

    # 4. 섹터 정합성
    sector = ctx.get("target_sector")
    if sector and target_code:
        lines += ["", f"### 🎯 {target_name or target_code} 섹터 정합성", ""]
        lines.append(f"- 섹터: **{sector['sector']}** (동종 {sector['peer_count']}개 종목)")
        lines.append(f"- 종목 등락: {sector['target_change']:+.2f}%")
        lines.append(f"- 섹터 평균: {sector['sector_avg_change']:+.2f}% / 중앙값: {sector['sector_median_change']:+.2f}%")
        rs = sector.get("relative_strength")
        if rs is not None:
            if rs > 1:
                lines.append(f"- **상대 강도: {rs:+.2f}%p — 섹터 대비 강세 ⭐**")
            elif rs < -1:
                lines.append(f"- **상대 강도: {rs:+.2f}%p — 섹터 대비 약세 ⚠️**")
            else:
                lines.append(f"- 상대 강도: {rs:+.2f}%p — 섹터와 유사")

    # 5. 시장 뉴스
    news = ctx.get("news") or []
    if news and not (len(news) == 1 and "error" in news[0]):
        lines += ["", "### 📰 시장 헤드라인 (네이버 금융 메인)", ""]
        for n in news[:8]:
            lines.append(f"- [{n['title']}]({n['url']})")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    target_name = ""
    if target:
        try:
            from _utils import resolve_ticker
            target, target_name = resolve_ticker(target)
        except Exception:
            pass

    ctx = analyze(target)
    print(to_markdown(ctx, target, target_name))
