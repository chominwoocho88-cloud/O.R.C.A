import unittest
from unittest.mock import patch

from orca import backtest


class BacktestDryLessonDebugTests(unittest.TestCase):
    def test_dry_generate_analysis_reports_selected_lessons(self) -> None:
        lesson_context = "\n[과거 교훈]\n  lesson one\n  lesson two\n"
        market_data = {
            "fear_greed": "42",
            "sp500_change": "+1.10%",
            "note": "dry backtest",
            "krw_usd": 1450.0,
            "kospi_change": "+0.40%",
        }

        with patch("orca.backtest._load_lessons_context", return_value=lesson_context):
            result = backtest.generate_analysis(backtest.DATES[1], market_data, dry=True)

        self.assertTrue(result["debug_lessons_present"])
        self.assertEqual(result["debug_lessons_count"], 2)


if __name__ == "__main__":
    unittest.main()
