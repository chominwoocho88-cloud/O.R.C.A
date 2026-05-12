"""Phase 11.12 contract shadow audit tests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from shared.contracts import AlphaSignal, EventEnvelope
from shared.contracts.validation import _hash_payload, shadow_validate
from orca import contract_shadow_audit as audit
from orca import jackal_memory_context as memory


class FileJsonlAuditLoggerTests(unittest.TestCase):
    def _event(self) -> dict:
        return {
            "contract_name": "MemoryContext",
            "context": "test",
            "validation_status": "pass",
            "error_count": 0,
            "error_summary": None,
            "event_id": "evt_1",
            "correlation_id": None,
            "prediction_event_id": None,
            "payload_hash": "abc",
        }

    def test_logger_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "contract_shadow_audit.log"
            with patch.object(audit, "CONTRACT_SHADOW_AUDIT_LOG", log_path):
                audit.file_jsonl_audit_logger(self._event())

            rows = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            data = json.loads(rows[0])
            self.assertEqual(data["contract_name"], "MemoryContext")
            self.assertEqual(data["validation_status"], "pass")

    def test_logger_adds_audit_id_and_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "contract_shadow_audit.log"
            with patch.object(audit, "CONTRACT_SHADOW_AUDIT_LOG", log_path):
                audit.file_jsonl_audit_logger(self._event())

            data = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertIn("audit_id", data)
            self.assertIn("timestamp", data)

    def test_logger_fail_open_on_write_error(self):
        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            audit.file_jsonl_audit_logger(self._event())


class ShadowValidateAuditExtensionTests(unittest.TestCase):
    def _valid_payload(self) -> dict:
        return {
            "event_id": "evt_alpha_1",
            "source_system": "jackal",
            "occurred_at": "2026-05-12T09:00:00+09:00",
            "ticker": "NVDA",
            "score": 82.5,
            "correlation_id": "corr_1",
        }

    def test_audit_event_includes_event_id_and_payload_hash(self):
        audit_logger = MagicMock()

        shadow_validate(
            AlphaSignal,
            self._valid_payload(),
            context="test.alpha",
            audit_logger=audit_logger,
        )

        event = audit_logger.call_args[0][0]
        self.assertEqual(event["event_id"], "evt_alpha_1")
        self.assertEqual(event["correlation_id"], "corr_1")
        self.assertIsNone(event["prediction_event_id"])
        self.assertIsInstance(event["payload_hash"], str)
        self.assertEqual(len(event["payload_hash"]), 64)

    def test_payload_hash_deterministic(self):
        left = {"b": 2, "a": 1}
        right = {"a": 1, "b": 2}

        self.assertEqual(_hash_payload(left), _hash_payload(right))

    def test_audit_event_has_no_full_payload(self):
        audit_logger = MagicMock()

        shadow_validate(
            AlphaSignal,
            self._valid_payload(),
            audit_logger=audit_logger,
        )

        event = audit_logger.call_args[0][0]
        self.assertNotIn("payload", event)
        self.assertNotIn("stats_block", event)

    def test_payload_without_optional_ids_uses_none(self):
        audit_logger = MagicMock()
        payload = {
            "source_system": "orca",
            "event_id": "evt_required",
            "event_type": "test",
            "occurred_at": "2026-05-12T09:00:00+09:00",
        }

        shadow_validate(EventEnvelope, payload, audit_logger=audit_logger)

        event = audit_logger.call_args[0][0]
        self.assertEqual(event["event_id"], "evt_required")
        self.assertIsNone(event["correlation_id"])
        self.assertIsNone(event["prediction_event_id"])


class MemoryContextAuditIntegrationTests(unittest.TestCase):
    def _context(self) -> dict:
        return {
            "stats_block": "sample=8 win_rate=75%",
            "sample_size": 8,
            "win_rate": 0.75,
            "avg_outcome": 3.2,
            "source": "candidate_lessons",
            "match_scope": "candidate_lessons_regime",
            "role": "analyst",
            "ticker": "NVDA",
            "global_resolved": 0,
        }

    def test_build_memory_context_writes_audit_jsonl(self):
        context = self._context()

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "contract_shadow_audit.log"
            with patch.object(audit, "CONTRACT_SHADOW_AUDIT_LOG", log_path), patch.object(
                memory, "_count_resolved_predictions", return_value=0
            ), patch.object(memory, "_build_from_candidate_lessons", return_value=context):
                result = memory.build_memory_context("NVDA", {"regime": "risk_on"}, "analyst")

            self.assertIs(result, context)
            rows = log_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(rows), 1)
            data = json.loads(rows[0])
            self.assertEqual(data["contract_name"], "MemoryContext")
            self.assertEqual(data["context"], memory.MEMORY_CONTEXT_VALIDATION_CONTEXT)
            self.assertEqual(data["validation_status"], "pass")
            self.assertIn("payload_hash", data)
            self.assertNotIn("payload", data)

    def test_build_memory_context_flow_preserved_when_audit_write_fails(self):
        context = self._context()

        with patch("pathlib.Path.open", side_effect=OSError("disk full")), patch.object(
            memory, "_count_resolved_predictions", return_value=0
        ), patch.object(memory, "_build_from_candidate_lessons", return_value=context):
            result = memory.build_memory_context("NVDA", {}, "analyst")

        self.assertIs(result, context)


if __name__ == "__main__":
    unittest.main()
