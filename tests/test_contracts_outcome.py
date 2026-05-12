"""PredictionOutcome shadow contract tests for Phase 11.5."""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from shared.contracts import EventEnvelope, PredictionOutcome


class PredictionOutcomeTests(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "event_id": "evt_outcome_1",
            "source_system": "orca",
            "occurred_at": datetime.now(timezone.utc),
            "prediction_event_id": "evt_alpha_1",
            "horizon": "d1",
            "outcome": "win",
            "observed_at": datetime.now(timezone.utc),
        }

    def test_minimal_required_fields(self):
        outcome = PredictionOutcome(**self._base_kwargs())

        self.assertEqual(outcome.schema_version, "v1")
        self.assertEqual(outcome.event_type, "prediction_outcome")
        self.assertEqual(outcome.prediction_event_id, "evt_alpha_1")
        self.assertEqual(outcome.horizon, "d1")
        self.assertEqual(outcome.outcome, "win")

    def test_inherits_event_envelope(self):
        outcome = PredictionOutcome(**self._base_kwargs())

        self.assertIsInstance(outcome, EventEnvelope)
        self.assertEqual(outcome.event_type, "prediction_outcome")

    def test_event_type_literal_rejects_other_values(self):
        with self.assertRaises(ValidationError):
            PredictionOutcome(**{**self._base_kwargs(), "event_type": "alpha_signal"})

    def test_horizon_literal(self):
        for horizon in ("d1", "d3", "d5"):
            with self.subTest(horizon=horizon):
                outcome = PredictionOutcome(**{**self._base_kwargs(), "horizon": horizon})
                self.assertEqual(outcome.horizon, horizon)

        with self.assertRaises(ValidationError):
            PredictionOutcome(**{**self._base_kwargs(), "horizon": "d7"})

    def test_outcome_literal(self):
        for label in ("win", "loss", "neutral"):
            with self.subTest(label=label):
                outcome = PredictionOutcome(**{**self._base_kwargs(), "outcome": label})
                self.assertEqual(outcome.outcome, label)

        with self.assertRaises(ValidationError):
            PredictionOutcome(**{**self._base_kwargs(), "outcome": "draw"})

    def test_prediction_event_id_required(self):
        kwargs = self._base_kwargs()
        del kwargs["prediction_event_id"]

        with self.assertRaises(ValidationError):
            PredictionOutcome(**kwargs)

    def test_observed_at_required(self):
        kwargs = self._base_kwargs()
        del kwargs["observed_at"]

        with self.assertRaises(ValidationError):
            PredictionOutcome(**kwargs)

    def test_actual_values_nullable(self):
        outcome = PredictionOutcome(**self._base_kwargs())

        self.assertIsNone(outcome.actual_high)
        self.assertIsNone(outcome.actual_low)
        self.assertIsNone(outcome.actual_close)
        self.assertIsNone(outcome.return_pct)
        self.assertIsNone(outcome.resolved_by)

    def test_actual_values_with_data(self):
        outcome = PredictionOutcome(
            **{
                **self._base_kwargs(),
                "actual_high": 920.0,
                "actual_low": 875.0,
                "actual_close": 905.0,
                "return_pct": 2.5,
                "resolved_by": "outcome_resolver",
            }
        )

        self.assertEqual(outcome.actual_high, 920.0)
        self.assertEqual(outcome.actual_low, 875.0)
        self.assertEqual(outcome.actual_close, 905.0)
        self.assertEqual(outcome.return_pct, 2.5)
        self.assertEqual(outcome.resolved_by, "outcome_resolver")

    def test_negative_return_pct_allowed(self):
        outcome = PredictionOutcome(
            **{
                **self._base_kwargs(),
                "outcome": "loss",
                "return_pct": -3.2,
            }
        )

        self.assertEqual(outcome.return_pct, -3.2)

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            PredictionOutcome(**{**self._base_kwargs(), "unknown": "X"})

    def test_prediction_card_d1_projection(self):
        projection = {
            "event_id": "evt_outcome_d1_card_xyz",
            "source_system": "orca",
            "occurred_at": "2026-05-12T16:00:00+09:00",
            "prediction_event_id": "evt_alpha_card_xyz",
            "horizon": "d1",
            "outcome": "win",
            "actual_high": 920.0,
            "actual_low": 880.0,
            "actual_close": 905.0,
            "return_pct": 1.5,
            "observed_at": "2026-05-12T16:00:00+09:00",
            "resolved_by": "outcome_resolver",
        }

        outcome = PredictionOutcome.model_validate(projection)

        self.assertEqual(outcome.horizon, "d1")
        self.assertEqual(outcome.outcome, "win")
        self.assertEqual(outcome.prediction_event_id, "evt_alpha_card_xyz")

    def test_three_horizons_independent_events(self):
        outcomes = []
        for horizon in ("d1", "d3", "d5"):
            outcomes.append(
                PredictionOutcome(
                    event_id=f"evt_outcome_{horizon}_card_1",
                    source_system="orca",
                    occurred_at=datetime.now(timezone.utc),
                    prediction_event_id="evt_alpha_card_1",
                    horizon=horizon,
                    outcome="win",
                    observed_at=datetime.now(timezone.utc),
                )
            )

        self.assertEqual([item.horizon for item in outcomes], ["d1", "d3", "d5"])
        for item in outcomes:
            self.assertEqual(item.prediction_event_id, "evt_alpha_card_1")

    def test_model_validate_json(self):
        json_payload = """
        {
            "event_id": "evt_o_json",
            "source_system": "orca",
            "occurred_at": "2026-05-12T16:00:00+09:00",
            "prediction_event_id": "evt_alpha_json",
            "horizon": "d5",
            "outcome": "loss",
            "actual_close": 850.0,
            "return_pct": -3.2,
            "observed_at": "2026-05-12T16:00:00+09:00"
        }
        """

        outcome = PredictionOutcome.model_validate_json(json_payload)

        self.assertEqual(outcome.horizon, "d5")
        self.assertEqual(outcome.outcome, "loss")
        self.assertEqual(outcome.actual_close, 850.0)
        self.assertEqual(outcome.return_pct, -3.2)


if __name__ == "__main__":
    unittest.main()
