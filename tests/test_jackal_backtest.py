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


if __name__ == "__main__":
    unittest.main()
