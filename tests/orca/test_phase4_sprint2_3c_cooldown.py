import os
import unittest
from datetime import datetime
from unittest.mock import patch

from orca.self_correction import (
    DriftResult,
    apply_phase4_correction,
    get_cooldown_days,
    is_in_cooldown,
)


class Phase4Sprint23cCooldownTests(unittest.TestCase):
    def _build_drift_result(self, **kwargs):
        defaults = dict(
            drift_detected=True,
            reason="low_accuracy",
            recent_accuracy=0.65,
            baseline_accuracy=0.90,
            recent_samples=10,
            baseline_samples=20,
            threshold_low_accuracy=0.75,
            threshold_drift_delta=0.15,
        )
        defaults.update(kwargs)
        return DriftResult(**defaults)

    def test_default_cooldown_days(self):
        """기본 7일."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_cooldown_days(), 7)

    def test_env_cooldown_days(self):
        """env 변수 인식."""
        with patch.dict(os.environ, {"PHASE4_COOLDOWN_DAYS": "14"}):
            self.assertEqual(get_cooldown_days(), 14)

    def test_invalid_env_fallback(self):
        """invalid env 시 기본값."""
        with patch.dict(os.environ, {"PHASE4_COOLDOWN_DAYS": "abc"}):
            self.assertEqual(get_cooldown_days(), 7)

    def test_empty_log_no_cooldown(self):
        """audit log 비어있으면 cooldown 비활성."""
        in_cd, reason = is_in_cooldown([])
        self.assertFalse(in_cd)
        self.assertIsNone(reason)

    def test_no_correction_in_log_no_cooldown(self):
        """correction 적용된 적 없으면 cooldown 비활성."""
        log = [
            {"timestamp": "2026-05-01 00:00:00", "correction_applied": False},
            {"timestamp": "2026-05-02 00:00:00", "correction_applied": False},
        ]
        in_cd, reason = is_in_cooldown(log)
        self.assertFalse(in_cd)
        self.assertIsNone(reason)

    def test_recent_correction_in_cooldown(self):
        """최근 correction이면 cooldown 활성."""
        now = datetime(2026, 5, 9, 0, 0, 0)
        log = [
            {"timestamp": "2026-05-08 00:00:00", "correction_applied": True},
        ]
        in_cd, reason = is_in_cooldown(log, cooldown_days=7, now=now)
        self.assertTrue(in_cd)
        self.assertIn("cooldown_active", reason)

    def test_old_correction_no_cooldown(self):
        """오래된 correction이면 cooldown 비활성."""
        now = datetime(2026, 5, 20, 0, 0, 0)
        log = [
            {"timestamp": "2026-05-08 00:00:00", "correction_applied": True},
        ]
        in_cd, reason = is_in_cooldown(log, cooldown_days=7, now=now)
        self.assertFalse(in_cd)
        self.assertIsNone(reason)

    def test_apply_correction_with_cooldown(self):
        """cooldown 활성 시 correction skip."""
        now = datetime(2026, 5, 9, 0, 0, 0)
        log = [
            {"timestamp": "2026-05-08 00:00:00", "correction_applied": True},
        ]
        r = self._build_drift_result()
        result = apply_phase4_correction(r, audit_log=log, cooldown_days=7, now=now)
        self.assertFalse(result["correction_applied"])
        self.assertIn("cooldown", result["reason"])

    def test_apply_correction_without_audit_log(self):
        """audit_log=None이면 cooldown 체크 없이 기존 동작."""
        r = self._build_drift_result()
        result = apply_phase4_correction(r)
        self.assertTrue(result["correction_applied"])

    def test_invalid_timestamp_no_cooldown(self):
        """timestamp 파싱 실패 시 cooldown 비활성."""
        log = [
            {"timestamp": "invalid", "correction_applied": True},
        ]
        in_cd, reason = is_in_cooldown(log)
        self.assertFalse(in_cd)
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
