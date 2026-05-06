"""Provider-facing LLM client for ORCA.

This module keeps Anthropic SDK details in one place and records every
successful or failed LLM call as append-only JSONL.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import importlib
import json
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
        self.log_path = Path(log_path) if log_path is not None else Path("data/llm_log.jsonl")
        self._client = None

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

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if use_search:
            kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

        total_attempts = max(1, int(max_retries or 1))
        last_exc: Exception | None = None

        for attempt in range(1, total_attempts + 1):
            start = time.perf_counter()
            full = ""
            web_search_count = 0
            final_message = None
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

                stream = self._get_client().messages.stream(**kwargs)
                with stream as s:
                    for ev in s:
                        ev_type = getattr(ev, "type", "")
                        if ev_type == "content_block_start":
                            block = getattr(ev, "content_block", None)
                            if getattr(block, "type", "") == "tool_use":
                                web_search_count += 1
                                query = self._tool_query(block)
                                if query:
                                    print("    Search [" + str(web_search_count) + "]: " + query)
                        elif ev_type == "content_block_delta":
                            delta = getattr(ev, "delta", None)
                            if getattr(delta, "type", "") == "text_delta":
                                full += getattr(delta, "text", "")
                    if hasattr(s, "get_final_message"):
                        final_message = s.get_final_message()

                if not full and final_message is not None:
                    full = self._text_from_message(final_message)
                if web_search_count == 0 and final_message is not None:
                    web_search_count = self._count_tool_use_blocks(final_message)

                usage = getattr(final_message, "usage", None)
                stop_reason = str(getattr(final_message, "stop_reason", "") or "")
                elapsed_ms = self._elapsed_ms(start)
                response = LLMResponse(
                    text=full,
                    model=model,
                    input_tokens=self._usage_int(usage, "input_tokens"),
                    output_tokens=self._usage_int(usage, "output_tokens"),
                    cache_read_tokens=self._usage_int(
                        usage,
                        "cache_read_tokens",
                        "cache_read_input_tokens",
                    ),
                    cache_creation_tokens=self._usage_int(
                        usage,
                        "cache_creation_tokens",
                        "cache_creation_input_tokens",
                    ),
                    web_search_count=web_search_count,
                    stop_reason=stop_reason,
                    elapsed_ms=elapsed_ms,
                    attempt=attempt,
                )
                self._log_success(response, call_site)
                if stop_reason == "max_tokens":
                    print(
                        "LLM warning: max_tokens reached "
                        + f"(call_site={call_site}, model={model}, max_tokens={max_tokens})"
                    )
                return response
            except auth_errors as exc:  # type: ignore[misc]
                elapsed_ms = self._elapsed_ms(start)
                failure = LLMFailure(
                    call_site=call_site,
                    error_type=self._error_type(exc, auth_error=True),
                    message=str(exc),
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

    def _get_client(self):
        if self._client is None:
            self._client = self._anthropic().Anthropic(api_key=self.api_key)
        return self._client

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
            value = getattr(usage, name, None)
            if value is None and isinstance(usage, dict):
                value = usage.get(name)
            if value is not None:
                try:
                    return int(value)
                except Exception:
                    return 0
        return 0

    @staticmethod
    def _text_from_message(message) -> str:
        parts: list[str] = []
        for block in getattr(message, "content", []) or []:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(str(text))
        return "".join(parts)

    @staticmethod
    def _count_tool_use_blocks(message) -> int:
        count = 0
        for block in getattr(message, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type is None and isinstance(block, dict):
                block_type = block.get("type")
            if block_type == "tool_use":
                count += 1
        return count

    @staticmethod
    def _tool_query(block) -> str:
        raw_input = getattr(block, "input", None)
        if raw_input is None and isinstance(block, dict):
            raw_input = block.get("input")
        if isinstance(raw_input, dict):
            return str(raw_input.get("query", "") or "")
        return ""

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

    def _append_jsonl(self, payload: dict[str, Any]) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
