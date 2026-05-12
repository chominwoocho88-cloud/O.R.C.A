"""Phase 11.20 AlphaSignal projection helper tests."""

import unittest

from pydantic import ValidationError

from orca import jackal_prediction_cards as cards
from shared.contracts import AlphaSignal


class AlphaSignalProjectionTests(unittest.TestCase):
    def _values(self, **overrides):
        values = {
            "card_id": "card_live_1",
            "event_id": "live_1",
            "event_kind": "hunt",
            "ticker": "NVDA",
            "name": "NVIDIA",
            "score": 82.5,
            "day1_score": 72.0,
            "swing_score": 88.0,
            "devil_score": 30.0,
            "devil_verdict": "neutral",
            "current_price": 100.0,
            "entry_price_low": 98.0,
            "entry_price_high": 102.0,
            "target_price": 110.0,
            "stop_price": 95.0,
            "horizon_days": 5,
            "pattern_label": "momentum",
            "main_reasoning": "reason",
            "market_regime": "risk_on",
            "fear_greed": 67,
            "fear_greed_label": "Greed",
            "inflow_sectors": '["semis", "software"]',
            "created_at": "2026-05-12T09:00:00+09:00",
            "build_hash": "build_1",
            "status": "open",
            "resolved_at": None,
            "actual_high": None,
            "actual_low": None,
            "actual_close_d1": None,
            "actual_close_d3": None,
            "actual_close_d5": None,
            "outcome_d1": None,
            "outcome_d3": None,
            "outcome_d5": None,
        }
        values.update(overrides)
        return values

    def test_basic_projection_validates_alpha_signal(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(self._values())

        signal = AlphaSignal.model_validate(payload)

        self.assertEqual(signal.event_id, "live_1")
        self.assertEqual(signal.event_type, "alpha_signal")
        self.assertEqual(signal.source_system, "jackal")
        self.assertEqual(signal.ticker, "NVDA")
        self.assertEqual(signal.score, 82.5)
        self.assertEqual(signal.inflow_sectors, ["semis", "software"])
        self.assertEqual(signal.analysis_date, "2026-05-12")
        self.assertTrue(signal.alerted)

    def test_inflow_sectors_list_passthrough(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(inflow_sectors='["ignored"]'),
            raw_payload={"inflow_sectors": ["AI", "Semis"]},
        )

        self.assertEqual(payload["inflow_sectors"], ["AI", "Semis"])
        self.assertEqual(AlphaSignal.model_validate(payload).inflow_sectors, ["AI", "Semis"])

    def test_inflow_sectors_json_string_normalized(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(inflow_sectors='["semis", "software", "cloud"]')
        )

        self.assertEqual(payload["inflow_sectors"], ["semis", "software", "cloud"])

    def test_inflow_sectors_plain_string_wrapped(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(inflow_sectors="semis")
        )

        self.assertEqual(payload["inflow_sectors"], ["semis"])

    def test_inflow_sectors_invalid_returns_empty(self):
        malformed = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(inflow_sectors="[broken")
        )
        unsupported = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(inflow_sectors={"sector": "semis"})
        )

        self.assertEqual(malformed["inflow_sectors"], [])
        self.assertEqual(unsupported["inflow_sectors"], [])

    def test_extra_keys_excluded(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(self._values())

        for key in (
            "card_id",
            "event_kind",
            "status",
            "resolved_at",
            "actual_high",
            "outcome_d5",
        ):
            with self.subTest(key=key):
                self.assertNotIn(key, payload)

        AlphaSignal.model_validate(payload)

    def test_source_system_jackal_fixed(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(source_system="orca")
        )

        self.assertEqual(payload["source_system"], "jackal")

    def test_occurred_at_from_created_at(self):
        created_at = "2026-05-12T09:30:00+09:00"
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(created_at=created_at)
        )

        signal = AlphaSignal.model_validate(payload)

        self.assertEqual(payload["occurred_at"], created_at)
        self.assertEqual(signal.occurred_at.isoformat(), created_at)

    def test_out_of_range_score_fails_validation(self):
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            self._values(score=150)
        )

        self.assertEqual(payload["score"], 150)
        with self.assertRaises(ValidationError):
            AlphaSignal.model_validate(payload)

    def test_helper_does_not_raise_on_missing_optional(self):
        values = self._values(
            name=None,
            day1_score=None,
            swing_score=None,
            devil_score=None,
            devil_verdict=None,
            current_price=None,
            entry_price_low=None,
            entry_price_high=None,
            target_price=None,
            stop_price=None,
            pattern_label=None,
            main_reasoning=None,
            market_regime=None,
            fear_greed=None,
            fear_greed_label=None,
            inflow_sectors=None,
            build_hash=None,
        )

        payload = cards._alpha_signal_payload_from_prediction_card_values(values)
        signal = AlphaSignal.model_validate(payload)

        self.assertEqual(signal.inflow_sectors, [])
        self.assertEqual(signal.horizon_days, 5)
        self.assertTrue(signal.alerted)


if __name__ == "__main__":
    unittest.main()
