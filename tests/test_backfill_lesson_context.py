from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from orca import context_snapshot
from orca import context_market_data
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
        cache[ticker] = _points([100 + idx for idx in range(30)])
    cache["XLK"] = _points([100 + idx * 4 for idx in range(30)])
    cache["XLE"] = _points([100 + idx * 3 for idx in range(30)])
    cache["XLV"] = _points([100 + idx * 2 for idx in range(30)])
    return cache


def _single_ticker_frame(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"Close": values},
        index=pd.to_datetime([f"2026-03-{idx + 1:02d}" for idx in range(len(values))]),
    )


class _FakeResponse:
    def __init__(self, text: str, error: Exception | None = None):
        self.text = text
        self._error = error

    def raise_for_status(self):
        if self._error:
            raise self._error


def _alpha_csv(rows: list[tuple[str, float]]) -> str:
    lines = ["timestamp,open,high,low,close,volume"]
    for date, close in rows:
        lines.append(f"{date},{close - 1},{close + 1},{close - 2},{close},1000")
    return "\n".join(lines)


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
        self._seed_backtest_lesson("2026-03-25", "AAA")
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

        with patch.object(context_market_data, "yf") as fake_yf, patch.object(
            context_market_data.time,
            "sleep",
        ):
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

        with patch.object(context_market_data, "yf") as fake_yf, patch.object(
            context_market_data.time,
            "sleep",
        ):
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

    def test_verify_backfill_completeness_passes_when_complete(self):
        self._seed_backtest_lesson("2026-03-25", "AAA")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            context_snapshot.backfill_lessons_context()

        result = context_snapshot.verify_backfill_completeness(
            expected_snapshots=1,
            expected_linked_lessons=1,
            require_market_metrics=True,
        )

        self.assertTrue(result["passed"], result["failures"])
        self.assertEqual(result["snapshots_backfill"], 1)
        self.assertEqual(result["lessons_linked"], 1)
        self.assertEqual(result["lessons_unlinked"], 0)
        self.assertEqual(result["vix_filled"], 1)
        self.assertEqual(result["sectors_filled"], 1)

    def test_verify_backfill_completeness_fails_when_missing_metrics(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value={},
        ):
            context_snapshot.backfill_lessons_context()

        result = context_snapshot.verify_backfill_completeness(
            expected_snapshots=1,
            expected_linked_lessons=1,
            require_market_metrics=True,
        )

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("vix_level" in failure for failure in result["failures"]),
            result["failures"],
        )
        self.assertTrue(
            any("dominant_sectors" in failure for failure in result["failures"]),
            result["failures"],
        )

    def test_verify_backfill_completeness_fails_when_unlinked_lessons(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")

        result = context_snapshot.verify_backfill_completeness(
            expected_snapshots=0,
            expected_linked_lessons=0,
            require_market_metrics=False,
        )

        self.assertFalse(result["passed"])
        self.assertTrue(
            any("unlinked backtest lessons remain" in failure for failure in result["failures"]),
            result["failures"],
        )

    def test_cleanup_backfill_data_removes_backfill_snapshots(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            context_snapshot.backfill_lessons_context()

        result = context_snapshot.cleanup_backfill_data()

        self.assertEqual(result["snapshots_deleted"], 1)
        self.assertEqual(self._context_count(), 0)

    def test_cleanup_backfill_data_preserves_live_snapshots(self):
        with state._connect_orca() as conn:
            state.record_lesson_context_snapshot(
                {
                    "snapshot_id": "ctx_live_1",
                    "created_at": "2026-03-10T09:00:00",
                    "trading_date": "2026-03-10",
                    "regime": "risk_on",
                    "regime_confidence": 0.7,
                    "vix_level": 18.0,
                    "vix_delta_7d": -1.2,
                    "sp500_momentum_5d": 1.0,
                    "sp500_momentum_20d": 3.0,
                    "nasdaq_momentum_5d": 1.5,
                    "nasdaq_momentum_20d": 4.0,
                    "dominant_sectors": '["Technology"]',
                    "source_event_type": "live",
                    "source_session_id": "live_session",
                },
                conn=conn,
            )

        result = context_snapshot.cleanup_backfill_data()

        self.assertEqual(result["snapshots_deleted"], 0)
        with state._connect_orca() as conn:
            live = state.get_lesson_context_snapshot("ctx_live_1", conn=conn)
        self.assertIsNotNone(live)
        self.assertEqual(self._context_count(), 1)

    def test_cleanup_backfill_data_unlinks_lessons(self):
        self._seed_backtest_lesson("2026-03-10", "AAA")
        with patch.object(
            context_snapshot,
            "_fetch_historical_market_data_range",
            return_value=_cached_market_data(),
        ):
            context_snapshot.backfill_lessons_context()

        result = context_snapshot.cleanup_backfill_data()

        self.assertEqual(result["lessons_unlinked"], 1)
        self.assertEqual(self._linked_count(), 0)

    def test_yfinance_batch_retry_succeeds_after_429(self):
        calls = []

        def fake_download(**_kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("Too Many Requests")
            return _single_ticker_frame([100, 101, 102])

        with patch.object(context_market_data, "yf") as fake_yf, patch.object(
            context_market_data.time,
            "sleep",
        ) as fake_sleep:
            fake_yf.download.side_effect = fake_download
            frame = context_market_data._fetch_yfinance_batch_with_retry(
                ("XLK",),
                "2026-03-01",
                "2026-03-10",
            )

        self.assertFalse(frame.empty)
        self.assertEqual(len(calls), 3)
        fake_sleep.assert_any_call(2)
        fake_sleep.assert_any_call(8)

    def test_yfinance_batch_retry_max_attempts_raises(self):
        with patch.object(context_market_data, "yf") as fake_yf, patch.object(
            context_market_data.time,
            "sleep",
        ):
            fake_yf.download.side_effect = RuntimeError("Too Many Requests")
            with self.assertRaises(RuntimeError):
                context_market_data._fetch_yfinance_batch_with_retry(
                    ("XLK",),
                    "2026-03-01",
                    "2026-03-10",
                )

        self.assertEqual(fake_yf.download.call_count, 3)

    def test_yfinance_ticker_retry_with_backoff(self):
        calls = []

        def fake_download(**_kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("rate limit")
            return _single_ticker_frame([100, 101, 102])

        with patch.object(context_market_data, "yf") as fake_yf, patch.object(
            context_market_data.time,
            "sleep",
        ) as fake_sleep:
            fake_yf.download.side_effect = fake_download
            frame = context_market_data._fetch_yfinance_ticker_with_retry(
                "XLK",
                "2026-03-01",
                "2026-03-10",
            )

        self.assertFalse(frame.empty)
        self.assertEqual(len(calls), 2)
        fake_sleep.assert_any_call(1)
        fake_sleep.assert_any_call(2)

    def test_yfinance_ticker_max_retries(self):
        with patch.object(context_market_data, "yf") as fake_yf, patch.object(
            context_market_data.time,
            "sleep",
        ):
            fake_yf.download.side_effect = RuntimeError("rate limit")
            with self.assertRaises(RuntimeError):
                context_market_data._fetch_yfinance_ticker_with_retry(
                    "XLK",
                    "2026-03-01",
                    "2026-03-10",
                )

        self.assertEqual(fake_yf.download.call_count, 3)

    def test_alpha_vantage_fetch_success(self):
        csv = _alpha_csv(
            [
                ("2026-03-03", 100),
                ("2026-03-04", 101),
                ("2026-03-05", 102),
            ]
        )
        with patch("requests.get", return_value=_FakeResponse(csv)) as fake_get:
            frame = context_market_data._fetch_alpha_vantage_history(
                "XLK",
                "2026-03-01",
                "2026-03-10",
                api_key="key",
            )

        self.assertEqual(list(frame["Close"]), [100, 101, 102])
        self.assertEqual(fake_get.call_args.kwargs["params"]["symbol"], "XLK")
        self.assertEqual(fake_get.call_args.kwargs["params"]["outputsize"], "full")

    def test_alpha_vantage_premium_notice_falls_back_to_compact(self):
        premium = '{"Information": "premium endpoint"}'
        compact = _alpha_csv([("2026-03-04", 101)])
        with patch(
            "requests.get",
            side_effect=[_FakeResponse(premium), _FakeResponse(compact)],
        ) as fake_get:
            frame = context_market_data._fetch_alpha_vantage_history(
                "XLK",
                "2026-03-01",
                "2026-03-10",
                api_key="key",
            )

        self.assertEqual(float(frame.iloc[0]["Close"]), 101.0)
        output_sizes = [call.kwargs["params"]["outputsize"] for call in fake_get.call_args_list]
        self.assertEqual(output_sizes, ["full", "compact"])

    def test_alpha_vantage_no_api_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                context_market_data._fetch_alpha_vantage_history(
                    "XLK",
                    "2026-03-01",
                    "2026-03-10",
                )

    def test_alpha_vantage_ticker_mapping(self):
        self.assertEqual(context_market_data._alpha_vantage_ticker("^VIX"), "VIXY")
        self.assertEqual(context_market_data._alpha_vantage_ticker("^GSPC"), "SPY")
        self.assertEqual(context_market_data._alpha_vantage_ticker("^IXIC"), "QQQ")
        self.assertEqual(context_market_data._alpha_vantage_ticker("XLK"), "XLK")

    def test_alpha_vantage_csv_parsing_and_date_filter(self):
        csv = _alpha_csv(
            [
                ("2026-02-28", 99),
                ("2026-03-03", 100),
                ("2026-03-04", 101),
                ("2026-03-20", 110),
            ]
        )

        frame = context_market_data._parse_alpha_vantage_csv(
            csv,
            "2026-03-01",
            "2026-03-10",
        )

        self.assertEqual(list(frame["Close"]), [100, 101])
        self.assertEqual(frame.index[0].strftime("%Y-%m-%d"), "2026-03-03")

    def test_fetch_with_fallback_uses_yfinance_first(self):
        frame = _single_ticker_frame([100, 101])
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            return_value=frame,
        ), patch.object(context_market_data, "_fetch_alpha_vantage_with_retry") as alpha:
            result, source = context_market_data._fetch_with_fallback(
                "XLK",
                "2026-03-01",
                "2026-03-10",
                av_api_key="key",
            )

        self.assertIs(result, frame)
        self.assertEqual(source, "yfinance_ticker")
        alpha.assert_not_called()

    def test_fetch_with_fallback_uses_alpha_vantage_when_yfinance_fails(self):
        frame = _single_ticker_frame([100, 101])
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            side_effect=RuntimeError("rate limit"),
        ), patch.object(
            context_market_data,
            "_fetch_alpha_vantage_with_retry",
            return_value=frame,
        ):
            result, source = context_market_data._fetch_with_fallback(
                "XLK",
                "2026-03-01",
                "2026-03-10",
                av_api_key="key",
            )

        self.assertIs(result, frame)
        self.assertEqual(source, "alpha_vantage")

    def test_fetch_with_fallback_no_api_key_skips_alpha_vantage(self):
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            side_effect=RuntimeError("rate limit"),
        ), patch.object(context_market_data, "_fetch_alpha_vantage_with_retry") as alpha:
            result, source = context_market_data._fetch_with_fallback(
                "XLK",
                "2026-03-01",
                "2026-03-10",
                av_api_key=None,
            )

        self.assertIsNone(result)
        self.assertIsNone(source)
        alpha.assert_not_called()

    def test_fetch_with_fallback_returns_none_when_both_fail(self):
        with patch.object(
            context_market_data,
            "_fetch_yfinance_ticker_with_retry",
            side_effect=RuntimeError("rate limit"),
        ), patch.object(
            context_market_data,
            "_fetch_alpha_vantage_with_retry",
            side_effect=RuntimeError("api limit"),
        ):
            result, source = context_market_data._fetch_with_fallback(
                "XLK",
                "2026-03-01",
                "2026-03-10",
                av_api_key="key",
            )

        self.assertIsNone(result)
        self.assertIsNone(source)

    def test_source_tracking_counters_accurate(self):
        frame = _single_ticker_frame([100, 101, 102])

        def fake_fallback(ticker: str, *_args, **_kwargs):
            if ticker == "^VIX":
                return frame, "yfinance_ticker"
            if ticker == "^GSPC":
                return frame, "alpha_vantage"
            return None, None

        with patch.object(
            context_market_data,
            "_fetch_yfinance_batch_with_retry",
            side_effect=RuntimeError("batch failed"),
        ), patch.object(
            context_market_data,
            "_fetch_with_fallback",
            side_effect=fake_fallback,
        ), patch("builtins.print") as fake_print:
            data = context_snapshot._fetch_historical_market_data_range(
                "2026-03-10",
                "2026-03-10",
            )

        self.assertTrue(data["^VIX"])
        self.assertTrue(data["^GSPC"])
        printed = "\n".join(str(call.args[0]) for call in fake_print.call_args_list)
        self.assertIn("yfinance_ticker_success=1", printed)
        self.assertIn("alpha_vantage_success=1", printed)
        self.assertIn("failed=12", printed)


if __name__ == "__main__":
    unittest.main()
