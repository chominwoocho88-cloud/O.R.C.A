"""RiskDecision shadow contract tests."""

import unittest

from pydantic import ValidationError

from shared.contracts import ContractModel, RiskDecision


class RiskDecisionTests(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "ticker": "PFE",
            "source_system": "jackal_hunter",
            "decision_stage": "final",
        }

    def test_minimal_required_fields(self):
        decision = RiskDecision(**self._base_kwargs())

        self.assertEqual(decision.ticker, "PFE")
        self.assertEqual(decision.source_system, "jackal_hunter")
        self.assertEqual(decision.decision_stage, "final")
        self.assertIsNone(decision.analyst_score)
        self.assertIsNone(decision.devil_score)
        self.assertIsNone(decision.final_score)
        self.assertFalse(decision.thesis_killer_hit)
        self.assertFalse(decision.is_dead_cat)
        self.assertFalse(decision.structural_decline)
        self.assertFalse(decision.is_entry)
        self.assertIsNone(decision.block_reason)
        self.assertIsNone(decision.decision_label)

    def test_inherits_contract_model(self):
        decision = RiskDecision(**self._base_kwargs())

        self.assertIsInstance(decision, ContractModel)

    def test_full_jackal_hunter_decision_payload(self):
        decision = RiskDecision(
            **{
                **self._base_kwargs(),
                "analyst_score": 72,
                "devil_score": 61,
                "verdict": "부분동의",
                "main_risk": "거래량 확인 필요",
                "thesis_killer_hit": False,
                "is_dead_cat": True,
                "structural_decline": True,
                "final_score": 24.5,
                "is_entry": False,
                "block_reason": "dead_cat",
                "decision_label": "Devil 차단",
            }
        )

        self.assertEqual(decision.analyst_score, 72)
        self.assertEqual(decision.devil_score, 61)
        self.assertEqual(decision.verdict, "부분동의")
        self.assertEqual(decision.main_risk, "거래량 확인 필요")
        self.assertFalse(decision.thesis_killer_hit)
        self.assertTrue(decision.is_dead_cat)
        self.assertTrue(decision.structural_decline)
        self.assertEqual(decision.final_score, 24.5)
        self.assertFalse(decision.is_entry)
        self.assertEqual(decision.block_reason, "dead_cat")
        self.assertEqual(decision.decision_label, "Devil 차단")

    def test_score_ranges_accept_boundaries(self):
        RiskDecision(
            **{
                **self._base_kwargs(),
                "analyst_score": 0,
                "devil_score": 100,
                "final_score": 55,
            }
        )

        RiskDecision(**{**self._base_kwargs(), "final_score": 55.7})

    def test_score_ranges_reject_out_of_bounds(self):
        for field_name, value in (
            ("analyst_score", -1),
            ("devil_score", 101),
            ("final_score", -1),
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    RiskDecision(**{**self._base_kwargs(), field_name: value})

        with self.assertRaises(ValidationError):
            RiskDecision(**{**self._base_kwargs(), "final_score": 100.1})

    def test_score_fields_reject_non_numeric_values(self):
        for field_name in ("analyst_score", "devil_score", "final_score"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    RiskDecision(**{**self._base_kwargs(), field_name: "high"})

    def test_extra_fields_forbidden(self):
        with self.assertRaises(ValidationError):
            RiskDecision(**{**self._base_kwargs(), "unexpected": "value"})


if __name__ == "__main__":
    unittest.main()
