"""PredictionOutcome shadow contract for Phase 11.5.

This model maps Phase 9-3 jackal_outcome_resolver outputs into
per-horizon outcome events.

One prediction can produce three outcome events: d1, d3, and d5.
This module defines the contract only. It must not activate runtime
validation in ORCA or JACKAL flows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .base import EventEnvelope


class PredictionOutcome(EventEnvelope):
    """Per-horizon prediction outcome contract."""

    event_type: Literal["prediction_outcome"] = "prediction_outcome"

    prediction_event_id: str = Field(
        description="Original AlphaSignal or prediction-card event_id."
    )
    horizon: Literal["d1", "d3", "d5"]
    outcome: Literal["win", "loss", "neutral"]

    actual_high: float | None = None
    actual_low: float | None = None
    actual_close: float | None = None
    return_pct: float | None = None

    observed_at: datetime
    resolved_by: str | None = None
