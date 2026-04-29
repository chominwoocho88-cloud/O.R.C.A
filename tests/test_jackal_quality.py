import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import jackal_quality, state


class JackalQualityDiagnosticsTests(unittest.TestCase):
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

    def test_shadow_state_reports_missing_reasons_without_source_rows(self) -> None:
        summary = jackal_quality.describe_jackal_shadow_state()

        self.assertEqual(summary["signal_rows"], 0)
        self.assertIn("missing_shadow_signals", summary["missing_reasons"])
        self.assertIn("missing_shadow_batches", summary["missing_reasons"])

    def test_shadow_batch_backfill_uses_resolved_shadow_outcomes(self) -> None:
        shadow_id = state.record_jackal_shadow_signal(
            {
                "timestamp": "2026-04-20T10:00:00+09:00",
                "ticker": "AAPL",
                "market": "US",
                "signal_family": "quality_skip",
                "price_at_scan": 100.0,
            }
        )
        state.resolve_jackal_shadow_signal(shadow_id, {"shadow_swing_ok": True})

        dry = jackal_quality.backfill_shadow_batches_from_resolved_signals(dry_run=True)
        result = jackal_quality.backfill_shadow_batches_from_resolved_signals(dry_run=False)
        summary = jackal_quality.describe_jackal_shadow_state()

        self.assertEqual(dry["status"], "planned")
        self.assertEqual(result["status"], "backfilled")
        self.assertEqual(summary["batch_rows"], 1)
        self.assertEqual(summary["rolling_10"]["batch_count"], 1)
        self.assertEqual(summary["rolling_10"]["rate"], 100.0)

    def test_recommendation_state_and_projection_backfill(self) -> None:
        missing = jackal_quality.describe_jackal_recommendation_accuracy_state()
        self.assertIn("missing_recommendation_samples", missing["missing_reasons"])

        state.sync_jackal_recommendations(
            [
                {
                    "ticker": "AAPL",
                    "market": "US",
                    "recommended_at": "2026-04-20T10:00:00+09:00",
                    "price_at_rec": 100.0,
                    "outcome_checked": True,
                    "outcome_correct": True,
                    "outcome_pct": 2.1,
                    "orca_regime": "risk_on",
                    "orca_inflows": ["semis"],
                }
            ]
        )

        dry = jackal_quality.backfill_recommendation_accuracy_projection(dry_run=True)
        result = jackal_quality.backfill_recommendation_accuracy_projection(dry_run=False)
        current = state.list_jackal_accuracy_projection(family="recommendation", scope="regime")

        self.assertEqual(dry["status"], "planned")
        self.assertEqual(result["status"], "backfilled")
        self.assertEqual(current[0]["entity_key"], "risk_on")
        self.assertEqual(current[0]["accuracy"], 100.0)

    def test_latest_raw_incremental_noop_is_info_when_evaluable_fresh(self) -> None:
        raw = {
            "status": "completed",
            "summary": {
                "total_tracked": 0,
                "selection_mode": "incremental",
                "backtest_days": 0,
                "materialized_candidates": 0,
                "materialized_outcomes": 0,
            },
        }
        evaluable = {"ended_at": "2026-04-29T10:00:00+09:00"}

        with patch.object(jackal_quality, "_now", return_value=jackal_quality._parse_dt("2026-04-29T12:00:00+09:00")):
            classification = jackal_quality.classify_latest_raw_jackal_session(raw, evaluable)

        self.assertEqual(classification["reason"], "incremental_no_new_data")
        self.assertEqual(classification["severity"], "info")
        self.assertFalse(classification["latest_evaluable_stale"])


if __name__ == "__main__":
    unittest.main()
