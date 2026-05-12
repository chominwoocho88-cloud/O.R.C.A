import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import state


class TestJackalPredictionCards(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.audit_log = self.tmpdir / "contract_shadow_audit.log"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch("orca.contract_shadow_audit.CONTRACT_SHADOW_AUDIT_LOG", self.audit_log),
        ]
        for item in self.patches:
            item.start()
        state.init_state_db()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _card_rows(self):
        with state._connect_jackal() as conn:
            return conn.execute(
                "SELECT * FROM jackal_prediction_cards ORDER BY created_at, ticker"
            ).fetchall()

    def test_schema_created(self):
        with state._connect_jackal() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE name = 'jackal_prediction_cards'"
            ).fetchone()

        self.assertIsNotNone(row)

    def test_sync_alerted_event_creates_normalized_card(self):
        entry = {
            "timestamp": "2026-05-11T10:00:00+09:00",
            "ticker": "207940.KS",
            "name": "삼성바이오로직스",
            "final_score": 82.5,
            "day1_score": 72,
            "swing_score": 88,
            "devil_score": 30,
            "devil_verdict": "부분동의",
            "price_at_scan": 100000.0,
            "target_price": 108000.0,
            "stop_price": 97000.0,
            "horizon_days": 5,
            "signal_family_label": "패닉반등",
            "reason_detail": "RSI 과매도 + 위험선호",
            "orca_regime": "위험선호",
            "fear_greed": 67,
            "fear_greed_label": "Greed",
            "orca_inflows": ["바이오", "헬스케어"],
            "alerted": True,
            "is_entry": True,
            "outcome_checked": False,
        }

        synced = state.sync_jackal_live_events("scan", [entry])
        rows = self._card_rows()

        self.assertEqual(synced, 1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["event_kind"], "scan")
        self.assertEqual(row["ticker"], "207940.KS")
        self.assertEqual(row["score"], 82.5)
        self.assertEqual(row["day1_score"], 72.0)
        self.assertEqual(row["swing_score"], 88.0)
        self.assertEqual(row["devil_verdict"], "부분동의")
        self.assertEqual(row["target_price"], 108000.0)
        self.assertEqual(row["stop_price"], 97000.0)
        self.assertEqual(row["horizon_days"], 5)
        self.assertEqual(row["market_regime"], "위험선호")
        self.assertEqual(row["fear_greed"], 67)
        self.assertEqual(row["fear_greed_label"], "Greed")
        self.assertEqual(json.loads(row["inflow_sectors"]), ["바이오", "헬스케어"])
        self.assertEqual(row["status"], "open")

    def test_non_alerted_event_does_not_create_card(self):
        entry = {
            "timestamp": "2026-05-11T10:05:00+09:00",
            "ticker": "NVDA",
            "final_score": 42.0,
            "alerted": False,
            "is_entry": True,
            "outcome_checked": False,
        }

        state.sync_jackal_live_events("scan", [entry])

        self.assertEqual(len(self._card_rows()), 0)

    def test_card_sync_is_idempotent_for_same_event(self):
        entry = {
            "timestamp": "2026-05-11T10:10:00+09:00",
            "ticker": "WFC",
            "name": "Wells Fargo",
            "final_score": 59.0,
            "price_at_hunt": 50.0,
            "alerted": True,
            "is_entry": True,
            "outcome_checked": False,
        }
        updated = dict(entry)
        updated["final_score"] = 61.0
        updated["reason"] = "updated reasoning"

        state.sync_jackal_live_events("hunt", [entry])
        state.sync_jackal_live_events("hunt", [updated])
        rows = self._card_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], 61.0)
        self.assertEqual(rows[0]["main_reasoning"], "updated reasoning")

    def test_outcome_fields_default_open_then_resolved(self):
        entry = {
            "timestamp": "2026-05-11T10:15:00+09:00",
            "ticker": "META",
            "final_score": 80.0,
            "alerted": True,
            "is_entry": True,
            "outcome_checked": False,
        }
        resolved = dict(entry)
        resolved.update(
            {
                "outcome_checked": True,
                "outcome_tracked_at": "2026-05-16T10:15:00+09:00",
                "price_peak": 110.0,
                "price_1d_later": 104.0,
                "price_5d_later": 98.0,
                "outcome_1d_hit": True,
                "outcome_swing_hit": False,
            }
        )

        state.sync_jackal_live_events("hunt", [entry])
        self.assertEqual(self._card_rows()[0]["status"], "open")

        state.sync_jackal_live_events("hunt", [resolved])
        row = self._card_rows()[0]

        self.assertEqual(row["status"], "resolved")
        self.assertEqual(row["resolved_at"], "2026-05-16T10:15:00+09:00")
        self.assertEqual(row["actual_high"], 110.0)
        self.assertEqual(row["actual_close_d1"], 104.0)
        self.assertEqual(row["actual_close_d5"], 98.0)
        self.assertEqual(row["outcome_d1"], "win")
        self.assertEqual(row["outcome_d5"], "loss")


if __name__ == "__main__":
    unittest.main()
