import unittest
from unittest.mock import patch

from orca import research_report


class ResearchReportSummaryTests(unittest.TestCase):
    def test_sanitize_orca_summary_keeps_applied_lesson_count_only(self) -> None:
        summary = {
            "lesson_count": 115,
            "generated_lesson_count": 170,
            "final_accuracy": 58.7,
        }

        clean = research_report._sanitize_orca_summary(summary)

        self.assertEqual(clean["lesson_count"], 115)
        self.assertNotIn("generated_lesson_count", clean)
        self.assertEqual(clean["final_accuracy"], 58.7)

    def test_sanitize_orca_session_strips_generated_lesson_count_from_nested_summary(self) -> None:
        session = {
            "session_id": "bt_test",
            "summary": {
                "lesson_count": 115,
                "generated_lesson_count": 170,
            },
        }

        clean = research_report._sanitize_orca_session(session)

        self.assertEqual(clean["summary"]["lesson_count"], 115)
        self.assertNotIn("generated_lesson_count", clean["summary"])

    def test_latest_jackal_sessions_skip_non_evaluable_raw_session(self) -> None:
        raw_no_data = {
            "session_id": "bt_raw",
            "status": "completed",
            "ended_at": "2026-04-28T13:00:00+09:00",
            "summary": {"total_tracked": 0},
        }
        evaluable = {
            "session_id": "bt_eval",
            "status": "completed",
            "ended_at": "2026-04-28T09:00:00+09:00",
            "summary": {"total_tracked": 120, "swing_accuracy": 61.2, "d1_accuracy": 48.1},
        }

        def fake_list(_system, *, label=None, status="completed", limit=10):
            if status == "completed":
                return [raw_no_data, evaluable]
            return []

        with patch.object(research_report, "list_backtest_sessions", side_effect=fake_list):
            latest, previous = research_report._find_latest_jackal_sessions()
            latest_raw = research_report._find_latest_raw_jackal_session()

        self.assertEqual(latest["session_id"], "bt_eval")
        self.assertIsNone(previous)
        self.assertEqual(latest_raw["session_id"], "bt_raw")
        self.assertEqual(research_report._jackal_session_evaluation_issue(raw_no_data), "total_tracked_zero")

    def test_accuracy_snapshot_exposes_projection_source_and_missing_reason(self) -> None:
        def fake_projection(*, family=None, scope=None, current_only=True, limit=500):
            if family == "system" and scope == "swing":
                return [
                    {
                        "entity_key": "jackal_backtest",
                        "accuracy": 70.0,
                        "total": 120,
                        "source": "backfill_jackal_backtest:bt_1",
                        "captured_at": "2026-04-28T10:00:00+09:00",
                        "metrics": {"source_session_id": "bt_1"},
                    }
                ]
            return []

        with (
            patch.object(research_report, "rebuild_latest_jackal_accuracy_projection", return_value=0),
            patch.object(
                research_report,
                "describe_jackal_accuracy_projection_state",
                return_value={
                    "snapshot_rows": 1,
                    "projection_rows": 1,
                    "current_rows": 1,
                    "max_sample_count": 120,
                    "latest_projection": {
                        "source": "backfill_jackal_backtest:bt_1",
                        "captured_at": "2026-04-28T10:00:00+09:00",
                        "generated_at": "2026-04-28T10:00:01+09:00",
                    },
                    "latest_source": "backfill_jackal_backtest:bt_1",
                    "latest_captured_at": "2026-04-28T10:00:00+09:00",
                    "latest_generated_at": "2026-04-28T10:00:01+09:00",
                    "missing_reasons": ["missing_accuracy_current"],
                    "by_family_scope": [],
                },
            ),
            patch.object(research_report, "list_jackal_accuracy_projection", side_effect=fake_projection),
        ):
            snapshot = research_report._build_accuracy_snapshot(min_total=3, limit=5)

        self.assertEqual(snapshot["meta"]["latest_source"], "backfill_jackal_backtest:bt_1")
        self.assertEqual(snapshot["meta"]["max_sample_count"], 120)
        self.assertIn("missing_accuracy_current", snapshot["meta"]["missing_reasons"])
        self.assertEqual(snapshot["system_swing_accuracy"][0]["entity_key"], "jackal_backtest")


if __name__ == "__main__":
    unittest.main()
