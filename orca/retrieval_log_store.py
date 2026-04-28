"""Persistence helpers for Wave F Phase 3 retrieval logs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from . import lesson_archive_store


KST = timezone(timedelta(hours=9))


def migrate_retrieval_log_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS retrieval_log (
            log_id TEXT PRIMARY KEY,
            source_system TEXT NOT NULL,
            source_event_type TEXT,
            source_event_id TEXT,
            trading_date TEXT NOT NULL,
            as_of_date TEXT,
            top_k INTEGER NOT NULL,
            quality_filter TEXT,
            signal_family TEXT,
            cluster_id TEXT,
            cluster_label TEXT,
            cluster_distance REAL,
            lessons_count INTEGER NOT NULL,
            win_rate REAL,
            avg_value REAL,
            high_quality_count INTEGER,
            top_lessons_json TEXT NOT NULL,
            mode TEXT NOT NULL,
            adjustment_value REAL,
            adjustment_capped INTEGER,
            actual_outcome REAL,
            outcome_at TEXT,
            outcome_match INTEGER,
            hunter_run_id TEXT,
            backtest_run_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_retrieval_log_source
            ON retrieval_log(source_system, trading_date);
        CREATE INDEX IF NOT EXISTS idx_retrieval_log_cluster
            ON retrieval_log(cluster_id);
        CREATE INDEX IF NOT EXISTS idx_retrieval_log_run
            ON retrieval_log(backtest_run_id);
        CREATE INDEX IF NOT EXISTS idx_retrieval_log_outcome_pending
            ON retrieval_log(outcome_at) WHERE actual_outcome IS NULL;
        """
    )


def record_retrieval_log(conn: sqlite3.Connection, log_data: dict[str, Any]) -> str:
    log_id = str(log_data.get("log_id") or f"retrieval_{uuid4().hex}")
    now = _now_iso()
    top_lessons = log_data.get("top_lessons_json", [])
    top_lessons_json = top_lessons if isinstance(top_lessons, str) else _json(top_lessons)
    conn.execute(
        """
        INSERT INTO retrieval_log (
            log_id, source_system, source_event_type, source_event_id,
            trading_date, as_of_date, top_k, quality_filter, signal_family,
            cluster_id, cluster_label, cluster_distance, lessons_count,
            win_rate, avg_value, high_quality_count, top_lessons_json,
            mode, adjustment_value, adjustment_capped, actual_outcome,
            outcome_at, outcome_match, hunter_run_id, backtest_run_id,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(log_id) DO UPDATE SET
            source_system = excluded.source_system,
            source_event_type = excluded.source_event_type,
            source_event_id = excluded.source_event_id,
            trading_date = excluded.trading_date,
            as_of_date = excluded.as_of_date,
            top_k = excluded.top_k,
            quality_filter = excluded.quality_filter,
            signal_family = excluded.signal_family,
            cluster_id = excluded.cluster_id,
            cluster_label = excluded.cluster_label,
            cluster_distance = excluded.cluster_distance,
            lessons_count = excluded.lessons_count,
            win_rate = excluded.win_rate,
            avg_value = excluded.avg_value,
            high_quality_count = excluded.high_quality_count,
            top_lessons_json = excluded.top_lessons_json,
            mode = excluded.mode,
            adjustment_value = excluded.adjustment_value,
            adjustment_capped = excluded.adjustment_capped,
            actual_outcome = excluded.actual_outcome,
            outcome_at = excluded.outcome_at,
            outcome_match = excluded.outcome_match,
            hunter_run_id = excluded.hunter_run_id,
            backtest_run_id = excluded.backtest_run_id,
            updated_at = excluded.updated_at
        """,
        (
            log_id,
            str(log_data.get("source_system") or "unknown"),
            log_data.get("source_event_type"),
            log_data.get("source_event_id"),
            str(log_data.get("trading_date") or _today()),
            log_data.get("as_of_date"),
            int(log_data.get("top_k") or 0),
            log_data.get("quality_filter"),
            log_data.get("signal_family"),
            log_data.get("cluster_id"),
            log_data.get("cluster_label"),
            log_data.get("cluster_distance"),
            int(log_data.get("lessons_count") or 0),
            log_data.get("win_rate"),
            log_data.get("avg_value"),
            log_data.get("high_quality_count"),
            top_lessons_json,
            str(log_data.get("mode") or "observe"),
            log_data.get("adjustment_value"),
            1 if log_data.get("adjustment_capped") else 0,
            log_data.get("actual_outcome"),
            log_data.get("outcome_at"),
            log_data.get("outcome_match"),
            log_data.get("hunter_run_id"),
            log_data.get("backtest_run_id"),
            log_data.get("created_at") or now,
            now,
        ),
    )
    return log_id


def update_retrieval_outcome(
    conn: sqlite3.Connection,
    log_id: str,
    actual_outcome: float,
    outcome_at: str,
    outcome_match: bool | int,
) -> None:
    cursor = conn.execute(
        """
        UPDATE retrieval_log
           SET actual_outcome = ?,
               outcome_at = ?,
               outcome_match = ?,
               updated_at = ?
         WHERE log_id = ?
        """,
        (float(actual_outcome), outcome_at, 1 if outcome_match else 0, _now_iso(), log_id),
    )
    if cursor.rowcount == 0:
        _update_cold_retrieval_outcome(
            log_id,
            actual_outcome,
            outcome_at,
            outcome_match,
            cold_db_path=lesson_archive_store.cold_archive_path_for_connection(conn),
        )


def get_retrieval_log(conn: sqlite3.Connection, log_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM retrieval_log WHERE log_id = ?", (log_id,)).fetchone()
    item = _row_to_retrieval_log(row)
    if item is not None:
        return item
    rows = lesson_archive_store.query_cold_retrieval_logs(
        "SELECT * FROM retrieval_log WHERE log_id = ?",
        (log_id,),
        cold_db_path=lesson_archive_store.cold_archive_path_for_connection(conn),
    )
    return _row_to_retrieval_log(rows[0]) if rows else None


def get_pending_outcomes(conn: sqlite3.Connection, before_date: str) -> list[dict[str, Any]]:
    rows = list(conn.execute(
        """
        SELECT *
          FROM retrieval_log
         WHERE actual_outcome IS NULL
           AND trading_date < ?
         ORDER BY trading_date, created_at
        """,
        (before_date[:10],),
    ).fetchall())
    rows.extend(
        lesson_archive_store.query_cold_retrieval_logs(
            """
            SELECT *
              FROM retrieval_log
             WHERE actual_outcome IS NULL
               AND trading_date < ?
            """,
            (before_date[:10],),
            cold_db_path=lesson_archive_store.cold_archive_path_for_connection(conn),
        )
    )
    items = [item for row in rows if (item := _row_to_retrieval_log(row)) is not None]
    items.sort(key=lambda item: (item.get("trading_date") or "", item.get("created_at") or ""))
    return items


def get_retrieval_stats_for_cluster(
    conn: sqlite3.Connection,
    cluster_id: str,
    since_date: str | None = None,
) -> dict[str, Any]:
    params: list[Any] = [cluster_id]
    query = "SELECT * FROM retrieval_log WHERE cluster_id = ?"
    if since_date:
        query += " AND trading_date >= ?"
        params.append(since_date[:10])
    rows = list(conn.execute(query, tuple(params)).fetchall())
    rows.extend(
        lesson_archive_store.query_cold_retrieval_logs(
            query,
            tuple(params),
            cold_db_path=lesson_archive_store.cold_archive_path_for_connection(conn),
        )
    )
    logs = [item for row in rows if (item := _row_to_retrieval_log(row)) is not None]
    completed = [item for item in logs if item.get("actual_outcome") is not None]
    matches = [item for item in completed if int(item.get("outcome_match") or 0) == 1]
    return {
        "cluster_id": cluster_id,
        "total_retrievals": len(logs),
        "completed_outcomes": len(completed),
        "accuracy": (len(matches) / len(completed)) if completed else None,
        "avg_logged_win_rate": _avg([item.get("win_rate") for item in logs]),
        "avg_logged_value": _avg([item.get("avg_value") for item in logs]),
    }


def measure_retrieval_accuracy(
    conn: sqlite3.Connection,
    backtest_run_id: str | None = None,
    since_date: str | None = None,
) -> dict[str, Any]:
    params: list[Any] = []
    query = "SELECT * FROM retrieval_log WHERE 1=1"
    if backtest_run_id:
        query += " AND backtest_run_id = ?"
        params.append(backtest_run_id)
    if since_date:
        query += " AND trading_date >= ?"
        params.append(since_date[:10])
    rows = list(conn.execute(query, tuple(params)).fetchall())
    rows.extend(
        lesson_archive_store.query_cold_retrieval_logs(
            query,
            tuple(params),
            cold_db_path=lesson_archive_store.cold_archive_path_for_connection(conn),
        )
    )
    logs = [item for row in rows if (item := _row_to_retrieval_log(row)) is not None]
    completed = [item for item in logs if item.get("actual_outcome") is not None]
    return {
        "total_retrievals": len(logs),
        "completed_outcomes": len(completed),
        "accuracy_overall": _accuracy(completed),
        "cluster_accuracy": _accuracy_by(completed, "cluster_id"),
        "signal_family_accuracy": _accuracy_by(completed, "signal_family"),
        "mode_accuracy": _accuracy_by(completed, "mode"),
    }


def _row_to_retrieval_log(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None
    keys = (
        "log_id", "source_system", "source_event_type", "source_event_id",
        "trading_date", "as_of_date", "top_k", "quality_filter", "signal_family",
        "cluster_id", "cluster_label", "cluster_distance", "lessons_count",
        "win_rate", "avg_value", "high_quality_count", "top_lessons_json",
        "mode", "adjustment_value", "adjustment_capped", "actual_outcome",
        "outcome_at", "outcome_match", "hunter_run_id", "backtest_run_id",
        "created_at", "updated_at",
    )
    item = {key: _row_value(row, key, idx) for idx, key in enumerate(keys)}
    item["top_lessons"] = _decode_json_text(item.get("top_lessons_json"), [])
    return item


def _update_cold_retrieval_outcome(
    log_id: str,
    actual_outcome: float,
    outcome_at: str,
    outcome_match: bool | int,
    *,
    cold_db_path: str | Path | None = None,
) -> None:
    db_path = Path(cold_db_path) if cold_db_path is not None else lesson_archive_store.COLD_ARCHIVE_DB_FILE
    if not db_path.exists():
        return
    cold = lesson_archive_store._connect_cold_archive(db_path)
    try:
        if not lesson_archive_store._cold_table_exists(cold, "retrieval_log"):
            return
        cold.execute(
            """
            UPDATE retrieval_log
               SET actual_outcome = ?,
                   outcome_at = ?,
                   outcome_match = ?,
                   updated_at = ?
             WHERE log_id = ?
            """,
            (float(actual_outcome), outcome_at, 1 if outcome_match else 0, _now_iso(), log_id),
        )
        cold.commit()
    finally:
        cold.close()


def _accuracy(items: list[dict[str, Any]]) -> float | None:
    if not items:
        return None
    return sum(1 for item in items if int(item.get("outcome_match") or 0) == 1) / len(items)


def _accuracy_by(items: list[dict[str, Any]], key: str) -> dict[str, float]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get(key) or "unknown"), []).append(item)
    return {group_key: float(_accuracy(group_items) or 0.0) for group_key, group_items in grouped.items()}


def _avg(values: list[Any]) -> float | None:
    clean = [float(value) for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _json(data: Any) -> str:
    return json.dumps(data or [], ensure_ascii=False, sort_keys=True)


def _decode_json_text(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _row_value(row: Any, key: str, index: int, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        try:
            return row[index]
        except (TypeError, KeyError, IndexError):
            return default


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")
