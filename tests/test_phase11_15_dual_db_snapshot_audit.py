"""Phase 11.15 dual DB snapshot contract audit coverage."""

from __future__ import annotations

import importlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _import_snapshot():
    sys.modules.pop("shared.snapshot.dual_db_snapshot", None)
    return importlib.import_module("shared.snapshot.dual_db_snapshot")


def _create_orca_db(path: Path) -> None:
    sqlite3.connect(path).close()


def _create_jackal_db(path: Path, snapshot, *, include_audit: bool = True) -> None:
    connection = sqlite3.connect(path)
    try:
        for table_name in snapshot.JACKAL_TABLES:
            if table_name == snapshot.CONTRACT_SHADOW_AUDIT_TABLE:
                if include_audit:
                    connection.execute(
                        """
                        CREATE TABLE contract_shadow_audit (
                            audit_id TEXT PRIMARY KEY,
                            timestamp TEXT,
                            validation_status TEXT
                        )
                        """
                    )
                continue
            connection.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()


def _insert_audit_rows(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executemany(
            """
            INSERT INTO contract_shadow_audit (audit_id, timestamp, validation_status)
            VALUES (?, ?, ?)
            """,
            [
                ("audit_1", "2026-05-12T09:00:00Z", "pass"),
                ("audit_2", "2026-05-12T09:05:00Z", "fail"),
                ("audit_3", "2026-05-12T09:03:00Z", "pass"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


class Phase11_15DualDBSnapshotAuditTests(unittest.TestCase):
    def _collect(self, *, include_audit: bool = True, seed_audit: bool = True):
        snapshot = _import_snapshot()
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp_path = Path(tmpdir.name)
        state_db = tmp_path / "orca_state.db"
        jackal_db = tmp_path / "jackal_state.db"
        _create_orca_db(state_db)
        _create_jackal_db(jackal_db, snapshot, include_audit=include_audit)
        if include_audit and seed_audit:
            _insert_audit_rows(jackal_db)

        with patch.object(snapshot, "STATE_DB_FILE", state_db), patch.object(
            snapshot,
            "JACKAL_DB_FILE",
            jackal_db,
        ):
            return snapshot.collect_dual_db_state()

    def test_snapshot_tables_include_contract_shadow_audit_count(self):
        payload = self._collect()

        self.assertEqual(payload["jackal_state_db"]["tables"]["contract_shadow_audit"], 3)

    def test_contract_shadow_audit_summary_row_count_is_exact(self):
        payload = self._collect()

        self.assertEqual(payload["jackal_state_db"]["contract_shadow_audit"]["row_count"], 3)

    def test_contract_shadow_audit_summary_counts_by_validation_status(self):
        payload = self._collect()

        self.assertEqual(
            payload["jackal_state_db"]["contract_shadow_audit"]["by_validation_status"],
            {"fail": 1, "pass": 2},
        )

    def test_contract_shadow_audit_summary_latest_timestamp(self):
        payload = self._collect()

        self.assertEqual(
            payload["jackal_state_db"]["contract_shadow_audit"]["latest_timestamp"],
            "2026-05-12T09:05:00Z",
        )

    def test_missing_contract_shadow_audit_table_reports_empty_summary(self):
        payload = self._collect(include_audit=False, seed_audit=False)
        jackal_db = payload["jackal_state_db"]

        self.assertEqual(jackal_db["tables"]["contract_shadow_audit"], 0)
        self.assertEqual(
            jackal_db["contract_shadow_audit"],
            {"row_count": 0, "by_validation_status": {}, "latest_timestamp": None},
        )

    def test_missing_jackal_db_preserves_existing_none_tables_flow(self):
        snapshot = _import_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            state_db = tmp_path / "orca_state.db"
            jackal_db = tmp_path / "missing_jackal_state.db"
            _create_orca_db(state_db)

            with patch.object(snapshot, "STATE_DB_FILE", state_db), patch.object(
                snapshot,
                "JACKAL_DB_FILE",
                jackal_db,
            ):
                payload = snapshot.collect_dual_db_state()

        jackal_payload = payload["jackal_state_db"]
        self.assertFalse(jackal_payload["exists"])
        self.assertIsNone(jackal_payload["tables"])
        self.assertIsNone(jackal_payload["contract_shadow_audit"])
        self.assertNotIn("error", jackal_payload)

    def test_corrupt_jackal_db_preserves_error_and_none_tables_flow(self):
        snapshot = _import_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            state_db = tmp_path / "orca_state.db"
            jackal_db = tmp_path / "jackal_state.db"
            _create_orca_db(state_db)
            jackal_db.write_text("not-a-sqlite-db", encoding="utf-8")

            with patch.object(snapshot, "STATE_DB_FILE", state_db), patch.object(
                snapshot,
                "JACKAL_DB_FILE",
                jackal_db,
            ):
                payload = snapshot.collect_dual_db_state()

        jackal_payload = payload["jackal_state_db"]
        self.assertTrue(jackal_payload["exists"])
        self.assertIsNone(jackal_payload["tables"])
        self.assertIsNone(jackal_payload["contract_shadow_audit"])
        self.assertIn("error", jackal_payload)

    def test_existing_jackal_table_counts_are_preserved(self):
        snapshot = _import_snapshot()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            state_db = tmp_path / "orca_state.db"
            jackal_db = tmp_path / "jackal_state.db"
            _create_orca_db(state_db)
            _create_jackal_db(jackal_db, snapshot)
            _insert_audit_rows(jackal_db)

            connection = sqlite3.connect(jackal_db)
            try:
                connection.executemany(
                    "INSERT INTO jackal_shadow_signals (id) VALUES (?)",
                    [(1,), (2,)],
                )
                connection.execute("INSERT INTO jackal_cooldowns (id) VALUES (1)")
                connection.commit()
            finally:
                connection.close()

            with patch.object(snapshot, "STATE_DB_FILE", state_db), patch.object(
                snapshot,
                "JACKAL_DB_FILE",
                jackal_db,
            ):
                payload = snapshot.collect_dual_db_state()

        tables = payload["jackal_state_db"]["tables"]
        self.assertEqual(tables["jackal_shadow_signals"], 2)
        self.assertEqual(tables["jackal_cooldowns"], 1)
        self.assertEqual(tables["contract_shadow_audit"], 3)


if __name__ == "__main__":
    unittest.main()
