"""Phase 11.14 MemoryContext contract audit DB wiring tests."""

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import contract_shadow_audit as audit
from orca import jackal_memory_context as memory
from orca import state


class Phase11_14MemoryContextAuditDBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.audit_log = self.tmpdir / "contract_shadow_audit.log"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch.object(audit, "CONTRACT_SHADOW_AUDIT_LOG", self.audit_log),
            patch.object(audit, "record_contract_shadow_audit", self._record_to_tmp_db),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _record_to_tmp_db(self, audit_event: dict) -> bool:
        state.init_state_db()
        with state._connect_jackal() as conn:
            return audit.record_contract_shadow_audit_conn(conn, audit_event)

    def _context(self) -> dict:
        return {
            "stats_block": "sample=8 win_rate=75%",
            "sample_size": 8,
            "win_rate": 0.75,
            "avg_outcome": 3.2,
            "source": "candidate_lessons",
            "match_scope": "candidate_lessons_regime",
            "role": "analyst",
            "ticker": "NVDA",
            "global_resolved": 0,
        }

    def _event(self, **overrides) -> dict:
        event = {
            "contract_name": "MemoryContext",
            "context": memory.MEMORY_CONTEXT_VALIDATION_CONTEXT,
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

    def _audit_rows(self):
        state.init_state_db()
        with state._connect_jackal() as conn:
            return conn.execute(
                "SELECT * FROM contract_shadow_audit ORDER BY timestamp, audit_id"
            ).fetchall()

    def test_build_memory_context_writes_same_audit_event_to_file_and_db(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ):
            result = memory.build_memory_context("NVDA", {"regime": "risk_on"}, "analyst")

        file_rows = self.audit_log.read_text(encoding="utf-8").splitlines()
        db_rows = self._audit_rows()
        file_event = json.loads(file_rows[0])

        self.assertIs(result, context)
        self.assertEqual(len(file_rows), 1)
        self.assertEqual(len(db_rows), 1)
        self.assertEqual(file_event["audit_id"], db_rows[0]["audit_id"])
        self.assertEqual(file_event["timestamp"], db_rows[0]["timestamp"])
        self.assertEqual(file_event["contract_name"], "MemoryContext")
        self.assertEqual(db_rows[0]["context"], memory.MEMORY_CONTEXT_VALIDATION_CONTEXT)
        self.assertEqual(file_event["payload_hash"], db_rows[0]["payload_hash"])
        self.assertNotIn("payload", file_event)

    def test_combined_logger_file_failure_still_writes_db(self):
        with patch.object(audit, "_append_jsonl_audit_event", side_effect=OSError("disk full")):
            audit.file_and_db_audit_logger(self._event(audit_id="file_fail"))

        rows = self._audit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["audit_id"], "file_fail")
        self.assertEqual(rows[0]["validation_status"], "pass")

    def test_combined_logger_db_failure_still_writes_file(self):
        with patch.object(audit, "record_contract_shadow_audit", side_effect=sqlite3.Error("db down")):
            audit.file_and_db_audit_logger(self._event(audit_id="db_fail"))

        file_event = json.loads(self.audit_log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(file_event["audit_id"], "db_fail")
        self.assertEqual(file_event["contract_name"], "MemoryContext")

    def test_build_memory_context_db_failure_is_fail_open(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(audit, "record_contract_shadow_audit", side_effect=sqlite3.Error("db down")):
            result = memory.build_memory_context("NVDA", {}, "analyst")

        file_rows = self.audit_log.read_text(encoding="utf-8").splitlines()
        self.assertIs(result, context)
        self.assertEqual(len(file_rows), 1)


if __name__ == "__main__":
    unittest.main()
