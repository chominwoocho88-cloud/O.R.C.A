import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from orca.self_correction import (
    DriftResult,
    append_self_correction_log,
    load_self_correction_log,
)


class Phase4Sprint23bAuditTests(unittest.TestCase):
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

    def test_load_empty_log(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "test_log.json"
            self.assertEqual(load_self_correction_log(log_file), [])

    def test_append_creates_file(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "test_log.json"
            result = self._build_drift_result()
            correction_info = {
                "correction_applied": True,
                "severity": "low_accuracy",
                "delta": -0.05,
                "reason": "correction_low_accuracy",
            }
            entry = append_self_correction_log(
                result,
                correction_info,
                log_file=log_file,
                timestamp="2026-05-09 02:30:00",
            )
            self.assertTrue(log_file.exists())
            self.assertTrue(entry["correction_applied"])
            self.assertEqual(entry["correction_severity"], "low_accuracy")

    def test_append_appends(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "test_log.json"
            result = self._build_drift_result()
            first = {
                "correction_applied": False,
                "severity": None,
                "delta": 0.0,
                "reason": "no_correction_needed",
            }
            second = {
                "correction_applied": True,
                "severity": "severe_drop",
                "delta": -0.10,
                "reason": "correction_severe_drop",
            }

            append_self_correction_log(result, first, log_file=log_file, timestamp="2026-05-09 02:30:00")
            append_self_correction_log(result, second, log_file=log_file, timestamp="2026-05-09 03:30:00")

            log = json.loads(log_file.read_text(encoding="utf-8"))
            self.assertEqual(len(log), 2)
            self.assertEqual(log[0]["timestamp"], "2026-05-09 02:30:00")
            self.assertEqual(log[1]["timestamp"], "2026-05-09 03:30:00")

    def test_entry_fields(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "test_log.json"
            result = self._build_drift_result()
            correction_info = {
                "correction_applied": True,
                "severity": "low_accuracy",
                "delta": -0.05,
                "reason": "correction_low_accuracy",
            }
            entry = append_self_correction_log(result, correction_info, log_file=log_file)

            expected_keys = {
                "timestamp",
                "drift_detected",
                "drift_reason",
                "recent_accuracy",
                "baseline_accuracy",
                "recent_samples",
                "baseline_samples",
                "correction_applied",
                "correction_severity",
                "correction_delta",
                "correction_reason",
            }
            self.assertEqual(set(entry.keys()), expected_keys)

    def test_no_drift_logged(self):
        with TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "test_log.json"
            result = self._build_drift_result(drift_detected=False, reason="stable")
            correction_info = {
                "correction_applied": False,
                "severity": None,
                "delta": 0.0,
                "reason": "no_correction_needed",
            }
            entry = append_self_correction_log(result, correction_info, log_file=log_file)

            self.assertFalse(entry["drift_detected"])
            self.assertFalse(entry["correction_applied"])

    def test_atomic_write(self):
        from orca import self_correction
        import inspect

        source = inspect.getsource(self_correction.append_self_correction_log)
        self.assertIn("atomic_write_json", source)


if __name__ == "__main__":
    unittest.main()
