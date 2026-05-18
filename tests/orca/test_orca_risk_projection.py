"""ORCA RiskDecision projection tests."""

import unittest

from apps.orca.risk_projection import project_orca_devil_to_risk_decision
from shared.contracts import RiskDecision


class OrcaRiskProjectionTests(unittest.TestCase):
    def test_happy_path_maps_orca_devil_fields(self):
        payload = project_orca_devil_to_risk_decision(
            ticker=None,
            analyst={"analyst_confidence": "high"},
            devil={
                "verdict": "partial",
                "counterarguments": [{"against": "crowded AI trade", "risk_level": "high"}],
                "thesis_killers": [
                    {
                        "event": "NASDAQ",
                        "timeframe": "close",
                        "confirms_if": "NASDAQ +1%",
                        "invalidates_if": "NASDAQ -1%",
                    }
                ],
                "tail_risks": [],
            },
        )

        self.assertEqual(payload["ticker"], "MARKET")
        self.assertEqual(payload["source_system"], "orca_devil")
        self.assertEqual(payload["decision_stage"], "devil")
        self.assertIsNone(payload["analyst_score"])
        self.assertIsNone(payload["devil_score"])
        self.assertEqual(payload["verdict"], "partial")
        self.assertEqual(payload["main_risk"], "crowded AI trade")
        self.assertTrue(payload["thesis_killer_hit"])
        self.assertFalse(payload["is_dead_cat"])
        self.assertFalse(payload["structural_decline"])
        self.assertIsNone(payload["final_score"])
        self.assertFalse(payload["is_entry"])
        self.assertIsNone(payload["block_reason"])
        self.assertIsNone(payload["decision_label"])
        self.assertEqual(RiskDecision(**payload).source_system, "orca_devil")

    def test_minimal_dict_uses_safe_defaults(self):
        payload = project_orca_devil_to_risk_decision(
            ticker=None,
            analyst={},
            devil={},
        )
        decision = RiskDecision(**payload)

        self.assertEqual(decision.ticker, "MARKET")
        self.assertIsNone(decision.analyst_score)
        self.assertIsNone(decision.devil_score)
        self.assertIsNone(decision.verdict)
        self.assertIsNone(decision.main_risk)
        self.assertFalse(decision.thesis_killer_hit)

    def test_ticker_override_is_preserved(self):
        payload = project_orca_devil_to_risk_decision(
            ticker="KOSPI",
            analyst={},
            devil={"verdict": "oppose"},
        )

        self.assertEqual(payload["ticker"], "KOSPI")
        self.assertEqual(RiskDecision(**payload).verdict, "oppose")

    def test_tail_risk_is_used_when_counterarguments_are_empty(self):
        payload = project_orca_devil_to_risk_decision(
            ticker=None,
            analyst={},
            devil={"tail_risks": [{"risk": "policy shock"}]},
        )

        self.assertEqual(payload["main_risk"], "policy shock")


if __name__ == "__main__":
    unittest.main()
