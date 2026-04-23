from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from jackal import backtest
from jackal import backtest_materialization as materialization
from orca import state


def _report(day: date) -> dict:
    return {
        "analysis_date": day.isoformat(),
        "mode": "MORNING",
        "market_regime": "위험선호",
        "inflows": [{"zone": "semiconductor", "reason": "rotation"}],
        "outflows": [{"zone": "utilities", "reason": "defensive"}],
        "one_line_summary": "risk-on session",
    }


class JackalBacktestUniverseTests(unittest.TestCase):
    def test_build_universe_uses_portfolio_exclusions(self):
        pools = {
            "alpha": ["AAA", "BBB", "CCC"],
            "beta": ["BBB", "DDD"],
        }
        with patch.object(backtest, "SECTOR_POOLS", pools), patch.object(
            backtest, "get_portfolio_exclusions", return_value={"BBB", "DDD"}
        ):
            universe = backtest._build_universe()

        self.assertEqual(universe, ["AAA", "CCC"])


class BacktestOutcomeTests(unittest.TestCase):
    def test_track_outcome_includes_price_fields(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "Close": [100, 101, 102, 104, 103, 105],
            },
            index=pd.to_datetime(
                [
                    "2026-01-02",
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-07",
                    "2026-01-08",
                    "2026-01-09",
                ]
            ),
        )

        outcome = backtest.track_outcome(df, "2026-01-02", tracking_days=5)

        self.assertEqual(outcome["entry_price"], 100.0)
        self.assertEqual(outcome["price_1d_later"], 101.0)
        self.assertEqual(outcome["price_peak"], 105.0)
        self.assertEqual(outcome["peak_day"], 5)
        self.assertTrue(outcome["swing_hit"])
        self.assertEqual(outcome["tracked_bars"], 5)

    def test_track_outcome_handles_missing_future_rows(self):
        import pandas as pd

        df = pd.DataFrame({"Close": [100]}, index=pd.to_datetime(["2026-01-02"]))
        outcome = backtest.track_outcome(df, "2026-01-02", tracking_days=5)

        self.assertIsNone(outcome["entry_price"])
        self.assertIsNone(outcome["price_peak"])
        self.assertEqual(outcome["tracked_bars"], 0)


class BacktestSelectionTests(unittest.TestCase):
    def test_merge_reports_by_analysis_date_prefers_first_source(self):
        first = [{"analysis_date": "2026-01-02", "mode": "MORNING", "value": "orca"}]
        second = [
            {"analysis_date": "2026-01-02", "mode": "MORNING", "value": "memory"},
            {"analysis_date": "2026-01-03", "mode": "MORNING", "value": "memory-new"},
        ]

        merged = materialization.merge_reports_by_analysis_date(first, second)

        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["value"], "orca")
        self.assertEqual(merged[1]["value"], "memory-new")

    def test_select_backtest_reports_full_uses_trading_day_count(self):
        reports = [_report(date(2025, 1, 1) + timedelta(days=offset)) for offset in range(300)]

        selected = materialization.select_backtest_reports(
            reports,
            backtest_days=252,
            tracking_days=10,
        )

        self.assertEqual(len(selected), 252)
        self.assertEqual(selected[0]["analysis_date"], reports[38]["analysis_date"])
        self.assertEqual(selected[-1]["analysis_date"], reports[289]["analysis_date"])

    def test_select_backtest_reports_incremental_uses_cursor(self):
        reports = [_report(date(2026, 1, 1) + timedelta(days=offset)) for offset in range(25)]
        cursor = reports[11]["analysis_date"]

        selected = materialization.select_backtest_reports(
            reports,
            backtest_days=252,
            tracking_days=10,
            after_analysis_date=cursor,
        )

        self.assertEqual([row["analysis_date"] for row in selected], [reports[12]["analysis_date"], reports[13]["analysis_date"], reports[14]["analysis_date"]])

    def test_load_memory_full_uses_selected_window(self):
        reports = [_report(date(2025, 1, 1) + timedelta(days=offset)) for offset in range(280)]
        with patch.object(backtest, "_load_all_morning_reports", return_value=(reports, {"source": "mock"})):
            selected, source_info = backtest.load_memory(mode=backtest.BACKTEST_MODE_FULL)

        self.assertEqual(len(selected), 252)
        self.assertEqual(source_info["selection_mode"], "full")
        self.assertIsNone(source_info["incremental_from_analysis_date"])

    def test_load_memory_incremental_respects_cursor(self):
        reports = [_report(date(2026, 1, 1) + timedelta(days=offset)) for offset in range(25)]
        with patch.object(backtest, "_load_all_morning_reports", return_value=(reports, {"source": "mock"})), patch.object(
            backtest, "_load_incremental_cursor", return_value=reports[11]["analysis_date"]
        ):
            selected, source_info = backtest.load_memory(mode=backtest.BACKTEST_MODE_INCREMENTAL)

        self.assertEqual(len(selected), 3)
        self.assertEqual(source_info["incremental_from_analysis_date"], reports[11]["analysis_date"])

    def test_load_memory_incremental_returns_empty_when_no_new_reports(self):
        reports = [_report(date(2026, 1, 1) + timedelta(days=offset)) for offset in range(15)]
        with patch.object(backtest, "_load_all_morning_reports", return_value=(reports, {"source": "mock"})), patch.object(
            backtest, "_load_incremental_cursor", return_value=reports[4]["analysis_date"]
        ):
            selected, source_info = backtest.load_memory(mode=backtest.BACKTEST_MODE_INCREMENTAL)

        self.assertEqual(selected, [])
        self.assertEqual(source_info["selection_mode"], "incremental")


class BacktestSignalTests(unittest.TestCase):
    def test_build_backtest_signals_detects_core_rules(self):
        signals = materialization.build_backtest_signals(
            ticker="NVDA",
            tech={
                "price": 98,
                "ma50": 100,
                "rsi": 28,
                "bb_pos": 10,
                "change_5d": -6,
                "vol_ratio": 2.2,
                "bullish_div": True,
            },
            inflows_text="semiconductor ai",
            sector_inflow_match=True,
        )

        self.assertIn("rsi_oversold", signals)
        self.assertIn("bb_touch", signals)
        self.assertIn("volume_climax", signals)
        self.assertIn("momentum_dip", signals)
        self.assertIn("rsi_divergence", signals)
        self.assertIn("ma_support", signals)
        self.assertIn("sector_rebound", signals)

    def test_build_backtest_quality_label_thresholds(self):
        self.assertEqual(materialization.build_backtest_quality_label(85), "최강")
        self.assertEqual(materialization.build_backtest_quality_label(70), "강")
        self.assertEqual(materialization.build_backtest_quality_label(55), "보통")
        self.assertEqual(materialization.build_backtest_quality_label(35), "약")

    def test_infer_market_uses_ticker_suffix(self):
        self.assertEqual(materialization.infer_market("005930.KS"), "KRX-KS")
        self.assertEqual(materialization.infer_market("035720.KQ"), "KRX-KQ")
        self.assertEqual(materialization.infer_market("AAPL"), "US")


class BacktestFamilyInferenceTests(unittest.TestCase):
    def _assert_inference(self, signals: list[str], expected_family: str, expected_raw: str):
        family, raw = materialization.infer_backtest_family(signals)
        self.assertEqual(family, expected_family)
        self.assertEqual(raw, expected_raw)

    def test_infer_backtest_family_rotation(self):
        self._assert_inference(["sector_rebound"], "rotation", "sector_rebound")

    def test_infer_backtest_family_panic_rebound(self):
        self._assert_inference(
            ["volume_climax", "momentum_dip"],
            "panic_rebound",
            "volume_climax",
        )

    def test_infer_backtest_family_momentum_pullback(self):
        self._assert_inference(["momentum_dip"], "momentum_pullback", "momentum_dip")

    def test_infer_backtest_family_ma_reclaim(self):
        self._assert_inference(["ma_support"], "ma_reclaim", "ma_support")

    def test_infer_backtest_family_divergence(self):
        self._assert_inference(["rsi_divergence"], "divergence", "rsi_divergence")

    def test_infer_backtest_family_oversold_rebound(self):
        self._assert_inference(
            ["rsi_oversold", "bb_touch"],
            "oversold_rebound",
            "rsi_oversold",
        )

    def test_infer_backtest_family_general_rebound(self):
        self._assert_inference([], "general_rebound", "general")

    def test_build_backtest_candidate_entry_uses_family_inference(self):
        entry = materialization.build_backtest_candidate_entry(
            session_id="bt_jackal_entry",
            source_session_id="bt_orca_entry",
            analysis_date="2026-04-01",
            ticker="AMD",
            rank_index=1,
            regime="위험선호",
            inflows=["semiconductor"],
            outflows=[],
            market_note="risk on",
            tech={"price": 100.0, "rsi": 31.0, "bb_pos": 14.0},
            quality_score=72.0,
            signals_fired=["rsi_oversold", "bb_touch"],
        )

        self.assertEqual(entry["signal_family"], "oversold_rebound")
        self.assertEqual(entry["signal_family_raw"], "rsi_oversold")


class BacktestMaterializationIntegrationTests(unittest.TestCase):
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

    def _daily_pick(self) -> list[dict]:
        return [
            {
                "rank_index": 1,
                "ticker": "NVDA",
                "sector_inflow_match": True,
                "scores": {"s1_score": 66.0, "s2_score": 74.0},
                "indicators": {
                    "price": 100.0,
                    "ma50": 98.0,
                    "rsi": 29.0,
                    "bb_pos": 12.0,
                    "change_5d": -6.5,
                    "vol_ratio": 2.1,
                    "bullish_div": True,
                },
                "outcome": {
                    "entry_price": 100.0,
                    "price_1d_later": 101.0,
                    "price_peak": 105.5,
                    "peak_day": 3,
                    "peak_pct": 5.5,
                    "final_pct": 3.2,
                    "d1_pct": 1.0,
                    "d1_hit": True,
                    "swing_hit": True,
                    "tracked_bars": 10,
                },
            }
        ]

    def test_materialize_backtest_day_writes_candidate_spine(self):
        result = materialization.materialize_backtest_day(
            session_id="bt_jackal_1",
            source_session_id="bt_orca_1",
            analysis_date="2026-04-01",
            regime="위험선호",
            inflows=["semiconductor", "ai"],
            outflows=["utilities"],
            inflows_text="semiconductor ai",
            market_note="risk on",
            daily_picks=self._daily_pick(),
            tracking_days=10,
        )

        self.assertEqual(result["candidates"], 1)
        self.assertEqual(result["outcomes"], 1)
        self.assertEqual(result["lessons"], 1)

        candidates = state.list_candidates(source_system="jackal", source_event_type="backtest")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["signal_family"], "divergence")
        self.assertEqual(candidates[0]["signal_family_raw"], "rsi_divergence")
        self.assertEqual(candidates[0]["status"], "resolved")
        self.assertEqual(candidates[0]["latest_outcome_horizon"], "swing")

        outcomes = state.list_candidate_outcomes(candidates[0]["candidate_id"])
        self.assertEqual({item["horizon_label"] for item in outcomes}, {"d1", "swing"})

    def test_materialize_backtest_day_is_idempotent_for_candidate_and_lessons(self):
        kwargs = {
            "session_id": "bt_jackal_1",
            "source_session_id": "bt_orca_1",
            "analysis_date": "2026-04-01",
            "regime": "위험선호",
            "inflows": ["semiconductor", "ai"],
            "outflows": ["utilities"],
            "inflows_text": "semiconductor ai",
            "market_note": "risk on",
            "daily_picks": self._daily_pick(),
            "tracking_days": 10,
        }

        materialization.materialize_backtest_day(**kwargs)
        materialization.materialize_backtest_day(**kwargs)

        with state._connect_orca() as conn:
            candidate_count = conn.execute("SELECT COUNT(*) FROM candidate_registry").fetchone()[0]
            outcome_count = conn.execute("SELECT COUNT(*) FROM candidate_outcomes").fetchone()[0]
            lesson_count = conn.execute("SELECT COUNT(*) FROM candidate_lessons").fetchone()[0]

        self.assertEqual(candidate_count, 1)
        self.assertEqual(outcome_count, 2)
        self.assertEqual(lesson_count, 1)

    def test_materialized_rows_store_backtest_origin_payload(self):
        materialization.materialize_backtest_day(
            session_id="bt_jackal_2",
            source_session_id="bt_orca_2",
            analysis_date="2026-04-02",
            regime="위험선호",
            inflows=["semiconductor"],
            outflows=["utilities"],
            inflows_text="semiconductor",
            market_note="risk on",
            daily_picks=self._daily_pick(),
            tracking_days=10,
        )

        with state._connect_orca() as conn:
            payload_json = conn.execute("SELECT payload_json FROM candidate_registry").fetchone()[0]
            lesson_json = conn.execute("SELECT lesson_json FROM candidate_lessons").fetchone()[0]
            outcome_json = conn.execute("SELECT outcome_json FROM candidate_outcomes WHERE horizon_label = 'swing'").fetchone()[0]

        self.assertIn('"origin": "backtest"', payload_json)
        self.assertIn('"origin": "backtest"', lesson_json)
        self.assertIn('"origin": "backtest"', outcome_json)


if __name__ == "__main__":
    unittest.main()
