import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import session as jackal_session
from apps.orca import state


class JackalSessionLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _table_columns(self) -> list[str]:
        with sqlite3.connect(self.jackal_db) as conn:
            return [row[1] for row in conn.execute("PRAGMA table_info(jackal_sessions)").fetchall()]

    def _index_names(self) -> set[str]:
        with sqlite3.connect(self.jackal_db) as conn:
            return {row[1] for row in conn.execute("PRAGMA index_list(jackal_sessions)").fetchall()}

    def test_init_state_db_creates_jackal_sessions_table_and_indexes(self) -> None:
        state.init_state_db()

        self.assertEqual(
            self._table_columns(),
            [
                "session_id",
                "workflow_run_id",
                "cron_schedule",
                "mode",
                "started_at",
                "ended_at",
                "status",
                "error_reason",
                "commit_sha",
                "notes",
            ],
        )
        indexes = self._index_names()
        self.assertIn("idx_jackal_sessions_started_at", indexes)
        self.assertIn("idx_jackal_sessions_mode", indexes)

    def test_start_jackal_session_persists_started_row(self) -> None:
        session_id = jackal_session.start_jackal_session(
            mode="full",
            workflow_run_id="123456789",
            cron_schedule="30 22 * * 0-4",
        )

        row = jackal_session.get_session_by_id(session_id)

        self.assertIsNotNone(row)
        self.assertTrue(session_id.startswith("jackal_session_"))
        self.assertEqual(row["workflow_run_id"], "123456789")
        self.assertEqual(row["cron_schedule"], "30 22 * * 0-4")
        self.assertEqual(row["mode"], "full")
        self.assertEqual(row["status"], "started")
        self.assertIsNone(row["ended_at"])
        self.assertTrue(row["started_at"].endswith("+09:00"))

    def test_start_jackal_session_accepts_explicit_session_id(self) -> None:
        session_id = jackal_session.start_jackal_session(
            mode="scanner_only",
            session_id="gha-123-scanner",
        )

        row = jackal_session.get_session_by_id(session_id)

        self.assertEqual(session_id, "gha-123-scanner")
        self.assertEqual(row["session_id"], "gha-123-scanner")
        self.assertEqual(row["mode"], "scanner_only")

    def test_finish_jackal_session_updates_status_and_ended_at(self) -> None:
        session_id = jackal_session.start_jackal_session(mode="full")

        jackal_session.finish_jackal_session(session_id)
        row = jackal_session.get_session_by_id(session_id)

        self.assertEqual(row["status"], "completed")
        self.assertIsNotNone(row["ended_at"])
        self.assertTrue(row["ended_at"].endswith("+09:00"))
        self.assertIsNone(row["error_reason"])

    def test_finish_jackal_session_persists_failure_metadata(self) -> None:
        session_id = jackal_session.start_jackal_session(mode="full")

        jackal_session.finish_jackal_session(
            session_id,
            status="failed",
            error_reason="push rejected",
            commit_sha="abc123",
            notes={"stage": "commit", "attempt": 2},
        )
        row = jackal_session.get_session_by_id(session_id)

        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["error_reason"], "push rejected")
        self.assertEqual(row["commit_sha"], "abc123")
        self.assertEqual(json.loads(row["notes"]), {"attempt": 2, "stage": "commit"})

    def test_finish_missing_session_is_graceful(self) -> None:
        jackal_session.finish_jackal_session(
            "missing-session",
            status="failed",
            error_reason="start step skipped",
        )

        self.assertIsNone(jackal_session.get_session_by_id("missing-session"))

    def test_get_recent_jackal_sessions_returns_newest_first(self) -> None:
        first = jackal_session.start_jackal_session(mode="full", session_id="first")
        second = jackal_session.start_jackal_session(mode="scanner_only", session_id="second")

        rows = jackal_session.get_recent_jackal_sessions(limit=2)

        self.assertEqual([row["session_id"] for row in rows], [second, first])

    def test_get_recent_jackal_sessions_handles_zero_limit(self) -> None:
        jackal_session.start_jackal_session(mode="full")

        self.assertEqual(jackal_session.get_recent_jackal_sessions(limit=0), [])


if __name__ == "__main__":
    unittest.main()
