"""ORCA Devil RiskDecision shadow validation wiring tests."""

import json
import unittest
from unittest.mock import patch

from apps.orca.pipeline import agents


class OrcaDevilShadowValidateTests(unittest.TestCase):
    def test_agent_devil_calls_shadow_validate_after_thesis_killer_normalization(self):
        devil_payload = {
            "verdict": "partial",
            "counterarguments": [{"against": "late-cycle risk", "risk_level": "high"}],
            "alternative_scenario": {"regime": "risk_off", "narrative": "shock", "probability": "medium"},
            "thesis_killers": [
                {
                    "event": "NASDAQ",
                    "timeframe": "close",
                    "confirms_if": "NASDAQ +1%",
                    "invalidates_if": "NASDAQ -1%",
                },
                {
                    "event": "DXY",
                    "timeframe": "close",
                    "confirms_if": "DXY +1%",
                    "invalidates_if": "DXY -1%",
                },
            ],
            "tail_risks": [],
        }

        with patch.object(agents.console, "print"), patch.object(
            agents, "call_api", return_value=json.dumps(devil_payload)
        ), patch.object(agents, "shadow_validate", return_value=(True, object(), None)) as mocked:
            result = agents.agent_devil(
                {"market_regime": "risk_on", "analyst_confidence": "high"},
                memory=[],
                mode="MORNING",
            )

        self.assertEqual([tk["event"] for tk in result["thesis_killers"]], ["NASDAQ"])
        args, kwargs = mocked.call_args
        self.assertIs(args[0], agents.RiskDecision)
        self.assertEqual(args[1]["source_system"], "orca_devil")
        self.assertEqual(args[1]["decision_stage"], "devil")
        self.assertEqual(args[1]["ticker"], "MARKET")
        self.assertEqual(args[1]["verdict"], "partial")
        self.assertEqual(args[1]["main_risk"], "late-cycle risk")
        self.assertTrue(args[1]["thesis_killer_hit"])
        self.assertEqual(kwargs["on_error"], "warn")
        self.assertEqual(kwargs["context"], "orca_devil.risk_decision")
        self.assertIs(kwargs["audit_logger"], agents.file_and_db_audit_logger)

    def test_agent_devil_fails_open_when_shadow_validate_fails(self):
        devil_payload = {
            "verdict": "agree",
            "counterarguments": [],
            "alternative_scenario": {},
            "thesis_killers": [],
            "tail_risks": [],
        }

        with patch.object(agents.console, "print"), patch.object(
            agents, "call_api", return_value=json.dumps(devil_payload)
        ), patch.object(agents, "shadow_validate", side_effect=RuntimeError("audit down")):
            result = agents.agent_devil({}, memory=[], mode="EVENING")

        self.assertEqual(result["verdict"], "agree")
        self.assertEqual(result["thesis_killers"], [])

    def test_shadow_wrapper_fails_open_when_projection_fails(self):
        with patch.object(
            agents,
            "project_orca_devil_to_risk_decision",
            side_effect=RuntimeError("projection down"),
        ), patch.object(agents, "shadow_validate") as mocked:
            agents._shadow_validate_orca_devil_risk_decision({}, {})

        mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
