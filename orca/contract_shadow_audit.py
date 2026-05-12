"""Contract shadow validation audit logger.

File JSONL audit only. DB audit spine is intentionally deferred.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.paths import JACKAL_LEGACY_DIR

logger = logging.getLogger(__name__)

CONTRACT_SHADOW_AUDIT_LOG = JACKAL_LEGACY_DIR / "contract_shadow_audit.log"


def file_jsonl_audit_logger(event: dict[str, Any]) -> None:
    """Append one shadow validation audit event to JSONL in fail-open mode."""
    try:
        _append_jsonl_audit_event(event, CONTRACT_SHADOW_AUDIT_LOG)
    except Exception as exc:
        logger.warning("[contract_shadow_audit] failed to write audit log: %s", exc)


def _append_jsonl_audit_event(event: dict[str, Any], log_path: Path) -> None:
    full_event = dict(event)
    full_event["audit_id"] = uuid.uuid4().hex
    full_event["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(full_event, ensure_ascii=False, default=str, sort_keys=True))
        handle.write("\n")
