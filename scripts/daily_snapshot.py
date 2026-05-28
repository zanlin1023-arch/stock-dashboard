"""일일 자동 스냅샷 — 보유 종목 + 관심 종목 분석 → Supabase 저장.

GitHub Actions cron으로 평일 18:00 KST에 실행.
환경변수 필요: SUPABASE_URL, SUPABASE_KEY, OPENDART_API_KEY
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Windows cp949 → UTF-8 강제 (이모지 출력)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# analyzer 패키지를 sys.path에 추가 (ROOT/analyzer/__init__.py)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))           # for: from analyzer import db
sys.path.insert(0, str(ROOT / "analyzer"))  # for: import technical (직접)

# 로컬 실행 시 .env에서 env 로드
if not os.getenv("SUPABASE_URL"):
    try:
        from dotenv import load_dotenv
        # 1) 로컬 .streamlit/secrets.toml 우선 (개발 환경)
        secrets_file = ROOT / ".streamlit" / "secrets.toml"
        if secrets_file.exists():
            for line in secrets_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


def run_snapshot() -> dict:
    """모든 보유+관심 종목 분석 후 DB 저장. 통계 반환."""
    from analyzer import db
    import technical
    from chart_ichimoku import (
        compute_ichimoku,
        detect_swing_points,
        compute_price_targets,
        make_decision,
    )

    if not db.is_db_available():
        print("[ERROR] Supabase 미설정 (SUPABASE_URL / SUPABASE_KEY)")
        return {"status": "failed", "reason": "no_db"}

    # 보유 + 관심 종목 코드 수집 (중복 제거)
    holdings = db.list_holdings()
    watchlist = db.list_watchlist()
    code_to_name = {}
    for h in holdings:
        code_to_name[h["stock_code"]] = h["stock_name"]
    for w in watchlist:
        code_to_name.setdefault(w["stock_code"], w["stock_name"])

    if not code_to_name:
        print("[INFO] 보유/관심 종목이 없습니다. 스냅샷 건너뜀.")
        return {"status": "skipped", "reason": "no_targets"}

    print(f"[INFO] 대상 종목 {len(code_to_name)}개: {list(code_to_name.values())}")

    results = {"success": [], "failed": []}

    for code, name in code_to_name.items():
        try:
            print(f"  [{code}] {name} 분석 중...")
            # OHLCV + 지표
            df = technical.fetch_ohlcv(code, days=180)
            df = technical.add_indicators(df)
            df = compute_ichimoku(df)

            # 종합 분석
            result = technical.analyze(code, name)

            # 일목 + 파동 + 의사결정
            swings = detect_swing_points(df, lookback=min(80, len(df)))
            A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
            targets = compute_price_targets(A, B, C)
            # ATR cap 통일 (전 경로 동일 목표가)
            from chart_ichimoku import cap_targets
            _atr_val = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns and df["atr_14"].iloc[-1] == df["atr_14"].iloc[-1] else None
            targets = cap_targets(targets, float(df["close"].iloc[-1]), _atr_val)
            decision = make_decision(df, swings, targets)

            # 일목 지표 추가
            tech_for_db = dict(result)
            for col in ["tenkan", "kijun", "senkou_a", "senkou_b"]:
                if col in df.columns and df[col].notna().any():
                    tech_for_db[col] = float(df[col].iloc[-1])
            if _atr_val is not None:
                tech_for_db["atr_14"] = _atr_val

            # 시간 사이클 + 미래 추세 + 수급 (DB 누적 분석용)
            from chart_ichimoku import compute_time_cycles, project_future_path
            cycles = compute_time_cycles(swings["C"]["idx"], len(df))
            future_path = project_future_path(
                decision["price"], cycles, targets, decision.get("stop"),
                swings=swings, atr_value=_atr_val,
            )
            flow_data = None
            try:
                import market_context as mc
                rev = mc.detect_flow_reversal(code, lookback=7)
                if rev.get("available"):
                    flow_data = {
                        "verdict": rev.get("verdict"),
                        "daily": rev.get("daily", [])[:7],
                        "signals": rev.get("signals", []),
                    }
            except Exception:
                pass

            pattern_data = None
            try:
                import pattern_match as pm
                pattern_data = pm.predict_future_path(
                    code=code, current_price=decision["price"],
                    window=60, n_future=20, top_k=3,
                )
            except Exception:
                pass

            # DB 저장 (scheduled로 표시)
            saved = db.save_analysis(
                code, name, tech_for_db, decision, targets, swings,
                snapshot_type="scheduled",
                cycles=cycles,
                future_path=future_path,
                flow=flow_data,
                pattern_match=pattern_data,
            )
            if saved:
                results["success"].append({"code": code, "name": name, "id": saved.get("id")})
                print(f"    ✅ 저장 완료 (id={saved.get('id')})")
            else:
                results["failed"].append({"code": code, "name": name, "reason": "no_data"})
                print(f"    ❌ 저장 실패")

            # API 폭주 방지 (FDR/네이버 호출 간격)
            time.sleep(1.5)

        except Exception as e:
            results["failed"].append({"code": code, "name": name, "reason": str(e)})
            print(f"    ❌ 에러: {e}")

    print(f"\n[SUMMARY] 성공 {len(results['success'])}건 / 실패 {len(results['failed'])}건")
    return {"status": "done", **results}


if __name__ == "__main__":
    print("=" * 60)
    print("📸 일일 자동 스냅샷 시작")
    print("=" * 60)
    summary = run_snapshot()
    print("=" * 60)
    print(f"완료: {summary.get('status')}")
    print("=" * 60)

    # CI 환경에서 실패 종목이 있으면 exit code 0 유지 (한두개 실패해도 다음날 다시 시도)
    sys.exit(0)
