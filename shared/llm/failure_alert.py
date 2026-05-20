"""Fail-open Telegram alert for final LLM failures."""

from __future__ import annotations

import os
from html import escape
from typing import Any


_LLM_FAILURE_ALERT_SENT = False


def _is_enabled() -> bool:
    return os.environ.get("LLM_FAILURE_TELEGRAM_ALERTS", "").strip() != "0"


def _format_message(failure: dict[str, Any]) -> str:
    error_type = escape(str(failure.get("error_type") or "unknown_error"))
    call_site = escape(str(failure.get("call_site") or "unknown"))
    model = escape(str(failure.get("model") or "unknown"))
    attempt = escape(str(failure.get("attempt") or "?"))
    message = str(failure.get("message") or "")
    if len(message) > 300:
        message = message[:297] + "..."
    message = escape(message)

    lines = [
        "<b>LLM final failure</b>",
        f"error_type: <code>{error_type}</code>",
        f"call_site: <code>{call_site}</code>",
        f"model: <code>{model}</code>",
        f"attempt: <code>{attempt}</code>",
    ]
    run_id = os.environ.get("GITHUB_RUN_ID")
    workflow = os.environ.get("GITHUB_WORKFLOW")
    if run_id:
        lines.append(f"run_id: <code>{run_id}</code>")
    if workflow:
        lines.append(f"workflow: <code>{workflow}</code>")
    if message:
        lines.append(f"message: <code>{message}</code>")
    lines.append("<i>Further LLM failures in this process are suppressed.</i>")
    return "\n".join(lines)


def maybe_alert_failure(failure: dict[str, Any]) -> None:
    """Send one Telegram alert per process for final LLM failures."""
    global _LLM_FAILURE_ALERT_SENT

    if _LLM_FAILURE_ALERT_SENT or not _is_enabled():
        return

    try:
        message = _format_message(failure)
    except Exception:
        _LLM_FAILURE_ALERT_SENT = True
        return

    try:
        from orca.notify_transport import send_message

        send_message(message)
    except Exception:
        pass
    finally:
        _LLM_FAILURE_ALERT_SENT = True


def reset_for_testing() -> None:
    global _LLM_FAILURE_ALERT_SENT
    _LLM_FAILURE_ALERT_SENT = False


__all__ = ["maybe_alert_failure", "reset_for_testing"]
