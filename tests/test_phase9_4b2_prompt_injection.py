import os
import shutil
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from jackal import hunter
from orca import jackal_memory_context as memory
from orca import state


class _CapturingLLMClient:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(text=self.text)


@contextmanager
def _memory_mode(value: str | None):
    old = os.environ.pop("JACKAL_MEMORY_PROMPT_MODE", None)
    if value is not None:
        os.environ["JACKAL_MEMORY_PROMPT_MODE"] = value
    try:
        yield
    finally:
        os.environ.pop("JACKAL_MEMORY_PROMPT_MODE", None)
        if old is not None:
            os.environ["JACKAL_MEMORY_PROMPT_MODE"] = old


def _context(stats_block: str = "learned stats win-rate 73%") -> dict:
    return {
        "stats_block": stats_block,
        "sample_size": 558,
        "win_rate": 0.731,
        "avg_outcome": 4.3,
        "source": "candidate_lessons",
    }


def _tech() -> dict:
    return {
        "price": 100.0,
        "rsi": 28,
        "bb_pos": 12.0,
        "vol_ratio": 1.8,
        "change_1d": 1.2,
        "change_3d": -2.0,
        "change_5d": -4.0,
        "ma50": 98.0,
        "bullish_div": True,
        "bullish_candle": False,
    }


def _aria() -> dict:
    return {
        "regime": "risk-on",
        "fear_greed": 67,
        "fear_greed_label": "Greed",
        "key_inflows": ["AI"],
        "key_outflows": [],
        "thesis_killers": [],
        "jackal_news": {},
        "all_headlines": [],
        "inflows_detail": [],
        "outflows_detail": [],
    }


def _analyst() -> dict:
    return {
        "analyst_score": 74,
        "day1_score": 72,
        "swing_score": 75,
        "swing_setup": "bounce",
        "swing_type": "technical_oversold",
        "bull_case": "oversold rebound",
        "signals_fired": ["rsi_oversold", "bb_touch"],
        "target_5d": "$108",
        "stop_loss": "$96",
    }


class TestPromptInjection(unittest.TestCase):
    def test_default_mode_shadow_prompt_unchanged(self):
        fake = _CapturingLLMClient('{"analyst_score": 71, "day1_score": 68, "swing_score": 73}')
        with _memory_mode(None), patch.object(hunter, "_llm_client", fake), patch.object(
            hunter._memory_context, "shadow_memory_context", return_value=_context()
        ):
            hunter._analyst_swing("NVDA", "NVIDIA", _tech(), "reason", _aria(), "$")

        prompt = fake.calls[0]["user"]
        self.assertNotIn("learned stats win-rate", prompt)

    def test_off_mode_prompt_unchanged(self):
        with _memory_mode(memory.MEMORY_MODE_OFF):
            content = memory.compose_prompt_user_content("NVDA", _aria(), "analyst", "market", "prompt")

        self.assertEqual(content, "market\n\nprompt")

    def test_on_mode_injects_block(self):
        fake = _CapturingLLMClient('{"analyst_score": 71, "day1_score": 68, "swing_score": 73}')
        with _memory_mode(memory.MEMORY_MODE_ON), patch.object(hunter, "_llm_client", fake), patch.object(
            hunter._memory_context, "shadow_memory_context", return_value=_context()
        ):
            hunter._analyst_swing("NVDA", "NVIDIA", _tech(), "reason", _aria(), "$")

        prompt = fake.calls[0]["user"]
        self.assertIn("learned stats win-rate 73%", prompt)
        self.assertIn("candidate_lessons", prompt)

    def test_on_mode_skips_when_no_memory(self):
        with _memory_mode(memory.MEMORY_MODE_ON), patch.object(memory, "shadow_memory_context", return_value=None):
            content = memory.compose_prompt_user_content("NVDA", _aria(), "analyst", "market", "prompt")

        self.assertEqual(content, "market\n\nprompt")

    def test_on_mode_injection_under_1000_chars(self):
        block = memory.compose_memory_injection_block(_context(), "analyst")

        self.assertIsNotNone(block)
        self.assertLessEqual(len(block), memory.MAX_INJECTION_BLOCK_CHARS)

    def test_on_mode_logs_to_shadow_db(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            with patch.object(state, "STATE_DB_FILE", tmpdir / "orca_state.db"), patch.object(
                state, "JACKAL_DB_FILE", tmpdir / "jackal_state.db"
            ), patch.dict(os.environ, {"JACKAL_MEMORY_SHADOW_LOG": str(tmpdir / "memory.log")}):
                state.init_state_db()
                memory.log_shadow_memory_context(
                    "NVDA", _aria(), "analyst", _context(), mode=memory.MEMORY_MODE_ON
                )
                with state._connect_jackal() as conn:
                    rows = conn.execute("SELECT memory_mode, source FROM jackal_memory_injection_shadow").fetchall()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["memory_mode"], memory.MEMORY_MODE_ON)
            self.assertEqual(rows[0]["source"], "candidate_lessons")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_devil_and_analyst_independent(self):
        def fake_shadow(ticker, aria, role):
            return _context(f"{role} learned stats")

        with _memory_mode(memory.MEMORY_MODE_ON), patch.object(memory, "shadow_memory_context", side_effect=fake_shadow):
            analyst = memory.compose_prompt_user_content("NVDA", _aria(), "analyst", "market", "prompt")
            devil = memory.compose_prompt_user_content("NVDA", _aria(), "devil", "market", "prompt")

        self.assertIn("analyst learned stats", analyst)
        self.assertIn("devil learned stats", devil)
        self.assertNotEqual(analyst, devil)

    def test_max_tokens_not_exceeded(self):
        fake = _CapturingLLMClient(
            '{"devil_score": 30, "verdict": "partial", "main_risk": "", '
            '"thesis_killer_hit": false, "is_dead_cat": false, '
            '"structural_decline": false, "volume_concern": "normal"}'
        )
        with _memory_mode(memory.MEMORY_MODE_ON), patch.object(hunter, "_llm_client", fake), patch.object(
            hunter._memory_context, "shadow_memory_context", return_value=_context()
        ):
            hunter._devil_swing("NVDA", _tech(), _analyst(), _aria(), "$")

        self.assertEqual(fake.calls[0]["max_tokens"], 1500)
        self.assertLessEqual(len(memory.compose_memory_injection_block(_context(), "devil")), 1000)


if __name__ == "__main__":
    unittest.main()
