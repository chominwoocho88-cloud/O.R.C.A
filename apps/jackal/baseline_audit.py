"""Baseline fallback audit helpers for JACKAL."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from shared.paths import JACKAL_LEGACY_DIR


KST = timezone(timedelta(hours=9))
AUDIT_LOG_PATH = JACKAL_LEGACY_DIR / "baseline_fallback_audit.log"

log = logging.getLogger(__name__)


def record_baseline_fallback(
    *,
    component: str,
    regime_source: str,
    regime: str,
    baseline_exists: bool,
    memory_exists: bool,
    extra: Mapping[str, Any] | None = None,
    audit_log_path: Path | None = None,
) -> None:
    """Append non-baseline regime source cases to a JSONL audit log."""
    if regime_source == "baseline":
        return

    path = audit_log_path or AUDIT_LOG_PATH
    try:
        entry: dict[str, Any] = {
            "ts": datetime.now(KST).isoformat(),
            "component": component,
            "regime_source": regime_source,
            "regime": regime,
            "baseline_exists": baseline_exists,
            "memory_exists": memory_exists,
        }
        if extra:
            entry["extra"] = dict(extra)

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        log.warning("baseline_audit append failed: %s", exc)


__all__ = ["AUDIT_LOG_PATH", "record_baseline_fallback"]
