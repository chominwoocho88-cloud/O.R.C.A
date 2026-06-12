"""D — Evolution 스킬 소비 회로: 내용이 프롬프트에 실제로 도달 (2026-06-12)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import hunter


class SkillsHintTestCase(unittest.TestCase):
    def _skills_dir(self, tmp: Path, count=1):
        d = tmp / "skills"
        d.mkdir()
        for i in range(count):
            (d / f"skill_{i}.json").write_text(json.dumps({
                "name": f"skill_{i}",
                "trigger": f"rsi_oversold fires with sample >= {i+5}",
                "action": f"increase confidence by +0.1{i}",
            }), encoding="utf-8")
        return tmp

    def test_skill_content_reaches_hint(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            base = self._skills_dir(Path(tmp_str))
            with patch.object(hunter, "_BASE", base):
                hint = hunter._skills_hint()

        self.assertIn("학습된 스킬", hint)
        self.assertIn("rsi_oversold fires", hint)
        self.assertIn("→ increase confidence", hint)

    def test_capped_at_five_latest(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            base = self._skills_dir(Path(tmp_str), count=9)
            with patch.object(hunter, "_BASE", base):
                hint = hunter._skills_hint()

        self.assertEqual(hint.count("→"), 5)
        self.assertIn("sample >= 13", hint)  # 최신(skill_8) 내용 포함

    def test_missing_dir_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp_str:
            with patch.object(hunter, "_BASE", Path(tmp_str)):
                self.assertEqual(hunter._skills_hint(), "")


if __name__ == "__main__":
    unittest.main()
