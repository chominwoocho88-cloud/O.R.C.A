"""AlphaSignal shadow contract for Phase 11.4.

This model maps the stable signal portion of Phase 9-2
jackal_prediction_cards into a typed contract.

It defines the contract only. It must not activate runtime validation
in ORCA or JACKAL flows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import EventEnvelope


class AlphaSignal(EventEnvelope):
    """Normalized hunt/scan alpha signal contract."""

    event_type: Literal["alpha_signal"] = "alpha_signal"

    ticker: str
    score: float = Field(ge=0, le=100)

    name: str | None = None
    day1_score: float | None = Field(default=None, ge=0, le=100)
    swing_score: float | None = Field(default=None, ge=0, le=100)
    devil_score: float | None = Field(default=None, ge=0, le=100)
    devil_verdict: str | None = None
    current_price: float | None = None
    entry_price_low: float | None = None
    entry_price_high: float | None = None
    target_price: float | None = None
    stop_price: float | None = None
    horizon_days: int = Field(default=5, ge=1, le=30)
    pattern_label: str | None = None
    main_reasoning: str | None = None
    market_regime: str | None = None
    fear_greed: int | None = Field(default=None, ge=0, le=100)
    fear_greed_label: str | None = None
    inflow_sectors: list[str] = Field(default_factory=list)
    alerted: bool = False
