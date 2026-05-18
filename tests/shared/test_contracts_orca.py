"""ORCA agent output contract tests."""

import unittest

from pydantic import ValidationError

from shared.contracts import (
    ContractModel,
    OrcaAnalystOutput,
    OrcaHunterOutput,
    OrcaReporterOutput,
)


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


class OrcaReporterOutputTests(unittest.TestCase):
    def test_happy_path(self):
        output = OrcaReporterOutput(
            analysis_date="2026-05-18",
            analysis_time="07:00 KST",
            mode="MORNING",
            mode_label="Morning Brief",
            one_line_summary="ORCA sees mixed risk-on conditions.",
            market_regime="mixed risk-on",
            trend_phase="early uptrend",
            confidence_overall="medium",
            consensus_level="partial",
            trend_strategy={"recommended": "selective entries", "difficulty": "medium"},
            volatility_index={"vix": "18.4", "level": "neutral"},
            retail_reversal_signal={"reliability": "medium"},
            korea_focus={"assessment": "watch exporters"},
            agent_consensus={"hunter": "risk-on", "devil": "cautious"},
            meta_improvement={"prompt": "cleaner"},
            top_headlines=[{"headline": "AI capex stays strong", "impact": "positive"}],
            outflows=[{"zone": "long bonds", "severity": "medium"}],
            inflows=[{"zone": "semiconductors", "momentum": "strong"}],
            neutral_waiting=[{"zone": "cash", "catalyst_needed": "CPI"}],
            hidden_signals=[{"signal": "breadth divergence"}],
            counterarguments=[{"against": "risk-on", "because": "yields rising"}],
            thesis_killers=[
                {
                    "event": "NVDA guidance miss",
                    "timeframe": "24h",
                    "confirms_if": "SOX -2%",
                    "invalidates_if": "SOX +1%",
                    "quality": "ok",
                }
            ],
            tail_risks=[{"risk": "liquidity shock"}],
            tomorrow_setup=[{"focus": "KOSPI open"}],
            actionable_watch=[{"ticker": "NVDA", "reason": "capex readthrough"}],
        )

        self.assertEqual(output.one_line_summary, "ORCA sees mixed risk-on conditions.")
        self.assertEqual(output.market_regime, "mixed risk-on")
        self.assertEqual(output.confidence_overall, "medium")
        self.assertEqual(output.trend_strategy["recommended"], "selective entries")
        self.assertEqual(output.inflows[0]["zone"], "semiconductors")
        self.assertEqual(output.thesis_killers[0]["quality"], "ok")
        self.assertEqual(output.actionable_watch[0]["ticker"], "NVDA")

    def test_minimal_requires_three_core_fields(self):
        output = OrcaReporterOutput(
            one_line_summary="Short summary.",
            market_regime="neutral",
            confidence_overall="low",
        )

        self.assertIsNone(output.analysis_date)
        self.assertIsNone(output.analysis_time)
        self.assertIsNone(output.mode)
        self.assertIsNone(output.mode_label)
        self.assertIsNone(output.trend_phase)
        self.assertIsNone(output.consensus_level)
        self.assertEqual(output.trend_strategy, {})
        self.assertEqual(output.volatility_index, {})
        self.assertEqual(output.retail_reversal_signal, {})
        self.assertEqual(output.korea_focus, {})
        self.assertEqual(output.agent_consensus, {})
        self.assertEqual(output.meta_improvement, {})
        self.assertEqual(output.top_headlines, [])
        self.assertEqual(output.outflows, [])
        self.assertEqual(output.inflows, [])
        self.assertEqual(output.neutral_waiting, [])
        self.assertEqual(output.hidden_signals, [])
        self.assertEqual(output.counterarguments, [])
        self.assertEqual(output.thesis_killers, [])
        self.assertEqual(output.tail_risks, [])
        self.assertEqual(output.tomorrow_setup, [])
        self.assertEqual(output.actionable_watch, [])

    def test_missing_one_line_summary_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaReporterOutput(
                market_regime="neutral",
                confidence_overall="low",
            )

    def test_missing_market_regime_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaReporterOutput(
                one_line_summary="Short summary.",
                confidence_overall="low",
            )

    def test_missing_confidence_overall_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaReporterOutput(
                one_line_summary="Short summary.",
                market_regime="neutral",
            )

    def test_dict_and_list_defaults_are_independent(self):
        first = OrcaReporterOutput(
            one_line_summary="First.",
            market_regime="neutral",
            confidence_overall="low",
        )
        second = OrcaReporterOutput(
            one_line_summary="Second.",
            market_regime="neutral",
            confidence_overall="low",
        )

        first.trend_strategy["recommended"] = "wait"
        first.thesis_killers.append({"event": "CPI surprise"})

        self.assertEqual(second.trend_strategy, {})
        self.assertEqual(second.thesis_killers, [])

    def test_thesis_killers_accept_loose_nested_payloads(self):
        output = OrcaReporterOutput(
            one_line_summary="Summary.",
            market_regime="neutral",
            confidence_overall="medium",
            thesis_killers=[
                {
                    "event": "Yield spike",
                    "confirms_if": "10Y > 4.7%",
                    "invalidates_if": "10Y < 4.4%",
                    "quality": "ok",
                    "extra_nested": {"kept": True},
                }
            ],
        )

        self.assertTrue(output.thesis_killers[0]["extra_nested"]["kept"])

    def test_korean_free_text_accepted(self):
        output = OrcaReporterOutput(
            one_line_summary="\ud63c\uc870\uc138\ub97c \uc720\uc9c0\ud558\ub294 \uc7a5\uc138.",
            market_regime="\ud63c\uc870 (\uc704\ud5d8\uc120\ud638 \ud45c\uba74)",
            confidence_overall="\ubcf4\ud1b5",
        )

        self.assertEqual(output.confidence_overall, "\ubcf4\ud1b5")

    def test_extra_fields_ignored(self):
        output = OrcaReporterOutput(
            one_line_summary="Summary.",
            market_regime="neutral",
            confidence_overall="medium",
            extra_field="ignored",
        )

        self.assertFalse(hasattr(output, "extra_field"))

    def test_inherits_contract_model(self):
        output = OrcaReporterOutput(
            one_line_summary="Summary.",
            market_regime="neutral",
            confidence_overall="medium",
        )

        self.assertIsInstance(output, ContractModel)


if __name__ == "__main__":
    unittest.main()
