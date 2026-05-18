"""JACKAL risk-decision projection tests."""

import unittest

from apps.jackal.risk_projection import project_hunter_to_risk_decision
from shared.contracts import RiskDecision


class HunterRiskProjectionTests(unittest.TestCase):
    def test_happy_path_maps_hunter_fields(self):
        payload = project_hunter_to_risk_decision(
            ticker="PFE",
            analyst={"analyst_score": 72},
            devil={
                "devil_score": 61,
                "verdict": "partial",
                "main_risk": "late chase",
                "thesis_killer_hit": False,
                "is_dead_cat": True,
                "structural_decline": True,
            },
            final={
                "final_score": 24.5,
                "is_entry": False,
                "label": "Devil block",
                "diag": {"block_reason": "dead_cat"},
            },
        )

        self.assertEqual(payload["ticker"], "PFE")
        self.assertEqual(payload["source_system"], "jackal_hunter")
        self.assertEqual(payload["decision_stage"], "final")
        self.assertEqual(payload["analyst_score"], 72)
        self.assertEqual(payload["devil_score"], 61)
        self.assertEqual(payload["verdict"], "partial")
        self.assertEqual(payload["main_risk"], "late chase")
        self.assertFalse(payload["thesis_killer_hit"])
        self.assertTrue(payload["is_dead_cat"])
        self.assertTrue(payload["structural_decline"])
        self.assertEqual(payload["final_score"], 24.5)
        self.assertFalse(payload["is_entry"])
        self.assertEqual(payload["block_reason"], "dead_cat")
        self.assertEqual(payload["decision_label"], "Devil block")
        self.assertEqual(RiskDecision(**payload).final_score, 24.5)

    def test_missing_dict_fields_use_contract_defaults(self):
        payload = project_hunter_to_risk_decision(
            ticker="RIVN",
            analyst={},
            devil={},
            final={},
        )
        decision = RiskDecision(**payload)

        self.assertEqual(decision.ticker, "RIVN")
        self.assertIsNone(decision.analyst_score)
        self.assertIsNone(decision.devil_score)
        self.assertIsNone(decision.final_score)
        self.assertFalse(decision.thesis_killer_hit)
        self.assertFalse(decision.is_dead_cat)
        self.assertFalse(decision.structural_decline)
        self.assertFalse(decision.is_entry)
        self.assertIsNone(decision.block_reason)
        self.assertIsNone(decision.decision_label)

    def test_non_dict_diag_is_ignored(self):
        payload = project_hunter_to_risk_decision(
            ticker="NOC",
            analyst={"analyst_score": 80},
            devil={"devil_score": 30},
            final={"final_score": 75.2, "diag": "not-a-dict"},
        )

        self.assertIsNone(payload["block_reason"])
        self.assertEqual(RiskDecision(**payload).final_score, 75.2)


if __name__ == "__main__":
    unittest.main()
