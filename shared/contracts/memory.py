"""MemoryContext shadow contract for Phase 11.6.

This model maps Phase 9-4 jackal_memory_context outputs into a typed
read-only context contract.

MemoryInjection is intentionally excluded from this phase.
This module defines the contract only. It must not activate runtime
validation in ORCA or JACKAL flows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .base import EventEnvelope


class MemoryContext(EventEnvelope):
    """Learned memory context contract."""

    event_type: Literal["memory_context"] = "memory_context"

    stats_block: str = Field(min_length=1)
    sample_size: int = Field(ge=0)
    win_rate: float = Field(ge=0.0, le=1.0)
    avg_outcome: float

    source: Literal["prediction_cards", "candidate_lessons"]
    match_scope: str = Field(min_length=1)
    role: Literal["analyst", "devil"]

    global_resolved: int | None = Field(default=None, ge=0)
