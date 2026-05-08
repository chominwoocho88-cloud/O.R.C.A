import json
import unittest
from pathlib import Path

from orca.self_correction import (
    DriftResult,
    apply_phase4_correction,
    detect_drift,
    get_correction_delta,
    get_correction_severity,
)


class Phase4Sprint23aCorrectionTests(unittest.TestCase):
    def _build_drift_result(self, **kwargs):
        defaults = dict(
            drift_detected=True,
            reason="low_accuracy",
            recent_accuracy=0.7,
            baseline_accuracy=0.85,
            recent_samples=10,
            baseline_samples=20,
            threshold_low_accuracy=0.75,
            threshold_drift_delta=0.15,
        )
        defaults.update(kwargs)
        return DriftResult(**defaults)

    def test_severity_no_drift(self):
        result = self._build_drift_result(drift_detected=False, reason="stable")
        self.assertIsNone(get_correction_severity(result))

    def test_severity_severe_drop(self):
        result = self._build_drift_result(recent_accuracy=0.7, baseline_accuracy=0.9)
        self.assertEqual(get_correction_severity(result), "severe_drop")

    def test_severity_low_accuracy(self):
        result = self._build_drift_result(recent_accuracy=0.72, baseline_accuracy=0.80)
        self.assertEqual(get_correction_severity(result), "low_accuracy")

    def test_delta_severe(self):
        self.assertEqual(get_correction_delta("severe_drop"), -0.10)

    def test_delta_low(self):
        self.assertEqual(get_correction_delta("low_accuracy"), -0.05)

    def test_delta_unknown(self):
        self.assertEqual(get_correction_delta("unknown"), 0.0)

    def test_apply_correction_no_drift(self):
        result = self._build_drift_result(drift_detected=False, reason="stable")
        correction = apply_phase4_correction(result)
        self.assertFalse(correction["correction_applied"])
        self.assertIsNone(correction["severity"])
        self.assertEqual(correction["delta"], 0.0)

    def test_apply_correction_severe(self):
        result = self._build_drift_result(recent_accuracy=0.65, baseline_accuracy=0.90)
        correction = apply_phase4_correction(result)
        self.assertTrue(correction["correction_applied"])
        self.assertEqual(correction["severity"], "severe_drop")
        self.assertEqual(correction["delta"], -0.10)

    def test_real_accuracy_data_no_correction(self):
        data = json.loads(Path("data/accuracy.json").read_text(encoding="utf-8"))
        drift_result = detect_drift(data)
        correction = apply_phase4_correction(drift_result)
        if drift_result.drift_detected:
            self.assertIn("correction_applied", correction)
        else:
            self.assertFalse(correction["correction_applied"])


if __name__ == "__main__":
    unittest.main()
