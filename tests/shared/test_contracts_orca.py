"""ORCA agent output contract tests."""

import unittest

from pydantic import ValidationError

from shared.contracts import ContractModel, OrcaAnalystOutput, OrcaHunterOutput


class OrcaHunterOutputTests(unittest.TestCase):
    def test_happy_path(self):
        output = OrcaHunterOutput(
            collected_at="2026-05-18 07:00 KST",
            mode="MORNING",
            raw_signals=[
                {
                    "category": "macro",
                    "headline": "Fed signal",
                    "data_point": "10Y 4.5%",
                    "source_hint": "Reuters",
                }
            ],
            market_snapshot={"sp500": "+0.5%", "vix": "18.4"},
            total_signals=1,
        )

        self.assertEqual(output.collected_at, "2026-05-18 07:00 KST")
        self.assertEqual(output.mode, "MORNING")
        self.assertEqual(output.raw_signals[0]["category"], "macro")
        self.assertEqual(output.market_snapshot["vix"], "18.4")
        self.assertEqual(output.total_signals, 1)

    def test_minimal_requires_only_mode(self):
        output = OrcaHunterOutput(mode="EVENING")

        self.assertIsNone(output.collected_at)
        self.assertEqual(output.mode, "EVENING")
        self.assertEqual(output.raw_signals, [])
        self.assertEqual(output.market_snapshot, {})
        self.assertIsNone(output.total_signals)

    def test_missing_mode_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaHunterOutput()

    def test_total_signals_range(self):
        OrcaHunterOutput(mode="MORNING", total_signals=0)

        with self.assertRaises(ValidationError):
            OrcaHunterOutput(mode="MORNING", total_signals=-1)

    def test_extra_fields_ignored(self):
        output = OrcaHunterOutput(mode="MORNING", extra_field="ignored")

        self.assertFalse(hasattr(output, "extra_field"))

    def test_inherits_contract_model(self):
        self.assertIsInstance(OrcaHunterOutput(mode="MORNING"), ContractModel)


class OrcaAnalystOutputTests(unittest.TestCase):
    def test_happy_path(self):
        output = OrcaAnalystOutput(
            market_regime="혼조 (위험선호 표면)",
            trend_phase="상승추세",
            analyst_confidence="보통",
            trend_strategy={"recommended": "hold", "difficulty": "어려움"},
            regime_reason="mixed flows",
            volatility_index={"vix": "18.4"},
            retail_reversal_signal={"reliability": "보통"},
            outflows=[{"zone": "KOSPI", "severity": "높음"}],
            inflows=[{"zone": "AI", "momentum": "강함"}],
            neutral_waiting=[{"zone": "cash", "catalyst_needed": "confirm"}],
            hidden_signals=[{"signal": "flow divergence"}],
            korea_focus={"krw_usd": "1490"},
        )

        self.assertEqual(output.market_regime, "혼조 (위험선호 표면)")
        self.assertEqual(output.trend_phase, "상승추세")
        self.assertEqual(output.analyst_confidence, "보통")
        self.assertEqual(output.trend_strategy["difficulty"], "어려움")
        self.assertEqual(output.outflows[0]["zone"], "KOSPI")
        self.assertEqual(output.inflows[0]["momentum"], "강함")
        self.assertEqual(output.korea_focus["krw_usd"], "1490")

    def test_minimal_requires_regime_and_trend(self):
        output = OrcaAnalystOutput(
            market_regime="혼조",
            trend_phase="횡보추세",
        )

        self.assertIsNone(output.analyst_confidence)
        self.assertEqual(output.trend_strategy, {})
        self.assertIsNone(output.regime_reason)
        self.assertEqual(output.volatility_index, {})
        self.assertEqual(output.retail_reversal_signal, {})
        self.assertEqual(output.outflows, [])
        self.assertEqual(output.inflows, [])
        self.assertEqual(output.neutral_waiting, [])
        self.assertEqual(output.hidden_signals, [])
        self.assertEqual(output.korea_focus, {})

    def test_missing_market_regime_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaAnalystOutput(trend_phase="횡보추세")

    def test_missing_trend_phase_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaAnalystOutput(market_regime="혼조")

    def test_list_and_dict_fields_accept_loose_nested_payloads(self):
        output = OrcaAnalystOutput(
            market_regime="위험선호 표면 / 내부 균열 심화",
            trend_phase="하락추세",
            outflows=[{"zone": "energy", "extra": {"nested": True}}],
            korea_focus={"assessment": "수급 공백"},
        )

        self.assertTrue(output.outflows[0]["extra"]["nested"])
        self.assertEqual(output.korea_focus["assessment"], "수급 공백")

    def test_extra_fields_ignored(self):
        output = OrcaAnalystOutput(
            market_regime="혼조",
            trend_phase="상승추세",
            extra_field="ignored",
        )

        self.assertFalse(hasattr(output, "extra_field"))

    def test_inherits_contract_model(self):
        output = OrcaAnalystOutput(market_regime="혼조", trend_phase="횡보추세")

        self.assertIsInstance(output, ContractModel)


if __name__ == "__main__":
    unittest.main()
