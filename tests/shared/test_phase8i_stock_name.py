import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import hunter
from shared.market_data import stock_name


class TestStockName(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.cache_path = self.tmpdir / "stock_name_cache.json"
        self.cache_patch = patch.object(stock_name, "CACHE_PATH", self.cache_path)
        self.cache_patch.start()
        stock_name._fdr_listing.cache_clear()

    def tearDown(self) -> None:
        self.cache_patch.stop()
        stock_name._fdr_listing.cache_clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_us_ticker_returns_none(self):
        self.assertIsNone(stock_name.get_stock_name("AAPL"))

    def test_kospi_ticker_returns_korean_name(self):
        with patch.object(stock_name, "_fetch_from_fdr", return_value="셀트리온"):
            self.assertEqual(stock_name.get_stock_name("068270.KS"), "셀트리온")

    def test_kosdaq_ticker_returns_korean_name(self):
        with patch.object(stock_name, "_fetch_from_fdr", return_value="에코프로"):
            self.assertEqual(stock_name.get_stock_name("086520.KQ"), "에코프로")

    def test_cache_load_save(self):
        stock_name._save_cache({"207940.KS": "삼성바이오로직스"})

        self.assertEqual(stock_name._load_cache(), {"207940.KS": "삼성바이오로직스"})

    def test_cache_hit_skips_fetch(self):
        stock_name._save_cache({"207940.KS": "삼성바이오로직스"})

        with patch.object(stock_name, "_fetch_from_fdr", side_effect=AssertionError("fetch called")):
            self.assertEqual(stock_name.get_stock_name("207940.KS"), "삼성바이오로직스")

    def test_unknown_ticker_returns_none(self):
        with patch.object(stock_name, "_fetch_from_fdr", return_value=None):
            self.assertIsNone(stock_name.get_stock_name("999999.KS"))

    def test_fetch_failure_returns_none(self):
        with patch.object(stock_name, "_fetch_from_fdr", side_effect=RuntimeError("provider down")):
            self.assertIsNone(stock_name.get_stock_name("068270.KS"))

    def test_hunter_message_uses_name(self):
        item = {
            "ticker": "068270.KS",
            "name": "068270.KS",
            "currency": "₩",
            "tech": {
                "price": 180000,
                "change_1d": 1.2,
                "change_5d": 3.4,
                "rsi": 28,
                "bb_pos": 12,
                "vol_ratio": 1.5,
            },
            "analyst": {
                "signals_fired": [],
                "swing_setup": "중립",
                "swing_type": "기술적과매도",
                "bull_case": "",
                "entry_zone": "",
                "target_5d": "",
                "stop_loss": "",
                "expected_days": 3,
            },
            "devil": {"verdict": "부분동의", "main_risk": ""},
            "final": {
                "final_score": 80,
                "label": "통과",
                "mode": "일반",
                "day1_score": 70,
                "swing_score": 82,
            },
            "signal_family": "panic_rebound",
            "historical_context": None,
        }

        with patch.object(hunter, "format_stock_display", return_value="셀트리온 (068270.KS)"):
            message = hunter._build_alert(item, {"regime": "위험선호"})

        self.assertIn("셀트리온 (068270.KS)", message)
        self.assertNotIn("068270.KS (068270.KS)", message)


if __name__ == "__main__":
    unittest.main()
