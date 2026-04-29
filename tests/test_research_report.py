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


if __name__ == "__main__":
    unittest.main()
