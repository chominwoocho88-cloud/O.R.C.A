from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import context_snapshot
from orca import state


def _series(values: list[float]) -> list[tuple[str, float]]:
    return [(f"2026-03-{idx + 1:02d}", value) for idx, value in enumerate(values)]


class ContextSnapshotTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_db = Path(self.tmpdir) / "orca_state.db"
        self.jackal_db = Path(self.tmpdir) / "jackal_state.db"
        self.baseline = Path(self.tmpdir) / "morning_baseline.json"
        self.patchers = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch.object(context_snapshot, "BASELINE_FILE", self.baseline),
        ]
        for patcher in self.patchers:
            patcher.start()
        state.init_state_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_lesson_context_snapshot_table_exists(self):
        with state._connect_orca() as conn:
            row = conn.execute(
                """
                SELECT name
                  FROM sqlite_master
                 WHERE type = 'table'
                   AND name = 'lesson_context_snapshot'
                """
            ).fetchone()

        self.assertIsNotNone(row)

    def test_candidate_lessons_has_context_snapshot_id_column(self):
        with state._connect_orca() as conn:
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(candidate_lessons)").fetchall()
            }

        self.assertIn("context_snapshot_id", columns)

    def test_context_indexes_exist(self):
        with state._connect_orca() as conn:
            indexes = {
                row["name"]
                for row in conn.execute("PRAGMA index_list(lesson_context_snapshot)").fetchall()
            }
            lesson_indexes = {
                row["name"]
                for row in conn.execute("PRAGMA index_list(candidate_lessons)").fetchall()
            }

        self.assertIn("idx_snapshot_date", indexes)
        self.assertIn("idx_snapshot_regime", indexes)
        self.assertIn("idx_lessons_context", lesson_indexes)

    def test_create_snapshot_first_time(self):
        snapshot_data = {
            "regime": "혼조",
            "regime_confidence": 0.35,
            "vix_level": 18.5,
            "vix_delta_7d": -1.2,
            "sp500_momentum_5d": 1.5,
            "sp500_momentum_20d": 4.0,
            "nasdaq_momentum_5d": 2.0,
            "nasdaq_momentum_20d": 5.5,
            "dominant_sectors": ["Technology", "Healthcare"],
        }
        with patch.object(context_snapshot, "_build_snapshot_data", return_value=snapshot_data):
            snapshot_id = context_snapshot.get_or_create_context_snapshot(
                "2026-04-01",
                "backtest",
                source_session_id="bt_ctx",
            )

        stored = state.get_lesson_context_snapshot(snapshot_id)
        self.assertIsNotNone(stored)
        self.assertEqual(stored["trading_date"], "2026-04-01")
        self.assertEqual(stored["source_event_type"], "backtest")
        self.assertEqual(stored["source_session_id"], "bt_ctx")
        self.assertEqual(stored["dominant_sectors"], ["Technology", "Healthcare"])

    def test_get_existing_snapshot_reuses(self):
        with patch.object(
            context_snapshot,
            "_build_snapshot_data",
            return_value={"regime": "혼조", "dominant_sectors": []},
        ) as mocked:
            first = context_snapshot.get_or_create_context_snapshot("2026-04-01", "backtest")
            second = context_snapshot.get_or_create_context_snapshot(
                "2026-04-01",
                "backtest",
                source_session_id="different",
            )

        self.assertEqual(first, second)
        self.assertEqual(mocked.call_count, 1)

    def test_snapshot_default_session_none(self):
        snapshot_id = state.record_lesson_context_snapshot(
            {
                "trading_date": "2026-04-01",
                "source_event_type": "live",
                "dominant_sectors": [],
            }
        )

        stored = state.get_lesson_context_snapshot(snapshot_id)
        self.assertIsNone(stored["source_session_id"])

    def test_fetch_regime_from_orca_report(self):
        with state._connect_orca() as conn:
            session_id = "bt_orca_ctx"
            conn.execute(
                """
                INSERT INTO backtest_sessions (
                    session_id, system, label, started_at, status
                ) VALUES (?, 'orca', 'walk_forward', ?, 'completed')
                """,
                (session_id, "2026-04-01T09:00:00+09:00"),
            )
            conn.execute(
                """
                INSERT INTO backtest_daily_results (
                    session_id, analysis_date, phase_label, analysis_json,
                    results_json, metrics_json, created_at
                ) VALUES (?, ?, 'Final Pass', ?, '[]', '{}', ?)
                """,
                (
                    session_id,
                    "2026-04-01",
                    json.dumps(
                        {
                            "market_regime": "위험선호",
                            "confidence_overall": "높음",
                        },
                        ensure_ascii=False,
                    ),
                    "2026-04-01T10:00:00+09:00",
                ),
            )
            regime, confidence = context_snapshot._fetch_regime_from_orca_report(
                "2026-04-01",
                conn,
            )

        self.assertEqual(regime, "위험선호")
        self.assertEqual(confidence, 1.0)

    def test_fetch_regime_from_baseline(self):
        self.baseline.write_text(
            json.dumps(
                {
                    "date": "2026-04-01",
                    "market_regime": "전환중",
                    "confidence": "보통",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        regime, confidence = context_snapshot._fetch_regime_from_baseline("2026-04-01")

        self.assertEqual(regime, "전환중")
        self.assertEqual(confidence, 0.67)

    def test_fetch_regime_fallback_to_heuristic(self):
        regime, confidence = context_snapshot._heuristic_regime(
            {
                "vix_level": 28.0,
                "sp500_momentum_20d": -2.0,
                "nasdaq_momentum_20d": -3.0,
            }
        )

        self.assertEqual(regime, "위험회피")
        self.assertEqual(confidence, 0.45)

    def test_fetch_regime_returns_none_when_unavailable(self):
        regime, confidence = context_snapshot._heuristic_regime(
            {
                "vix_level": None,
                "sp500_momentum_20d": None,
                "nasdaq_momentum_20d": None,
            }
        )

        self.assertIsNone(regime)
        self.assertIsNone(confidence)

    def test_fetch_market_data_normal(self):
        def fake_history(ticker: str, _date: str, *, lookback_days: int):
            if ticker == "^VIX":
                return _series([20, 21, 22, 23, 24, 25, 26, 27])
            if ticker == "^GSPC":
                return _series([100 + idx for idx in range(21)])
            if ticker == "^IXIC":
                return _series([200 + idx for idx in range(21)])
            return []

        with patch.object(context_snapshot, "_fetch_history_points", side_effect=fake_history):
            data = context_snapshot._fetch_market_data_for_date("2026-04-01")

        self.assertEqual(data["vix_level"], 27)
        self.assertEqual(data["vix_delta_7d"], 7)
        self.assertEqual(data["sp500_momentum_20d"], 20.0)
        self.assertEqual(data["nasdaq_momentum_20d"], 10.0)

    def test_fetch_market_data_handles_empty_history(self):
        with patch.object(context_snapshot, "_fetch_history_points", return_value=[]):
            data = context_snapshot._fetch_market_data_for_date("2026-04-01")

        self.assertIsNone(data["vix_level"])
        self.assertIsNone(data["sp500_momentum_5d"])
        self.assertIsNone(data["nasdaq_momentum_20d"])

    def test_compute_dominant_sectors_returns_top_3(self):
        changes = {
            "XLK": _series([100, 100, 100, 100, 100, 120]),
            "XLV": _series([100, 100, 100, 100, 100, 108]),
            "XLE": _series([100, 100, 100, 100, 100, 115]),
            "XLF": _series([100, 100, 100, 100, 100, 103]),
        }

        def fake_history(ticker: str, _date: str, *, lookback_days: int):
            return changes.get(ticker, [])

        with patch.object(context_snapshot, "_fetch_history_points", side_effect=fake_history):
            sectors = context_snapshot._compute_dominant_sectors("2026-04-01")

        self.assertEqual(sectors, ["Technology", "Energy", "Healthcare"])

    def test_compute_dominant_sectors_excludes_negative(self):
        changes = {
            "XLK": _series([100, 100, 100, 100, 100, 95]),
            "XLV": _series([100, 100, 100, 100, 100, 102]),
        }

        def fake_history(ticker: str, _date: str, *, lookback_days: int):
            return changes.get(ticker, [])

        with patch.object(context_snapshot, "_fetch_history_points", side_effect=fake_history):
            sectors = context_snapshot._compute_dominant_sectors("2026-04-01")

        self.assertEqual(sectors, ["Healthcare"])

    def test_compute_dominant_sectors_handles_missing_data(self):
        with patch.object(context_snapshot, "_fetch_history_points", return_value=[]):
            sectors = context_snapshot._compute_dominant_sectors("2026-04-01")

        self.assertEqual(sectors, [])


if __name__ == "__main__":
    unittest.main()
