import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import memory_context as memory
from apps.orca import state


class TestMemoryShadowDB(unittest.TestCase):
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

    def _rows(self):
        with state._connect_jackal() as conn:
            return conn.execute(
                "SELECT * FROM jackal_memory_context_shadow ORDER BY timestamp, shadow_id"
            ).fetchall()

    def test_record_creates_table(self):
        state.init_state_db()

        with state._connect_jackal() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE name = 'jackal_memory_context_shadow'"
            ).fetchone()

        self.assertIsNotNone(row)

    def test_record_inserts_row(self):
        shadow_id = memory.record_memory_context_shadow(
            ticker="AAPL",
            role="analyst",
            aria={"regime": "risk_on", "fear_greed": 67},
            memory_context=None,
            memory_mode="shadow",
            timestamp="2026-05-11T00:00:00Z",
        )
        rows = self._rows()

        self.assertTrue(shadow_id.startswith("shadow_"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AAPL")
        self.assertEqual(rows[0]["role"], "analyst")
        self.assertEqual(rows[0]["memory_mode"], "shadow")

    def test_record_with_memory_context(self):
        context = {
            "sample_size": 25,
            "win_rate": 0.72,
            "avg_outcome": 4.3,
            "source": "candidate_lessons",
            "stats_block": "[과거 학습] sample",
        }

        memory.record_memory_context_shadow(
            ticker="207940.KS",
            role="devil",
            aria={"regime": "risk_on", "fear_greed": "67"},
            memory_context=context,
            memory_mode="shadow",
        )
        row = self._rows()[0]

        self.assertEqual(row["ticker"], "207940.KS")
        self.assertEqual(row["fear_greed"], 67)
        self.assertEqual(row["sample_size"], 25)
        self.assertAlmostEqual(row["win_rate"], 0.72)
        self.assertAlmostEqual(row["avg_outcome"], 4.3)
        self.assertEqual(row["source"], "candidate_lessons")
        self.assertEqual(row["stats_block"], "[과거 학습] sample")
        self.assertEqual(row["would_inject"], 1)

    def test_record_without_memory_context(self):
        memory.record_memory_context_shadow(
            ticker="NVDA",
            role="devil",
            aria={"regime": "risk_off", "fear_greed": 30},
            memory_context=None,
            memory_mode="shadow",
        )
        row = self._rows()[0]

        self.assertEqual(row["would_inject"], 0)
        self.assertIsNone(row["sample_size"])
        self.assertIsNone(row["stats_block"])

    def test_record_idempotent_unique_id(self):
        first = memory.record_memory_context_shadow(
            ticker="META",
            role="analyst",
            aria={},
            memory_context=None,
            memory_mode="shadow",
        )
        second = memory.record_memory_context_shadow(
            ticker="META",
            role="analyst",
            aria={},
            memory_context=None,
            memory_mode="shadow",
        )

        self.assertNotEqual(first, second)
        self.assertEqual(len(self._rows()), 2)

    def test_file_log_still_works(self):
        log_path = self.tmpdir / "memory_context_shadow.log"
        context = {
            "sample_size": 5,
            "win_rate": 0.8,
            "avg_outcome": 2.5,
            "source": "prediction_cards",
            "stats_block": "stats",
        }

        memory.log_shadow_memory_context(
            "WFC",
            {"regime": "risk_on", "fear_greed": 70},
            "analyst",
            context,
            mode="shadow",
            log_path=log_path,
        )

        file_entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        db_row = self._rows()[0]
        self.assertEqual(file_entry["ticker"], "WFC")
        self.assertEqual(file_entry["memory_context"]["source"], "prediction_cards")
        self.assertEqual(db_row["ticker"], "WFC")
        self.assertEqual(db_row["source"], "prediction_cards")

    def test_db_failure_silent(self):
        log_path = self.tmpdir / "memory_context_shadow.log"

        with patch.object(memory, "record_memory_context_shadow", side_effect=sqlite3.Error("db down")):
            memory.log_shadow_memory_context(
                "LMT",
                {"regime": "risk_off"},
                "devil",
                None,
                mode="shadow",
                log_path=log_path,
            )

        rows = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0])["ticker"], "LMT")


if __name__ == "__main__":
    unittest.main()
