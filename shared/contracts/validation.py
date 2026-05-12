"""Shadow validation helper for contract models.

This module provides a fail-open validation helper for future ORCA/JACKAL
runtime boundaries. It does not create file logs, database audit rows, or
runtime wiring by itself.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Literal, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
ValidationMode = Literal["warn", "strict", "hard"]


def shadow_validate(
    model_cls: type[T],
    payload: dict[str, Any],
    *,
    on_error: ValidationMode = "warn",
    context: str = "",
    audit_logger: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[bool, T | None, ValidationError | None]:
    """Validate a payload against a contract model in shadow mode.

    Returns:
        (is_valid, model_instance_or_none, error_or_none)

    Raises:
        ValidationError: when validation fails and on_error is "hard".
        ValueError: when on_error is not a supported mode.
    """
    if on_error not in ("warn", "strict", "hard"):
        raise ValueError(f"Unsupported shadow validation mode: {on_error}")

    try:
        model = model_cls.model_validate(payload)
        _emit_audit_event(
            audit_logger,
            _build_audit_event(
                model_cls,
                payload,
                "pass",
                error_count=0,
                error_summary=None,
                context=context,
            )
        )
        return True, model, None
    except ValidationError as error:
        error_summary = _summarize_error(error)

        if on_error == "warn":
            logger.warning(
                "[shadow_validate] %s @ %s failed: %s",
                model_cls.__name__,
                context or "unknown",
                error_summary,
            )
        elif on_error == "strict":
            logger.error(
                "[shadow_validate] %s @ %s failed (strict): %s",
                model_cls.__name__,
                context or "unknown",
                error_summary,
            )

        _emit_audit_event(
            audit_logger,
            _build_audit_event(
                model_cls,
                payload,
                "fail",
                error_count=len(error.errors()),
                error_summary=error_summary,
                context=context,
            )
        )

        if on_error == "hard":
            raise

        return False, None, error


def _build_audit_event(
    model_cls: type[BaseModel],
    payload: dict[str, Any],
    validation_status: Literal["pass", "fail"],
    *,
    error_count: int,
    error_summary: str | None,
    context: str,
) -> dict[str, Any]:
    """Build audit metadata without storing the full payload."""
    return {
        "contract_name": model_cls.__name__,
        "context": context,
        "validation_status": validation_status,
        "error_count": error_count,
        "error_summary": error_summary,
        "event_id": _payload_field(payload, "event_id"),
        "correlation_id": _payload_field(payload, "correlation_id"),
        "prediction_event_id": _payload_field(payload, "prediction_event_id"),
        "payload_hash": _hash_payload(payload),
    }


def _payload_field(payload: dict[str, Any], key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return None


def _hash_payload(payload: dict[str, Any]) -> str | None:
    """Return a deterministic SHA256 hash for a payload."""
    try:
        canonical = json.dumps(
            payload,
            sort_keys=True,
            default=str,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    except Exception:
        return None


def _emit_audit_event(
    audit_logger: Callable[[dict[str, Any]], None] | None,
    event: dict[str, Any],
) -> None:
    """Emit an audit event without letting logger failures affect validation."""
    if not audit_logger:
        return
    try:
        audit_logger(event)
    except Exception as exc:
        logger.warning("[shadow_validate] audit logger failed: %s", exc)


def _summarize_error(error: ValidationError) -> str:
    """Summarize the first validation error in a compact form."""
    errors = error.errors()
    if not errors:
        return ""

    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", []))
    msg = first.get("msg", "")
    return f"{loc}: {msg}" if loc else msg
