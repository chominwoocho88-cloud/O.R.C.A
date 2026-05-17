"""EventEnvelope smoke and contract checks for Phase 11.3."""

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from shared.contracts import ContractModel, EventEnvelope


class EventEnvelopeTests(unittest.TestCase):
    def test_minimal_required_fields(self):
        env = EventEnvelope(
            event_id="evt_1",
            source_system="orca",
            event_type="alpha_signal",
            occurred_at=datetime.now(timezone.utc),
        )

        self.assertEqual(env.schema_version, "v1")
        self.assertEqual(env.event_id, "evt_1")
        self.assertEqual(env.source_system, "orca")
        self.assertEqual(env.event_type, "alpha_signal")
        self.assertEqual(env.payload, {})

    def test_optional_fields_are_preserved(self):
        occurred_at = datetime.now(timezone.utc)

        env = EventEnvelope(
            event_id="evt_full",
            source_system="jackal",
            event_type="scan_result",
            occurred_at=occurred_at,
            analysis_date="2026-05-12",
            run_id="run_1",
            correlation_id="corr_1",
            ticker="NVDA",
            market="US",
            build_hash="abc123",
        )

        self.assertEqual(env.analysis_date, "2026-05-12")
        self.assertEqual(env.run_id, "run_1")
        self.assertEqual(env.correlation_id, "corr_1")
        self.assertEqual(env.ticker, "NVDA")
        self.assertEqual(env.market, "US")
        self.assertEqual(env.build_hash, "abc123")

    def test_all_source_systems_valid(self):
        for source_system in ("orca", "jackal", "atlas", "falcon", "system"):
            with self.subTest(source_system=source_system):
                env = EventEnvelope(
                    event_id=f"evt_{source_system}",
                    source_system=source_system,
                    event_type="test",
                    occurred_at=datetime.now(timezone.utc),
                )
                self.assertEqual(env.source_system, source_system)

    def test_invalid_source_system_rejected(self):
        with self.assertRaises(ValidationError):
            EventEnvelope(
                event_id="evt_x",
                source_system="invalid_system",
                event_type="test",
                occurred_at=datetime.now(timezone.utc),
            )

    def test_market_literal(self):
        for market in ("US", "KR", "CRYPTO", "UNKNOWN"):
            with self.subTest(market=market):
                env = EventEnvelope(
                    event_id=f"evt_{market.lower()}",
                    source_system="jackal",
                    event_type="alpha_signal",
                    occurred_at=datetime.now(timezone.utc),
                    market=market,
                )
                self.assertEqual(env.market, market)

        with self.assertRaises(ValidationError):
            EventEnvelope(
                event_id="evt_jp",
                source_system="jackal",
                event_type="alpha_signal",
                occurred_at=datetime.now(timezone.utc),
                market="JP",
            )

    def test_extra_field_forbidden(self):
        with self.assertRaises(ValidationError):
            EventEnvelope(
                event_id="evt_x",
                source_system="orca",
                event_type="test",
                occurred_at=datetime.now(timezone.utc),
                unknown_field="X",
            )

    def test_payload_dict_accepted(self):
        env = EventEnvelope(
            event_id="evt_payload",
            source_system="orca",
            event_type="test",
            occurred_at=datetime.now(timezone.utc),
            payload={"score": 82.5, "ticker": "NVDA"},
        )

        self.assertEqual(env.payload["score"], 82.5)
        self.assertEqual(env.payload["ticker"], "NVDA")

    def test_model_validate_json(self):
        json_payload = """
        {
            "event_id": "evt_json",
            "source_system": "jackal",
            "event_type": "alpha_signal",
            "occurred_at": "2026-05-12T09:00:00+09:00",
            "ticker": "NVDA",
            "market": "US",
            "payload": {"score": 82.5}
        }
        """

        env = EventEnvelope.model_validate_json(json_payload)

        self.assertEqual(env.event_id, "evt_json")
        self.assertEqual(env.ticker, "NVDA")
        self.assertEqual(env.market, "US")
        self.assertEqual(env.payload["score"], 82.5)

    def test_contract_model_strips_whitespace(self):
        env = EventEnvelope(
            event_id="  evt_trim  ",
            source_system="orca",
            event_type="  test_event  ",
            occurred_at=datetime.now(timezone.utc),
        )

        self.assertEqual(env.event_id, "evt_trim")
        self.assertEqual(env.event_type, "test_event")

    def test_contract_model_exported(self):
        self.assertTrue(issubclass(EventEnvelope, ContractModel))


if __name__ == "__main__":
    unittest.main()
