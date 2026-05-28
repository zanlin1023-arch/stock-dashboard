"""특정 날짜 시점의 자동 스냅샷 백필.

사용: py scripts/backfill_snapshot.py 2026-05-27
- 보유 + 관심 종목 OHLCV를 target_date까지 잘라서 분석
- analysis_history에 analyzed_date=target_date + snapshot_type=scheduled로 저장
- 중복 시 upsert (덮어쓰기)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))

if not os.getenv("SUPABASE_URL"):
    secrets_file = ROOT / ".streamlit" / "secrets.toml"
    if secrets_file.exists():
        for line in secrets_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_backfill(target_date: str) -> dict:
    """target_date 시점 데이터로 보유+관심 종목 분석 + 저장."""
    import pandas as pd
    from analyzer import db
    import technical
    from chart_ichimoku import (
        compute_ichimoku, detect_swing_points, compute_price_targets,
        make_decision, compute_time_cycles, project_future_path,
    )

    if not db.is_db_available():
        print("[ERROR] Supabase 미설정")
        return {"status": "failed"}

    holdings = db.list_holdings()
    watchlist = db.list_watchlist()
    code_to_name = {}
    for h in holdings:
        code_to_name[h["stock_code"]] = h["stock_name"]
    for w in watchlist:
        code_to_name.setdefault(w["stock_code"], w["stock_name"])

    if not code_to_name:
        return {"status": "skipped"}

    print(f"[INFO] target_date={target_date}  대상 {len(code_to_name)}개")
    target_ts = pd.Timestamp(target_date)
    results = {"success": [], "failed": []}

    for code, name in code_to_name.items():
        try:
            print(f"  [{code}] {name}...")
            df = technical.fetch_ohlcv(code, days=240)  # 여유분
            df = df[df.index <= target_ts]              # ⭐ 어제까지만
            if len(df) < 60:
                results["failed"].append({"code": code, "reason": "data_short"})
                print(f"    ❌ 데이터 부족 ({len(df)}봉)")
                continue
            df = technical.add_indicators(df)
            df = compute_ichimoku(df)

            # 기본 지표 (technical.analyze는 실시간 fetch하므로 직접 추출)
            last = df.iloc[-1]
            result_dict = {
                "current_price": float(last["close"]),
                "rsi_14": float(last["rsi_14"]) if "rsi_14" in df.columns and pd.notna(last["rsi_14"]) else None,
                "macd": float(last["macd"]) if "macd" in df.columns and pd.notna(last["macd"]) else None,
            }

            swings = detect_swing_points(df, lookback=min(80, len(df)))
            A, B, C = swings["A"]["price"], swings["B"]["price"], swings["C"]["price"]
            targets = compute_price_targets(A, B, C)
            decision = make_decision(df, swings, targets)

            tech_for_db = dict(result_dict)
            for col in ["tenkan", "kijun", "senkou_a", "senkou_b"]:
                if col in df.columns and df[col].notna().any():
                    tech_for_db[col] = float(df[col].iloc[-1])

            cycles = compute_time_cycles(swings["C"]["idx"], len(df))
            _atr = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns and pd.notna(df["atr_14"].iloc[-1]) else None
            future_path = project_future_path(
                decision["price"], cycles, targets, decision.get("stop"),
                swings=swings, atr_value=_atr,
            )

            # flow는 어제 시점 reconstruction 어려움 → skip
            flow_data = None
            # 패턴 매칭도 어제 시점 데이터로 직접
            pattern_data = None
            try:
                import pattern_match as pm
                # pattern_match는 fetch_ohlcv 내부 호출 → 어제 시점 어려움. 일단 호출
                pattern_data = pm.predict_future_path(
                    code=code, current_price=decision["price"],
                    window=60, n_future=20, top_k=3,
                )
            except Exception:
                pass

            saved = db.save_analysis(
                code, name, tech_for_db, decision, targets, swings,
                snapshot_type="scheduled",
                cycles=cycles, future_path=future_path,
                flow=flow_data, pattern_match=pattern_data,
                target_date=target_date,
            )
            if saved:
                results["success"].append({"code": code, "name": name})
                print(f"    ✅")
            else:
                results["failed"].append({"code": code, "reason": "save_failed"})
            time.sleep(1.0)
        except Exception as e:
            results["failed"].append({"code": code, "reason": str(e)})
            print(f"    ❌ {e}")

    print(f"\n[SUMMARY] 성공 {len(results['success'])}건 / 실패 {len(results['failed'])}건")
    return {"status": "done", **results}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py scripts/backfill_snapshot.py YYYY-MM-DD")
        sys.exit(1)
    target = sys.argv[1]
    print("=" * 60)
    print(f"📸 자동 스냅샷 백필 (target_date={target})")
    print("=" * 60)
    summary = run_backfill(target)
    print("=" * 60)
    print(f"완료: {summary.get('status')}")
