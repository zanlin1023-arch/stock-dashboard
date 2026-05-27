"""일일 추천 종목 — 장 마감 후 자동 추천 → Supabase 저장.

GitHub Actions cron으로 평일 16:30 KST 실행.
환경변수: SUPABASE_URL, SUPABASE_KEY, OPENDART_API_KEY
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Windows cp949 → UTF-8 (로컬 테스트용)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analyzer"))

# 로컬 .streamlit/secrets.toml에서 env 로드
if not os.getenv("SUPABASE_URL"):
    secrets_file = ROOT / ".streamlit" / "secrets.toml"
    if secrets_file.exists():
        for line in secrets_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run_daily_recommend(top_n: int = 5, session: str = "evening", target_date: str | None = None) -> dict:
    from analyzer import db
    import recommend

    if not db.is_db_available():
        print("[ERROR] Supabase 미설정 (SUPABASE_URL / SUPABASE_KEY)")
        return {"status": "failed", "reason": "no_db"}

    # 보유 종목은 제외 (관심은 포함 — 변화 추적)
    exclude = set()
    try:
        for h in db.list_holdings():
            exclude.add(h["stock_code"])
        print(f"[INFO] 제외 종목 {len(exclude)}개")
    except Exception as e:
        print(f"[WARN] 보유 조회 실패 (계속 진행): {e}")

    print(f"[INFO] 추천 분석 시작 (top_n={top_n}, session={session})")
    try:
        results = recommend.recommend(top_n_per_tier=top_n, exclude=exclude, session=session)
    except Exception as e:
        print(f"[ERROR] recommend 실패: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "failed", "reason": str(e)}

    total = sum(len(results.get(k, [])) for k in ["large", "mid", "small"])
    print(f"[INFO] 추천 종목 {total}개 (대형 {len(results.get('large', []))}, "
          f"중형 {len(results.get('mid', []))}, 소형 {len(results.get('small', []))})")

    if total == 0:
        print("[WARN] 추천 종목 없음. 저장 건너뜀.")
        return {"status": "no_results"}

    saved = db.save_recommendations(results, session=session, target_date=target_date)
    print(f"[OK] DB 저장 완료: {saved}건 (date={target_date or 'today'})")

    return {"status": "done", "saved": saved, "tier_counts": {
        k: len(results.get(k, [])) for k in ["large", "mid", "small"]
    }}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--session", default="evening", choices=["morning", "evening"])
    parser.add_argument("--date", default=None, help="YYYY-MM-DD (백필용, 미지정 시 오늘)")
    args = parser.parse_args()

    print("=" * 60)
    print(f"🎯 일일 추천 종목 ({args.session}) date={args.date or 'today'}")
    print("=" * 60)
    result = run_daily_recommend(top_n=args.top_n, session=args.session, target_date=args.date)
    print("=" * 60)
    print(f"완료: {result}")
    print("=" * 60)
