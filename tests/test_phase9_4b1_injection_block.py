import inspect
import shutil
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from jackal import hunter
from orca import jackal_memory_context as memory
from orca import state


class TestMemoryInjectionBlock(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
        ]
        for item in self.patches:
            item.start()
        state.init_state_db()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _context(self, stats_block: str = "성공률 72%, 평균 결과 +4.3%.") -> dict:
        return {
            "stats_block": stats_block,
            "sample_size": 558,
            "win_rate": 0.731,
            "avg_outcome": 4.3,
            "source": "candidate_lessons",
        }

    def _injection_rows(self):
        with state._connect_jackal() as conn:
            return conn.execute(
                "SELECT * FROM jackal_memory_injection_shadow ORDER BY timestamp, injection_id"
            ).fetchall()

    def test_compose_returns_block_with_context(self):
        block = memory.compose_memory_injection_block(self._context(), "analyst")

        self.assertIsNotNone(block)
        self.assertIn("[과거 학습 통계", block)
        self.assertIn("성공률 72%", block)
        self.assertIn("표본: 558건", block)

    def test_compose_returns_none_without_context(self):
        self.assertIsNone(memory.compose_memory_injection_block(None, "analyst"))
        self.assertIsNone(memory.compose_memory_injection_block({}, "devil"))

    def test_compose_role_analyst(self):
        block = memory.compose_memory_injection_block(self._context(), "analyst")

        self.assertIn("본인 평가 우선", block)
        self.assertNotIn("본인 반론 평가 우선", block)

    def test_compose_role_devil(self):
        block = memory.compose_memory_injection_block(self._context(), "devil")

        self.assertIn("본인 반론 평가 우선", block)

    def test_compose_under_1000_chars(self):
        block = memory.compose_memory_injection_block(self._context(), "analyst")

        self.assertLessEqual(len(block), memory.MAX_INJECTION_BLOCK_CHARS)
        self.assertLessEqual(len(block.splitlines()), 3)

    def test_compose_truncates_too_long(self):
        long_stats = " ".join(["긴통계"] * 800)
        block = memory.compose_memory_injection_block(self._context(long_stats), "devil")

        self.assertLessEqual(len(block), memory.MAX_INJECTION_BLOCK_CHARS)
        self.assertLessEqual(len(block.splitlines()), 3)
        self.assertIn("...", block)

    def test_record_injection_shadow_inserts_row(self):
        block = memory.compose_memory_injection_block(self._context(), "analyst")
        injection_id = memory.record_memory_injection_shadow(
            ticker="NVDA",
            role="analyst",
            injection_block=block,
            memory_context=self._context(),
            memory_mode="shadow",
            timestamp="2026-05-11T00:00:00Z",
        )
        row = self._injection_rows()[0]

        self.assertTrue(injection_id.startswith("injection_"))
        self.assertEqual(row["ticker"], "NVDA")
        self.assertEqual(row["role"], "analyst")
        self.assertEqual(row["injection_block"], block)
        self.assertEqual(row["injection_block_chars"], len(block))
        self.assertEqual(row["sample_size"], 558)
        self.assertEqual(row["source"], "candidate_lessons")

    def test_actual_prompt_unchanged(self):
        analyst_source = inspect.getsource(hunter._analyst_swing)
        devil_source = inspect.getsource(hunter._devil_swing)

        self.assertIn('user=market_psychology + "\\n\\n" + prompt', analyst_source)
        self.assertIn('user=market_psychology + "\\n\\n" + prompt', devil_source)
        self.assertNotIn("compose_memory_injection_block", analyst_source)
        self.assertNotIn("compose_memory_injection_block", devil_source)


if __name__ == "__main__":
    unittest.main()
