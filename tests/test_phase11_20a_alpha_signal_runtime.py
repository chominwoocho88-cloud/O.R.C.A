"""Phase 11.20a AlphaSignal runtime shadow validation tests."""

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import jackal_prediction_cards as cards
from shared.contracts import AlphaSignal


class AlphaSignalRuntimeShadowValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.audit_log = self.tmpdir / "contract_shadow_audit.log"
        self.audit_log_patcher = patch(
            "orca.contract_shadow_audit.CONTRACT_SHADOW_AUDIT_LOG",
            self.audit_log,
        )
        self.audit_log_patcher.start()
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        cards.migrate_jackal_prediction_cards(self.conn)

    def tearDown(self):
        self.conn.close()
        self.audit_log_patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _payload(self, **overrides):
        payload = {
            "timestamp": "2026-05-12T09:00:00+09:00",
            "ticker": "NVDA",
            "name": "NVIDIA",
            "final_score": 82.5,
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
            "reason_detail": "reason",
            "market_regime": "risk_on",
            "fear_greed": 67,
            "fear_greed_label": "Greed",
            "inflow_sectors": ["semis", "software"],
            "alerted": True,
            "is_entry": True,
            "outcome_checked": False,
            "build_hash": "build_1",
        }
        payload.update(overrides)
        return payload

    def _record(self, event_id="live_1", payload=None):
        return cards.record_jackal_prediction_card_conn(
            self.conn,
            event_id,
            "hunt",
            payload if payload is not None else self._payload(),
            build_hash="build_1",
        )

    def _row_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM jackal_prediction_cards").fetchone()[0]

    def _card_row(self, event_id="live_1"):
        return self.conn.execute(
            "SELECT * FROM jackal_prediction_cards WHERE event_id = ?",
            (event_id,),
        ).fetchone()

    def test_record_card_calls_shadow_validate(self):
        with patch.object(cards, "shadow_validate") as mocked:
            card_id = self._record()

        self.assertEqual(card_id, "card_live_1")
        mocked.assert_called_once()
        args, kwargs = mocked.call_args
        self.assertIs(args[0], AlphaSignal)
        self.assertEqual(args[1]["event_id"], "live_1")
        self.assertEqual(args[1]["event_type"], "alpha_signal")
        self.assertEqual(kwargs["on_error"], "warn")
        self.assertEqual(
            kwargs["context"],
            "jackal_prediction_cards.record_jackal_prediction_card_conn",
        )
        self.assertIs(kwargs["audit_logger"], cards.file_and_db_audit_logger)

    def test_record_card_insert_flow_preserved(self):
        with patch.object(cards, "file_and_db_audit_logger"):
            card_id = self._record()

        row = self._card_row()

        self.assertEqual(card_id, "card_live_1")
        self.assertEqual(self._row_count(), 1)
        self.assertEqual(row["ticker"], "NVDA")
        self.assertEqual(row["score"], 82.5)
        self.assertEqual(row["status"], "open")

    def test_non_alerted_skips_validation(self):
        with patch.object(cards, "shadow_validate") as mocked:
            card_id = self._record(payload=self._payload(alerted=False))

        self.assertIsNone(card_id)
        mocked.assert_not_called()
        self.assertEqual(self._row_count(), 0)

    def test_projection_error_fails_open(self):
        with patch.object(
            cards,
            "_alpha_signal_payload_from_prediction_card_values",
            side_effect=RuntimeError("projection down"),
        ), patch.object(cards, "shadow_validate") as mocked:
            card_id = self._record()

        self.assertEqual(card_id, "card_live_1")
        self.assertEqual(self._row_count(), 1)
        mocked.assert_not_called()

    def test_validation_failure_fails_open(self):
        with patch.object(cards, "file_and_db_audit_logger") as audit_logger:
            card_id = self._record(payload=self._payload(final_score=150))

        row = self._card_row()
        event = audit_logger.call_args.args[0]

        self.assertEqual(card_id, "card_live_1")
        self.assertEqual(row["score"], 150.0)
        self.assertEqual(event["contract_name"], "AlphaSignal")
        self.assertEqual(event["validation_status"], "fail")

    def test_audit_logger_error_fails_open(self):
        with patch.object(
            cards,
            "file_and_db_audit_logger",
            side_effect=RuntimeError("audit down"),
        ):
            card_id = self._record()

        self.assertEqual(card_id, "card_live_1")
        self.assertEqual(self._row_count(), 1)

    def test_audit_event_includes_event_id(self):
        with patch.object(cards, "file_and_db_audit_logger") as audit_logger:
            self._record()

        event = audit_logger.call_args.args[0]

        self.assertEqual(event["contract_name"], "AlphaSignal")
        self.assertEqual(event["event_id"], "live_1")
        self.assertEqual(event["validation_status"], "pass")
        self.assertTrue(event["payload_hash"])

    def test_retained_resync_allows_duplicate_audit(self):
        cards._contract_shadow_audit.migrate_contract_shadow_audit(self.conn)
        self.conn.execute("BEGIN")

        with patch.object(cards._contract_shadow_audit, "file_jsonl_audit_logger") as audit_logger:
            first = self._record(payload=self._payload(final_score=82.5))
            second = self._record(payload=self._payload(final_score=84.0))

        row = self._card_row()
        audit_count = self.conn.execute(
            """
            SELECT COUNT(*)
              FROM contract_shadow_audit
             WHERE contract_name = 'AlphaSignal'
            """
        ).fetchone()[0]

        self.assertEqual(first, "card_live_1")
        self.assertEqual(second, "card_live_1")
        self.assertEqual(audit_logger.call_count, 2)
        self.assertEqual(audit_count, 2)
        self.assertEqual(self._row_count(), 1)
        self.assertEqual(row["score"], 84.0)

    def test_inflow_sectors_normalized_in_runtime(self):
        with patch.object(cards, "shadow_validate") as mocked:
            self._record(payload=self._payload(inflow_sectors=["AI", "Semis"]))

        payload = mocked.call_args.args[1]

        self.assertEqual(payload["inflow_sectors"], ["AI", "Semis"])

    def test_phase_11_20_projection_helper_still_validates(self):
        values = cards._prediction_card_values(
            "live_projection",
            "hunt",
            self._payload(),
            build_hash="build_1",
        )
        payload = cards._alpha_signal_payload_from_prediction_card_values(
            values,
            raw_payload=self._payload(),
        )

        signal = AlphaSignal.model_validate(payload)

        self.assertEqual(signal.event_id, "live_projection")
        self.assertEqual(signal.source_system, "jackal")
        self.assertEqual(signal.inflow_sectors, ["semis", "software"])


if __name__ == "__main__":
    unittest.main()
