"""ORCA agent output contract tests."""

import unittest

from pydantic import ValidationError

from shared.contracts import (
    ContractModel,
    OrcaAnalystOutput,
    OrcaCounterargument,
    OrcaHunterOutput,
    OrcaInflow,
    OrcaOutflow,
    OrcaReporterOutput,
    OrcaThesisKiller,
    OrcaTopHeadline,
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
            top_headlines=[{"headline": "AI capex stays strong", "impact": "높음"}],
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
        self.assertEqual(output.inflows[0].zone, "semiconductors")
        self.assertEqual(output.thesis_killers[0].quality, "ok")
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
        first.thesis_killers.append(OrcaThesisKiller(event="CPI surprise"))

        self.assertEqual(second.trend_strategy, {})
        self.assertEqual(second.thesis_killers, [])

    def test_thesis_killers_accept_nested_payloads(self):
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

        self.assertIsInstance(output.thesis_killers[0], OrcaThesisKiller)
        self.assertEqual(output.thesis_killers[0].event, "Yield spike")
        self.assertFalse(hasattr(output.thesis_killers[0], "extra_nested"))

    def test_thesis_killers_reject_invalid_quality(self):
        with self.assertRaises(ValidationError):
            OrcaReporterOutput(
                one_line_summary="Summary.",
                market_regime="neutral",
                confidence_overall="medium",
                thesis_killers=[
                    {
                        "event": "Yield spike",
                        "quality": "invalid_value",
                    }
                ],
            )

    def test_structured_lists_accept_nested_payloads(self):
        output = OrcaReporterOutput(
            one_line_summary="Summary.",
            market_regime="neutral",
            confidence_overall="medium",
            top_headlines=[
                {
                    "headline": "TSMC earnings beat",
                    "signal_tag": "반도체 강세",
                    "impact": "높음",
                }
            ],
            outflows=[
                {
                    "zone": "long bonds",
                    "reason": "yields rising",
                    "severity": "보통~높음",
                    "data_point": "10Y 4.7%",
                }
            ],
            inflows=[
                {
                    "zone": "semiconductors",
                    "reason": "AI demand",
                    "momentum": "강함(단기 과열 주의)",
                    "data_point": "SOX +2%",
                }
            ],
            counterarguments=[
                {
                    "against": "risk-on continuation",
                    "because": "positioning crowded",
                    "risk_level": "보통",
                }
            ],
        )

        self.assertIsInstance(output.top_headlines[0], OrcaTopHeadline)
        self.assertIsInstance(output.outflows[0], OrcaOutflow)
        self.assertIsInstance(output.inflows[0], OrcaInflow)
        self.assertIsInstance(output.counterarguments[0], OrcaCounterargument)
        self.assertEqual(output.top_headlines[0].impact, "높음")
        self.assertEqual(output.outflows[0].severity, "보통~높음")
        self.assertEqual(output.inflows[0].momentum, "강함(단기 과열 주의)")
        self.assertEqual(output.counterarguments[0].risk_level, "보통")

    def test_structured_lists_reject_invalid_literals(self):
        with self.assertRaises(ValidationError):
            OrcaReporterOutput(
                one_line_summary="Summary.",
                market_regime="neutral",
                confidence_overall="medium",
                top_headlines=[{"headline": "TSMC earnings beat", "impact": "critical"}],
            )

        with self.assertRaises(ValidationError):
            OrcaReporterOutput(
                one_line_summary="Summary.",
                market_regime="neutral",
                confidence_overall="medium",
                counterarguments=[{"against": "risk-on", "risk_level": "critical"}],
            )

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


class OrcaThesisKillerTests(unittest.TestCase):
    def test_happy_path(self):
        thesis_killer = OrcaThesisKiller(
            event="Nasdaq",
            timeframe="next close",
            confirms_if="Nasdaq closes above 26500",
            invalidates_if="Nasdaq closes below 25900",
            quality="ok",
        )

        self.assertEqual(thesis_killer.event, "Nasdaq")
        self.assertEqual(thesis_killer.timeframe, "next close")
        self.assertEqual(thesis_killer.confirms_if, "Nasdaq closes above 26500")
        self.assertEqual(thesis_killer.invalidates_if, "Nasdaq closes below 25900")
        self.assertEqual(thesis_killer.quality, "ok")

    def test_minimal_requires_only_event(self):
        thesis_killer = OrcaThesisKiller(event="KOSPI")

        self.assertEqual(thesis_killer.event, "KOSPI")
        self.assertIsNone(thesis_killer.timeframe)
        self.assertIsNone(thesis_killer.confirms_if)
        self.assertIsNone(thesis_killer.invalidates_if)
        self.assertIsNone(thesis_killer.quality)

    def test_missing_event_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaThesisKiller()

    def test_quality_literals(self):
        self.assertEqual(OrcaThesisKiller(event="Nasdaq", quality="ok").quality, "ok")
        self.assertEqual(
            OrcaThesisKiller(event="Nasdaq", quality="vague").quality,
            "vague",
        )
        self.assertIsNone(OrcaThesisKiller(event="Nasdaq", quality=None).quality)

        with self.assertRaises(ValidationError):
            OrcaThesisKiller(event="Nasdaq", quality="invalid_value")

    def test_extra_fields_ignored(self):
        thesis_killer = OrcaThesisKiller(event="Nasdaq", extra_field="ignored")

        self.assertFalse(hasattr(thesis_killer, "extra_field"))

    def test_strips_whitespace(self):
        thesis_killer = OrcaThesisKiller(
            event="  Nasdaq  ",
            timeframe="  next close  ",
        )

        self.assertEqual(thesis_killer.event, "Nasdaq")
        self.assertEqual(thesis_killer.timeframe, "next close")

    def test_inherits_contract_model(self):
        self.assertIsInstance(OrcaThesisKiller(event="Nasdaq"), ContractModel)


class OrcaTopHeadlineTests(unittest.TestCase):
    def test_happy_path(self):
        headline = OrcaTopHeadline(
            headline="TSMC earnings beat",
            signal_tag="반도체 강세",
            impact="높음",
        )

        self.assertEqual(headline.headline, "TSMC earnings beat")
        self.assertEqual(headline.signal_tag, "반도체 강세")
        self.assertEqual(headline.impact, "높음")

    def test_minimal_requires_only_headline(self):
        headline = OrcaTopHeadline(headline="TSMC earnings beat")

        self.assertEqual(headline.headline, "TSMC earnings beat")
        self.assertIsNone(headline.signal_tag)
        self.assertIsNone(headline.impact)

    def test_missing_headline_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaTopHeadline()

    def test_impact_literals(self):
        for impact in ("높음", "보통", "낮음", None):
            self.assertEqual(
                OrcaTopHeadline(headline="TSMC earnings beat", impact=impact).impact,
                impact,
            )

        with self.assertRaises(ValidationError):
            OrcaTopHeadline(headline="TSMC earnings beat", impact="critical")

    def test_signal_tag_is_free_text(self):
        headline = OrcaTopHeadline(
            headline="TSMC earnings beat",
            signal_tag="🔴 위험신호 / BULLISH",
        )

        self.assertEqual(headline.signal_tag, "🔴 위험신호 / BULLISH")

    def test_extra_fields_ignored_and_whitespace_stripped(self):
        headline = OrcaTopHeadline(
            headline="  TSMC earnings beat  ",
            signal_tag="  반도체 강세  ",
            extra_field="ignored",
        )

        self.assertEqual(headline.headline, "TSMC earnings beat")
        self.assertEqual(headline.signal_tag, "반도체 강세")
        self.assertFalse(hasattr(headline, "extra_field"))


class OrcaOutflowTests(unittest.TestCase):
    def test_happy_path(self):
        outflow = OrcaOutflow(
            zone="long bonds",
            reason="yields rising",
            severity="보통~높음",
            data_point="10Y 4.7%",
        )

        self.assertEqual(outflow.zone, "long bonds")
        self.assertEqual(outflow.reason, "yields rising")
        self.assertEqual(outflow.severity, "보통~높음")
        self.assertEqual(outflow.data_point, "10Y 4.7%")

    def test_minimal_requires_only_zone(self):
        outflow = OrcaOutflow(zone="long bonds")

        self.assertEqual(outflow.zone, "long bonds")
        self.assertIsNone(outflow.reason)
        self.assertIsNone(outflow.severity)
        self.assertIsNone(outflow.data_point)

    def test_missing_zone_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaOutflow()

    def test_severity_is_free_text(self):
        self.assertEqual(OrcaOutflow(zone="bonds", severity="보통~높음").severity, "보통~높음")

    def test_extra_fields_ignored_and_whitespace_stripped(self):
        outflow = OrcaOutflow(zone="  bonds  ", extra_field="ignored")

        self.assertEqual(outflow.zone, "bonds")
        self.assertFalse(hasattr(outflow, "extra_field"))


class OrcaInflowTests(unittest.TestCase):
    def test_happy_path(self):
        inflow = OrcaInflow(
            zone="semiconductors",
            reason="AI demand",
            momentum="강함(단기 과열 주의)",
            data_point="SOX +2%",
        )

        self.assertEqual(inflow.zone, "semiconductors")
        self.assertEqual(inflow.reason, "AI demand")
        self.assertEqual(inflow.momentum, "강함(단기 과열 주의)")
        self.assertEqual(inflow.data_point, "SOX +2%")

    def test_minimal_requires_only_zone(self):
        inflow = OrcaInflow(zone="semiconductors")

        self.assertEqual(inflow.zone, "semiconductors")
        self.assertIsNone(inflow.reason)
        self.assertIsNone(inflow.momentum)
        self.assertIsNone(inflow.data_point)

    def test_missing_zone_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaInflow()

    def test_momentum_is_free_text(self):
        self.assertEqual(
            OrcaInflow(zone="semiconductors", momentum="중립→상승 전환 대기").momentum,
            "중립→상승 전환 대기",
        )

    def test_extra_fields_ignored_and_whitespace_stripped(self):
        inflow = OrcaInflow(zone="  semiconductors  ", extra_field="ignored")

        self.assertEqual(inflow.zone, "semiconductors")
        self.assertFalse(hasattr(inflow, "extra_field"))


class OrcaCounterargumentTests(unittest.TestCase):
    def test_happy_path(self):
        counterargument = OrcaCounterargument(
            against="risk-on continuation",
            because="positioning crowded",
            risk_level="높음",
        )

        self.assertEqual(counterargument.against, "risk-on continuation")
        self.assertEqual(counterargument.because, "positioning crowded")
        self.assertEqual(counterargument.risk_level, "높음")

    def test_minimal_requires_only_against(self):
        counterargument = OrcaCounterargument(against="risk-on continuation")

        self.assertEqual(counterargument.against, "risk-on continuation")
        self.assertIsNone(counterargument.because)
        self.assertIsNone(counterargument.risk_level)

    def test_missing_against_rejected(self):
        with self.assertRaises(ValidationError):
            OrcaCounterargument()

    def test_risk_level_literals(self):
        for risk_level in ("높음", "보통", "낮음", None):
            self.assertEqual(
                OrcaCounterargument(
                    against="risk-on continuation",
                    risk_level=risk_level,
                ).risk_level,
                risk_level,
            )

        with self.assertRaises(ValidationError):
            OrcaCounterargument(against="risk-on continuation", risk_level="critical")

    def test_extra_fields_ignored_and_whitespace_stripped(self):
        counterargument = OrcaCounterargument(
            against="  risk-on continuation  ",
            because="  crowded positioning  ",
            extra_field="ignored",
        )

        self.assertEqual(counterargument.against, "risk-on continuation")
        self.assertEqual(counterargument.because, "crowded positioning")
        self.assertFalse(hasattr(counterargument, "extra_field"))


if __name__ == "__main__":
    unittest.main()
