"""Provider interfaces for LLM SDK abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from shared.llm.client import LLMResponse


@dataclass
class LLMProviderRequest:
    """Provider-agnostic request payload."""

    system: str
    user: str
    model: str
    max_tokens: int
    use_search: bool = False


@runtime_checkable
class LLMProvider(Protocol):
    """Provider interface for one SDK call.

    Retry, logging, auth standardization, and JSONL ledger ownership remain
    with LLMClient. Providers only translate a request into one SDK call.
    """

    auth_error_types: tuple[type[BaseException], ...]
    retry_error_types: tuple[type[BaseException], ...]

    def call_once(self, request: LLMProviderRequest) -> LLMResponse:
        """Make exactly one SDK call. Raise on error."""
        ...


__all__ = ["LLMProvider", "LLMProviderRequest"]
