from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from orca import context_snapshot
from orca import state


def _points(values: list[float], *, start_day: int = 1) -> list[tuple[str, float]]:
    return [(f"2026-03-{start_day + idx:02d}", value) for idx, value in enumerate(values)]


def _cached_market_data() -> dict[str, list[tuple[str, float]]]:
    base = _points([100 + idx for idx in range(30)])
    cache = {
        "^VIX": _points([20 + idx for idx in range(30)]),
        "^GSPC": base,
        "^IXIC": _points([200 + idx for idx in range(30)]),
    }
    for ticker in context_snapshot.SECTOR_ETFS:
        cache[ticker] = _points([100, 100, 100, 100, 100, 101])
    cache["XLK"] = _points([100, 100, 100, 100, 100, 120])
    cache["XLE"] = _points([100, 100, 100, 100, 100, 115])
    cache["XLV"] = _points([100, 100, 100, 100, 100, 110])
    return cache


def _single_ticker_frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"Close": values},
        index=pd.to_datetime([f"2026-03-{idx + 1:02d}" for idx in range(len(values))]),
    )


class BackfillLessonContextTests(unittest.TestCase):
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
        state.init_state_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed_backtest_lesson(
        self,
        trading_date: str,
        ticker: str,
        *,
        regime: str = "위험선호",
        source_session_id: str = "bt_seed",
    ) -> str:
        candidate_id = state.record_backtest_candidate(
            {
                "ticker": ticker,
                "analysis_date": trading_date,
                "timestamp": f"{trading_date}T16:00:00+09:00",
                "signal_family": "momentum_pullback",
                "quality_score": 70.0,
                "market": "USA",
            },
            source_external_key=f"backtest:{trading_date}:{ticker}",
            source_session_id=source_session_id,
        )
        lesson_id = state.record_backtest_lesson(
            candidate_id,
            lesson_type="backtest_win",
            label="backtest win",
            lesson_value=2.5,
            lesson_timestamp=f"{trading_date}T16:00:00+09:00",
            lesson={
                "origin": "backtest",
                "analysis_date": trading_date,
                "ticker": ticker,
                "regime": regime,
                "signal_family": "momentum_pullback",
            },
        )
        self.assertIsNotNone(lesson_id)
        return str(lesson_id)

    def _context_count(self) -> int:
        with state._connect_orca() as conn:
            return conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot").fetchone()[0]

    def _linked_count(self) -> int:
        with state._connect_orca() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM candidate_lessons WHERE context_snapshot_id IS NOT NULL"
            ).fetchone()[0]

    def test_backfill_dry_run_no_db_changes(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with patch.object(context_snapshot, "_fetch_historical_market_data_range") as fetch:
            result = context_snapshot.backfill_lessons_context(dry_run=True)

        fetch.assert_not_called()
        self.assertEqual(result["lessons_processed"], 1)
        self.assertEqual(result["snapshots_created"], 1)
        self.assertEqual(self._context_count(), 0)
        self.assertEqual(self._linked_count(), 0)

    def test_backfill_creates_snapshots_for_distinct_dates(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        self._seed_backtest_lesson("2026-03-10", "BBB")
        self._seed_backtest_lesson("2026-03-11", "CCC")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            result = context_snapshot.backfill_lessons_context()

        self.assertEqual(result["snapshots_created"], 2)
        self.assertEqual(result["lessons_processed"], 3)
        self.assertEqual(self._context_count(), 2)
        self.assertEqual(self._linked_count(), 3)

    def test_backfill_reuses_existing_snapshots(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with state._connect_orca() as conn:
            existing_id = state.record_lesson_context_snapshot(
                {
                    "trading_date": "2026-03-10",
                    "source_event_type": context_snapshot.BACKFILL_SOURCE_EVENT_TYPE,
                    "dominant_sectors": [],
                },
                conn=conn,
            )
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            result = context_snapshot.backfill_lessons_context()

        self.assertEqual(result["snapshots_reused"], 1)
        self.assertEqual(result["snapshots_created"], 0)
        with state._connect_orca() as conn:
            row = conn.execute("SELECT context_snapshot_id FROM candidate_lessons").fetchone()
        self.assertEqual(row["context_snapshot_id"], existing_id)

    def test_backfill_processes_only_null_context(self):
        first = self._seed_backtest_lesson("2026-03-10", "AAA")
        self._seed_backtest_lesson("2026-03-11", "BBB")
        with state._connect_orca() as conn:
            existing_id = state.record_lesson_context_snapshot(
                {
                    "trading_date": "2026-03-10",
                    "source_event_type": context_snapshot.BACKFILL_SOURCE_EVENT_TYPE,
                    "dominant_sectors": [],
                },
                conn=conn,
            )
            conn.execute(
                "UPDATE candidate_lessons SET context_snapshot_id = ? WHERE lesson_id = ?",
                (existing_id, first),
            )
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            result = context_snapshot.backfill_lessons_context()

        self.assertEqual(result["lessons_processed"], 1)
        self.assertEqual(self._linked_count(), 2)

    def test_backfill_idempotent(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            first = context_snapshot.backfill_lessons_context()
            second = context_snapshot.backfill_lessons_context()

        self.assertEqual(first["snapshots_created"], 1)
        self.assertEqual(second["snapshots_created"], 0)
        self.assertEqual(second["lessons_processed"], 0)
        self.assertEqual(self._context_count(), 1)

    def test_backfill_handles_yfinance_batch_failure(self):
        def fake_download(*, tickers, **_kwargs):
            if isinstance(tickers, list):
                raise RuntimeError("batch failed")
            return _single_ticker_frame([100, 101, 102, 103, 104, 105])

        with patch.object(context_snapshot, "yf") as fake_yf:
            fake_yf.download.side_effect = fake_download
            data = context_snapshot._fetch_historical_market_data_range(
                "2026-03-10",
                "2026-03-10",
            )

        self.assertTrue(data["^VIX"])
        self.assertTrue(data["XLK"])

    def test_backfill_per_ticker_fallback_on_batch_failure(self):
        calls: list[object] = []

        def fake_download(*, tickers, **_kwargs):
            calls.append(tickers)
            if isinstance(tickers, list):
                raise RuntimeError("batch failed")
            return _single_ticker_frame([100, 101, 102, 103, 104, 105])

        with patch.object(context_snapshot, "yf") as fake_yf:
            fake_yf.download.side_effect = fake_download
            context_snapshot._fetch_historical_market_data_range("2026-03-10", "2026-03-10")

        self.assertIsInstance(calls[0], list)
        self.assertIn("^VIX", calls[1:])

    def test_backfill_limit_processes_only_n_dates(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        self._seed_backtest_lesson("2026-03-11", "BBB")
        self._seed_backtest_lesson("2026-03-12", "CCC")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            result = context_snapshot.backfill_lessons_context(limit=2)

        self.assertEqual(result["dates_processed"], 2)
        self.assertEqual(result["lessons_processed"], 2)
        self.assertEqual(self._linked_count(), 2)

    def test_backfill_summary_counters_accurate(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        self._seed_backtest_lesson("2026-03-11", "BBB")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            result = context_snapshot.backfill_lessons_context(limit=1)

        self.assertEqual(result["lessons_total"], 2)
        self.assertEqual(result["lessons_processed"], 1)
        self.assertEqual(result["lessons_skipped"], 1)
        self.assertEqual(result["snapshots_created"], 1)

    def test_backfill_provenance_source_event_type(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            context_snapshot.backfill_lessons_context()

        with state._connect_orca() as conn:
            row = conn.execute("SELECT source_event_type FROM lesson_context_snapshot").fetchone()
        self.assertEqual(row["source_event_type"], "backtest_backfill")

    def test_backfill_failed_date_does_not_block_others(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        self._seed_backtest_lesson("2026-03-11", "BBB")

        def fake_metrics(trading_date: str, _cache: dict):
            if trading_date == "2026-03-10":
                raise RuntimeError("bad date")
            return {
                "vix_level": 20.0,
                "vix_delta_7d": None,
                "sp500_momentum_5d": 1.0,
                "sp500_momentum_20d": 2.0,
                "nasdaq_momentum_5d": 1.0,
                "nasdaq_momentum_20d": 2.0,
                "dominant_sectors": ["Technology"],
            }

        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ), patch.object(context_snapshot, "_compute_metrics_for_date", side_effect=fake_metrics):
            result = context_snapshot.backfill_lessons_context()

        self.assertEqual(len(result["failed_dates"]), 1)
        self.assertEqual(result["lessons_processed"], 1)
        self.assertEqual(self._linked_count(), 1)

    def test_backfill_uses_lesson_json_regime(self):
        self._seed_backtest_lesson("2026-03-10", "AAA", regime="위험회피")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            context_snapshot.backfill_lessons_context()

        with state._connect_orca() as conn:
            row = conn.execute("SELECT regime FROM lesson_context_snapshot").fetchone()
        self.assertEqual(row["regime"], "위험회피")


if __name__ == "__main__":
    unittest.main()
