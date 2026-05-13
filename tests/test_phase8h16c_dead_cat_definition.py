"""Phase 8h-1.6c tests: strict Devil blocking flag definitions."""

import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class _CapturingLLMClient:
    def __init__(self, text: str):
        self.text = text
        self.calls = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(text=self.text)


def _tech() -> dict:
    return {
        "price": 100.0,
        "rsi": 28,
        "bb_pos": 12.0,
        "vol_ratio": 1.8,
        "change_1d": 1.2,
        "change_5d": -4.0,
    }


def _analyst() -> dict:
    return {
        "analyst_score": 74,
        "day1_score": 72,
        "swing_score": 75,
        "swing_setup": "반등가능",
        "swing_type": "기술적과매도",
        "bull_case": "RSI 과매도 + BB 하단 + 섹터 유입",
        "signals_fired": ["rsi_oversold", "bb_touch"],
        "target_5d": "$108",
        "stop_loss": "$96",
    }


def _aria() -> dict:
    return {
        "regime": "위험선호",
        "fear_greed": 67,
        "fear_greed_label": "Greed",
        "key_inflows": ["반도체/AI"],
        "key_outflows": ["방어주"],
        "thesis_killers": [],
        "jackal_news": {},
        "all_headlines": [],
        "inflows_detail": [],
        "outflows_detail": [],
    }


def _capture_devil_prompt() -> str:
    from apps.jackal import hunter

    fake = _CapturingLLMClient(
        '{"devil_score": 38, "verdict": "부분동의", "main_risk": "", '
        '"thesis_killer_hit": false, "is_dead_cat": false, '
        '"structural_decline": false, "volume_concern": "정상"}'
    )
    with patch.object(hunter, "_llm_client", fake):
        hunter._devil_swing("NVDA", _tech(), _analyst(), _aria(), "$")
    return fake.calls[0]["user"]


class Phase8h16cDeadCatDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.patches = [
            patch("apps.orca.state.STATE_DB_FILE", self.tmpdir / "orca_state.db"),
            patch("apps.orca.state.JACKAL_DB_FILE", self.tmpdir / "jackal_state.db"),
            patch(
                "shared.audit.contract_shadow_audit.CONTRACT_SHADOW_AUDIT_LOG",
                self.tmpdir / "contract_shadow_audit.log",
            ),
            patch.dict(os.environ, {"JACKAL_MEMORY_SHADOW_LOG": str(self.tmpdir / "memory_context_shadow.log")}),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_prompt_includes_dead_cat_strict_definition(self):
        prompt = _capture_devil_prompt()

        self.assertIn("is_dead_cat", prompt)
        self.assertIn("구조적 하락 추세", prompt)
        self.assertIn("약한 반등 신호", prompt)
        self.assertIn("재하락 가능성", prompt)
        self.assertIn("단순 RSI 과매도", prompt)

    def test_prompt_includes_thesis_killer_strict_definition(self):
        prompt = _capture_devil_prompt()

        self.assertIn("thesis_killer_hit", prompt)
        self.assertIn("핵심 매수 thesis", prompt)
        self.assertIn("진짜 깨졌을 때만 true", prompt)
        self.assertIn("thesis 무효화 증거", prompt)

    def test_devil_essence_preserved(self):
        prompt = _capture_devil_prompt()

        self.assertIn("반드시 반박", prompt)
        self.assertIn("회의적", prompt)
        self.assertIn("devil_score/main_risk로 표현", prompt)

    def test_market_environment_still_included(self):
        prompt = _capture_devil_prompt()

        self.assertIn("ORCA 레짐: 위험선호", prompt)
        self.assertIn("Fear & Greed: 67 (Greed)", prompt)
        self.assertIn("시장 바이어스: risk_on_greed", prompt)


if __name__ == "__main__":
    unittest.main()
