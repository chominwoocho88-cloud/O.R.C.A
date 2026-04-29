import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jackal import scanner
from orca import jackal_quality, research_gate, research_report, state
from scripts import audit_quality, backfill_jackal_shadow


class JackalOperationalPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch.object(scanner, "JACKAL_WATCHLIST", self.tmpdir / "jackal_watchlist.json"),
            patch.object(scanner, "RECOMMEND_LOG_FILE", self.tmpdir / "recommendation_log.json"),
        ]
        for item in self.patches:
            item.start()
        state.init_state_db()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_scanner_quality_skip_persists_shadow_signal_without_llm(self) -> None:
        tech = {
            "price": 100.0,
            "rsi": 42.0,
            "bb_pos": 36.0,
            "vol_ratio": 1.4,
            "change_1d": 0.2,
            "change_5d": 1.1,
        }
        quality = {
            "skip": True,
            "quality_score": 38.0,
            "quality_label": "weak",
            "signal_family": "ma_support",
            "reasons": ["fixture quality skip"],
            "skip_threshold": 45.0,
            "rebound_bonus": 0.0,
            "vix_used": 18.0,
        }
        aria = {"regime": "risk_on", "sentiment_score": 55, "trend": "up", "key_inflows": ["semis"]}

        with patch.object(scanner, "fetch_all", return_value={"fred": {"vix": 18.0, "hy_spread": 3.1, "yield_curve": 0.2}}), \
            patch.object(scanner, "_load_orca_context", return_value=aria), \
            patch.object(scanner, "_load_portfolio", return_value={"AAPL": {"name": "Apple", "market": "US", "currency": "$", "portfolio": True}}), \
            patch.object(scanner, "_load_candidate_watchlist", return_value={}), \
            patch.object(scanner, "_load_recommendation_watchlist", return_value={}), \
            patch.object(scanner, "_suggest_extra_tickers", return_value={}), \
            patch.object(scanner, "_save_watchlist_snapshot", return_value=None), \
            patch.object(scanner, "fetch_technicals", return_value=tech), \
            patch.object(scanner, "_is_on_cooldown", return_value=False), \
            patch.object(scanner, "detect_pre_rule_signals", return_value=["ma_support"]), \
            patch.object(scanner, "_calc_signal_quality", return_value=quality), \
            patch.object(scanner, "_load_weights", return_value={}), \
            patch.object(scanner, "_send_telegram", return_value=None):
            result = scanner.run_scan(force=True)

        summary = jackal_quality.describe_jackal_shadow_state()

        self.assertEqual(result["scanned"], 1)
        self.assertEqual(summary["signal_rows"], 1)
        self.assertEqual(summary["signal_status_counts"].get("open"), 1)
        self.assertNotIn("missing_shadow_signals", summary["missing_reasons"])
        self.assertEqual(summary["source_path"], jackal_quality.SHADOW_SOURCE_PATH)

    def test_resolved_shadow_outcome_makes_dry_run_backfill_planned(self) -> None:
        shadow_id = state.record_jackal_shadow_signal(
            {
                "timestamp": "2026-04-20T10:00:00+09:00",
                "ticker": "AAPL",
                "market": "US",
                "signal_family": "ma_support",
                "quality_score": 38.0,
            }
        )
        state.resolve_jackal_shadow_signal(shadow_id, {"shadow_swing_ok": True})

        dry = backfill_jackal_shadow.run_backfill(dry_run=True, make_backup=False)

        self.assertEqual(dry["status"], "planned")
        self.assertEqual(dry["total"], 1)
        self.assertEqual(dry["worked"], 1)

    def test_recommendation_message_path_persists_row_and_requires_outcome_for_projection(self) -> None:
        aria = {"regime": "risk_on", "key_inflows": ["software"], "trend": "up"}
        extra = {
            "MSFT": {
                "name": "Microsoft",
                "market": "US",
                "currency": "$",
                "reason": "fixture recommendation",
            }
        }

        with patch("orca.market_fetch.fetch_latest_close", return_value=(100.0, 0.0, "fixture")), \
            patch.object(scanner, "_send_telegram", return_value=None):
            scanner._send_orca_extra_message(extra, aria)

        recommendations = state.list_jackal_recommendations(limit=5)
        missing = jackal_quality.describe_jackal_recommendation_accuracy_state()
        dry_missing = jackal_quality.backfill_recommendation_accuracy_projection(dry_run=True)

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(missing["recommendation_rows"], 1)
        self.assertIn("missing_recommendation_outcomes", missing["missing_reasons"])
        self.assertEqual(dry_missing["status"], "skipped")
        self.assertEqual(dry_missing["reason"], "missing_recommendation_outcomes")

        checked = dict(recommendations[0])
        checked.update({"outcome_checked": True, "outcome_correct": True, "outcome_pct": 1.2})
        state.sync_jackal_recommendations([checked])

        dry_ready = jackal_quality.backfill_recommendation_accuracy_projection(dry_run=True)
        backfilled = jackal_quality.backfill_recommendation_accuracy_projection(dry_run=False)
        projection = state.list_jackal_accuracy_projection(family="recommendation", scope="regime")

        self.assertEqual(dry_ready["status"], "planned")
        self.assertEqual(backfilled["status"], "backfilled")
        self.assertEqual(projection[0]["entity_key"], "risk_on")
        self.assertEqual(projection[0]["accuracy"], 100.0)

    def test_fixture_quality_path_is_visible_to_report_gate_and_audit(self) -> None:
        shadow_id = state.record_jackal_shadow_signal(
            {
                "timestamp": "2026-04-20T10:00:00+09:00",
                "ticker": "AAPL",
                "market": "US",
                "signal_family": "ma_support",
            }
        )
        state.resolve_jackal_shadow_signal(shadow_id, {"shadow_swing_ok": True})
        jackal_quality.backfill_shadow_batches_from_resolved_signals(dry_run=False)
        state.sync_jackal_recommendations(
            [
                {
                    "ticker": "MSFT",
                    "market": "US",
                    "recommended_at": "2026-04-20T10:00:00+09:00",
                    "outcome_checked": True,
                    "outcome_correct": True,
                    "outcome_pct": 1.2,
                    "orca_regime": "risk_on",
                    "orca_inflows": ["software"],
                }
            ]
        )
        jackal_quality.backfill_recommendation_accuracy_projection(dry_run=False)

        report = research_report.build_report()
        gate = research_gate.evaluate_report(report)
        metrics = audit_quality.collect_state_metrics()

        self.assertEqual(report["jackal_shadow"]["state"]["signal_rows"], 1)
        self.assertEqual(report["jackal_recommendation_accuracy"]["recommendation_rows"], 1)
        self.assertEqual(metrics["jackal_row_counts"]["jackal_shadow_signals"], 1)
        self.assertEqual(metrics["jackal_row_counts"]["jackal_recommendations"], 1)
        self.assertIn(gate["status"], {"pass", "warn", "fail"})


if __name__ == "__main__":
    unittest.main()
