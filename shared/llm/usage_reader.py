"""Read token usage from the shared LLM JSONL ledger."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from shared.paths import LLM_LOG_FILE


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


def _int_field(entry: dict[str, Any], key: str) -> int:
    try:
        return int(entry.get(key, 0) or 0)
    except Exception:
        return 0
