import json
import unittest
from pathlib import Path
from unittest.mock import patch


class Phase4Sprint22bTelegramTests(unittest.TestCase):
    def test_phase4_drift_badge_flag_false(self):
        from orca.notify import _build_phase4_drift_badge

        report = {
            "phase4_drift": {
                "drift_detected": True,
                "reason": "low_accuracy",
                "recent_accuracy": 0.7,
                "baseline_accuracy": 0.9,
                "flag_enabled": False,
            }
        }
        self.assertEqual(_build_phase4_drift_badge(report), "")

    def test_phase4_drift_badge_no_drift(self):
        from orca.notify import _build_phase4_drift_badge

        report = {
            "phase4_drift": {
                "drift_detected": False,
                "reason": "stable",
                "flag_enabled": True,
            }
        }
        self.assertEqual(_build_phase4_drift_badge(report), "")

    def test_phase4_drift_badge_drift_with_flag(self):
        from orca.notify import _build_phase4_drift_badge

        report = {
            "phase4_drift": {
                "drift_detected": True,
                "reason": "low_accuracy",
                "recent_accuracy": 0.7,
                "baseline_accuracy": 0.9,
                "flag_enabled": True,
            }
        }
        result = _build_phase4_drift_badge(report)
        self.assertIn("🟡 Drift 감지", result)
        self.assertIn("low_accuracy", result)
        self.assertIn("70.0%", result)
        self.assertIn("90.0%", result)

    def test_phase4_drift_badge_no_phase4_key(self):
        from orca.notify import _build_phase4_drift_badge

        self.assertEqual(_build_phase4_drift_badge({}), "")

    def test_run_cycle_returns_drift_info(self):
        from modules.orca.pipeline.run_cycle import _run_phase4_drift_check

        data = json.loads(Path("data/accuracy.json").read_text(encoding="utf-8"))
        with patch("builtins.print"):
            result = _run_phase4_drift_check(data)
        self.assertIsInstance(result, dict)
        self.assertIn("drift_detected", result)
        self.assertIn("reason", result)
        self.assertIn("flag_enabled", result)


if __name__ == "__main__":
    unittest.main()
