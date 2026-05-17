import unittest

from orca.notify import _format_ticker_display


class Phase52dKoreanTickerDisplayTests(unittest.TestCase):
    """Phase 5-2d: show readable candidate names in Telegram review lines."""

    def test_korean_with_name(self):
        item = {"ticker": "466920.KS", "name": "SOL 코리아고배당"}
        self.assertEqual(
            _format_ticker_display(item),
            "SOL 코리아고배당 (466920.KS)",
        )

    def test_us_with_name(self):
        item = {"ticker": "AVGO", "name": "브로드컴"}
        self.assertEqual(_format_ticker_display(item), "브로드컴 (AVGO)")

    def test_us_nvda(self):
        item = {"ticker": "NVDA", "name": "엔비디아"}
        self.assertEqual(_format_ticker_display(item), "엔비디아 (NVDA)")

    def test_no_name_fallback_ticker(self):
        item = {"ticker": "NVDA"}
        self.assertEqual(_format_ticker_display(item), "NVDA")

    def test_empty_name_fallback(self):
        item = {"ticker": "NVDA", "name": ""}
        self.assertEqual(_format_ticker_display(item), "NVDA")

    def test_whitespace_name_fallback(self):
        item = {"ticker": "NVDA", "name": "   "}
        self.assertEqual(_format_ticker_display(item), "NVDA")

    def test_name_equals_ticker_no_dup(self):
        item = {"ticker": "NVDA", "name": "NVDA"}
        self.assertEqual(_format_ticker_display(item), "NVDA")

    def test_empty_ticker(self):
        item = {"ticker": "", "name": "엔비디아"}
        self.assertEqual(_format_ticker_display(item), "엔비디아 ()")

    def test_none_values(self):
        item = {"ticker": None, "name": None}
        self.assertEqual(_format_ticker_display(item), "")

    def test_empty_dict(self):
        self.assertEqual(_format_ticker_display({}), "")
