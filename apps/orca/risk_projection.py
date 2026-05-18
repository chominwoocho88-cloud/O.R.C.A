"""Projection helpers for ORCA risk-decision shadow contracts."""

from __future__ import annotations

from typing import Any


def _first_text(items: Any, *keys: str) -> str | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = str(item.get(key, "")).strip()
            if value:
                return value
    return None


def project_orca_devil_to_risk_decision(
    ticker: str | None,
    analyst: dict[str, Any] | None,
    devil: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project ORCA Devil output to a RiskDecision payload."""

    analyst = analyst or {}
    devil = devil or {}
    thesis_killers = devil.get("thesis_killers", [])
    main_risk = _first_text(devil.get("counterarguments", []), "against", "because", "risk_level")
    if not main_risk:
        main_risk = _first_text(devil.get("tail_risks", []), "risk", "event", "description")

    return {
        "ticker": str(ticker or "MARKET"),
        "source_system": "orca_devil",
        "decision_stage": "devil",
        "analyst_score": None,
        "devil_score": None,
        "verdict": devil.get("verdict"),
        "main_risk": main_risk,
        "thesis_killer_hit": bool(thesis_killers),
        "is_dead_cat": False,
        "structural_decline": False,
        "final_score": None,
        "is_entry": False,
        "block_reason": None,
        "decision_label": None,
    }


__all__ = ["project_orca_devil_to_risk_decision"]
