"""Provider-facing LLM client for ORCA.

This module keeps Anthropic SDK details in one place and records every
successful or failed LLM call as append-only JSONL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
import time
from typing import Any


KST = timezone(timedelta(hours=9))


@dataclass
class LLMResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    web_search_count: int = 0
    server_tool_use_web_search_requests: int = 0
    service_tier: str = ""
    stop_reason: str = ""
    elapsed_ms: int = 0
    attempt: int = 1
    success: bool = True


@dataclass
class LLMFailure:
    call_site: str
    error_type: str
    message: str
    attempt: int
    elapsed_ms: int
    model: str


class LLMClient:
    """Small Anthropic adapter with usage capture and JSONL audit logging."""

    def __init__(self, api_key: str | None, fail_fast: bool = True, log_path: str | Path | None = None):
        if fail_fast and not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY missing - LLM client requires API key")
        self.api_key = api_key or ""
        self.fail_fast = fail_fast
        if log_path is None:
            env_log_path = os.environ.get("ORCA_LLM_LOG_PATH")
            log_path = Path(env_log_path) if env_log_path else Path("data/llm_log.jsonl")
        self.log_path = Path(log_path)
        self._log_path = self.log_path
        self._provider = None

    def call(
        self,
        *,
        system: str,
        user: str,
        model: str,
        max_tokens: int,
        use_search: bool = False,
        max_retries: int = 2,
        call_site: str,
    ) -> LLMResponse:
        """Call the LLM and return text plus usage metadata.

        ``max_retries`` follows the legacy ORCA meaning: it is the total number
        of attempts, not retries after the first attempt.
        """

        total_attempts = max(1, int(max_retries or 1))
        last_exc: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            start = time.perf_counter()
            auth_errors: tuple[type[BaseException], ...] = ()
            retry_errors: tuple[type[BaseException], ...] = ()
            try:
                anthropic = self._anthropic()
                auth_errors = self._exception_tuple(
                    anthropic,
                    "AuthenticationError",
                    "PermissionDeniedError",
                    "NotFoundError",
                )
                retry_errors = self._exception_tuple(
                    anthropic,
                    "InternalServerError",
                    "RateLimitError",
                )

                from shared.llm.providers.base import LLMProviderRequest

                request = LLMProviderRequest(
                    system=system,
                    user=user,
                    model=model,
                    max_tokens=max_tokens,
                    use_search=use_search,
                )
                response = self._get_provider().call_once(request)
                response.attempt = attempt
                self._log_success(response, call_site)
                if response.stop_reason == "max_tokens":
                    print(
                        "LLM warning: max_tokens reached "
                        + f"(call_site={call_site}, model={model}, max_tokens={max_tokens})"
                    )
                return response
            except auth_errors as exc:  # type: ignore[misc]
                elapsed_ms = self._elapsed_ms(start)
                standard_message = self._format_auth_failure_message(
                    call_site=call_site,
                    model=model,
                    attempt=attempt,
                    error_class=type(exc).__name__,
                    original_msg=str(exc),
                )
                exc.args = (standard_message,)
                failure = LLMFailure(
                    call_site=call_site,
                    error_type=self._error_type(exc, auth_error=True),
                    message=standard_message,
                    attempt=attempt,
                    elapsed_ms=elapsed_ms,
                    model=model,
                )
                self._log_failure(failure)
                raise
            except retry_errors as exc:  # type: ignore[misc]
                last_exc = exc
                if attempt < total_attempts:
                    continue
                elapsed_ms = self._elapsed_ms(start)
                failure = LLMFailure(
                    call_site=call_site,
                    error_type="retry_exhausted",
                    message=str(exc),
                    attempt=attempt,
                    elapsed_ms=elapsed_ms,
                    model=model,
                )
                self._log_failure(failure)
                raise
            except Exception as exc:
                elapsed_ms = self._elapsed_ms(start)
                failure = LLMFailure(
                    call_site=call_site,
                    error_type=self._error_type(exc),
                    message=str(exc),
                    attempt=attempt,
                    elapsed_ms=elapsed_ms,
                    model=model,
                )
                self._log_failure(failure)
                raise

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("LLM call failed without an exception")

    def _log_success(self, response: LLMResponse, call_site: str) -> None:
        payload = {
            "ts": self._timestamp(),
            "type": "success",
            "call_site": call_site,
            **asdict(response),
        }
        payload["web_search_requests"] = payload.pop("server_tool_use_web_search_requests")
        payload.pop("text", None)
        payload.pop("success", None)
        self._append_jsonl(payload)

    def _log_failure(self, failure: LLMFailure) -> None:
        payload = {
            "ts": self._timestamp(),
            "type": "failure",
            **asdict(failure),
        }
        self._append_jsonl(payload)

    def _get_provider(self):
        if self._provider is None:
            from shared.llm.providers.anthropic import AnthropicProvider

            self._provider = AnthropicProvider(api_key=self.api_key)
        return self._provider

    @staticmethod
    def _anthropic():
        return importlib.import_module("anthropic")

    @staticmethod
    def _exception_tuple(module, *names: str) -> tuple[type[BaseException], ...]:
        classes: list[type[BaseException]] = []
        for name in names:
            cls = getattr(module, name, None)
            if isinstance(cls, type) and issubclass(cls, BaseException):
                classes.append(cls)
        return tuple(classes)

    @staticmethod
    def _elapsed_ms(start: float) -> int:
        return int(round((time.perf_counter() - start) * 1000))

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(KST).isoformat(timespec="seconds")

    @staticmethod
    def _usage_int(usage, *names: str) -> int:
        if usage is None:
            return 0
        for name in names:
            value = LLMClient._usage_value(usage, name)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    return 0
        return 0

    @staticmethod
    def _usage_value(usage, name: str):
        if usage is None:
            return None
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        return value

    @staticmethod
    def _error_type(exc: Exception, *, auth_error: bool = False) -> str:
        name = type(exc).__name__
        if auth_error:
            if name == "AuthenticationError":
                return "auth_failed"
            if name == "PermissionDeniedError":
                return "permission_denied"
            if name == "NotFoundError":
                return "not_found"
        if name == "RateLimitError":
            return "rate_limit"
        if name == "InternalServerError":
            return "server_error"
        return name or "unknown_error"

    @staticmethod
    def _format_auth_failure_message(
        *,
        call_site: str,
        model: str,
        attempt: int,
        error_class: str,
        original_msg: str,
    ) -> str:
        return (
            f"LLM authentication failure at {call_site} "
            f"(model={model}, attempt={attempt}): "
            f"{error_class}: {original_msg}. "
            "Check ANTHROPIC_API_KEY / GitHub Secret ANTHROPIC_API_KEY."
        )

    def _append_jsonl(self, payload: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
