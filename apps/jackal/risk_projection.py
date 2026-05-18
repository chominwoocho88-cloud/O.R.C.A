"""Projection helpers for JACKAL risk-decision shadow contracts."""

from __future__ import annotations

from typing import Any


def project_hunter_to_risk_decision(
    ticker: str,
    analyst: dict[str, Any] | None,
    devil: dict[str, Any] | None,
    final: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project JACKAL Hunter Devil/Final dicts to a RiskDecision payload."""

    analyst = analyst or {}
    devil = devil or {}
    final = final or {}
    diag = final.get("diag") if isinstance(final.get("diag"), dict) else {}

    return {
        "ticker": ticker,
        "source_system": "jackal_hunter",
        "decision_stage": "final",
        "analyst_score": analyst.get("analyst_score"),
        "devil_score": devil.get("devil_score"),
        "verdict": devil.get("verdict"),
        "main_risk": devil.get("main_risk"),
        "thesis_killer_hit": bool(devil.get("thesis_killer_hit", False)),
        "is_dead_cat": bool(devil.get("is_dead_cat", False)),
        "structural_decline": bool(devil.get("structural_decline", False)),
        "final_score": final.get("final_score"),
        "is_entry": bool(final.get("is_entry", False)),
        "block_reason": diag.get("block_reason"),
        "decision_label": final.get("label"),
    }


__all__ = ["project_hunter_to_risk_decision"]
