"""Persistence helpers for JACKAL memory-context shadow logs."""
from __future__ import annotations

import sqlite3
from typing import Any
from uuid import uuid4


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jackal_memory_context_shadow (
    shadow_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    ticker TEXT NOT NULL,
    role TEXT NOT NULL,
    regime TEXT,
    fear_greed INTEGER,
    sample_size INTEGER,
    win_rate REAL,
    avg_outcome REAL,
    source TEXT,
    stats_block TEXT,
    would_inject INTEGER NOT NULL DEFAULT 0,
    memory_mode TEXT,
    build_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_shadow_timestamp
    ON jackal_memory_context_shadow(timestamp);

CREATE INDEX IF NOT EXISTS idx_memory_shadow_ticker
    ON jackal_memory_context_shadow(ticker);

CREATE INDEX IF NOT EXISTS idx_memory_shadow_role
    ON jackal_memory_context_shadow(role);
"""

INJECTION_SHADOW_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jackal_memory_injection_shadow (
    injection_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    ticker TEXT NOT NULL,
    role TEXT NOT NULL,
    injection_block TEXT NOT NULL,
    injection_block_chars INTEGER NOT NULL,
    sample_size INTEGER,
    win_rate REAL,
    avg_outcome REAL,
    source TEXT,
    memory_mode TEXT,
    build_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_injection_shadow_timestamp
    ON jackal_memory_injection_shadow(timestamp);

CREATE INDEX IF NOT EXISTS idx_injection_shadow_ticker
    ON jackal_memory_injection_shadow(ticker);

CREATE INDEX IF NOT EXISTS idx_injection_shadow_role
    ON jackal_memory_injection_shadow(role);
"""


def migrate_memory_context_shadow(conn: sqlite3.Connection) -> None:
    """Create memory-context shadow tables and indexes."""
    conn.executescript(SCHEMA_SQL)
    conn.executescript(INJECTION_SHADOW_SCHEMA_SQL)


def record_memory_context_shadow_conn(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    ticker: str,
    role: str,
    aria: dict[str, Any] | None,
    memory_context: dict[str, Any] | None,
    memory_mode: str,
    build_hash: str | None = None,
) -> str:
    """Persist one memory-context shadow entry."""
    aria = aria or {}
    memory_context = memory_context or {}
    shadow_id = f"shadow_{uuid4().hex[:16]}"
    conn.execute(
        """
        INSERT INTO jackal_memory_context_shadow (
            shadow_id, timestamp, ticker, role, regime, fear_greed,
            sample_size, win_rate, avg_outcome, source, stats_block,
            would_inject, memory_mode, build_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shadow_id,
            timestamp,
            ticker,
            role,
            aria.get("regime"),
            _to_int(aria.get("fear_greed")),
            _to_int(memory_context.get("sample_size")),
            _to_float(memory_context.get("win_rate")),
            _to_float(memory_context.get("avg_outcome")),
            memory_context.get("source"),
            memory_context.get("stats_block"),
            1 if memory_context else 0,
            memory_mode,
            build_hash,
        ),
    )
    return shadow_id


def record_memory_injection_shadow_conn(
    conn: sqlite3.Connection,
    *,
    timestamp: str,
    ticker: str,
    role: str,
    injection_block: str,
    memory_context: dict[str, Any] | None,
    memory_mode: str,
    build_hash: str | None = None,
) -> str:
    """Persist one dry-run memory injection block."""
    memory_context = memory_context or {}
    injection_id = f"injection_{uuid4().hex[:16]}"
    conn.execute(
        """
        INSERT INTO jackal_memory_injection_shadow (
            injection_id, timestamp, ticker, role, injection_block,
            injection_block_chars, sample_size, win_rate, avg_outcome,
            source, memory_mode, build_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            injection_id,
            timestamp,
            ticker,
            role,
            injection_block,
            len(injection_block),
            _to_int(memory_context.get("sample_size")),
            _to_float(memory_context.get("win_rate")),
            _to_float(memory_context.get("avg_outcome")),
            memory_context.get("source"),
            memory_mode,
            build_hash,
        ),
    )
    return injection_id


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    return int(number) if number is not None else None
