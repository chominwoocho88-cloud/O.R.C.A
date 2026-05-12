"""MemoryContext and MemoryInjection shadow contracts.

These models describe learned-memory context payloads and the derived
prompt-injection block used by JACKAL memory shadow flows.

This module defines contracts only. It must not activate runtime
validation or prompt injection in ORCA or JACKAL flows.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

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


class MemoryInjection(EventEnvelope):
    """Prompt injection block produced from learned memory context."""

    event_type: Literal["memory_injection"] = "memory_injection"

    injection_block: str = Field(min_length=1, max_length=1000)
    injection_block_chars: int = Field(ge=0, le=1000)
    role: Literal["analyst", "devil"]
    source: Literal["prediction_cards", "candidate_lessons"]
    sample_size: int = Field(ge=0)

    @model_validator(mode="after")
    def _block_length_matches(self) -> "MemoryInjection":
        if self.injection_block_chars != len(self.injection_block):
            raise ValueError("injection_block_chars must match len(injection_block)")
        return self
