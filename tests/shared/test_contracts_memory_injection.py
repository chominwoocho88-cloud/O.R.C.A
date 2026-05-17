"""MemoryInjection shadow contract tests for Phase 11.6a."""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from shared.contracts import EventEnvelope, MemoryInjection


class MemoryInjectionTests(unittest.TestCase):
    def _base_kwargs(self):
        block = "Memory: sample=15 win_rate=66.7%"
        return {
            "event_id": "evt_inj_1",
            "source_system": "jackal",
            "occurred_at": datetime.now(timezone.utc),
            "injection_block": block,
            "injection_block_chars": len(block),
            "role": "analyst",
            "source": "prediction_cards",
            "sample_size": 15,
        }

    def test_minimal_required_fields(self):
        injection = MemoryInjection(**self._base_kwargs())

        self.assertEqual(injection.schema_version, "v1")
        self.assertEqual(injection.event_type, "memory_injection")
        self.assertEqual(injection.role, "analyst")
        self.assertEqual(injection.source, "prediction_cards")
        self.assertEqual(injection.sample_size, 15)

    def test_inherits_event_envelope(self):
        injection = MemoryInjection(**self._base_kwargs())

        self.assertIsInstance(injection, EventEnvelope)
        self.assertEqual(injection.event_type, "memory_injection")

    def test_event_type_literal_rejects_other_values(self):
        with self.assertRaises(ValidationError):
            MemoryInjection(**{**self._base_kwargs(), "event_type": "memory_context"})

    def test_role_literal(self):
        for role in ("analyst", "devil"):
            with self.subTest(role=role):
                injection = MemoryInjection(**{**self._base_kwargs(), "role": role})
                self.assertEqual(injection.role, role)

        with self.assertRaises(ValidationError):
            MemoryInjection(**{**self._base_kwargs(), "role": "hunter"})

    def test_source_literal(self):
        for source in ("prediction_cards", "candidate_lessons"):
            with self.subTest(source=source):
                injection = MemoryInjection(**{**self._base_kwargs(), "source": source})
                self.assertEqual(injection.source, source)

        with self.assertRaises(ValidationError):
            MemoryInjection(**{**self._base_kwargs(), "source": "unknown"})

    def test_injection_block_chars_must_match_actual_length(self):
        block = "Memory block"
        injection = MemoryInjection(
            **{
                **self._base_kwargs(),
                "injection_block": block,
                "injection_block_chars": len(block),
            }
        )
        self.assertEqual(injection.injection_block_chars, len(block))

        with self.assertRaises(ValidationError):
            MemoryInjection(
                **{
                    **self._base_kwargs(),
                    "injection_block": block,
                    "injection_block_chars": len(block) + 1,
                }
            )

    def test_injection_block_max_1000_chars(self):
        block = "A" * 1000
        injection = MemoryInjection(
            **{
                **self._base_kwargs(),
                "injection_block": block,
                "injection_block_chars": len(block),
            }
        )
        self.assertEqual(injection.injection_block_chars, 1000)

        too_long = "A" * 1001
        with self.assertRaises(ValidationError):
            MemoryInjection(
                **{
                    **self._base_kwargs(),
                    "injection_block": too_long,
                    "injection_block_chars": len(too_long),
                }
            )

    def test_injection_block_required_non_empty(self):
        with self.assertRaises(ValidationError):
            MemoryInjection(
                **{
                    **self._base_kwargs(),
                    "injection_block": "",
                    "injection_block_chars": 0,
                }
            )

    def test_sample_size_non_negative(self):
        injection = MemoryInjection(**{**self._base_kwargs(), "sample_size": 0})
        self.assertEqual(injection.sample_size, 0)

        with self.assertRaises(ValidationError):
            MemoryInjection(**{**self._base_kwargs(), "sample_size": -1})

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            MemoryInjection(**{**self._base_kwargs(), "unknown": "X"})

    def test_shadow_db_row_projection_analyst(self):
        block = "A" * 205
        projection = {
            "event_id": "evt_inj_nvda_analyst",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T10:00:00+09:00",
            "injection_block": block,
            "injection_block_chars": len(block),
            "role": "analyst",
            "source": "prediction_cards",
            "sample_size": 15,
            "ticker": "NVDA",
        }

        injection = MemoryInjection.model_validate(projection)

        self.assertEqual(injection.injection_block_chars, 205)
        self.assertEqual(injection.role, "analyst")
        self.assertEqual(injection.ticker, "NVDA")

    def test_shadow_db_row_projection_devil_candidate_lessons(self):
        block = "D" * 208
        projection = {
            "event_id": "evt_inj_nvda_devil",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T10:00:00+09:00",
            "injection_block": block,
            "injection_block_chars": len(block),
            "role": "devil",
            "source": "candidate_lessons",
            "sample_size": 10,
        }

        injection = MemoryInjection.model_validate(projection)

        self.assertEqual(injection.injection_block_chars, 208)
        self.assertEqual(injection.role, "devil")
        self.assertEqual(injection.source, "candidate_lessons")

    def test_raw_shadow_db_extra_fields_rejected(self):
        block = "Memory block"
        with self.assertRaises(ValidationError):
            MemoryInjection.model_validate(
                {
                    "event_id": "evt_raw_shadow",
                    "source_system": "jackal",
                    "occurred_at": "2026-05-12T10:00:00+09:00",
                    "injection_block": block,
                    "injection_block_chars": len(block),
                    "role": "analyst",
                    "source": "prediction_cards",
                    "sample_size": 10,
                    "memory_mode": "shadow",
                    "build_hash": "abc123",
                }
            )

    def test_model_validate_json(self):
        json_payload = """
        {
            "event_id": "evt_inj_json",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T10:00:00+09:00",
            "injection_block": "Memory block",
            "injection_block_chars": 12,
            "role": "analyst",
            "source": "prediction_cards",
            "sample_size": 10
        }
        """

        injection = MemoryInjection.model_validate_json(json_payload)

        self.assertEqual(injection.role, "analyst")
        self.assertEqual(injection.injection_block_chars, 12)


if __name__ == "__main__":
    unittest.main()
