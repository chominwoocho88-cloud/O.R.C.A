import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from apps.orca import state
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
        self.assertEqual(report["baseline_fallback_audit"]["status"], "ok")

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

    def test_baseline_fallback_summary_missing_log_is_ok(self) -> None:
        missing = self.tmpdir / "missing_baseline_fallback_audit.log"

        summary = check_jackal_operational_intake.collect_baseline_fallback_summary(
            audit_log_path=missing,
            now=datetime(2026, 5, 20, 12, 0, tzinfo=check_jackal_operational_intake.KST),
        )

        self.assertFalse(summary["log_exists"])
        self.assertEqual(summary["total_events"], 0)
        self.assertEqual(summary["today_events"], 0)
        self.assertEqual(summary["last_7d_events"], 0)
        self.assertEqual(summary["status"], "ok")

    def test_baseline_fallback_summary_empty_log_is_ok(self) -> None:
        audit_path = self.tmpdir / "baseline_fallback_audit.log"
        audit_path.write_text("", encoding="utf-8")

        summary = check_jackal_operational_intake.collect_baseline_fallback_summary(
            audit_log_path=audit_path,
            now=datetime(2026, 5, 20, 12, 0, tzinfo=check_jackal_operational_intake.KST),
        )

        self.assertTrue(summary["log_exists"])
        self.assertEqual(summary["total_events"], 0)
        self.assertEqual(summary["parse_error_count"], 0)
        self.assertEqual(summary["status"], "ok")

    def test_baseline_fallback_summary_aggregates_sources_and_dates(self) -> None:
        now = datetime(2026, 5, 20, 12, 0, tzinfo=check_jackal_operational_intake.KST)
        old = now - timedelta(days=10)
        audit_path = self.tmpdir / "baseline_fallback_audit.log"
        rows = [
            {
                "ts": now.isoformat(),
                "component": "hunter",
                "regime_source": "memory",
                "regime": "risk_on",
                "baseline_exists": False,
                "memory_exists": True,
            },
            {
                "ts": (now - timedelta(days=2)).isoformat(),
                "component": "scanner",
                "regime_source": "fallback",
                "regime": "mixed",
                "baseline_exists": False,
                "memory_exists": False,
            },
            {
                "ts": old.isoformat(),
                "component": "scanner",
                "regime_source": "none",
                "regime": "",
                "baseline_exists": False,
                "memory_exists": False,
            },
        ]
        audit_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")

        summary = check_jackal_operational_intake.collect_baseline_fallback_summary(
            audit_log_path=audit_path,
            now=now,
        )

        self.assertEqual(summary["total_events"], 3)
        self.assertEqual(summary["today_events"], 1)
        self.assertEqual(summary["last_7d_events"], 2)
        self.assertEqual(summary["by_component"]["hunter"], 1)
        self.assertEqual(summary["by_component"]["scanner"], 2)
        self.assertEqual(summary["by_regime_source"]["memory"], 1)
        self.assertEqual(summary["by_regime_source"]["fallback"], 1)
        self.assertEqual(summary["by_regime_source"]["none"], 1)
        self.assertEqual(summary["latest_event"]["regime_source"], "memory")
        self.assertEqual(summary["status"], "warn")

    def test_baseline_fallback_summary_malformed_lines_are_warn_only(self) -> None:
        now = datetime(2026, 5, 20, 12, 0, tzinfo=check_jackal_operational_intake.KST)
        audit_path = self.tmpdir / "baseline_fallback_audit.log"
        valid = {
            "ts": (now - timedelta(days=10)).isoformat(),
            "component": "hunter",
            "regime_source": "memory",
            "regime": "risk_on",
            "baseline_exists": False,
            "memory_exists": True,
        }
        audit_path.write_text("{bad json}\n" + json.dumps(valid, ensure_ascii=False) + "\n", encoding="utf-8")

        summary = check_jackal_operational_intake.collect_baseline_fallback_summary(
            audit_log_path=audit_path,
            now=now,
        )

        self.assertEqual(summary["total_events"], 1)
        self.assertEqual(summary["parse_error_count"], 1)
        self.assertEqual(summary["status"], "warn")

    def test_baseline_fallback_summary_read_failure_is_warn_only(self) -> None:
        summary = check_jackal_operational_intake.collect_baseline_fallback_summary(
            audit_log_path=self.tmpdir,
            now=datetime(2026, 5, 20, 12, 0, tzinfo=check_jackal_operational_intake.KST),
        )

        self.assertTrue(summary["log_exists"])
        self.assertEqual(summary["parse_error_count"], 1)
        self.assertEqual(summary["status"], "warn")

    def test_render_markdown_includes_baseline_fallback_section_for_zero_events(self) -> None:
        report = check_jackal_operational_intake.collect_operational_intake()

        markdown = check_jackal_operational_intake.render_markdown(report)

        self.assertIn("## Baseline Fallback Audit", markdown)
        self.assertIn("- Status: `ok`", markdown)
        self.assertIn("- Total events: `0`", markdown)


if __name__ == "__main__":
    unittest.main()
