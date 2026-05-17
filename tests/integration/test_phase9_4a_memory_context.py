import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import memory_context as memory
from apps.orca import state


class TestJackalMemoryContext(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.audit_log = self.tmpdir / "contract_shadow_audit.log"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch("shared.audit.contract_shadow_audit.CONTRACT_SHADOW_AUDIT_LOG", self.audit_log),
        ]
        for item in self.patches:
            item.start()
        state.init_state_db()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_card(
        self,
        idx: int,
        *,
        regime: str = "risk_on",
        fear_greed: int = 67,
        outcome: str = "win",
        current_price: float = 100.0,
        close: float = 106.0,
    ) -> None:
        with state._connect_jackal() as conn:
            conn.execute(
                """
                INSERT INTO jackal_live_events (
                    event_id, event_type, external_key, ticker, event_timestamp,
                    analysis_date, alerted, is_entry, outcome_checked,
                    payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"event_{idx}",
                    "hunt",
                    f"hunt|2026-05-01T10:00:00+09:00|T{idx:03d}",
                    f"T{idx:03d}",
                    "2026-05-01T10:00:00+09:00",
                    "2026-05-01",
                    1,
                    1,
                    1,
                    "{}",
                    "2026-05-06T10:00:00+09:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO jackal_prediction_cards (
                    card_id, event_id, event_kind, ticker, score,
                    current_price, actual_close_d5, market_regime, fear_greed,
                    created_at, status, outcome_d5
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"card_{idx}",
                    f"event_{idx}",
                    "hunt",
                    f"T{idx:03d}",
                    80.0,
                    current_price,
                    close,
                    regime,
                    fear_greed,
                    "2026-05-01T10:00:00+09:00",
                    "resolved",
                    outcome,
                ),
            )

    def _insert_lesson(
        self,
        idx: int,
        *,
        lesson_type: str = "backtest_win",
        value: float = 3.0,
        regime: str = "risk_on",
    ) -> None:
        payload = {
            "ticker": f"L{idx:03d}",
            "regime": regime,
            "signal_family": "panic_rebound",
            "peak_pct": value,
        }
        with state._connect_orca() as conn:
            conn.execute(
                """
                INSERT INTO candidate_registry (
                    candidate_id, external_key, source_system, source_event_type,
                    source_event_id, source_run_id, source_session_id, ticker,
                    name, market, detected_at, analysis_date, signal_family,
                    quality_label, quality_score, orca_alignment, status,
                    payload_json, latest_outcome_horizon, latest_outcome_at,
                    latest_outcome_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"candidate_{idx}",
                    f"candidate|{idx}",
                    "test",
                    "backtest",
                    None,
                    None,
                    None,
                    f"L{idx:03d}",
                    f"L{idx:03d}",
                    "US",
                    "2026-05-01T10:00:00+09:00",
                    "2026-05-01",
                    "panic_rebound",
                    "test",
                    70.0,
                    "neutral",
                    "resolved",
                    "{}",
                    None,
                    None,
                    None,
                    "2026-05-01T10:00:00+09:00",
                    "2026-05-01T10:00:00+09:00",
                ),
            )
            conn.execute(
                """
                INSERT INTO candidate_lessons (
                    lesson_id, candidate_id, outcome_id, lesson_type, label,
                    lesson_value, lesson_timestamp, lesson_json, context_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"lesson_{idx}",
                    f"candidate_{idx}",
                    None,
                    lesson_type,
                    lesson_type.replace("_", " "),
                    value,
                    "2026-05-01T10:00:00+09:00",
                    json.dumps(payload),
                    None,
                ),
            )

    def test_get_memory_mode_default_shadow(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(memory.get_memory_mode(), memory.MEMORY_MODE_SHADOW)

    def test_get_memory_mode_off(self):
        with patch.dict(os.environ, {"JACKAL_MEMORY_PROMPT_MODE": "off"}):
            self.assertEqual(memory.get_memory_mode(), memory.MEMORY_MODE_OFF)

    def test_build_skips_prediction_cards_below_global_min_without_fallback(self):
        result = memory.build_memory_context("AAPL", {"regime": "risk_on", "fear_greed": 67}, "analyst")
        self.assertIsNone(result)

    def test_build_skips_prediction_cards_below_pattern_min(self):
        for idx in range(20):
            self._insert_card(idx, regime="risk_off", fear_greed=30, outcome="loss", close=94.0)

        result = memory.build_memory_context("AAPL", {"regime": "risk_on", "fear_greed": 67}, "analyst")

        self.assertIsNone(result)

    def test_build_returns_stats_block_when_enough_prediction_cards(self):
        for idx in range(6):
            self._insert_card(idx, regime="risk_on", fear_greed=67, outcome="win", close=106.0)
        for idx in range(6, 20):
            self._insert_card(idx, regime="risk_off", fear_greed=30, outcome="loss", close=94.0)

        result = memory.build_memory_context("AAPL", {"regime": "risk_on", "fear_greed": 67}, "devil")

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "prediction_cards")
        self.assertEqual(result["sample_size"], 6)
        self.assertAlmostEqual(result["win_rate"], 1.0)
        self.assertIn("[과거 학습]", result["stats_block"])

    def test_stats_block_under_1000_chars(self):
        block = memory._format_stats_block(
            win_rate=0.8,
            avg_outcome=4.2,
            sample_size=25,
            regime="risk_on",
            fear_greed=67,
            role="analyst",
            source="prediction_cards",
        )

        self.assertLessEqual(len(block), memory.MAX_STATS_BLOCK_CHARS)
        self.assertLessEqual(len(block.splitlines()), 3)

    def test_log_shadow_writes_to_file(self):
        log_path = self.tmpdir / "memory_context_shadow.log"
        context = {"stats_block": "sample", "source": "candidate_lessons"}

        with patch.dict(os.environ, {"JACKAL_MEMORY_SHADOW_LOG": str(log_path)}):
            memory.log_shadow_memory_context(
                "AAPL",
                {"regime": "risk_on", "fear_greed": 67},
                "analyst",
                context,
                mode="shadow",
            )

        rows = log_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(rows), 1)
        data = json.loads(rows[0])
        self.assertEqual(data["ticker"], "AAPL")
        self.assertTrue(data["would_inject"])
        self.assertEqual(data["memory_context"]["source"], "candidate_lessons")

    def test_fallback_to_candidate_lessons(self):
        for idx in range(5):
            self._insert_lesson(idx, lesson_type="backtest_win", value=2.0 + idx, regime="risk_on")
        for idx in range(5, 8):
            self._insert_lesson(idx, lesson_type="backtest_loss", value=-1.0, regime="risk_on")

        result = memory.build_memory_context("AAPL", {"regime": "risk_on", "fear_greed": 67}, "analyst")

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "candidate_lessons")
        self.assertEqual(result["match_scope"], "candidate_lessons_regime")
        self.assertEqual(result["sample_size"], 8)
        self.assertGreater(result["win_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
