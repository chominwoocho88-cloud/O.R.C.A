"""Persistence helpers for Wave F lesson archive rows."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .paths import DATA_DIR


KST = timezone(timedelta(hours=9))
COLD_ARCHIVE_DB_FILE = DATA_DIR / "archive" / "lesson_archive_cold.db"
COLD_TABLE_KEYS = {
    "lesson_archive": ("archive_id",),
    "retrieval_log": ("log_id",),
    "backtest_daily_results": ("session_id", "analysis_date", "phase_label"),
    "backtest_pick_results": ("session_id", "analysis_date", "selection_stage", "rank_index", "ticker"),
}


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
    archive = _row_to_lesson_archive(row)
    if archive is not None:
        return archive
    rows = _query_cold_rows(
        "lesson_archive",
        "SELECT * FROM lesson_archive WHERE archive_id = ?",
        (archive_id,),
        cold_db_path=cold_archive_path_for_connection(conn),
    )
    return _row_to_lesson_archive(rows[0]) if rows else None


def get_archives_for_lesson(conn: sqlite3.Connection, lesson_id: str) -> list[dict[str, Any]]:
    rows = list(conn.execute(
        """
        SELECT *
          FROM lesson_archive
         WHERE lesson_id = ?
         ORDER BY archived_at DESC, quality_score DESC
        """,
        (lesson_id,),
    ).fetchall())
    rows.extend(
        _query_cold_rows(
            "lesson_archive",
            """
            SELECT *
              FROM lesson_archive
             WHERE lesson_id = ?
            """,
            (lesson_id,),
            cold_db_path=cold_archive_path_for_connection(conn),
        )
    )
    archives = [archive for row in rows if (archive := _row_to_lesson_archive(row)) is not None]
    archives.sort(key=lambda row: (row.get("archived_at") or "", row.get("quality_score") or 0), reverse=True)
    return archives


def get_latest_archive_run_id(conn: sqlite3.Connection) -> str | None:
    """Get the most recent lesson archive run_id with or without Row factory."""
    rows = list(conn.execute(
        """
        SELECT run_id, archived_at, COALESCE(updated_at, archived_at) AS updated_order
          FROM lesson_archive
         WHERE run_id IS NOT NULL
         ORDER BY archived_at DESC, COALESCE(updated_at, archived_at) DESC, run_id DESC
        """
    ).fetchall())
    rows.extend(
        _query_cold_rows(
            "lesson_archive",
            """
            SELECT run_id, archived_at, COALESCE(updated_at, archived_at) AS updated_order
              FROM lesson_archive
             WHERE run_id IS NOT NULL
            """,
            cold_db_path=cold_archive_path_for_connection(conn),
        )
    )
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            str(_row_value(row, "archived_at", 1) or ""),
            str(_row_value(row, "updated_order", 2) or ""),
            str(_row_value(row, "run_id", 0) or ""),
        ),
        reverse=True,
    )
    return _row_value(rows[0], "run_id", 0)


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
    rows = list(conn.execute(query, tuple(params)).fetchall())
    rows.extend(_query_cold_rows("lesson_archive", query, tuple(params), cold_db_path=cold_archive_path_for_connection(conn)))
    archives = [archive for row in rows if (archive := _row_to_lesson_archive(row)) is not None]
    archives.sort(
        key=lambda row: (
            row.get("quality_score") or 0,
            row.get("lesson_value") or 0,
            row.get("analysis_date") or "",
        ),
        reverse=True,
    )
    return archives


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


def migrate_to_cold(
    conn: sqlite3.Connection | None = None,
    *,
    threshold_runs: int = 1,
    cold_db_path: str | Path | None = None,
    include_retrieval_logs: bool = True,
    include_backtest_results: bool = True,
    vacuum: bool = False,
) -> dict[str, Any]:
    """Move cold archive/log/backtest rows out of the hot ORCA DB.

    Keeps the latest ``threshold_runs`` lesson_archive runs in the hot DB.
    Backtest retrieval logs and raw backtest result rows are moved because they
    are read-heavy historical data and the largest source of repository bloat.
    """
    owns_conn = conn is None
    if conn is None:
        from .paths import STATE_DB_FILE

        conn = sqlite3.connect(STATE_DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    cold_path = Path(cold_db_path) if cold_db_path is not None else COLD_ARCHIVE_DB_FILE
    cold = _connect_cold_archive(cold_path)
    try:
        moved: dict[str, int] = {}
        archive_run_ids = _archive_run_ids_to_move(conn, threshold_runs)
        moved["lesson_archive"] = _move_rows_to_cold(
            conn,
            cold,
            "lesson_archive",
            _where_in("run_id", archive_run_ids),
            tuple(archive_run_ids),
        ) if archive_run_ids else 0
        if include_retrieval_logs:
            moved["retrieval_log"] = _move_rows_to_cold(
                conn,
                cold,
                "retrieval_log",
                "source_event_type = ? OR source_system LIKE ? OR backtest_run_id IS NOT NULL",
                ("backtest", "%backtest%"),
            )
        if include_backtest_results:
            moved["backtest_daily_results"] = _move_rows_to_cold(conn, cold, "backtest_daily_results")
            moved["backtest_pick_results"] = _move_rows_to_cold(conn, cold, "backtest_pick_results")
        conn.commit()
        cold.commit()
    finally:
        cold.close()
        if owns_conn:
            conn.close()
    if vacuum:
        from .paths import STATE_DB_FILE

        vacuum_sqlite_database(STATE_DB_FILE)
        vacuum_sqlite_database(cold_path)
    return {
        "cold_db_path": str(cold_path),
        "moved": moved,
        "rows_moved": sum(moved.values()),
    }


def restore_from_cold(
    conn: sqlite3.Connection | None = None,
    *,
    cold_db_path: str | Path | None = None,
    tables: tuple[str, ...] = ("lesson_archive", "retrieval_log", "backtest_daily_results", "backtest_pick_results"),
    delete_cold_rows: bool = False,
) -> dict[str, int]:
    """Copy cold archive rows back into the hot DB for rollback."""
    owns_conn = conn is None
    if conn is None:
        from .paths import STATE_DB_FILE

        conn = sqlite3.connect(STATE_DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
    cold_path = Path(cold_db_path) if cold_db_path is not None else COLD_ARCHIVE_DB_FILE
    cold = _connect_cold_archive(cold_path)
    try:
        restored = {}
        for table in tables:
            restored[table] = _restore_table_from_cold(conn, cold, table, delete_cold_rows=delete_cold_rows)
        conn.commit()
        cold.commit()
        return restored
    finally:
        cold.close()
        if owns_conn:
            conn.close()


def vacuum_sqlite_database(path: str | Path) -> dict[str, float]:
    """Run PRAGMA optimize + VACUUM and return before/after MB."""
    db_path = Path(path)
    before = db_path.stat().st_size if db_path.exists() else 0
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA optimize")
        conn.execute("VACUUM")
    finally:
        conn.close()
    after = db_path.stat().st_size if db_path.exists() else 0
    return {"before_mb": round(before / 1024 / 1024, 2), "after_mb": round(after / 1024 / 1024, 2)}


def get_cold_backtest_days(
    session_id: str,
    *,
    phase_label: str | None = None,
    cold_db_path: str | Path | None = None,
) -> list[sqlite3.Row]:
    params: list[Any] = [session_id]
    query = """
        SELECT analysis_date, phase_label, market_note, analysis_json, results_json, metrics_json
          FROM backtest_daily_results
         WHERE session_id = ?
    """
    if phase_label:
        query += " AND phase_label = ?"
        params.append(phase_label)
    query += " ORDER BY analysis_date ASC"
    return _query_cold_rows("backtest_daily_results", query, tuple(params), cold_db_path=cold_db_path)


def query_cold_retrieval_logs(
    query: str,
    params: tuple[Any, ...] = (),
    *,
    cold_db_path: str | Path | None = None,
) -> list[sqlite3.Row]:
    return _query_cold_rows("retrieval_log", query, params, cold_db_path=cold_db_path)


def cold_archive_path_for_connection(conn: sqlite3.Connection) -> Path:
    row = conn.execute("PRAGMA database_list").fetchone()
    hot_path = _row_value(row, "file", 2)
    return cold_archive_path_for_hot_db(hot_path) if hot_path else COLD_ARCHIVE_DB_FILE


def cold_archive_path_for_hot_db(hot_db_path: str | Path) -> Path:
    hot_path = Path(hot_db_path)
    return hot_path.parent / "archive" / "lesson_archive_cold.db"


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


def _connect_cold_archive(path: str | Path | None = None) -> sqlite3.Connection:
    db_path = Path(path) if path is not None else COLD_ARCHIVE_DB_FILE
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _query_cold_rows(
    table: str,
    query: str,
    params: tuple[Any, ...] = (),
    *,
    cold_db_path: str | Path | None = None,
) -> list[sqlite3.Row]:
    db_path = Path(cold_db_path) if cold_db_path is not None else COLD_ARCHIVE_DB_FILE
    if not db_path.exists():
        return []
    cold = _connect_cold_archive(db_path)
    try:
        if not _cold_table_exists(cold, table):
            return []
        return list(cold.execute(query, params).fetchall())
    finally:
        cold.close()


def _cold_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _archive_run_ids_to_move(conn: sqlite3.Connection, threshold_runs: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT run_id, MAX(archived_at) AS latest_archived_at, MAX(COALESCE(updated_at, archived_at)) AS latest_updated_at
          FROM lesson_archive
         WHERE run_id IS NOT NULL
         GROUP BY run_id
         ORDER BY latest_archived_at DESC, latest_updated_at DESC, run_id DESC
        """
    ).fetchall()
    keep = max(0, int(threshold_runs or 0))
    return [str(_row_value(row, "run_id", 0)) for row in rows[keep:]]


def _move_rows_to_cold(
    hot: sqlite3.Connection,
    cold: sqlite3.Connection,
    table: str,
    where_sql: str = "1=1",
    params: tuple[Any, ...] = (),
) -> int:
    if not _hot_table_exists(hot, table):
        return 0
    _ensure_cold_table_like(hot, cold, table)
    columns = _table_columns(hot, table)
    keys = COLD_TABLE_KEYS.get(table, tuple(columns[:1]))
    rows = list(hot.execute(f'SELECT {", ".join(_q(col) for col in columns)} FROM {_q(table)} WHERE {where_sql}', params))
    if not rows:
        return 0
    for row in rows:
        key_values = tuple(_row_value(row, key, columns.index(key)) for key in keys)
        cold.execute(
            f'DELETE FROM {_q(table)} WHERE ' + " AND ".join(f"{_q(key)} = ?" for key in keys),
            key_values,
        )
    placeholders = ", ".join("?" for _ in columns)
    cold.executemany(
        f'INSERT INTO {_q(table)} ({", ".join(_q(col) for col in columns)}) VALUES ({placeholders})',
        [tuple(_row_value(row, col, idx) for idx, col in enumerate(columns)) for row in rows],
    )
    hot.execute(f'DELETE FROM {_q(table)} WHERE {where_sql}', params)
    return len(rows)


def _restore_table_from_cold(
    hot: sqlite3.Connection,
    cold: sqlite3.Connection,
    table: str,
    *,
    delete_cold_rows: bool,
) -> int:
    if not _cold_table_exists(cold, table) or not _hot_table_exists(hot, table):
        return 0
    columns = _table_columns(hot, table)
    keys = COLD_TABLE_KEYS.get(table, tuple(columns[:1]))
    rows = list(cold.execute(f'SELECT {", ".join(_q(col) for col in columns)} FROM {_q(table)}'))
    for row in rows:
        key_values = tuple(_row_value(row, key, columns.index(key)) for key in keys)
        hot.execute(
            f'DELETE FROM {_q(table)} WHERE ' + " AND ".join(f"{_q(key)} = ?" for key in keys),
            key_values,
        )
    placeholders = ", ".join("?" for _ in columns)
    hot.executemany(
        f'INSERT INTO {_q(table)} ({", ".join(_q(col) for col in columns)}) VALUES ({placeholders})',
        [tuple(_row_value(row, col, idx) for idx, col in enumerate(columns)) for row in rows],
    )
    if delete_cold_rows:
        cold.execute(f"DELETE FROM {_q(table)}")
    return len(rows)


def _ensure_cold_table_like(hot: sqlite3.Connection, cold: sqlite3.Connection, table: str) -> None:
    cols = hot.execute(f"PRAGMA table_info({_q(table)})").fetchall()
    if not cols:
        raise sqlite3.OperationalError(f"table not found: {table}")
    definitions = []
    for row in cols:
        name = _row_value(row, "name", 1)
        col_type = _row_value(row, "type", 2) or "TEXT"
        definitions.append(f"{_q(str(name))} {col_type}")
    cold.execute(f"CREATE TABLE IF NOT EXISTS {_q(table)} ({', '.join(definitions)})")
    key_cols = COLD_TABLE_KEYS.get(table)
    if key_cols:
        cold.execute(
            f"CREATE INDEX IF NOT EXISTS idx_cold_{table}_key ON {_q(table)} "
            + "("
            + ", ".join(_q(col) for col in key_cols)
            + ")"
        )


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(_row_value(row, "name", 1)) for row in conn.execute(f"PRAGMA table_info({_q(table)})").fetchall()]


def _hot_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _where_in(column: str, values: list[str]) -> str:
    if not values:
        return "0=1"
    return f"{_q(column)} IN ({', '.join('?' for _ in values)})"


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
