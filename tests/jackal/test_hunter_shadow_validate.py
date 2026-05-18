"""Hunter RiskDecision shadow validation wiring tests."""

import unittest
from unittest.mock import patch

from apps.jackal import hunter


class HunterRiskDecisionShadowTests(unittest.TestCase):
    def test_shadow_wrapper_calls_risk_decision_contract(self):
        analyst = {"analyst_score": 72}
        devil = {"devil_score": 61, "is_dead_cat": True}
        final = {
            "final_score": 24.5,
            "is_entry": False,
            "label": "Devil block",
            "diag": {"block_reason": "dead_cat"},
        }

        with patch.object(hunter, "shadow_validate", return_value=(True, object(), None)) as mocked:
            hunter._shadow_validate_hunter_risk_decision("PFE", analyst, devil, final)

        args, kwargs = mocked.call_args
        self.assertIs(args[0], hunter.RiskDecision)
        self.assertEqual(args[1]["ticker"], "PFE")
        self.assertEqual(args[1]["source_system"], "jackal_hunter")
        self.assertEqual(args[1]["final_score"], 24.5)
        self.assertEqual(args[1]["block_reason"], "dead_cat")
        self.assertEqual(kwargs["on_error"], "warn")
        self.assertEqual(kwargs["context"], "jackal_hunter.stage4.risk_decision")
        self.assertIs(kwargs["audit_logger"], hunter.file_and_db_audit_logger)

    def test_shadow_wrapper_fails_open(self):
        with patch.object(hunter, "shadow_validate", side_effect=RuntimeError("audit down")):
            hunter._shadow_validate_hunter_risk_decision(
                "RIVN",
                {"analyst_score": 70},
                {"devil_score": 30},
                {"final_score": 71.5},
            )

    def test_stage4_calls_shadow_after_final_adjustments(self):
        top10 = [
            {
                "ticker": "PFE",
                "tech": {"rsi": 28.3},
                "currency": "USD",
                "name": "Pfizer",
                "hunt_reason": "setup",
            }
        ]
        analyst = {"analyst_score": 72, "signals_fired": [], "swing_type": "rebound"}
        devil = {"devil_score": 30}
        final = {"final_score": 70.0, "is_entry": True, "label": "Entry", "entry_threshold": 55}
        probability_final = {**final, "final_score": 72.5, "probability_adjustment": 0.0}
        historical_final = {**probability_final, "final_score": 75.5}

        with patch.object(hunter, "_is_on_cooldown", return_value=False), patch.object(
            hunter, "_analyst_swing", return_value=analyst
        ), patch.object(hunter, "_devil_swing", return_value=devil), patch.object(
            hunter, "_final", return_value=final
        ), patch.object(hunter, "canonical_family_key", return_value="rebound"), patch.object(
            hunter, "load_probability_summary", return_value={}
        ), patch.object(
            hunter, "apply_probability_adjustment", return_value=probability_final
        ), patch.object(
            hunter, "_historical_market_features_from_aria", return_value={}
        ), patch.object(
            hunter, "_try_retrieve_historical_context", return_value=None
        ), patch.object(
            hunter, "_apply_historical_context", return_value=historical_final
        ), patch.object(
            hunter, "format_final_diag", return_value=""
        ), patch.object(
            hunter, "_shadow_validate_hunter_risk_decision"
        ) as mocked_shadow:
            results = hunter._stage4_full_analysis(top10, aria={})

        mocked_shadow.assert_called_once_with("PFE", analyst, devil, historical_final)
        self.assertEqual(results[0]["final"]["final_score"], 75.5)


if __name__ == "__main__":
    unittest.main()
