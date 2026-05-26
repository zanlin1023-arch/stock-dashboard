"""공통 유틸: 종목 코드/이름 변환, 환경 로드, 출력 포맷."""
from __future__ import annotations

import io
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Windows 콘솔(cp949)에서 이모지 출력 가능하도록 stdout/stderr를 UTF-8로 강제
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, io.UnsupportedOperation):
        pass

# pykrx KRX 인증 경고 + 미사용 함수 에러 메시지 억제
# (공개 데이터는 정상 작동, FinanceDataReader/네이버 fallback 사용 중)
warnings.filterwarnings("ignore", category=UserWarning, module="pykrx")
warnings.filterwarnings("ignore", category=FutureWarning, module="pykrx")


class _PykrxNoiseFilter:
    """pykrx의 KRX 인증 경고 / 'Error occurred in get_xxx' 잡음만 필터링."""
    NOISE_PATTERNS = [
        "KRX 로그인 실패",
        "KRX 로그인 시도",
        "로그인 ID",
        "KRX_ID",
        "KRX_PW",
        "Error occurred in get_",
        "Error occurred in __fetch",
        "Error occurred in get_market_trading",
        "Error occurred in get_market_fundamental",
        "Error occurred in get_index",
        "Expecting value: line 1 column 1",
        "조회된 데이타가 없습니다",
        "_skip_auth_",
        "char 0)",
    ]

    def __init__(self, real_stream):
        self._real = real_stream
        self._buffer = ""

    def write(self, text: str):
        # 라인 단위로 필터
        self._buffer += text
        if "\n" not in self._buffer:
            return
        lines = self._buffer.split("\n")
        self._buffer = lines[-1]  # 마지막 미완료 라인 보관
        for line in lines[:-1]:
            if not any(p in line for p in self.NOISE_PATTERNS):
                self._real.write(line + "\n")

    def flush(self):
        if self._buffer and not any(p in self._buffer for p in self.NOISE_PATTERNS):
            self._real.write(self._buffer)
        self._buffer = ""
        self._real.flush()

    def __getattr__(self, name):
        return getattr(self._real, name)


# stdout/stderr를 잡음 필터로 감싸기
sys.stdout = _PykrxNoiseFilter(sys.stdout)
sys.stderr = _PykrxNoiseFilter(sys.stderr)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
REPORTS_DIR = ROOT / "reports"

load_dotenv(CONFIG_DIR / ".env")


def get_dart_key() -> str:
    key = os.getenv("OPENDART_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            f"OPENDART_API_KEY not set. Add it to {CONFIG_DIR / '.env'}"
        )
    return key


def is_stock_code(s: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", s.strip()))


_LISTING_CACHE = None


def _load_listing():
    """KRX 종목 리스트. 캐시 CSV 우선, 실패 시 fdr 호출."""
    global _LISTING_CACHE
    if _LISTING_CACHE is not None:
        return _LISTING_CACHE

    # 1) repo 내 캐시 CSV (Streamlit Cloud에서도 동작)
    cache_path = Path(__file__).parent / "data" / "krx_listing.csv"
    if cache_path.exists():
        try:
            import pandas as pd
            df = pd.read_csv(cache_path, dtype={"Code": str})
            df["Code"] = df["Code"].astype(str).str.zfill(6)
            _LISTING_CACHE = df
            return df
        except Exception:
            pass

    # 2) FDR 실시간 호출 (로컬 PC에서만 가능, KRX 접근 가능 환경)
    try:
        import FinanceDataReader as fdr
        df = fdr.StockListing("KRX")
        if "Code" in df.columns:
            df["Code"] = df["Code"].astype(str).str.zfill(6)
        _LISTING_CACHE = df
        return df
    except Exception:
        pass

    return None


def resolve_ticker(query: str) -> tuple[str, str]:
    """종목코드 또는 종목명 → (code, name) 반환.

    KOSPI/KOSDAQ에서 검색. 동명이인 발생 시 첫 매칭 반환.
    """
    q = query.strip()
    listing = _load_listing()

    if is_stock_code(q):
        code = q
        if listing is not None:
            code_col = "Code" if "Code" in listing.columns else "Symbol"
            try:
                match = listing[listing[code_col].astype(str).str.zfill(6) == code]
                if len(match) > 0:
                    return code, str(match.iloc[0]["Name"])
            except Exception:
                pass
        # pykrx 폴백 (있을 때만)
        try:
            from pykrx import stock
            name = stock.get_market_ticker_name(code)
            if name:
                return code, name
        except Exception:
            pass
        return code, code

    # 종목명으로 검색
    if listing is None:
        raise ValueError(f"종목 리스트 로드 실패 (캐시/FDR 모두 실패): {query}")

    code_col = "Code" if "Code" in listing.columns else "Symbol"
    name_col = "Name"
    exact = listing[listing[name_col] == q]
    if len(exact) > 0:
        row = exact.iloc[0]
        return str(row[code_col]).zfill(6), str(row[name_col])
    partial = listing[listing[name_col].astype(str).str.contains(q, na=False)]
    if len(partial) > 0:
        row = partial.iloc[0]
        return str(row[code_col]).zfill(6), str(row[name_col])
    raise ValueError(f"종목을 찾을 수 없음: {query}")


def date_range(days: int = 180) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def date_range_iso(days: int = 30) -> tuple[str, str]:
    end = datetime.now()
    start = end - timedelta(days=days)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def report_path(name: str, suffix: str = "") -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    safe = re.sub(r"[^\w가-힣]", "_", name)
    fname = f"{safe}_{today}{('_' + suffix) if suffix else ''}.md"
    return REPORTS_DIR / fname


def fmt_num(x, unit: str = "", decimals: int = 2) -> str:
    if x is None:
        return "-"
    try:
        if isinstance(x, (int,)) or (isinstance(x, float) and x.is_integer()):
            return f"{int(x):,}{unit}"
        return f"{x:,.{decimals}f}{unit}"
    except Exception:
        return str(x)


def fmt_pct(x, decimals: int = 2) -> str:
    if x is None:
        return "-"
    try:
        return f"{x:+.{decimals}f}%"
    except Exception:
        return str(x)
