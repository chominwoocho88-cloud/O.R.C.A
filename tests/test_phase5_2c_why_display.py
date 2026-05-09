import unittest
from unittest.mock import patch

from orca.notify import _build_morning


class Phase52cWhyDisplayTests(unittest.TestCase):
    """Phase 5-2c option D: reason [:4] plus short why display."""

    def _build_report(self, highlights):
        return {
            "outflows": [],
            "inflows": [],
            "thesis_killers": [],
            "actionable_watch": [],
            "jackal_candidate_review": {
                "reviewed_count": len(highlights),
                "aligned_count": 1,
                "neutral_count": max(len(highlights) - 1, 0),
                "opposed_count": 0,
                "review_verdict_breakdown": {
                    "strong_aligned": 0,
                    "aligned": 0,
                    "neutral": len(highlights),
                    "opposed": 0,
                    "strong_opposed": 0,
                },
                "average_review_confidence": "low",
                "market_bias_label": "risk_on",
                "highlights": highlights,
            },
        }

    def _render(self, report):
        with patch("orca.notify.get_active_lessons", return_value=[]):
            return "\n".join(_build_morning(report))

    def test_reason_displays_4(self):
        """Four reason codes are displayed, not just two."""
        highlights = [
            {
                "ticker": "NVDA",
                "alignment": "neutral",
                "review_verdict": "neutral",
                "quality_score": 50,
                "alignment_reason_codes": [
                    "market_bias_tailwind",
                    "insufficient_data",
                    "devil_bearish_warn",
                    "devil_contradicts_thesis",
                ],
                "why": "",
            }
        ]

        msg = self._render(self._build_report(highlights))
        self.assertIn("시장우호", msg)
        self.assertIn("데이터부족", msg)
        self.assertIn("반론경고", msg)
        self.assertIn("논리충돌", msg)

    def test_why_displayed_when_present(self):
        """A why line is added when why is present."""
        highlights = [
            {
                "ticker": "TEST",
                "alignment": "neutral",
                "review_verdict": "neutral",
                "quality_score": 50,
                "alignment_reason_codes": ["market_bias_tailwind"],
                "why": "테스트 why 짧은 텍스트",
            }
        ]

        msg = self._render(self._build_report(highlights))
        self.assertIn("↳", msg)
        self.assertIn("테스트 why 짧은 텍스트", msg)

    def test_why_truncated_at_60(self):
        """A long why line is truncated with an ASCII ellipsis."""
        long_why = "긴 why 텍스트 " * 20
        highlights = [
            {
                "ticker": "TEST",
                "alignment": "neutral",
                "review_verdict": "neutral",
                "quality_score": 50,
                "alignment_reason_codes": [],
                "why": long_why,
            }
        ]

        msg = self._render(self._build_report(highlights))
        self.assertIn("...", msg)
        self.assertNotIn(long_why, msg)

    def test_no_why_no_extra_line(self):
        """No why means no extra arrow line."""
        highlights = [
            {
                "ticker": "TEST",
                "alignment": "neutral",
                "review_verdict": "neutral",
                "quality_score": 50,
                "alignment_reason_codes": ["market_bias_tailwind"],
                "why": "",
            }
        ]

        msg = self._render(self._build_report(highlights))
        self.assertNotIn("↳", msg)

    def test_message_length_under_limit(self):
        """Three highlighted candidates stay under the Telegram chunk limit."""
        highlights = [
            {
                "ticker": f"T{i}",
                "alignment": "neutral",
                "review_verdict": "neutral",
                "quality_score": 50,
                "alignment_reason_codes": [
                    "market_bias_tailwind",
                    "insufficient_data",
                    "devil_bearish_warn",
                    "devil_contradicts_thesis",
                ],
                "why": "긴 why 텍스트 " * 10,
            }
            for i in range(3)
        ]

        msg = self._render(self._build_report(highlights))
        self.assertLess(len(msg), 4000)

    def test_arrow_unicode(self):
        """The why marker uses U+21B3."""
        highlights = [
            {
                "ticker": "TEST",
                "alignment": "neutral",
                "review_verdict": "neutral",
                "quality_score": 50,
                "alignment_reason_codes": [],
                "why": "test",
            }
        ]

        msg = self._render(self._build_report(highlights))
        self.assertIn("\u21b3", msg)


if __name__ == "__main__":
    unittest.main()
