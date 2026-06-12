"""점수 신뢰도 곡선 — 과신/과소신 진단 (관측 전용, 2026-06-12)."""
from __future__ import annotations

import unittest

from jackal.calibration import (bin_label, calibration_hint, calibration_rows,
                                record_calibration)


def _entry(score, hit, reward=0.5):
    return {"final_score": score, "outcome_swing_hit": hit, "reward": reward}


class CalibrationTestCase(unittest.TestCase):
    def test_bin_label_boundaries(self):
        self.assertEqual(bin_label(39.9), "~39")
        self.assertEqual(bin_label(40), "40-54")
        self.assertEqual(bin_label(75), "75+")
        self.assertEqual(bin_label(100), "75+")
        self.assertIsNone(bin_label(None))
        self.assertIsNone(bin_label("뭔가"))

    def test_overconfidence_detected(self):
        weights = {}
        for _ in range(10):  # 70점대를 주는데 실현 30%
            record_calibration(weights, _entry(70, False, -0.5))
        for _ in range(4):
            record_calibration(weights, _entry(70, True, 0.8))

        rows = calibration_rows(weights)

        self.assertEqual(rows[0]["bin"], "65-74")
        self.assertEqual(rows[0]["verdict"], "과신")
        self.assertAlmostEqual(rows[0]["hit_pct"], 28.6, places=1)

    def test_underconfidence_detected(self):
        weights = {}
        for _ in range(6):  # 45점 주는데 다 맞음
            record_calibration(weights, _entry(45, True))

        rows = calibration_rows(weights)

        self.assertEqual(rows[0]["verdict"], "과소신")

    def test_min_samples_gate(self):
        weights = {}
        for _ in range(3):
            record_calibration(weights, _entry(70, True))

        self.assertEqual(calibration_rows(weights, min_samples=5), [])
        self.assertEqual(calibration_hint(weights), "")

    def test_hint_text(self):
        weights = {}
        for _ in range(6):
            record_calibration(weights, _entry(70, True))

        hint = calibration_hint(weights)

        self.assertIn("65-74점대", hint)
        self.assertIn("점수 신뢰도", hint)
        self.assertIn("과신 구간에선", hint)


if __name__ == "__main__":
    unittest.main()
