import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import state
from orca import jackal_accuracy_projection


class JackalAccuracyProjectionTests(unittest.TestCase):
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
        state.init_state_db()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_record_jackal_weight_snapshot_populates_projection_and_current_view(self) -> None:
        snapshot_id = state.record_jackal_weight_snapshot(
            {
                "signal_accuracy": {
                    "breakout": {
                        "total": 10,
                        "correct": 7,
                        "accuracy": 70.0,
                        "swing_correct": 8,
                        "swing_accuracy": 80.0,
                        "d1_correct": 6,
                        "d1_accuracy": 60.0,
                    }
                }
            },
            source="unit_test",
        )

        latest = jackal_accuracy_projection.load_latest_jackal_weight_snapshot_metadata()
        rows = state.list_jackal_accuracy_projection(current_only=False)
        current = state.list_jackal_accuracy_projection()

        self.assertEqual(latest["snapshot_id"], snapshot_id)
        self.assertEqual(latest["source"], "unit_test")
        self.assertGreaterEqual(len(rows), 3)
        self.assertGreaterEqual(len(current), 3)

    def test_backfill_from_latest_evaluable_backtest_creates_current_projection_rows(self) -> None:
        summary = {
            "total_tracked": 120,
            "swing_accuracy": 70.0,
            "d1_accuracy": 45.0,
            "source": {"orca_session_id": "orca_bt_1"},
            "regime_accuracy": {
                "risk_on": {"total": 120, "swing_correct": 84, "swing_accuracy": 70.0}
            },
            "ticker_accuracy": {
                "AAA": {"total": 120, "swing_correct": 84, "swing_accuracy": 70.0}
            },
        }
        with state._connect_orca() as conn:
            conn.execute(
                """
                INSERT INTO backtest_sessions (
                    session_id, system, label, started_at, ended_at, status, config_json, summary_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "jackal_bt_1",
                    "jackal",
                    "backtest",
                    "2026-04-28T09:00:00+09:00",
                    "2026-04-28T10:00:00+09:00",
                    "completed",
                    "{}",
                    json.dumps(summary),
                ),
            )

        result = jackal_accuracy_projection.backfill_jackal_accuracy_projection_from_backtest()
        projection_state = jackal_accuracy_projection.describe_jackal_accuracy_projection_state()
        system_swing = state.list_jackal_accuracy_projection(family="system", scope="swing")

        self.assertEqual(result["status"], "backfilled")
        self.assertEqual(result["source_session_id"], "jackal_bt_1")
        self.assertGreaterEqual(result["projection_rows"], 4)
        self.assertGreaterEqual(projection_state["current_rows"], 4)
        self.assertEqual(projection_state["max_sample_count"], 120.0)
        self.assertIn("jackal_bt_1", projection_state["latest_source"])
        self.assertEqual(system_swing[0]["total"], 120.0)
        self.assertEqual(system_swing[0]["accuracy"], 70.0)


if __name__ == "__main__":
    unittest.main()
