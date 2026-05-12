"""Shared contract model base for Phase 11.3.

This module defines shadow contract types only.
It must not activate runtime validation in ORCA or JACKAL flows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Common base for typed contract models."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class EventEnvelope(ContractModel):
    """Common envelope for future file, DB, and event handoffs."""

    schema_version: Literal["v1"] = "v1"
    event_id: str
    source_system: Literal["orca", "jackal", "atlas", "falcon", "system"]
    event_type: str
    occurred_at: datetime

    analysis_date: str | None = None
    run_id: str | None = None
    correlation_id: str | None = None
    ticker: str | None = None
    market: Literal["US", "KR", "CRYPTO", "UNKNOWN"] | None = None
    build_hash: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
