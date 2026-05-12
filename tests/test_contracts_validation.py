"""Shadow validation helper tests for Phase 11.9."""

import unittest
from unittest.mock import MagicMock

from pydantic import ValidationError

from shared.contracts import AlphaSignal, EventEnvelope
from shared.contracts.validation import shadow_validate


class ShadowValidateTests(unittest.TestCase):
    def _valid_alpha_payload(self):
        return {
            "event_id": "evt_alpha_test",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T09:00:00+09:00",
            "ticker": "NVDA",
            "score": 82.5,
        }

    def test_valid_payload_returns_true_model_none_error(self):
        is_valid, model, error = shadow_validate(
            AlphaSignal,
            self._valid_alpha_payload(),
        )

        self.assertTrue(is_valid)
        self.assertIsInstance(model, AlphaSignal)
        self.assertIsNone(error)
        self.assertEqual(model.ticker, "NVDA")

    def test_warn_mode_fail_open(self):
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        with self.assertLogs("shared.contracts.validation", level="WARNING"):
            is_valid, model, error = shadow_validate(
                AlphaSignal,
                invalid,
                on_error="warn",
            )

        self.assertFalse(is_valid)
        self.assertIsNone(model)
        self.assertIsInstance(error, ValidationError)

    def test_strict_mode_fail_open(self):
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        with self.assertLogs("shared.contracts.validation", level="ERROR"):
            is_valid, model, error = shadow_validate(
                AlphaSignal,
                invalid,
                on_error="strict",
            )

        self.assertFalse(is_valid)
        self.assertIsNone(model)
        self.assertIsInstance(error, ValidationError)

    def test_hard_mode_raises_validation_error(self):
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        with self.assertRaises(ValidationError):
            shadow_validate(
                AlphaSignal,
                invalid,
                on_error="hard",
            )

    def test_invalid_mode_raises_value_error(self):
        with self.assertRaises(ValueError):
            shadow_validate(
                AlphaSignal,
                self._valid_alpha_payload(),
                on_error="unknown",  # type: ignore[arg-type]
            )

    def test_audit_logger_called_on_pass(self):
        audit_logger = MagicMock()

        shadow_validate(
            AlphaSignal,
            self._valid_alpha_payload(),
            context="test.alpha.pass",
            audit_logger=audit_logger,
        )

        audit_logger.assert_called_once()
        event = audit_logger.call_args[0][0]
        self.assertEqual(event["contract_name"], "AlphaSignal")
        self.assertEqual(event["context"], "test.alpha.pass")
        self.assertEqual(event["validation_status"], "pass")
        self.assertEqual(event["error_count"], 0)
        self.assertIsNone(event["error_summary"])

    def test_audit_logger_called_on_fail(self):
        audit_logger = MagicMock()
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        with self.assertLogs("shared.contracts.validation", level="WARNING"):
            shadow_validate(
                AlphaSignal,
                invalid,
                context="test.alpha.fail",
                audit_logger=audit_logger,
            )

        audit_logger.assert_called_once()
        event = audit_logger.call_args[0][0]
        self.assertEqual(event["contract_name"], "AlphaSignal")
        self.assertEqual(event["context"], "test.alpha.fail")
        self.assertEqual(event["validation_status"], "fail")
        self.assertGreater(event["error_count"], 0)
        self.assertIn("score", event["error_summary"])

    def test_audit_logger_optional(self):
        is_valid, model, error = shadow_validate(
            AlphaSignal,
            self._valid_alpha_payload(),
        )

        self.assertTrue(is_valid)
        self.assertIsInstance(model, AlphaSignal)
        self.assertIsNone(error)

    def test_context_in_warning_log(self):
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        with self.assertLogs("shared.contracts.validation", level="WARNING") as logs:
            shadow_validate(
                AlphaSignal,
                invalid,
                context="my.test.context",
            )

        self.assertTrue(any("my.test.context" in msg for msg in logs.output))

    def test_default_mode_is_warn(self):
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        try:
            with self.assertLogs("shared.contracts.validation", level="WARNING"):
                is_valid, model, error = shadow_validate(AlphaSignal, invalid)
        except ValidationError:
            self.fail("default mode must be warn/fail-open")

        self.assertFalse(is_valid)
        self.assertIsNone(model)
        self.assertIsInstance(error, ValidationError)

    def test_multiple_models_supported(self):
        payload = {
            "event_id": "evt_envelope_test",
            "source_system": "orca",
            "event_type": "test_event",
            "occurred_at": "2026-05-12T09:00:00+09:00",
        }

        is_valid, model, error = shadow_validate(EventEnvelope, payload)

        self.assertTrue(is_valid)
        self.assertIsInstance(model, EventEnvelope)
        self.assertIsNone(error)

    def test_strict_mode_logs_error(self):
        invalid = {**self._valid_alpha_payload(), "score": 150.0}

        with self.assertLogs("shared.contracts.validation", level="ERROR") as logs:
            shadow_validate(
                AlphaSignal,
                invalid,
                on_error="strict",
                context="strict.context",
            )

        self.assertTrue(any("strict.context" in msg for msg in logs.output))


if __name__ == "__main__":
    unittest.main()
