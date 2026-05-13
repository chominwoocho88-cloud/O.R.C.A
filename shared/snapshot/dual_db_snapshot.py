"""Read-only dual-DB snapshot helpers for report payloads."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from shared.paths import JACKAL_DB_FILE, ORCA_LEGACY_DIR, STATE_DB_FILE

PACKAGE_DIR = ORCA_LEGACY_DIR

KST = timezone(timedelta(hours=9))
REPO_ROOT = PACKAGE_DIR.parent
CONTRACT_SHADOW_AUDIT_TABLE = "contract_shadow_audit"
JACKAL_TABLES = (
    "jackal_shadow_signals",
    "jackal_live_events",
    "jackal_shadow_batches",
    "jackal_weight_snapshots",
    "jackal_recommendations",
    "jackal_accuracy_projection",
    "jackal_cooldowns",
    CONTRACT_SHADOW_AUDIT_TABLE,
)


def _single_line(message: str) -> str:
    return " ".join(str(message).split())


def _warn(message: str, error: Exception | str) -> None:
    print(
        f"[WARN] dual-db snapshot: {_single_line(message)} ({_single_line(str(error))})",
        file=sys.stderr,
    )


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _mtime_iso(path: Path) -> str | None:
    try:
        stat = path.stat()
    except OSError as exc:
        _warn(f"mtime lookup failed for {_display_path(path)}", exc)
        return None
    return datetime.fromtimestamp(stat.st_mtime, tz=KST).isoformat()


def _size_bytes(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError as exc:
        _warn(f"size lookup failed for {_display_path(path)}", exc)
        return None


def _base_snapshot(path: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": _display_path(path),
        "exists": exists,
        "size_bytes": _size_bytes(path) if exists else None,
        "mtime_iso": _mtime_iso(path) if exists else None,
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return bool(row)


def _jackal_table_counts(path: Path) -> tuple[dict[str, int | None] | None, str | None]:
    if not path.exists():
        return None, None

    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as exc:
        _warn(f"open failed for {_display_path(path)}", exc)
        return None, _single_line(str(exc))

    counts: dict[str, int | None] = {}
    try:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        for table_name in JACKAL_TABLES:
            try:
                if not _table_exists(connection, table_name):
                    counts[table_name] = 0
                    continue
                row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                counts[table_name] = int(row[0]) if row else 0
            except sqlite3.Error as exc:
                _warn(f"count failed for {table_name} in {_display_path(path)}", exc)
                counts[table_name] = None
    except sqlite3.Error as exc:
        _warn(f"schema probe failed for {_display_path(path)}", exc)
        return None, _single_line(str(exc))
    finally:
        connection.close()

    return counts, None


def _empty_contract_shadow_audit_summary() -> dict[str, Any]:
    return {
        "row_count": 0,
        "by_validation_status": {},
        "latest_timestamp": None,
    }


def _contract_shadow_audit_summary(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, None

    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as exc:
        _warn(f"open failed for {_display_path(path)}", exc)
        return None, _single_line(str(exc))

    try:
        connection.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        if not _table_exists(connection, CONTRACT_SHADOW_AUDIT_TABLE):
            return _empty_contract_shadow_audit_summary(), None

        row = connection.execute(
            f"SELECT COUNT(*) FROM {CONTRACT_SHADOW_AUDIT_TABLE}"
        ).fetchone()
        status_rows = connection.execute(
            f"""
            SELECT validation_status, COUNT(*)
              FROM {CONTRACT_SHADOW_AUDIT_TABLE}
             GROUP BY validation_status
             ORDER BY validation_status
            """
        ).fetchall()
        latest_row = connection.execute(
            f"SELECT MAX(timestamp) FROM {CONTRACT_SHADOW_AUDIT_TABLE}"
        ).fetchone()
    except sqlite3.Error as exc:
        _warn(f"audit summary failed for {_display_path(path)}", exc)
        return None, _single_line(str(exc))
    finally:
        connection.close()

    return {
        "row_count": int(row[0]) if row else 0,
        "by_validation_status": {
            str(status): int(count)
            for status, count in status_rows
            if status is not None
        },
        "latest_timestamp": latest_row[0] if latest_row else None,
    }, None


def collect_dual_db_state() -> dict[str, Any]:
    """Collect a read-only runtime snapshot for ORCA and JACKAL state DBs."""
    try:
        orca_snapshot = _base_snapshot(STATE_DB_FILE)
        jackal_snapshot = _base_snapshot(JACKAL_DB_FILE)
        table_counts, error = _jackal_table_counts(JACKAL_DB_FILE)
        audit_summary = None
        if table_counts is not None:
            audit_summary, audit_error = _contract_shadow_audit_summary(JACKAL_DB_FILE)
            if error is None and audit_error is not None:
                error = audit_error
        jackal_snapshot["tables"] = table_counts
        jackal_snapshot["contract_shadow_audit"] = audit_summary
        if error is not None:
            jackal_snapshot["error"] = error

        return {
            "orca_state_db": orca_snapshot,
            "jackal_state_db": jackal_snapshot,
        }
    except Exception as exc:
        _warn("snapshot collection failed", exc)
        fallback_orca = _base_snapshot(STATE_DB_FILE)
        fallback_jackal = _base_snapshot(JACKAL_DB_FILE)
        fallback_jackal["tables"] = None
        fallback_jackal["contract_shadow_audit"] = None
        fallback_jackal["error"] = _single_line(str(exc))
        return {
            "orca_state_db": fallback_orca,
            "jackal_state_db": fallback_jackal,
        }
