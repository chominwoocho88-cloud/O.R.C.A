"""점수 신뢰도 곡선 — "이 시스템의 70점은 실제로 몇 점인가" (2026-06-12).

hunt 시점 final_score(기대)와 확정 결과(실현)를 점수 구간별로 증분
집계한다. 과신(점수 > 실현 승률)·과소신이 수치로 드러나고, 이 표가
쌓이면 R4 서프라이즈 학습(r' = r − 기대치)의 기대치 테이블이 된다.

관측 전용 — 어떤 점수도 바꾸지 않는다.
"""
from __future__ import annotations

# 구간 경계 (이상~미만). 라벨은 표시용.
SCORE_BINS: tuple[tuple[int, int, str], ...] = (
    (0, 40, "~39"),
    (40, 55, "40-54"),
    (55, 65, "55-64"),
    (65, 75, "65-74"),
    (75, 101, "75+"),
)


def bin_label(score: float) -> str | None:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    for low, high, label in SCORE_BINS:
        if low <= value < high:
            return label
    return None


def record_calibration(weights: dict, entry: dict) -> None:
    """확정 entry 1건을 score_calibration에 증분 반영 (additive 키)."""
    label = bin_label(entry.get("final_score"))
    if label is None:
        return
    hit = bool(entry.get("outcome_swing_hit") or entry.get("outcome_correct"))
    reward = entry.get("reward")
    table = weights.setdefault("score_calibration", {})
    rec = table.setdefault(label, {"n": 0, "hits": 0, "sum_score": 0.0, "sum_reward": 0.0})
    rec["n"] += 1
    rec["hits"] += int(hit)
    rec["sum_score"] = round(rec["sum_score"] + float(entry.get("final_score") or 0.0), 2)
    if reward is not None:
        rec["sum_reward"] = round(rec["sum_reward"] + float(reward), 4)


def calibration_rows(weights: dict, *, min_samples: int = 5) -> list[dict]:
    """표시용 행 — [{bin, n, avg_score, hit_pct, avg_reward, verdict}]."""
    table = weights.get("score_calibration") or {}
    rows = []
    for _, _, label in SCORE_BINS:
        rec = table.get(label) or {}
        n = int(rec.get("n") or 0)
        if n < min_samples:
            continue
        avg_score = rec["sum_score"] / n
        hit_pct = rec["hits"] / n * 100
        gap = avg_score - hit_pct
        verdict = "과신" if gap > 10 else ("과소신" if gap < -10 else "적정")
        rows.append({
            "bin": label, "n": n,
            "avg_score": round(avg_score, 1),
            "hit_pct": round(hit_pct, 1),
            "avg_reward": round(rec["sum_reward"] / n, 3),
            "verdict": verdict,
        })
    return rows


def calibration_hint(weights: dict, *, min_samples: int = 5) -> str:
    """Analyst 자기 보정 힌트 — 점수대별 실현 성적을 본인에게 환류."""
    rows = calibration_rows(weights, min_samples=min_samples)
    if not rows:
        return ""
    parts = [
        f"{row['bin']}점대: 실현 {row['hit_pct']:.0f}% ({row['verdict']}, n={row['n']})"
        for row in rows
    ]
    return ("\n[점수 신뢰도 — 네 과거 점수의 실현 성적]\n" + " | ".join(parts)
            + "\n과신 구간에선 점수를 보수적으로, 과소신 구간에선 소신껏 매겨라.\n")


__all__ = ("SCORE_BINS", "bin_label", "record_calibration",
           "calibration_rows", "calibration_hint")
