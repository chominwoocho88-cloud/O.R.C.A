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


class OrcaReporterOutput(ContractModel):
    """Loose contract for ORCA Reporter output."""

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    one_line_summary: str
    market_regime: str
    confidence_overall: str

    analysis_date: str | None = None
    analysis_time: str | None = None
    mode: str | None = None
    mode_label: str | None = None
    trend_phase: str | None = None
    consensus_level: str | None = None

    trend_strategy: dict[str, Any] = Field(default_factory=dict)
    volatility_index: dict[str, Any] = Field(default_factory=dict)
    retail_reversal_signal: dict[str, Any] = Field(default_factory=dict)
    korea_focus: dict[str, Any] = Field(default_factory=dict)
    agent_consensus: dict[str, Any] = Field(default_factory=dict)
    meta_improvement: dict[str, Any] = Field(default_factory=dict)

    top_headlines: list[dict[str, Any]] = Field(default_factory=list)
    outflows: list[dict[str, Any]] = Field(default_factory=list)
    inflows: list[dict[str, Any]] = Field(default_factory=list)
    neutral_waiting: list[dict[str, Any]] = Field(default_factory=list)
    hidden_signals: list[dict[str, Any]] = Field(default_factory=list)
    counterarguments: list[dict[str, Any]] = Field(default_factory=list)
    thesis_killers: list[dict[str, Any]] = Field(default_factory=list)
    tail_risks: list[dict[str, Any]] = Field(default_factory=list)
    tomorrow_setup: list[dict[str, Any]] = Field(default_factory=list)
    actionable_watch: list[dict[str, Any]] = Field(default_factory=list)


__all__ = ["OrcaHunterOutput", "OrcaAnalystOutput", "OrcaReporterOutput"]
