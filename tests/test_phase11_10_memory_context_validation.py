"""Phase 11.10 MemoryContext runtime shadow validation tests."""

import unittest
from unittest.mock import MagicMock, patch

from shared.contracts import MemoryContext
from orca import jackal_memory_context as memory


class Phase11_10MemoryContextValidationTests(unittest.TestCase):
    def _context(self, *, source: str = "candidate_lessons") -> dict:
        return {
            "stats_block": "sample=8 win_rate=75%",
            "sample_size": 8,
            "win_rate": 0.75,
            "avg_outcome": 3.2,
            "source": source,
            "match_scope": "candidate_lessons_regime",
            "role": "analyst",
            "ticker": "NVDA",
            "global_resolved": 0,
        }

    def test_candidate_lessons_branch_calls_shadow_validate(self):
        context = self._context(source="candidate_lessons")

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(memory, "shadow_validate", return_value=(True, MagicMock(), None)) as mock_validate:
            result = memory.build_memory_context("NVDA", {"regime": "risk_on"}, "analyst")

        self.assertIs(result, context)
        mock_validate.assert_called_once()
        args, kwargs = mock_validate.call_args
        self.assertIs(args[0], MemoryContext)
        self.assertEqual(kwargs["on_error"], "warn")
        self.assertEqual(kwargs["context"], memory.MEMORY_CONTEXT_VALIDATION_CONTEXT)

    def test_prediction_cards_branch_calls_shadow_validate(self):
        context = self._context(source="prediction_cards")
        similar = [{"ticker": f"T{i:03d}"} for i in range(memory.MIN_PATTERN_RESOLVED)]

        with patch.object(
            memory, "_count_resolved_predictions", return_value=memory.MIN_GLOBAL_RESOLVED
        ), patch.object(memory, "_query_similar_resolved", return_value=similar), patch.object(
            memory, "_context_from_records", return_value=context
        ), patch.object(memory, "shadow_validate", return_value=(True, MagicMock(), None)) as mock_validate:
            result = memory.build_memory_context("NVDA", {"regime": "risk_on"}, "devil")

        self.assertIs(result, context)
        mock_validate.assert_called_once()

    def test_none_context_does_not_validate(self):
        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=None
        ), patch.object(memory, "shadow_validate") as mock_validate:
            result = memory.build_memory_context("NVDA", {}, "analyst")

        self.assertIsNone(result)
        mock_validate.assert_not_called()

    def test_validation_exception_is_fail_open(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(memory, "shadow_validate", side_effect=RuntimeError("validation down")):
            result = memory.build_memory_context("NVDA", {}, "analyst")

        self.assertIs(result, context)

    def test_validation_failure_tuple_is_fail_open(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(memory, "shadow_validate", return_value=(False, None, MagicMock())):
            result = memory.build_memory_context("NVDA", {}, "analyst")

        self.assertIs(result, context)

    def test_validation_payload_maps_memory_context_fields(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(memory, "shadow_validate", return_value=(True, MagicMock(), None)) as mock_validate:
            memory.build_memory_context("NVDA", {"regime": "risk_on"}, "analyst")

        payload = mock_validate.call_args.args[1]
        self.assertEqual(payload["source_system"], "orca")
        self.assertEqual(payload["event_type"], "memory_context")
        self.assertEqual(payload["ticker"], "NVDA")
        self.assertEqual(payload["stats_block"], context["stats_block"])
        self.assertEqual(payload["sample_size"], context["sample_size"])
        self.assertEqual(payload["win_rate"], context["win_rate"])
        self.assertEqual(payload["avg_outcome"], context["avg_outcome"])
        self.assertEqual(payload["source"], context["source"])
        self.assertEqual(payload["match_scope"], context["match_scope"])
        self.assertEqual(payload["role"], context["role"])
        self.assertEqual(payload["global_resolved"], context["global_resolved"])

    def test_context_string_exact(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(memory, "shadow_validate", return_value=(True, MagicMock(), None)) as mock_validate:
            memory.build_memory_context("NVDA", {}, "analyst")

        self.assertEqual(
            mock_validate.call_args.kwargs["context"],
            "jackal_memory_context.build_memory_context",
        )

    def test_shadow_memory_context_still_logs_existing_pattern(self):
        context = self._context()

        with patch.object(memory, "_count_resolved_predictions", return_value=0), patch.object(
            memory, "_build_from_candidate_lessons", return_value=context
        ), patch.object(memory, "log_shadow_memory_context") as mock_log, patch.object(
            memory, "shadow_validate", return_value=(True, MagicMock(), None)
        ):
            result = memory.shadow_memory_context("NVDA", {"regime": "risk_on"}, "analyst")

        self.assertIs(result, context)
        mock_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
