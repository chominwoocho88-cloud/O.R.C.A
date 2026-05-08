"""ORCA Phase 4 self-correction detector.

Phase 4 migration Sprint 2-1:
- drift detection only
- no behavior changes
- trigger wiring is planned for Sprint 2-2
- correction action is planned for Sprint 2-3

Design reference: docs/phase6/wave-f-meta-learning-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


DEFAULT_RECENT_DAYS = 7
DEFAULT_BASELINE_DAYS = 30
DEFAULT_MIN_RECENT_SAMPLES = 5
DEFAULT_MIN_BASELINE_SAMPLES = 15
DEFAULT_LOW_ACCURACY_THRESHOLD = 0.75
DEFAULT_DRIFT_DELTA_PCT = 0.15
DEFAULT_SEVERE_DROP_THRESHOLD = 0.15
PHASE4_CORRECTION_LADDER = [
    ("severe_drop", -0.10),
    ("low_accuracy", -0.05),
]


@dataclass(frozen=True)
class DriftResult:
    """Result of accuracy drift detection."""

    drift_detected: bool
    reason: str
    recent_accuracy: float
    baseline_accuracy: float
    recent_samples: int
    baseline_samples: int
    threshold_low_accuracy: float
    threshold_drift_delta: float


def _rate(correct: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return correct / total


def detect_drift(
    accuracy_data: dict[str, Any],
    *,
    recent_days: int = DEFAULT_RECENT_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    min_recent_samples: int = DEFAULT_MIN_RECENT_SAMPLES,
    min_baseline_samples: int = DEFAULT_MIN_BASELINE_SAMPLES,
    low_accuracy_threshold: float = DEFAULT_LOW_ACCURACY_THRESHOLD,
    drift_delta_pct: float = DEFAULT_DRIFT_DELTA_PCT,
    today: str | None = None,
) -> DriftResult:
    """Detect accuracy drift from ORCA accuracy data.

    The function is intentionally pure: it reads only the given dictionary and
    returns a structured result. It does not mutate weights, write files, send
    notifications, or change runtime behavior.
    """
    history = accuracy_data.get("history", [])

    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    recent_cutoff = (today_dt - timedelta(days=recent_days)).strftime("%Y-%m-%d")
    baseline_cutoff = (today_dt - timedelta(days=baseline_days)).strftime("%Y-%m-%d")

    recent = [h for h in history if h.get("date", "") > recent_cutoff]
    baseline = [h for h in history if h.get("date", "") > baseline_cutoff]

    recent_total = sum(h.get("total", 0) for h in recent)
    recent_correct = sum(h.get("correct", 0) for h in recent)
    baseline_total = sum(h.get("total", 0) for h in baseline)
    baseline_correct = sum(h.get("correct", 0) for h in baseline)

    recent_accuracy = _rate(recent_correct, recent_total)
    baseline_accuracy = _rate(baseline_correct, baseline_total)

    if recent_total < min_recent_samples or baseline_total < min_baseline_samples:
        return DriftResult(
            drift_detected=False,
            reason="insufficient_samples",
            recent_accuracy=recent_accuracy,
            baseline_accuracy=baseline_accuracy,
            recent_samples=recent_total,
            baseline_samples=baseline_total,
            threshold_low_accuracy=low_accuracy_threshold,
            threshold_drift_delta=drift_delta_pct,
        )

    is_low_accuracy = recent_accuracy < low_accuracy_threshold
    is_significant_drop = (baseline_accuracy - recent_accuracy) >= drift_delta_pct
    drift_detected = is_low_accuracy or is_significant_drop

    if drift_detected:
        if is_low_accuracy and is_significant_drop:
            reason = "low_accuracy_and_drop"
        elif is_low_accuracy:
            reason = "low_accuracy"
        else:
            reason = "significant_drop"
    else:
        reason = "stable"

    return DriftResult(
        drift_detected=drift_detected,
        reason=reason,
        recent_accuracy=recent_accuracy,
        baseline_accuracy=baseline_accuracy,
        recent_samples=recent_total,
        baseline_samples=baseline_total,
        threshold_low_accuracy=low_accuracy_threshold,
        threshold_drift_delta=drift_delta_pct,
    )


def get_correction_severity(drift_result: DriftResult) -> str | None:
    """Classify drift severity for future correction actions."""
    if not drift_result.drift_detected:
        return None

    delta = drift_result.baseline_accuracy - drift_result.recent_accuracy
    if delta >= DEFAULT_SEVERE_DROP_THRESHOLD:
        return "severe_drop"
    if drift_result.recent_accuracy < DEFAULT_LOW_ACCURACY_THRESHOLD:
        return "low_accuracy"
    return None


def get_correction_delta(severity: str) -> float:
    """Return the conservative correction delta for a severity label."""
    for label, delta in PHASE4_CORRECTION_LADDER:
        if label == severity:
            return delta
    return 0.0


def apply_phase4_correction(drift_result: DriftResult) -> dict[str, Any]:
    """Return Phase 4 correction decision info without mutating weights."""
    severity = get_correction_severity(drift_result)
    if severity is None:
        return {
            "correction_applied": False,
            "severity": None,
            "delta": 0.0,
            "reason": "no_correction_needed",
        }

    delta = get_correction_delta(severity)
    return {
        "correction_applied": True,
        "severity": severity,
        "delta": delta,
        "reason": f"correction_{severity}",
    }


__all__ = [
    "DEFAULT_RECENT_DAYS",
    "DEFAULT_BASELINE_DAYS",
    "DEFAULT_MIN_RECENT_SAMPLES",
    "DEFAULT_MIN_BASELINE_SAMPLES",
    "DEFAULT_LOW_ACCURACY_THRESHOLD",
    "DEFAULT_DRIFT_DELTA_PCT",
    "DEFAULT_SEVERE_DROP_THRESHOLD",
    "PHASE4_CORRECTION_LADDER",
    "DriftResult",
    "detect_drift",
    "get_correction_severity",
    "get_correction_delta",
    "apply_phase4_correction",
]
