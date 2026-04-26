from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import context_snapshot
from orca import state


class Phase12LiveHookTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_db = Path(self.tmpdir) / "orca_state.db"
        self.jackal_db = Path(self.tmpdir) / "jackal_state.db"
        self.patchers = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
        ]
        for patcher in self.patchers:
            patcher.start()
        state.clear_health_events()
        state.init_state_db()

    def tearDown(self):
        state.clear_health_events()
        for patcher in reversed(self.patchers):
            patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed_candidate(
        self,
        *,
        source_event_type: str = "hunt",
        analysis_date: str = "2026-04-20",
        ticker: str = "NVDA",
        source_session_id: str | None = "live_session",
    ) -> str:
        return state.record_candidate(
            {
                "ticker": ticker,
                "analysis_date": analysis_date,
                "timestamp": f"{analysis_date}T09:00:00+09:00",
                "signal_family": "momentum_pullback",
                "quality_score": 72.0,
                "price_at_scan": 100.0,
            },
            source_system="jackal",
            source_event_type=source_event_type,
            source_external_key=f"{source_event_type}:{analysis_date}:{ticker}",
            source_session_id=source_session_id,
        )

    def _lesson_row(self, lesson_id: str):
        with state._connect_orca() as conn:
            return conn.execute(
                """
                SELECT lesson_id, candidate_id, context_snapshot_id, lesson_timestamp
                  FROM candidate_lessons
                 WHERE lesson_id = ?
                """,
                (lesson_id,),
            ).fetchone()

    def _snapshot_row(self, snapshot_id: str):
        with state._connect_orca() as conn:
            return conn.execute(
                """
                SELECT snapshot_id, trading_date, source_event_type, source_session_id
                  FROM lesson_context_snapshot
                 WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()

    def test_record_candidate_lesson_creates_snapshot(self):
        candidate_id = self._seed_candidate(source_event_type="hunt", analysis_date="2026-04-20")
        with patch.object(
            context_snapshot,
            "_build_snapshot_data",
            return_value={"regime": "risk_on", "dominant_sectors": []},
        ):
            lesson_id = state.record_candidate_lesson(
                candidate_id,
                lesson_type="aligned_win",
                label="aligned win",
                lesson_value=2.5,
                lesson={"analysis_date": "2026-04-21"},
            )

        lesson = self._lesson_row(lesson_id)
        self.assertIsNotNone(lesson["context_snapshot_id"])
        snapshot = self._snapshot_row(lesson["context_snapshot_id"])
        self.assertEqual(snapshot["trading_date"], "2026-04-20")
        self.assertEqual(snapshot["source_event_type"], "live")
        self.assertEqual(snapshot["source_session_id"], "live_session")

    def test_record_candidate_lesson_with_existing_snapshot_id_reuses(self):
        candidate_id = self._seed_candidate()
        snapshot_id = state.record_lesson_context_snapshot(
            {
                "snapshot_id": "ctx_manual",
                "trading_date": "2026-04-20",
                "source_event_type": "live",
                "dominant_sectors": [],
            }
        )

        with patch.object(context_snapshot, "get_or_create_context_snapshot") as mocked:
            lesson_id = state.record_candidate_lesson(
                candidate_id,
                lesson_type="aligned_win",
                label="aligned win",
                lesson_value=1.5,
                lesson={"analysis_date": "2026-04-20"},
                context_snapshot_id=snapshot_id,
            )

        mocked.assert_not_called()
        lesson = self._lesson_row(lesson_id)
        self.assertEqual(lesson["context_snapshot_id"], "ctx_manual")

    def test_record_backtest_lesson_creates_backtest_snapshot(self):
        candidate_id = state.record_backtest_candidate(
            {
                "ticker": "AMD",
                "analysis_date": "2026-04-18",
                "timestamp": "2026-04-18T16:00:00+09:00",
                "signal_family": "momentum_pullback",
                "quality_score": 70.0,
            },
            source_external_key="backtest:2026-04-18:AMD",
            source_session_id="bt_live_hook",
        )

        with patch.object(
            context_snapshot,
            "_build_snapshot_data",
            return_value={"regime": "risk_on", "dominant_sectors": []},
        ):
            lesson_id = state.record_backtest_lesson(
                candidate_id,
                lesson_type="backtest_win",
                label="backtest win",
                lesson_value=3.0,
                lesson_timestamp="2026-04-18T16:00:00+09:00",
                lesson={"analysis_date": "2026-04-18", "ticker": "AMD"},
            )

        lesson = self._lesson_row(str(lesson_id))
        snapshot = self._snapshot_row(lesson["context_snapshot_id"])
        self.assertEqual(snapshot["source_event_type"], "backtest")
        self.assertEqual(snapshot["trading_date"], "2026-04-18")
        self.assertEqual(snapshot["source_session_id"], "bt_live_hook")

    def test_lesson_insert_succeeds_when_snapshot_creation_fails(self):
        candidate_id = self._seed_candidate(source_event_type="scan")

        with patch.object(
            context_snapshot,
            "get_or_create_context_snapshot",
            side_effect=RuntimeError("market data unavailable"),
        ):
            lesson_id = state.record_candidate_lesson(
                candidate_id,
                lesson_type="neutral_loss",
                label="neutral loss",
                lesson_value=-1.0,
                lesson={"analysis_date": "2026-04-20"},
            )

        lesson = self._lesson_row(lesson_id)
        self.assertIsNotNone(lesson)
        self.assertIsNone(lesson["context_snapshot_id"])
        events = state.drain_health_events()
        self.assertEqual(events[-1]["code"], "context_snapshot_failed")
        self.assertIn("market data unavailable", events[-1]["message"])

    def test_source_event_type_mapping(self):
        self.assertEqual(state._snapshot_source_event_type("hunt"), "live")
        self.assertEqual(state._snapshot_source_event_type("scan"), "live")
        self.assertEqual(state._snapshot_source_event_type("shadow"), "live")
        self.assertEqual(state._snapshot_source_event_type("backtest"), "backtest")
        self.assertEqual(state._snapshot_source_event_type("manual"), "manual")
        self.assertEqual(state._snapshot_source_event_type(None), "unknown")

    def test_analysis_date_fallback_chain(self):
        candidate_id = self._seed_candidate(analysis_date="2026-04-20")
        with state._connect_orca() as conn:
            metadata = state._get_candidate_context_metadata(conn, candidate_id)
            self.assertEqual(
                state._lesson_context_trading_date(
                    metadata,
                    {"analysis_date": "2026-04-21"},
                    "2026-04-22T09:00:00+09:00",
                ),
                "2026-04-20",
            )
            self.assertEqual(
                state._lesson_context_trading_date(
                    {},
                    {"analysis_date": "2026-04-21"},
                    "2026-04-22T09:00:00+09:00",
                ),
                "2026-04-21",
            )
            self.assertEqual(
                state._lesson_context_trading_date(
                    {},
                    {},
                    "2026-04-22T09:00:00+09:00",
                ),
                "2026-04-22",
            )
            with patch.object(state, "_now_iso", return_value="2026-04-23T09:00:00+09:00"):
                self.assertEqual(state._lesson_context_trading_date({}, {}, None), "2026-04-23")

    def test_concurrent_lesson_inserts_share_snapshot(self):
        first_candidate = self._seed_candidate(
            source_event_type="hunt",
            analysis_date="2026-04-20",
            ticker="AAPL",
        )
        second_candidate = self._seed_candidate(
            source_event_type="hunt",
            analysis_date="2026-04-20",
            ticker="MSFT",
        )

        with patch.object(
            context_snapshot,
            "_build_snapshot_data",
            return_value={"regime": "risk_on", "dominant_sectors": []},
        ) as mocked:
            first_lesson = state.record_candidate_lesson(
                first_candidate,
                lesson_type="aligned_win",
                label="aligned win",
                lesson_value=1.0,
            )
            second_lesson = state.record_candidate_lesson(
                second_candidate,
                lesson_type="aligned_win",
                label="aligned win",
                lesson_value=2.0,
            )

        first_row = self._lesson_row(first_lesson)
        second_row = self._lesson_row(second_lesson)
        self.assertEqual(first_row["context_snapshot_id"], second_row["context_snapshot_id"])
        self.assertEqual(mocked.call_count, 1)

    def test_get_candidate_context_metadata_missing_candidate(self):
        with state._connect_orca() as conn:
            self.assertEqual(state._get_candidate_context_metadata(conn, "missing"), {})

    def test_sync_candidate_probability_lesson_creates_snapshot(self):
        candidate_id = state.record_candidate(
            {
                "ticker": "TSLA",
                "analysis_date": "2026-04-19",
                "timestamp": "2026-04-19T09:00:00+09:00",
                "signal_family": "momentum_pullback",
                "quality_score": 72.0,
                "price_at_scan": 100.0,
                "price_1d_later": 104.0,
                "outcome_1d_pct": 4.0,
                "outcome_1d_hit": True,
                "outcome_tracked_at": "2026-04-20T16:00:00+09:00",
            },
            source_system="jackal",
            source_event_type="scan",
            source_external_key="scan:2026-04-19:TSLA",
            source_session_id="scan_sync",
        )

        with patch.object(
            context_snapshot,
            "_build_snapshot_data",
            return_value={"regime": "risk_on", "dominant_sectors": []},
        ):
            state.record_candidate_review(
                candidate_id,
                analysis_date="2026-04-19",
                alignment="aligned",
                review_verdict="approved",
                orca_regime="risk_on",
            )

        with state._connect_orca() as conn:
            row = conn.execute(
                """
                SELECT l.context_snapshot_id, s.source_event_type, s.trading_date
                  FROM candidate_lessons l
                  JOIN lesson_context_snapshot s
                    ON s.snapshot_id = l.context_snapshot_id
                 WHERE l.candidate_id = ?
                """,
                (candidate_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["source_event_type"], "live")
        self.assertEqual(row["trading_date"], "2026-04-19")

    def test_existing_lessons_unaffected(self):
        old_candidate = self._seed_candidate(ticker="OLD", analysis_date="2026-04-10")
        old_lesson_id = state.record_candidate_lesson(
            old_candidate,
            lesson_type="aligned_win",
            label="old aligned win",
            lesson_value=1.0,
            auto_context_snapshot=False,
        )
        new_candidate = self._seed_candidate(ticker="NEW", analysis_date="2026-04-11")

        with patch.object(
            context_snapshot,
            "_build_snapshot_data",
            return_value={"regime": "risk_on", "dominant_sectors": []},
        ):
            new_lesson_id = state.record_candidate_lesson(
                new_candidate,
                lesson_type="aligned_win",
                label="new aligned win",
                lesson_value=1.0,
            )

        self.assertIsNone(self._lesson_row(old_lesson_id)["context_snapshot_id"])
        self.assertIsNotNone(self._lesson_row(new_lesson_id)["context_snapshot_id"])


if __name__ == "__main__":
    unittest.main()
