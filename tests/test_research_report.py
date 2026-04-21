import unittest

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


if __name__ == "__main__":
    unittest.main()
