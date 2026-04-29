import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import state
from scripts import check_jackal_operational_intake


class JackalOperationalIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.tmpdir / "orca_state.db"),
            patch.object(state, "JACKAL_DB_FILE", self.tmpdir / "jackal_state.db"),
        ]
        for item in self.patches:
            item.start()
        state.init_state_db()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_intake_waits_for_operational_samples(self) -> None:
        report = check_jackal_operational_intake.collect_operational_intake()

        self.assertEqual(report["status"], "waiting_for_operational_samples")
        self.assertEqual(report["tables"]["jackal_shadow_signals"]["rows"], 0)
        self.assertEqual(report["tables"]["jackal_recommendations"]["rows"], 0)
        self.assertEqual(report["backfill_readiness"]["shadow"]["status"], "skipped")

    def test_resolved_shadow_outcome_marks_backfill_ready(self) -> None:
        shadow_id = state.record_jackal_shadow_signal(
            {
                "timestamp": "2026-04-20T10:00:00+09:00",
                "ticker": "AAPL",
                "market": "US",
                "signal_family": "ma_support",
            }
        )
        state.resolve_jackal_shadow_signal(shadow_id, {"shadow_swing_ok": True})

        report = check_jackal_operational_intake.collect_operational_intake()

        self.assertEqual(report["status"], "ready_for_backfill_dry_run")
        self.assertEqual(report["tables"]["jackal_shadow_signals"]["rows"], 1)
        self.assertEqual(report["tables"]["jackal_shadow_signals"]["resolved_with_outcome"], 1)
        self.assertEqual(report["backfill_readiness"]["shadow"]["status"], "planned")

    def test_recommendation_without_outcome_waits_for_outcomes(self) -> None:
        state.sync_jackal_recommendations(
            [
                {
                    "ticker": "MSFT",
                    "market": "US",
                    "recommended_at": "2026-04-20T10:00:00+09:00",
                    "outcome_checked": False,
                    "orca_regime": "risk_on",
                }
            ]
        )

        report = check_jackal_operational_intake.collect_operational_intake()

        self.assertEqual(report["status"], "waiting_for_outcomes")
        self.assertEqual(report["tables"]["jackal_recommendations"]["rows"], 1)
        self.assertEqual(report["tables"]["jackal_recommendations"]["checked_rows"], 0)
        self.assertEqual(report["backfill_readiness"]["recommendation"]["reason"], "missing_recommendation_outcomes")


if __name__ == "__main__":
    unittest.main()
