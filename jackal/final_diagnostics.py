"""Diagnostic helpers for JACKAL Hunter final scoring."""

from __future__ import annotations


def build_final_diag(
    analyst: dict,
    devil: dict,
    *,
    block_reason: str | None = None,
    day1_score: int | float | None = None,
    swing_score: int | float | None = None,
    raw_score: int | float | None = None,
    penalty: int | float | None = None,
    before_adjust: int | float | None = None,
    weights: dict | None = None,
) -> dict:
    return {
        "block_reason": block_reason,
        "analyst_score": analyst.get("analyst_score"),
        "day1_score": day1_score if day1_score is not None else analyst.get("day1_score"),
        "swing_score": swing_score if swing_score is not None else analyst.get("swing_score"),
        "devil_score": devil.get("devil_score"),
        "raw_score": raw_score,
        "penalty": penalty,
        "before_adjust": before_adjust,
        "weights": weights,
    }


def format_final_diag(final: dict) -> str:
    diag = final.get("diag", {}) or {}
    if not diag:
        return ""

    parts = [
        f"d1:{diag.get('day1_score', '?')}",
        f"sw:{diag.get('swing_score', '?')}",
    ]
    block_reason = diag.get("block_reason")
    if block_reason:
        parts.append(f"block:{block_reason}")
        parts.append(f"pre:{diag.get('before_adjust', '?')}")
    else:
        parts.extend(
            [
                f"raw:{diag.get('raw_score', '?')}",
                f"pen:{diag.get('penalty', '?')}",
                f"pre:{diag.get('before_adjust', '?')}",
            ]
        )
    parts.append(f"learn:{final.get('probability_adjustment', 0)}")
    parts.append(f"hist:{final.get('historical_adjustment', 0)}")
    return " | [" + ",".join(parts) + "]"
