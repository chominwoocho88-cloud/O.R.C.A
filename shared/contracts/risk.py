"""RiskDecision shadow contract for JACKAL decision boundaries.

This model describes the stable risk-decision fields produced around
JACKAL Devil and final-decision outputs. It defines the contract only.
Runtime shadow validation wiring is intentionally deferred to a future
sprint.
"""

from __future__ import annotations

from pydantic import Field

from .base import ContractModel


class RiskDecision(ContractModel):
    """Normalized risk decision contract."""

    ticker: str
    source_system: str
    decision_stage: str

    analyst_score: int | None = Field(default=None, ge=0, le=100)
    devil_score: int | None = Field(default=None, ge=0, le=100)
    verdict: str | None = None
    main_risk: str | None = None

    thesis_killer_hit: bool = False
    is_dead_cat: bool = False
    structural_decline: bool = False

    final_score: int | None = Field(default=None, ge=0, le=100)
    is_entry: bool = False
    block_reason: str | None = None
    decision_label: str | None = None


__all__ = ["RiskDecision"]
