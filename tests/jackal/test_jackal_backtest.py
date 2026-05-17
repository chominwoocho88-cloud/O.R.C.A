import unittest
from unittest.mock import patch

from jackal import backtest


class JackalBacktestUniverseTests(unittest.TestCase):
    def test_build_universe_uses_portfolio_exclusions(self):
        pools = {
            "alpha": ["AAA", "BBB", "CCC"],
            "beta": ["BBB", "DDD"],
        }
        with patch.object(backtest, "SECTOR_POOLS", pools), patch.object(
            backtest, "get_portfolio_exclusions", return_value={"BBB", "DDD"}
        ):
            universe = backtest._build_universe()

        self.assertEqual(universe, ["AAA", "CCC"])

    def test_run_backtest_marks_no_data_incremental_session_skipped(self):
        source = {"incremental_from_analysis_date": "2026-04-18"}
        with patch.object(backtest, "load_memory", return_value=([], source)), patch.object(
            backtest, "start_backtest_session", return_value="bt_test"
        ), patch.object(backtest, "save_backtest_state") as save_state, patch.object(
            backtest, "finish_backtest_session"
        ) as finish_session:
            summary = backtest.run_backtest(mode=backtest.BACKTEST_MODE_INCREMENTAL)

        self.assertFalse(summary["evaluable"])
        self.assertEqual(summary["skip_reason"], "no_new_incremental_data")
        self.assertEqual(summary["total_tracked"], 0)
        save_state.assert_called_once()
        finish_session.assert_called_once()
        self.assertEqual(finish_session.call_args.args[1], backtest.SKIPPED_NO_NEW_DATA_STATUS)


if __name__ == "__main__":
    unittest.main()
