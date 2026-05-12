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
        "change_3d": -2.0,
        "change_5d": -4.0,
        "ma50": 98.0,
        "bullish_div": True,
        "bullish_candle": False,
    }


def _aria(regime: str, fear_greed, label: str) -> dict:
    return {
        "regime": regime,
        "fear_greed": fear_greed,
        "fear_greed_label": label,
        "key_inflows": ["반도체/AI"],
        "key_outflows": ["방어주"],
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
        "swing_setup": "반등가능",
        "swing_type": "기술적과매도",
        "bull_case": "과매도 반등",
        "signals_fired": ["rsi_oversold", "bb_touch"],
        "target_5d": "$108",
        "stop_loss": "$96",
    }


class Phase8h15PromptRegimeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.patches = [
            patch("orca.state.STATE_DB_FILE", self.tmpdir / "orca_state.db"),
            patch("orca.state.JACKAL_DB_FILE", self.tmpdir / "jackal_state.db"),
            patch(
                "orca.contract_shadow_audit.CONTRACT_SHADOW_AUDIT_LOG",
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

    def test_market_psychology_context_differs_between_greed_and_fear(self):
        from jackal import hunter

        greed = hunter._format_market_psychology_context(
            _aria("위험선호", "80", "Extreme Greed"),
            role="analyst",
        )
        fear = hunter._format_market_psychology_context(
            _aria("위험회피", "30", "Fear"),
            role="devil",
        )

        self.assertIn("시장 바이어스: risk_on_greed", greed)
        self.assertIn("Analyst 지침", greed)
        self.assertIn("시장 바이어스: risk_off_fear", fear)
        self.assertIn("Devil 지침", fear)
        self.assertIn("악마의 변호인 본질은 유지", fear)
        self.assertNotEqual(greed, fear)

    def test_analyst_prompt_includes_orca_regime_and_fear_greed(self):
        from jackal import hunter

        fake = _CapturingLLMClient(
            '{"analyst_score": 71, "day1_score": 68, "swing_score": 73}'
        )
        with patch.object(hunter, "_llm_client", fake):
            hunter._analyst_swing(
                "NVDA",
                "엔비디아",
                _tech(),
                "RSI oversold",
                _aria("위험선호", "80", "Extreme Greed"),
                "$",
            )

        prompt = fake.calls[0]["user"]
        self.assertIn("ORCA 레짐: 위험선호", prompt)
        self.assertIn("Fear & Greed: 80 (Extreme Greed)", prompt)
        self.assertIn("시장 바이어스: risk_on_greed", prompt)
        self.assertIn("Analyst 지침", prompt)

    def test_devil_prompt_includes_regime_fear_greed_and_preserves_role(self):
        from jackal import hunter

        fake = _CapturingLLMClient(
            '{"devil_score": 64, "verdict": "부분동의", '
            '"main_risk": "시장 공포가 반등 실패를 키울 수 있음", '
            '"thesis_killer_hit": false, "is_dead_cat": false, '
            '"structural_decline": false, "volume_concern": "정상"}'
        )
        with patch.object(hunter, "_llm_client", fake):
            hunter._devil_swing(
                "NVDA",
                _tech(),
                _analyst(),
                _aria("위험회피", "30", "Fear"),
                "$",
            )

        prompt = fake.calls[0]["user"]
        self.assertIn("ORCA 레짐: 위험회피", prompt)
        self.assertIn("Fear & Greed: 30 (Fear)", prompt)
        self.assertIn("시장 바이어스: risk_off_fear", prompt)
        self.assertIn("Devil 지침", prompt)
        self.assertIn("악마의 변호인 본질은 유지", prompt)
        self.assertIn("강한 반대", prompt)


if __name__ == "__main__":
    unittest.main()
