"""JACKAL live-session ledger helpers.

The helpers are intentionally unused until the workflow recorder sprint wires
them into jackal_session.yml. They only define the persistence boundary for a
single workflow-triggered JACKAL session.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from apps.orca import state

KST = timezone(timedelta(hours=9))


def _now_kst_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _serialize_notes(notes: dict[str, Any] | None) -> str | None:
    if notes is None:
        return None
    return json.dumps(notes, ensure_ascii=False, sort_keys=True)


def start_jackal_session(
    *,
    mode: str,
    workflow_run_id: str | None = None,
    cron_schedule: str | None = None,
    session_id: str | None = None,
) -> str:
    """Start a JACKAL session, persist it to the ledger, and return its id."""
    state.init_state_db()
    session_id = session_id or f"jackal_session_{uuid4().hex}"
    with state._connect_jackal() as conn:
        conn.execute(
            """
            INSERT INTO jackal_sessions (
                session_id,
                workflow_run_id,
                cron_schedule,
                mode,
                started_at,
                status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                workflow_run_id,
                cron_schedule,
                mode,
                _now_kst_iso(),
                "started",
            ),
        )
    return session_id


def finish_jackal_session(
    session_id: str,
    *,
    status: str = "completed",
    error_reason: str | None = None,
    commit_sha: str | None = None,
    notes: dict[str, Any] | None = None,
) -> None:
    """Finish a JACKAL session ledger row.

    Missing session ids are ignored so future workflow cleanup can remain
    fail-open if the start step was skipped or interrupted.
    """
    state.init_state_db()
    with state._connect_jackal() as conn:
        conn.execute(
            """
            UPDATE jackal_sessions
               SET ended_at = ?,
                   status = ?,
                   error_reason = ?,
                   commit_sha = ?,
                   notes = ?
             WHERE session_id = ?
            """,
            (
                _now_kst_iso(),
                status,
                error_reason,
                commit_sha,
                _serialize_notes(notes),
                session_id,
            ),
        )


def get_session_by_id(session_id: str) -> dict[str, Any] | None:
    """Return one JACKAL session ledger row by id."""
    state.init_state_db()
    with state._connect_jackal() as conn:
        row = conn.execute(
            """
            SELECT session_id,
                   workflow_run_id,
                   cron_schedule,
                   mode,
                   started_at,
                   ended_at,
                   status,
                   error_reason,
                   commit_sha,
                   notes
              FROM jackal_sessions
             WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
    return dict(row) if row else None


def get_recent_jackal_sessions(limit: int = 10) -> list[dict[str, Any]]:
    """Return recent JACKAL session ledger rows, newest first."""
    state.init_state_db()
    with state._connect_jackal() as conn:
        rows = conn.execute(
            """
            SELECT session_id,
                   workflow_run_id,
                   cron_schedule,
                   mode,
                   started_at,
                   ended_at,
                   status,
                   error_reason,
                   commit_sha,
                   notes
              FROM jackal_sessions
             ORDER BY started_at DESC, session_id DESC
             LIMIT ?
            """,
            (max(0, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


__all__ = [
    "finish_jackal_session",
    "get_recent_jackal_sessions",
    "get_session_by_id",
    "start_jackal_session",
]
