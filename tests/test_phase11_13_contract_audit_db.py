"""Phase 11.13 contract shadow audit DB tests."""

import json
import importlib
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.audit import contract_shadow_audit as audit


class ContractShadowAuditDBTests(unittest.TestCase):
    def setUp(self):
        self.state = importlib.import_module("apps.orca.state")
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.patches = [
            patch.object(self.state, "STATE_DB_FILE", self.state_db),
            patch.object(self.state, "JACKAL_DB_FILE", self.jackal_db),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _event(self, **overrides):
        event = {
            "audit_id": "audit_1",
            "timestamp": "2026-05-12T09:00:00Z",
            "contract_name": "MemoryContext",
            "context": "jackal_memory_context.build_memory_context",
            "validation_status": "pass",
            "error_count": 0,
            "error_summary": None,
            "event_id": "evt_1",
            "correlation_id": None,
            "prediction_event_id": None,
            "payload_hash": "abc123",
        }
        event.update(overrides)
        return event

    def test_init_state_db_creates_contract_shadow_audit_table(self):
        self.state.init_state_db()

        with self.state._connect_jackal() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='contract_shadow_audit'"
            ).fetchone()

        self.assertIsNotNone(row)

    def test_init_creates_indexes(self):
        self.state.init_state_db()

        with self.state._connect_jackal() as conn:
            names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='contract_shadow_audit'"
                ).fetchall()
            }

        self.assertIn("idx_contract_shadow_audit_timestamp", names)
        self.assertIn("idx_contract_shadow_audit_contract", names)
        self.assertIn("idx_contract_shadow_audit_validation", names)

    def test_record_contract_shadow_audit_conn_inserts_row(self):
        self.state.init_state_db()
        with self.state._connect_jackal() as conn:
            inserted = audit.record_contract_shadow_audit_conn(conn, self._event())
            rows = conn.execute("SELECT * FROM contract_shadow_audit").fetchall()

        self.assertTrue(inserted)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contract_name"], "MemoryContext")
        self.assertEqual(rows[0]["validation_status"], "pass")

    def test_record_contract_shadow_audit_public_inserts_row(self):
        inserted = audit.record_contract_shadow_audit(self._event(audit_id="audit_public"))

        with self.state._connect_jackal() as conn:
            row = conn.execute(
                "SELECT audit_id FROM contract_shadow_audit WHERE audit_id='audit_public'"
            ).fetchone()

        self.assertTrue(inserted)
        self.assertIsNotNone(row)

    def test_duplicate_audit_id_is_ignored(self):
        self.state.init_state_db()
        with self.state._connect_jackal() as conn:
            first = audit.record_contract_shadow_audit_conn(conn, self._event())
            second = audit.record_contract_shadow_audit_conn(conn, self._event())
            count = conn.execute("SELECT COUNT(*) FROM contract_shadow_audit").fetchone()[0]

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(count, 1)

    def test_query_by_validation_status(self):
        self.state.init_state_db()
        with self.state._connect_jackal() as conn:
            audit.record_contract_shadow_audit_conn(
                conn,
                self._event(audit_id="pass_1", validation_status="pass"),
            )
            audit.record_contract_shadow_audit_conn(
                conn,
                self._event(audit_id="fail_1", validation_status="fail", error_count=1),
            )
            fail_count = conn.execute(
                "SELECT COUNT(*) FROM contract_shadow_audit WHERE validation_status='fail'"
            ).fetchone()[0]

        self.assertEqual(fail_count, 1)

    def test_timestamp_ordering(self):
        self.state.init_state_db()
        with self.state._connect_jackal() as conn:
            audit.record_contract_shadow_audit_conn(
                conn,
                self._event(audit_id="later", timestamp="2026-05-12T09:02:00Z"),
            )
            audit.record_contract_shadow_audit_conn(
                conn,
                self._event(audit_id="earlier", timestamp="2026-05-12T09:01:00Z"),
            )
            rows = conn.execute(
                "SELECT audit_id FROM contract_shadow_audit ORDER BY timestamp"
            ).fetchall()

        self.assertEqual([row["audit_id"] for row in rows], ["earlier", "later"])

    def test_record_fail_open_on_db_error(self):
        with patch.object(self.state, "_connect_jackal", side_effect=sqlite3.Error("db down")):
            result = audit.record_contract_shadow_audit(self._event())

        self.assertFalse(result)

    def test_missing_audit_id_and_timestamp_are_filled(self):
        self.state.init_state_db()
        event = self._event()
        event.pop("audit_id")
        event.pop("timestamp")

        with self.state._connect_jackal() as conn:
            inserted = audit.record_contract_shadow_audit_conn(conn, event)
            row = conn.execute(
                "SELECT audit_id, timestamp FROM contract_shadow_audit"
            ).fetchone()

        self.assertTrue(inserted)
        self.assertTrue(row["audit_id"])
        self.assertTrue(row["timestamp"])

    def test_file_jsonl_audit_logger_regression(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "contract_shadow_audit.log"
            with patch.object(audit, "CONTRACT_SHADOW_AUDIT_LOG", log_path):
                audit.file_jsonl_audit_logger(self._event())

            data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(data["contract_name"], "MemoryContext")
        self.assertEqual(data["payload_hash"], "abc123")
        self.assertNotIn("payload", data)


if __name__ == "__main__":
    unittest.main()
