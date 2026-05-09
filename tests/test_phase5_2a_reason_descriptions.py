import unittest

from orca.notify import REASON_DESCRIPTIONS


class Phase52aReasonDescriptionsTests(unittest.TestCase):
    def test_market_bias_tailwind(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("market_bias_tailwind"), "시장우호")

    def test_market_bias_headwind(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("market_bias_headwind"), "시장역풍")

    def test_regime_unclear(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("regime_unclear"), "시장모호")

    def test_insufficient_data(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("insufficient_data"), "데이터부족")

    def test_unknown_code_fallback(self):
        """Unknown codes are not mapped so notify can fall back to the code."""
        self.assertIsNone(REASON_DESCRIPTIONS.get("some_unknown_code"))

    def test_descriptions_are_short(self):
        """Descriptions stay short enough for the existing Telegram format."""
        for code, desc in REASON_DESCRIPTIONS.items():
            self.assertLessEqual(len(desc), 6, f"{code} -> {desc} too long")

    def test_notify_uses_descriptions(self):
        """Morning Telegram body uses mapped descriptions instead of raw codes."""
        from orca.notify import _build_morning

        report = {
            "jackal_candidate_review": {
                "reviewed_count": 1,
                "aligned_count": 0,
                "neutral_count": 1,
                "opposed_count": 0,
                "review_verdict_breakdown": {"neutral": 1},
                "market_bias_label": "위험선호",
                "highlights": [
                    {
                        "ticker": "TEST",
                        "alignment": "neutral",
                        "review_verdict": "neutral",
                        "quality_score": 50,
                        "alignment_reason_codes": [
                            "market_bias_tailwind",
                            "insufficient_data",
                        ],
                    }
                ],
            }
        }

        msg = "\n".join(_build_morning(report))
        self.assertIn("시장우호", msg)
        self.assertIn("데이터부족", msg)
        self.assertNotIn("market_bias_tailwind", msg)
        self.assertNotIn("insufficient_data", msg)


if __name__ == "__main__":
    unittest.main()
