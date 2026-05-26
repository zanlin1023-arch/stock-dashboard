"""진입 적합도 점수화: 기술적 + 펀더멘털 지표 종합 → 객관 신호 평가."""
from __future__ import annotations

from typing import Any


def score_technical(tech: dict) -> tuple[int, list[tuple[str, int, str]]]:
    """기술적 분석 결과 → (점수, [(항목, 점수, 사유)])."""
    items: list[tuple[str, int, str]] = []
    score = 0

    rsi = tech.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            items.append(("RSI", +25, f"RSI {rsi:.1f} 과매도 — 반등 가능"))
            score += 25
        elif rsi < 50:
            items.append(("RSI", +10, f"RSI {rsi:.1f} 중립~약세권"))
            score += 10
        elif rsi <= 70:
            items.append(("RSI", 0, f"RSI {rsi:.1f} 중립"))
        else:
            items.append(("RSI", -25, f"RSI {rsi:.1f} 과매수 — 단기 차익실현 주의"))
            score -= 25

    sigs = tech.get("signals", [])
    for s in sigs:
        if "골든크로스" in s and "MACD" not in s:
            items.append(("이동평균", +20, "골든크로스 발생"))
            score += 20
        elif "데드크로스" in s and "MACD" not in s:
            items.append(("이동평균", -20, "데드크로스 발생"))
            score -= 20
        elif "정배열" in s:
            items.append(("배열", +15, "5>20>60 정배열 (상승 추세)"))
            score += 15
        elif "역배열" in s:
            items.append(("배열", -15, "5<20<60 역배열 (하락 추세)"))
            score -= 15
        elif "MACD 골든" in s:
            items.append(("MACD", +10, "MACD 골든크로스"))
            score += 10
        elif "MACD 데드" in s:
            items.append(("MACD", -10, "MACD 데드크로스"))
            score -= 10
        elif "볼린저 하단" in s:
            items.append(("볼린저", +10, "하단 이탈 (저점 가능)"))
            score += 10
        elif "볼린저 상단" in s:
            items.append(("볼린저", -10, "상단 이탈 (과열)"))
            score -= 10

    return max(-100, min(100, score)), items


def score_fundamental(fund: dict) -> tuple[int, list[tuple[str, int, str]]]:
    """기본적 분석 결과 → (점수, [(항목, 점수, 사유)])."""
    items: list[tuple[str, int, str]] = []
    score = 0

    ratios = fund.get("ratios") or {}
    fin = fund.get("financials") or {}
    years = fin.get("years", []) if fin.get("available") else []

    # PER
    per = ratios.get("per")
    if per is not None:
        if per > 50:
            items.append(("PER", -15, f"PER {per:.1f}배 — 고평가"))
            score -= 15
        elif per < 10:
            items.append(("PER", +10, f"PER {per:.1f}배 — 저평가권"))
            score += 10

    # PBR
    pbr = ratios.get("pbr")
    if pbr is not None:
        if pbr < 1:
            items.append(("PBR", +15, f"PBR {pbr:.2f}배 — 청산가치 이하"))
            score += 15
        elif pbr > 5:
            items.append(("PBR", -10, f"PBR {pbr:.2f}배 — 자산 대비 고평가"))
            score -= 10

    if years:
        latest = years[-1]
        # ROE
        roe = latest.get("roe")
        if roe is not None:
            if roe > 15:
                items.append(("ROE", +20, f"ROE {roe:.1f}% — 우수"))
                score += 20
            elif roe > 10:
                items.append(("ROE", +10, f"ROE {roe:.1f}% — 양호"))
                score += 10
            elif roe < 5:
                items.append(("ROE", -10, f"ROE {roe:.1f}% — 저조"))
                score -= 10

        # 영업이익률
        op_margin = latest.get("operating_margin")
        if op_margin is not None:
            if op_margin > 15:
                items.append(("영업이익률", +15, f"{op_margin:.1f}% — 고수익성"))
                score += 15
            elif op_margin < 5:
                items.append(("영업이익률", -10, f"{op_margin:.1f}% — 저수익성"))
                score -= 10

        # 영업이익률 추세
        if len(years) >= 2:
            prev_op = years[-2].get("operating_margin")
            if prev_op is not None and op_margin is not None and op_margin > prev_op + 2:
                items.append(("수익성 추세", +10, f"영업이익률 {prev_op:.1f}%→{op_margin:.1f}% 개선"))
                score += 10
            elif prev_op is not None and op_margin is not None and op_margin < prev_op - 2:
                items.append(("수익성 추세", -10, f"영업이익률 {prev_op:.1f}%→{op_margin:.1f}% 악화"))
                score -= 10

        # 매출 성장률
        rev_growth = latest.get("revenue_growth")
        if rev_growth is not None:
            if rev_growth > 15:
                items.append(("성장성", +15, f"매출 성장률 {rev_growth:+.1f}% — 고성장"))
                score += 15
            elif rev_growth > 5:
                items.append(("성장성", +5, f"매출 성장률 {rev_growth:+.1f}%"))
                score += 5
            elif rev_growth < 0:
                items.append(("성장성", -15, f"매출 성장률 {rev_growth:+.1f}% — 역성장"))
                score -= 15

        # 부채비율
        debt = latest.get("debt_ratio")
        if debt is not None:
            if debt < 50:
                items.append(("재무안정성", +10, f"부채비율 {debt:.1f}% — 안정"))
                score += 10
            elif debt < 100:
                items.append(("재무안정성", +5, f"부채비율 {debt:.1f}% — 양호"))
                score += 5
            elif debt > 200:
                items.append(("재무안정성", -15, f"부채비율 {debt:.1f}% — 위험"))
                score -= 15

    return max(-100, min(100, score)), items


def verdict(total: int) -> tuple[str, str]:
    """종합 점수 → (라벨, 해설)."""
    if total >= 70:
        return ("🟢 적극 진입 검토", "기술/펀더 모두 우호 — 추세/가치 동시 충족")
    if total >= 40:
        return ("🟢 진입 우호", "전반적 긍정 — 일부 약점 있으나 진입 명분 충분")
    if total >= 0:
        return ("🟡 중립/관망", "혼조 시그널 — 추가 확인 후 분할 진입 고려")
    if total >= -40:
        return ("🟠 진입 부적합", "약세 우세 — 진입 시점 재검토 필요")
    return ("🔴 강한 회피", "추세/지표 악화 — 보유 시 손절 검토")


def evaluate(tech: dict, fund: dict) -> dict[str, Any]:
    t_score, t_items = score_technical(tech)
    f_score, f_items = score_fundamental(fund)
    total = t_score + f_score
    label, comment = verdict(total)
    return {
        "technical_score": t_score,
        "fundamental_score": f_score,
        "total_score": total,
        "label": label,
        "comment": comment,
        "technical_items": t_items,
        "fundamental_items": f_items,
    }


def to_markdown(result: dict) -> str:
    lines = [
        "## 🎯 진입 적합도 평가",
        "",
        f"### 종합: {result['label']} (총점 **{result['total_score']:+d}**)",
        f"_{result['comment']}_",
        "",
        f"| 영역 | 점수 |",
        f"|------|-----|",
        f"| 기술적 | {result['technical_score']:+d} |",
        f"| 펀더멘털 | {result['fundamental_score']:+d} |",
        f"| **합계** | **{result['total_score']:+d}** |",
        "",
        "### 가산/감점 내역",
        "| 영역 | 항목 | 점수 | 사유 |",
        "|------|------|------|------|",
    ]
    for name, pts, reason in result["technical_items"]:
        lines.append(f"| 기술 | {name} | {pts:+d} | {reason} |")
    for name, pts, reason in result["fundamental_items"]:
        lines.append(f"| 펀더 | {name} | {pts:+d} | {reason} |")
    lines += [
        "",
        "> ⚠️ 본 점수는 객관 지표를 규칙 기반으로 합산한 **참고용 신호**이며 매수/매도 추천이 아닙니다. 거시 환경, 종목 고유 이슈, 본인 투자 목표를 함께 고려하세요.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    import fundamental
    import technical
    from _utils import resolve_ticker

    q = sys.argv[1] if len(sys.argv) > 1 else "005930"
    code, name = resolve_ticker(q)
    t = technical.analyze(code, name)
    f = fundamental.analyze(code, name)
    r = evaluate(t, f)
    print(to_markdown(r))
