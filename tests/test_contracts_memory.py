"""MemoryContext shadow contract tests for Phase 11.6."""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from shared.contracts import EventEnvelope, MemoryContext


class MemoryContextTests(unittest.TestCase):
    def _base_kwargs(self):
        return {
            "event_id": "evt_mem_1",
            "source_system": "orca",
            "occurred_at": datetime.now(timezone.utc),
            "stats_block": "sample=15, win_rate=66.7%, avg=+2.5%",
            "sample_size": 15,
            "win_rate": 0.667,
            "avg_outcome": 2.5,
            "source": "prediction_cards",
            "match_scope": "regime_fear_greed",
            "role": "analyst",
        }

    def test_minimal_required_fields(self):
        ctx = MemoryContext(**self._base_kwargs())

        self.assertEqual(ctx.schema_version, "v1")
        self.assertEqual(ctx.event_type, "memory_context")
        self.assertEqual(ctx.role, "analyst")
        self.assertEqual(ctx.source, "prediction_cards")

    def test_inherits_event_envelope(self):
        ctx = MemoryContext(**self._base_kwargs())

        self.assertIsInstance(ctx, EventEnvelope)
        self.assertEqual(ctx.event_type, "memory_context")

    def test_event_type_literal_rejects_other_values(self):
        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "event_type": "memory_injection"})

    def test_source_literal(self):
        for source in ("prediction_cards", "candidate_lessons"):
            with self.subTest(source=source):
                ctx = MemoryContext(**{**self._base_kwargs(), "source": source})
                self.assertEqual(ctx.source, source)

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "source": "unknown_source"})

    def test_role_literal(self):
        for role in ("analyst", "devil"):
            with self.subTest(role=role):
                ctx = MemoryContext(**{**self._base_kwargs(), "role": role})
                self.assertEqual(ctx.role, role)

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "role": "hunter"})

    def test_win_rate_range(self):
        MemoryContext(**{**self._base_kwargs(), "win_rate": 0.0})
        MemoryContext(**{**self._base_kwargs(), "win_rate": 1.0})

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "win_rate": -0.1})

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "win_rate": 1.1})

    def test_sample_size_non_negative(self):
        ctx = MemoryContext(**{**self._base_kwargs(), "sample_size": 0})
        self.assertEqual(ctx.sample_size, 0)

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "sample_size": -1})

    def test_avg_outcome_negative_allowed(self):
        ctx = MemoryContext(**{**self._base_kwargs(), "avg_outcome": -3.5})
        self.assertEqual(ctx.avg_outcome, -3.5)

    def test_ticker_inherited_optional_field(self):
        self.assertIsNone(MemoryContext(**self._base_kwargs()).ticker)

        ctx = MemoryContext(**{**self._base_kwargs(), "ticker": "NVDA"})
        self.assertEqual(ctx.ticker, "NVDA")

    def test_global_resolved_non_negative(self):
        ctx = MemoryContext(**{**self._base_kwargs(), "global_resolved": 100})
        self.assertEqual(ctx.global_resolved, 100)

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "global_resolved": -1})

    def test_stats_block_and_match_scope_required_non_empty(self):
        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "stats_block": ""})

        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "match_scope": ""})

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            MemoryContext(**{**self._base_kwargs(), "unknown": "X"})

    def test_build_memory_context_projection(self):
        memory_context_like = {
            "event_id": "evt_mem_projection",
            "source_system": "orca",
            "occurred_at": "2026-05-12T10:00:00+09:00",
            "stats_block": "sample=25, win_rate=72.0%, avg=+3.2%",
            "sample_size": 25,
            "win_rate": 0.72,
            "avg_outcome": 3.2,
            "source": "prediction_cards",
            "match_scope": "regime_fear_greed",
            "role": "analyst",
            "ticker": "NVDA",
            "global_resolved": 30,
        }

        ctx = MemoryContext.model_validate(memory_context_like)

        self.assertEqual(ctx.win_rate, 0.72)
        self.assertEqual(ctx.ticker, "NVDA")
        self.assertEqual(ctx.global_resolved, 30)

    def test_candidate_lessons_projection(self):
        ctx = MemoryContext(
            **{
                **self._base_kwargs(),
                "source": "candidate_lessons",
                "match_scope": "candidate_lessons_regime",
                "role": "devil",
                "ticker": "068270.KS",
            }
        )

        self.assertEqual(ctx.source, "candidate_lessons")
        self.assertEqual(ctx.match_scope, "candidate_lessons_regime")
        self.assertEqual(ctx.role, "devil")
        self.assertEqual(ctx.ticker, "068270.KS")

    def test_model_validate_json(self):
        json_payload = """
        {
            "event_id": "evt_mem_json",
            "source_system": "orca",
            "occurred_at": "2026-05-12T10:00:00+09:00",
            "stats_block": "sample=10, win_rate=60.0%",
            "sample_size": 10,
            "win_rate": 0.6,
            "avg_outcome": 1.5,
            "source": "candidate_lessons",
            "match_scope": "candidate_lessons_global",
            "role": "devil"
        }
        """

        ctx = MemoryContext.model_validate_json(json_payload)

        self.assertEqual(ctx.source, "candidate_lessons")
        self.assertEqual(ctx.match_scope, "candidate_lessons_global")
        self.assertEqual(ctx.role, "devil")


if __name__ == "__main__":
    unittest.main()
