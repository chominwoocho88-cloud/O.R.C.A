import json
import unittest
from pathlib import Path

from orca.self_correction import DriftResult, detect_drift


class DriftDetectorTests(unittest.TestCase):
    def _build_history(self, days_data: list) -> dict:
        return {
            "history": [
                {
                    "date": d,
                    "total": t,
                    "correct": c,
                    "accuracy": (c / t * 100 if t > 0 else 0),
                }
                for d, t, c in days_data
            ]
        }

    def test_insufficient_recent_samples(self):
        data = self._build_history(
            [
                ("2026-05-06", 1, 1),
                ("2026-05-07", 1, 1),
            ]
        )
        result = detect_drift(data, today="2026-05-08")
        self.assertFalse(result.drift_detected)
        self.assertEqual(result.reason, "insufficient_samples")
        self.assertEqual(result.recent_samples, 2)

    def test_insufficient_baseline_samples(self):
        data = self._build_history(
            [
                ("2026-05-05", 5, 5),
                ("2026-05-06", 5, 5),
            ]
        )
        result = detect_drift(data, today="2026-05-08", min_baseline_samples=20)
        self.assertFalse(result.drift_detected)
        self.assertEqual(result.reason, "insufficient_samples")
        self.assertEqual(result.baseline_samples, 10)

    def test_stable_accuracy(self):
        days = []
        for i in range(20, 31):
            days.append((f"2026-04-{i:02d}", 3, 3))
        for i in range(1, 8):
            days.append((f"2026-05-{i:02d}", 3, 3))

        data = self._build_history(days)
        result = detect_drift(data, today="2026-05-08")

        self.assertFalse(result.drift_detected)
        self.assertEqual(result.reason, "stable")
        self.assertEqual(result.recent_accuracy, 1.0)
        self.assertEqual(result.baseline_accuracy, 1.0)

    def test_low_accuracy_detected(self):
        days = []
        for i in range(10, 31):
            days.append((f"2026-04-{i:02d}", 5, 5))
        for i in range(1, 8):
            days.append((f"2026-05-{i:02d}", 4, 2))

        data = self._build_history(days)
        result = detect_drift(data, today="2026-05-08")

        self.assertTrue(result.drift_detected)
        self.assertEqual(result.reason, "low_accuracy_and_drop")
        self.assertLess(result.recent_accuracy, 0.75)

    def test_significant_drop_detected(self):
        days = []
        for i in range(10, 31):
            days.append((f"2026-04-{i:02d}", 20, 20))
        for i in range(1, 8):
            days.append((f"2026-05-{i:02d}", 25, 19))

        data = self._build_history(days)
        result = detect_drift(data, today="2026-05-08")

        self.assertTrue(result.drift_detected)
        self.assertEqual(result.reason, "significant_drop")
        self.assertGreaterEqual(result.baseline_accuracy - result.recent_accuracy, 0.15)

    def test_real_accuracy_json(self):
        path = Path("data/accuracy.json")
        if not path.exists():
            self.skipTest("data/accuracy.json does not exist")

        data = json.loads(path.read_text(encoding="utf-8"))
        result = detect_drift(data)

        self.assertIsInstance(result, DriftResult)

    def test_returns_drift_result(self):
        data = self._build_history(
            [
                ("2026-05-07", 3, 3),
                ("2026-05-08", 3, 3),
            ]
        )
        result = detect_drift(data, today="2026-05-08")
        self.assertIsInstance(result, DriftResult)
        self.assertIsInstance(result.drift_detected, bool)
        self.assertIsInstance(result.reason, str)

    def test_no_history(self):
        result = detect_drift({}, today="2026-05-08")
        self.assertFalse(result.drift_detected)
        self.assertEqual(result.reason, "insufficient_samples")
        self.assertEqual(result.recent_samples, 0)
        self.assertEqual(result.baseline_samples, 0)


if __name__ == "__main__":
    unittest.main()
