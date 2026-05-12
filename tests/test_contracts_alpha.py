"""AlphaSignal shadow contract tests for Phase 11.4."""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from shared.contracts import AlphaSignal, EventEnvelope


class AlphaSignalTests(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "event_id": "evt_alpha_1",
            "source_system": "jackal",
            "occurred_at": datetime.now(timezone.utc),
            "ticker": "NVDA",
            "score": 82.5,
        }

    def test_minimal_required_fields(self):
        signal = AlphaSignal(**self._base_kwargs())

        self.assertEqual(signal.schema_version, "v1")
        self.assertEqual(signal.event_type, "alpha_signal")
        self.assertEqual(signal.source_system, "jackal")
        self.assertEqual(signal.ticker, "NVDA")
        self.assertEqual(signal.score, 82.5)
        self.assertEqual(signal.horizon_days, 5)
        self.assertFalse(signal.alerted)

    def test_inherits_event_envelope(self):
        signal = AlphaSignal(**self._base_kwargs())

        self.assertIsInstance(signal, EventEnvelope)
        self.assertEqual(signal.event_type, "alpha_signal")

    def test_event_type_literal_rejects_other_values(self):
        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "event_type": "scan_result"})

    def test_score_range_validation(self):
        AlphaSignal(**{**self._base_kwargs(), "score": 0})
        AlphaSignal(**{**self._base_kwargs(), "score": 100})

        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "score": -0.1})

        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "score": 100.1})

    def test_optional_score_ranges_validation(self):
        signal = AlphaSignal(
            **{
                **self._base_kwargs(),
                "day1_score": 74.0,
                "swing_score": 86.0,
                "devil_score": 61.0,
            }
        )

        self.assertEqual(signal.day1_score, 74.0)
        self.assertEqual(signal.swing_score, 86.0)
        self.assertEqual(signal.devil_score, 61.0)

        for field_name in ("day1_score", "swing_score", "devil_score"):
            with self.subTest(field_name=field_name):
                with self.assertRaises(ValidationError):
                    AlphaSignal(**{**self._base_kwargs(), field_name: 150.0})

    def test_horizon_days_range(self):
        self.assertEqual(AlphaSignal(**self._base_kwargs()).horizon_days, 5)
        self.assertEqual(
            AlphaSignal(**{**self._base_kwargs(), "horizon_days": 1}).horizon_days,
            1,
        )
        self.assertEqual(
            AlphaSignal(**{**self._base_kwargs(), "horizon_days": 30}).horizon_days,
            30,
        )

        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "horizon_days": 0})

        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "horizon_days": 31})

    def test_fear_greed_range(self):
        self.assertEqual(
            AlphaSignal(**{**self._base_kwargs(), "fear_greed": 67}).fear_greed,
            67,
        )

        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "fear_greed": -1})

        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "fear_greed": 101})

    def test_optional_price_fields(self):
        signal = AlphaSignal(
            **{
                **self._base_kwargs(),
                "current_price": 890.0,
                "entry_price_low": 884.0,
                "entry_price_high": 892.0,
                "target_price": 915.0,
                "stop_price": 872.0,
            }
        )

        self.assertEqual(signal.current_price, 890.0)
        self.assertEqual(signal.entry_price_low, 884.0)
        self.assertEqual(signal.entry_price_high, 892.0)
        self.assertEqual(signal.target_price, 915.0)
        self.assertEqual(signal.stop_price, 872.0)

    def test_inflow_sectors_default_and_list(self):
        self.assertEqual(AlphaSignal(**self._base_kwargs()).inflow_sectors, [])

        signal = AlphaSignal(
            **{
                **self._base_kwargs(),
                "inflow_sectors": ["Tech", "Semi"],
            }
        )
        self.assertEqual(signal.inflow_sectors, ["Tech", "Semi"])

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            AlphaSignal(**{**self._base_kwargs(), "unknown": "X"})

    def test_model_validate_prediction_card_projection(self):
        prediction_card_projection = {
            "event_id": "evt_pc_1",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T09:00:00+09:00",
            "ticker": "NVDA",
            "score": 82.5,
            "day1_score": 74.0,
            "swing_score": 86.0,
            "devil_score": 61.0,
            "devil_verdict": "pass",
            "current_price": 890.0,
            "entry_price_low": 884.0,
            "entry_price_high": 892.0,
            "target_price": 915.0,
            "stop_price": 872.0,
            "horizon_days": 5,
            "pattern_label": "momentum_pullback",
            "main_reasoning": "Strong setup with sector inflow.",
            "market_regime": "risk_on",
            "fear_greed": 68,
            "fear_greed_label": "Greed",
            "inflow_sectors": ["Tech", "Semi"],
            "alerted": True,
            "build_hash": "abc123",
        }

        signal = AlphaSignal.model_validate(prediction_card_projection)

        self.assertEqual(signal.event_type, "alpha_signal")
        self.assertEqual(signal.ticker, "NVDA")
        self.assertEqual(signal.fear_greed_label, "Greed")
        self.assertEqual(signal.inflow_sectors, ["Tech", "Semi"])
        self.assertTrue(signal.alerted)

    def test_prediction_outcome_fields_are_not_part_of_alpha_signal(self):
        with self.assertRaises(ValidationError):
            AlphaSignal.model_validate(
                {
                    **self._base_kwargs(),
                    "status": "resolved",
                    "actual_close_d5": 915.0,
                    "outcome_d5": "win",
                }
            )

    def test_model_validate_json(self):
        json_payload = """
        {
            "event_id": "evt_json_1",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T09:30:00+09:00",
            "ticker": "207940.KS",
            "score": 64.0,
            "market_regime": "risk_on",
            "fear_greed": 68,
            "inflow_sectors": ["Bio"]
        }
        """

        signal = AlphaSignal.model_validate_json(json_payload)

        self.assertEqual(signal.event_type, "alpha_signal")
        self.assertEqual(signal.ticker, "207940.KS")
        self.assertEqual(signal.inflow_sectors, ["Bio"])

    def test_korean_stock_name_supported(self):
        signal = AlphaSignal(
            **{
                **self._base_kwargs(),
                "ticker": "068270.KS",
                "name": "\uc140\ud2b8\ub9ac\uc628",
            }
        )

        self.assertEqual(signal.ticker, "068270.KS")
        self.assertEqual(signal.name, "\uc140\ud2b8\ub9ac\uc628")


if __name__ == "__main__":
    unittest.main()
