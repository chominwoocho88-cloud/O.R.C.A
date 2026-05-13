"""Contract shadow validation audit storage utilities."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.paths import JACKAL_LEGACY_DIR

logger = logging.getLogger(__name__)

CONTRACT_SHADOW_AUDIT_LOG = JACKAL_LEGACY_DIR / "contract_shadow_audit.log"
CONTRACT_SHADOW_AUDIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS contract_shadow_audit (
    audit_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    contract_name TEXT NOT NULL,
    context TEXT,
    validation_status TEXT NOT NULL,
    error_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    event_id TEXT,
    correlation_id TEXT,
    prediction_event_id TEXT,
    payload_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_contract_shadow_audit_timestamp
    ON contract_shadow_audit(timestamp);

CREATE INDEX IF NOT EXISTS idx_contract_shadow_audit_contract
    ON contract_shadow_audit(contract_name);

CREATE INDEX IF NOT EXISTS idx_contract_shadow_audit_validation
    ON contract_shadow_audit(validation_status);
"""


def migrate_contract_shadow_audit(conn: sqlite3.Connection) -> None:
    """Create contract shadow audit table and indexes."""
    conn.executescript(CONTRACT_SHADOW_AUDIT_SCHEMA_SQL)


def file_jsonl_audit_logger(event: dict[str, Any]) -> None:
    """Append one shadow validation audit event to JSONL in fail-open mode."""
    try:
        _append_jsonl_audit_event(event, CONTRACT_SHADOW_AUDIT_LOG)
    except Exception as exc:
        logger.warning("[contract_shadow_audit] failed to write audit log: %s", exc)


def file_and_db_audit_logger(event: dict[str, Any]) -> None:
    """Append one audit event to JSONL and DB without breaking runtime flow."""
    full_event = _audit_event_with_storage_metadata(event)
    try:
        _append_jsonl_audit_event(full_event, CONTRACT_SHADOW_AUDIT_LOG)
    except Exception as exc:
        logger.warning("[contract_shadow_audit] failed to write audit log: %s", exc)
    try:
        record_contract_shadow_audit(full_event)
    except Exception as exc:
        logger.warning("[contract_shadow_audit] combined DB write failed: %s", exc)


def _append_jsonl_audit_event(event: dict[str, Any], log_path: Path) -> None:
    full_event = _audit_event_with_storage_metadata(event)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(full_event, ensure_ascii=False, default=str, sort_keys=True))
        handle.write("\n")


def record_contract_shadow_audit_conn(
    conn: sqlite3.Connection,
    audit_event: dict[str, Any],
) -> bool:
    """Persist one contract shadow audit event using an existing connection."""
    event = _audit_event_with_storage_metadata(audit_event)
    cursor = conn.execute(
        """
        INSERT OR IGNORE INTO contract_shadow_audit (
            audit_id, timestamp, contract_name, context,
            validation_status, error_count, error_summary,
            event_id, correlation_id, prediction_event_id,
            payload_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event.get("audit_id"),
            event.get("timestamp"),
            event.get("contract_name"),
            event.get("context"),
            event.get("validation_status"),
            int(event.get("error_count") or 0),
            event.get("error_summary"),
            event.get("event_id"),
            event.get("correlation_id"),
            event.get("prediction_event_id"),
            event.get("payload_hash"),
        ),
    )
    return cursor.rowcount > 0


def record_contract_shadow_audit(audit_event: dict[str, Any]) -> bool:
    """Persist one contract shadow audit event to jackal_state.db.

    Fail-open: DB write failure must not break runtime flow.
    """
    try:
        from orca import state

        state.init_state_db()
        with state._connect_jackal() as conn:
            return record_contract_shadow_audit_conn(conn, audit_event)
    except Exception as exc:
        logger.warning("[contract_shadow_audit] DB write failed: %s", exc)
        return False


def _audit_event_with_storage_metadata(audit_event: dict[str, Any]) -> dict[str, Any]:
    event = dict(audit_event)
    event.setdefault("audit_id", uuid.uuid4().hex)
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    return event
