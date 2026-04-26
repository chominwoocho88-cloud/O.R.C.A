"""Persistence helpers for Wave F lesson archive rows."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


KST = timezone(timedelta(hours=9))


def migrate_lesson_archive_table(conn: sqlite3.Connection) -> None:
    """Create the Wave F Phase 3 lesson archive table."""
    expected_cols = {
        "archive_id",
        "lesson_id",
        "cluster_id",
        "run_id",
        "quality_tier",
        "quality_score",
        "outcome_percentile",
        "win_score",
        "speed_score",
        "signal_score",
        "cluster_fit_score",
        "lesson_value",
        "peak_pct",
        "peak_day",
        "signal_family",
        "ticker",
        "analysis_date",
        "archived_at",
        "updated_at",
    }
    rows = conn.execute("PRAGMA table_info(lesson_archive)").fetchall()
    existing_cols = {_row_value(row, "name", 1) for row in rows}
    if existing_cols and not expected_cols.issubset(existing_cols):
        conn.execute("DROP TABLE IF EXISTS lesson_archive")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS lesson_archive (
            archive_id TEXT PRIMARY KEY,
            lesson_id TEXT NOT NULL,
            cluster_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            quality_tier TEXT NOT NULL,
            quality_score REAL NOT NULL,
            outcome_percentile REAL,
            win_score REAL,
            speed_score REAL,
            signal_score REAL,
            cluster_fit_score REAL,
            lesson_value REAL,
            peak_pct REAL,
            peak_day INTEGER,
            signal_family TEXT,
            ticker TEXT,
            analysis_date TEXT,
            archived_at TEXT NOT NULL,
            updated_at TEXT,
            FOREIGN KEY(cluster_id) REFERENCES lesson_clusters(cluster_id)
        );

        CREATE INDEX IF NOT EXISTS idx_archive_cluster_quality
            ON lesson_archive(cluster_id, quality_tier, quality_score DESC);

        CREATE INDEX IF NOT EXISTS idx_archive_lesson_id
            ON lesson_archive(lesson_id);

        CREATE INDEX IF NOT EXISTS idx_archive_run_id
            ON lesson_archive(run_id);
        """
    )


def record_lesson_archive(
    conn: sqlite3.Connection,
    archive_id: str,
    lesson_id: str,
    cluster_id: str,
    run_id: str,
    quality_tier: str,
    quality_score: float,
    outcome_percentile: float | None,
    win_score: float | None,
    speed_score: float | None,
    signal_score: float | None,
    cluster_fit_score: float | None,
    lesson_value: float | None,
    peak_pct: float | None,
    peak_day: int | None,
    signal_family: str | None,
    ticker: str | None,
    analysis_date: str | None,
) -> str:
    """Insert or update one lesson archive row."""
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO lesson_archive (
            archive_id, lesson_id, cluster_id, run_id, quality_tier, quality_score,
            outcome_percentile, win_score, speed_score, signal_score,
            cluster_fit_score, lesson_value, peak_pct, peak_day, signal_family,
            ticker, analysis_date, archived_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(archive_id) DO UPDATE SET
            lesson_id = excluded.lesson_id,
            cluster_id = excluded.cluster_id,
            run_id = excluded.run_id,
            quality_tier = excluded.quality_tier,
            quality_score = excluded.quality_score,
            outcome_percentile = excluded.outcome_percentile,
            win_score = excluded.win_score,
            speed_score = excluded.speed_score,
            signal_score = excluded.signal_score,
            cluster_fit_score = excluded.cluster_fit_score,
            lesson_value = excluded.lesson_value,
            peak_pct = excluded.peak_pct,
            peak_day = excluded.peak_day,
            signal_family = excluded.signal_family,
            ticker = excluded.ticker,
            analysis_date = excluded.analysis_date,
            updated_at = excluded.updated_at
        """,
        (
            archive_id,
            lesson_id,
            cluster_id,
            run_id,
            quality_tier,
            quality_score,
            outcome_percentile,
            win_score,
            speed_score,
            signal_score,
            cluster_fit_score,
            lesson_value,
            peak_pct,
            peak_day,
            signal_family,
            ticker,
            analysis_date,
            now,
            now,
        ),
    )
    return archive_id


def get_lesson_archive(conn: sqlite3.Connection, archive_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM lesson_archive WHERE archive_id = ?",
        (archive_id,),
    ).fetchone()
    return _row_to_lesson_archive(row)


def get_archives_for_lesson(conn: sqlite3.Connection, lesson_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
          FROM lesson_archive
         WHERE lesson_id = ?
         ORDER BY archived_at DESC, quality_score DESC
        """,
        (lesson_id,),
    ).fetchall()
    return [archive for row in rows if (archive := _row_to_lesson_archive(row)) is not None]


def get_latest_archive_run_id(conn: sqlite3.Connection) -> str | None:
    """Get the most recent lesson archive run_id with or without Row factory."""
    row = conn.execute(
        """
        SELECT run_id
          FROM lesson_archive
         WHERE run_id IS NOT NULL
         ORDER BY archived_at DESC, COALESCE(updated_at, archived_at) DESC, run_id DESC
         LIMIT 1
        """
    ).fetchone()
    return row[0] if row else None


def get_archives_for_cluster(
    conn: sqlite3.Connection,
    cluster_id: str,
    run_id: str | None = None,
    quality_tier: str | None = None,
) -> list[dict[str, Any]]:
    effective_run_id = run_id or get_latest_archive_run_id(conn)
    params: list[Any] = [cluster_id]
    query = """
        SELECT *
          FROM lesson_archive
         WHERE cluster_id = ?
    """
    if effective_run_id:
        query += " AND run_id = ?"
        params.append(effective_run_id)
    if quality_tier:
        query += " AND quality_tier = ?"
        params.append(str(quality_tier).lower())
    query += " ORDER BY quality_score DESC, lesson_value DESC, analysis_date DESC"
    rows = conn.execute(query, tuple(params)).fetchall()
    return [archive for row in rows if (archive := _row_to_lesson_archive(row)) is not None]


def clear_lesson_archive(conn: sqlite3.Connection, run_id: str | None = None) -> dict[str, int]:
    """Clear archive rows for a specific run or all archive data."""
    if run_id is None:
        deleted = conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0]
        conn.execute("DELETE FROM lesson_archive")
        return {"archives_deleted": deleted}
    deleted = conn.execute(
        "SELECT COUNT(*) FROM lesson_archive WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    conn.execute("DELETE FROM lesson_archive WHERE run_id = ?", (run_id,))
    return {"archives_deleted": deleted}


def _row_to_lesson_archive(row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "archive_id": _row_value(row, "archive_id", 0),
        "lesson_id": _row_value(row, "lesson_id", 1),
        "cluster_id": _row_value(row, "cluster_id", 2),
        "run_id": _row_value(row, "run_id", 3),
        "quality_tier": _row_value(row, "quality_tier", 4),
        "quality_score": _row_value(row, "quality_score", 5),
        "outcome_percentile": _row_value(row, "outcome_percentile", 6),
        "win_score": _row_value(row, "win_score", 7),
        "speed_score": _row_value(row, "speed_score", 8),
        "signal_score": _row_value(row, "signal_score", 9),
        "cluster_fit_score": _row_value(row, "cluster_fit_score", 10),
        "lesson_value": _row_value(row, "lesson_value", 11),
        "peak_pct": _row_value(row, "peak_pct", 12),
        "peak_day": _row_value(row, "peak_day", 13),
        "signal_family": _row_value(row, "signal_family", 14),
        "ticker": _row_value(row, "ticker", 15),
        "analysis_date": _row_value(row, "analysis_date", 16),
        "archived_at": _row_value(row, "archived_at", 17),
        "updated_at": _row_value(row, "updated_at", 18),
    }


def _now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


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
