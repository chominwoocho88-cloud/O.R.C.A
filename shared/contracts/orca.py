"""ORCA agent output shadow contracts."""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from .base import ContractModel


class OrcaHunterOutput(ContractModel):
    """Loose contract for ORCA Hunter output."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    collected_at: str | None = None
    mode: str
    raw_signals: list[dict[str, Any]] = Field(default_factory=list)
    market_snapshot: dict[str, Any] = Field(default_factory=dict)
    total_signals: int | None = Field(default=None, ge=0)


class OrcaAnalystOutput(ContractModel):
    """Loose contract for ORCA Analyst output."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    market_regime: str
    trend_phase: str
    analyst_confidence: str | None = None
    trend_strategy: dict[str, Any] = Field(default_factory=dict)
    regime_reason: str | None = None
    volatility_index: dict[str, Any] = Field(default_factory=dict)
    retail_reversal_signal: dict[str, Any] = Field(default_factory=dict)
    outflows: list[dict[str, Any]] = Field(default_factory=list)
    inflows: list[dict[str, Any]] = Field(default_factory=list)
    neutral_waiting: list[dict[str, Any]] = Field(default_factory=list)
    hidden_signals: list[dict[str, Any]] = Field(default_factory=list)
    korea_focus: dict[str, Any] = Field(default_factory=dict)


__all__ = ["OrcaHunterOutput", "OrcaAnalystOutput"]
