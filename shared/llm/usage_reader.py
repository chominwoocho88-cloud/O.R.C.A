"""Read token usage from the shared LLM JSONL ledger."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from shared.paths import LLM_LOG_FILE

KST = timezone(timedelta(hours=9))

_EMPTY_USAGE = {
    "call_count": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cache_read_tokens": 0,
    "cache_creation_tokens": 0,
    "web_search_requests": 0,
}


def read_jackal_today_tokens(
    today: str | None = None,
    log_path: Path | None = None,
) -> int:
    """Read today's JACKAL token usage from data/llm_log.jsonl."""
    target_date = today or date.today().isoformat()
    return read_jackal_tokens_by_date(log_path=log_path).get(target_date, 0)


def read_jackal_tokens_by_date(log_path: Path | None = None) -> dict[str, int]:
    """Return JACKAL token totals grouped by YYYY-MM-DD."""
    totals: dict[str, int] = {}
    path = Path(log_path) if log_path is not None else LLM_LOG_FILE
    if not path.exists():
        return totals

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return totals

    for line in lines:
        entry = _parse_json_line(line)
        if not entry:
            continue
        if entry.get("type") != "success":
            continue
        if not str(entry.get("call_site", "")).startswith("jackal."):
            continue
        entry_date = str(entry.get("ts", ""))[:10]
        if not entry_date:
            continue
        totals[entry_date] = totals.get(entry_date, 0) + _actual_tokens(entry)
    return totals


def read_orca_usage_by_month(log_path: Path | None = None) -> dict[str, dict[str, int]]:
    """Read ORCA token usage from data/llm_log.jsonl grouped by KST month."""
    totals: dict[str, dict[str, int]] = {}
    for entry in _iter_success_entries(log_path=log_path, prefix="orca."):
        ts = _parse_timestamp(entry.get("ts"))
        if ts is None:
            continue
        month = ts.astimezone(KST).strftime("%Y-%m")
        bucket = totals.setdefault(month, _empty_usage())
        _add_usage(bucket, entry)
    return totals


def read_orca_today_usage(
    today: str | None = None,
    log_path: Path | None = None,
) -> dict[str, int]:
    """Read today's ORCA token usage from data/llm_log.jsonl using KST dates."""
    target_date = today or date.today().isoformat()
    usage = _empty_usage()
    for entry in _iter_success_entries(log_path=log_path, prefix="orca."):
        ts = _parse_timestamp(entry.get("ts"))
        if ts is None:
            continue
        if ts.astimezone(KST).date().isoformat() != target_date:
            continue
        _add_usage(usage, entry)
    return usage


def _iter_success_entries(log_path: Path | None, prefix: str):
    path = Path(log_path) if log_path is not None else LLM_LOG_FILE
    if not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    for line in lines:
        entry = _parse_json_line(line)
        if not entry:
            continue
        if entry.get("type") != "success":
            continue
        if not str(entry.get("call_site", "")).startswith(prefix):
            continue
        yield entry


def _parse_json_line(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _actual_tokens(entry: dict[str, Any]) -> int:
    return (
        _int_field(entry, "input_tokens")
        + _int_field(entry, "output_tokens")
        + _int_field(entry, "cache_read_tokens")
        + _int_field(entry, "cache_creation_tokens")
    )


def _add_usage(bucket: dict[str, int], entry: dict[str, Any]) -> None:
    bucket["call_count"] += 1
    bucket["input_tokens"] += _int_field(entry, "input_tokens")
    bucket["output_tokens"] += _int_field(entry, "output_tokens")
    bucket["cache_read_tokens"] += _int_field(entry, "cache_read_tokens")
    bucket["cache_creation_tokens"] += _int_field(entry, "cache_creation_tokens")
    bucket["web_search_requests"] += _int_field(entry, "web_search_requests")


def _empty_usage() -> dict[str, int]:
    return dict(_EMPTY_USAGE)


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KST)
    return parsed


def _int_field(entry: dict[str, Any], key: str) -> int:
    try:
        return int(entry.get(key, 0) or 0)
    except Exception:
        return 0
