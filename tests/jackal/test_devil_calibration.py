"""Devil 자기 보정 환류 — 판정별 성적이 본인 프롬프트로 (2026-06-12)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import hunter


def _weights_file(tmp: Path, dev_acc: dict) -> Path:
    path = tmp / "jackal_weights.json"
    path.write_text(json.dumps({"devil_accuracy": dev_acc}), encoding="utf-8")
    return path


class DevilCalibrationHintTestCase(unittest.TestCase):
    def test_hint_shows_verdict_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            path = _weights_file(Path(tmp_str), {
                "반대": {"correct": 7, "total": 17},
                "부분동의": {"correct": 30, "total": 52},
            })
            with patch.object(hunter, "JACKAL_WEIGHTS_FILE", path):
                hint = hunter._devil_calibration_hint()

        self.assertIn("반대 적중 41% (n=17)", hint)
        self.assertIn("부분동의 적중 58% (n=52)", hint)
        self.assertIn("과차단", hint)

    def test_small_samples_are_hidden(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            path = _weights_file(Path(tmp_str), {"반대": {"correct": 2, "total": 3}})
            with patch.object(hunter, "JACKAL_WEIGHTS_FILE", path):
                self.assertEqual(hunter._devil_calibration_hint(), "")

    def test_missing_file_is_silent(self):
        with patch.object(hunter, "JACKAL_WEIGHTS_FILE", Path("/no/such/file.json")):
            self.assertEqual(hunter._devil_calibration_hint(), "")


if __name__ == "__main__":
    unittest.main()
