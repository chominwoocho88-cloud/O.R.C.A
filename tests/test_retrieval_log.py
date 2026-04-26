from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jackal import backtest as jackal_backtest
from jackal import historical_context as jackal_historical_context
from orca import lesson_retrieval
from orca import state


class RetrievalLogTests(unittest.TestCase):
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

    def _seed_fixture(self) -> dict[str, str]:
        run_id = "cluster_run_retrieval_log"
        cluster_id = "cluster_c00"
        snapshots = {
            "past": "ctx_past",
            "target": "ctx_target",
            "future": "ctx_future",
        }
        dates = {
            "past": "2026-04-01",
            "target": "2026-04-03",
            "future": "2026-04-05",
        }
        for key, snapshot_id in snapshots.items():
            state.record_lesson_context_snapshot(
                {
                    "snapshot_id": snapshot_id,
                    "trading_date": dates[key],
                    "source_event_type": "backtest_backfill",
                    "regime": "위험선호",
                    "dominant_sectors": ["Technology"],
                    "vix_level": 18.0,
                    "sp500_momentum_5d": 1.0,
                    "sp500_momentum_20d": 3.0,
                    "nasdaq_momentum_5d": 1.2,
                    "nasdaq_momentum_20d": 3.5,
                }
            )

        with state._connect_orca() as conn:
            state.record_lesson_cluster(
                conn,
                {
                    "cluster_id": cluster_id,
                    "cluster_label": "medium_vix_bullish_riskon_growth",
                    "size": 3,
                    "representative_snapshot_id": snapshots["target"],
                    "centroid_vix": 0.0,
                    "centroid_sp500_5d": 0.0,
                    "centroid_sp500_20d": 0.0,
                    "centroid_nasdaq_5d": 0.0,
                    "centroid_nasdaq_20d": 0.0,
                    "dominant_regime": "위험선호",
                    "common_sectors": ["Technology"],
                    "silhouette_score": 0.2,
                    "within_variance": 1.0,
                    "algorithm": "kmeans",
                    "n_clusters_total": 1,
                    "random_seed": 42,
                    "run_id": run_id,
                    "created_at": "2026-04-01T09:00:00+09:00",
                },
            )
            for snapshot_id in snapshots.values():
                state.assign_snapshot_to_cluster(conn, snapshot_id, cluster_id, 0.25, run_id)
            conn.commit()

        self._seed_lesson("AAA", snapshots["past"], dates["past"], 10.0, "momentum_pullback")
        self._seed_lesson("BBB", snapshots["future"], dates["future"], 20.0, "momentum_pullback")
        return {"run_id": run_id, "cluster_id": cluster_id, **snapshots, **dates}

    def _seed_lesson(
        self,
        ticker: str,
        snapshot_id: str,
        analysis_date: str,
        value: float,
        signal_family: str,
    ) -> str:
        candidate_id = state.record_candidate(
            {
                "ticker": ticker,
                "analysis_date": analysis_date,
                "timestamp": f"{analysis_date}T09:00:00+09:00",
                "signal_family": signal_family,
            },
            source_system="jackal",
            source_event_type="backtest",
            source_external_key=f"retrieval-log:{ticker}",
            source_session_id="retrieval_log_test",
        )
        return state.record_candidate_lesson(
            candidate_id,
            lesson_type="backtest_win" if value > 0 else "backtest_loss",
            label="backtest",
            lesson_value=value,
            lesson={
                "analysis_date": analysis_date,
                "ticker": ticker,
                "signal_family": signal_family,
                "peak_pct": value,
                "peak_day": 3,
                "signals_fired": [signal_family],
            },
            context_snapshot_id=snapshot_id,
            auto_context_snapshot=False,
        )

    def test_migrate_creates_retrieval_log_table(self):
        with state._connect_orca() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(retrieval_log)")}

        self.assertIn("source_system", columns)
        self.assertIn("top_lessons_json", columns)
        self.assertIn("outcome_match", columns)

    def test_migrate_retrieval_log_idempotent(self):
        state.init_state_db()
        state.init_state_db()
        with state._connect_orca() as conn:
            columns = [row["name"] for row in conn.execute("PRAGMA table_info(retrieval_log)")]

        self.assertEqual(columns.count("log_id"), 1)

    def test_retrieval_log_indexes_created(self):
        with state._connect_orca() as conn:
            indexes = {row["name"] for row in conn.execute("PRAGMA index_list(retrieval_log)")}

        self.assertIn("idx_retrieval_log_source", indexes)
        self.assertIn("idx_retrieval_log_cluster", indexes)
        self.assertIn("idx_retrieval_log_run", indexes)
        self.assertIn("idx_retrieval_log_outcome_pending", indexes)

    def test_record_retrieval_log_inserts_and_decodes_top_lessons(self):
        with state._connect_orca() as conn:
            log_id = state.record_retrieval_log(conn, self._log_payload())
            row = state.get_retrieval_log(conn, log_id)

        self.assertEqual(row["source_system"], "jackal_backtest")
        self.assertEqual(row["top_lessons"][0]["lesson_id"], "lesson_1")

    def test_record_retrieval_log_updates_existing(self):
        payload = self._log_payload(log_id="log_one", avg_value=5.0)
        with state._connect_orca() as conn:
            state.record_retrieval_log(conn, payload)
            payload["avg_value"] = 9.5
            state.record_retrieval_log(conn, payload)
            row = state.get_retrieval_log(conn, "log_one")

        self.assertEqual(row["avg_value"], 9.5)

    def test_update_retrieval_outcome(self):
        with state._connect_orca() as conn:
            log_id = state.record_retrieval_log(conn, self._log_payload())
            state.update_retrieval_outcome(conn, log_id, 7.5, "2026-04-10", True)
            row = state.get_retrieval_log(conn, log_id)

        self.assertEqual(row["actual_outcome"], 7.5)
        self.assertEqual(row["outcome_match"], 1)

    def test_get_pending_outcomes_filters_by_date(self):
        with state._connect_orca() as conn:
            old_id = state.record_retrieval_log(conn, self._log_payload(trading_date="2026-04-01"))
            new_id = state.record_retrieval_log(conn, self._log_payload(trading_date="2026-04-10"))
            state.update_retrieval_outcome(conn, new_id, 1.0, "2026-04-12", True)
            pending = state.get_pending_outcomes(conn, "2026-04-05")

        self.assertEqual([row["log_id"] for row in pending], [old_id])

    def test_get_retrieval_stats_for_cluster(self):
        with state._connect_orca() as conn:
            one = state.record_retrieval_log(conn, self._log_payload(cluster_id="cluster_c00"))
            two = state.record_retrieval_log(conn, self._log_payload(cluster_id="cluster_c00"))
            state.update_retrieval_outcome(conn, one, 5.0, "2026-04-10", True)
            state.update_retrieval_outcome(conn, two, -2.0, "2026-04-10", False)
            stats = state.get_retrieval_stats_for_cluster(conn, "cluster_c00")

        self.assertEqual(stats["total_retrievals"], 2)
        self.assertEqual(stats["completed_outcomes"], 2)
        self.assertEqual(stats["accuracy"], 0.5)

    def test_measure_retrieval_accuracy_returns_breakdowns(self):
        with state._connect_orca() as conn:
            one = state.record_retrieval_log(conn, self._log_payload(signal_family="momentum_pullback", mode="observe"))
            two = state.record_retrieval_log(conn, self._log_payload(signal_family="panic_rebound", mode="adjust"))
            state.update_retrieval_outcome(conn, one, 5.0, "2026-04-10", True)
            state.update_retrieval_outcome(conn, two, -2.0, "2026-04-10", False)
            stats = state.measure_retrieval_accuracy(conn)

        self.assertEqual(stats["total_retrievals"], 2)
        self.assertEqual(stats["completed_outcomes"], 2)
        self.assertEqual(stats["accuracy_overall"], 0.5)
        self.assertEqual(stats["signal_family_accuracy"]["momentum_pullback"], 1.0)
        self.assertEqual(stats["mode_accuracy"]["adjust"], 0.0)

    def test_retrieve_with_log_retrieval_creates_entry(self):
        fixture = self._seed_fixture()
        with state._connect_orca() as conn:
            lessons = lesson_retrieval.retrieve_similar_lessons(
                analysis_date=fixture["target"],
                as_of_date=fixture["target"],
                top_k=5,
                log_retrieval=True,
                source_system="jackal_backtest",
                source_event_type="backtest",
                source_event_id="event_1",
                backtest_run_id="bt_run",
                conn=conn,
            )
            rows = conn.execute("SELECT * FROM retrieval_log").fetchall()

        self.assertEqual(len(lessons), 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_system"], "jackal_backtest")

    def test_retrieve_without_log_retrieval_creates_no_entry(self):
        fixture = self._seed_fixture()
        with state._connect_orca() as conn:
            lesson_retrieval.retrieve_similar_lessons(
                analysis_date=fixture["target"],
                as_of_date=fixture["target"],
                top_k=5,
                conn=conn,
            )
            count = conn.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0]

        self.assertEqual(count, 0)

    def test_retrieve_log_includes_cluster_info(self):
        fixture = self._seed_fixture()
        with state._connect_orca() as conn:
            lesson_retrieval.retrieve_similar_lessons(
                analysis_date=fixture["target"],
                as_of_date=fixture["target"],
                top_k=5,
                log_retrieval=True,
                source_system="test",
                conn=conn,
            )
            row = conn.execute("SELECT cluster_id, cluster_label FROM retrieval_log").fetchone()

        self.assertEqual(row["cluster_id"], fixture["cluster_id"])
        self.assertEqual(row["cluster_label"], "medium_vix_bullish_riskon_growth")

    def test_retrieve_log_top_lessons_excludes_future_lessons(self):
        fixture = self._seed_fixture()
        with state._connect_orca() as conn:
            lesson_retrieval.retrieve_similar_lessons(
                analysis_date=fixture["target"],
                as_of_date=fixture["target"],
                top_k=5,
                log_retrieval=True,
                source_system="test",
                conn=conn,
            )
            row = conn.execute("SELECT top_lessons_json FROM retrieval_log").fetchone()
        top_lessons = json.loads(row["top_lessons_json"])

        self.assertEqual([lesson["ticker"] for lesson in top_lessons], ["AAA"])

    def test_jackal_historical_context_passes_logging_options(self):
        with patch.object(
            jackal_historical_context,
            "retrieve_similar_lessons_for_features",
            return_value=[self._retrieved_lesson()],
        ) as mocked:
            result = jackal_historical_context.try_retrieve_historical_context(
                self._features(),
                "momentum_pullback",
                as_of_date="2026-04-03",
                source_system="jackal_backtest",
                source_event_type="backtest",
                source_event_id="evt",
                backtest_run_id="bt",
                log_retrieval=True,
            )

        self.assertIsNotNone(result)
        self.assertEqual(mocked.call_args.kwargs["as_of_date"], "2026-04-03")
        self.assertTrue(mocked.call_args.kwargs["log_retrieval"])
        self.assertEqual(mocked.call_args.kwargs["source_system"], "jackal_backtest")

    def test_jackal_backtest_helper_uses_as_of_date(self):
        item = self._backtest_item()
        with patch.object(
            jackal_historical_context,
            "try_retrieve_historical_context",
            return_value={"mode": "observe", "win_rate": 1.0, "avg_value": 10.0, "high_quality_count": 5},
        ) as mocked:
            result = jackal_backtest._attach_historical_context_to_backtest_item(
                item,
                {"historical_context_features": self._features()},
                "2026-04-03",
                1,
            )

        self.assertEqual(mocked.call_args.kwargs["as_of_date"], "2026-04-03")
        self.assertTrue(mocked.call_args.kwargs["log_retrieval"])
        self.assertEqual(mocked.call_args.kwargs["source_system"], "jackal_backtest")
        self.assertEqual(result["historical_adjustment"], 0.0)

    def test_jackal_backtest_helper_logs_retrieval(self):
        fixture = self._seed_fixture()
        item = self._backtest_item()
        with patch.object(jackal_backtest, "_JACKAL_SESSION_ID", "bt_session_1"):
            result = jackal_backtest._attach_historical_context_to_backtest_item(
                item,
                {},
                fixture["target"],
                2,
            )
        with state._connect_orca() as conn:
            row = conn.execute("SELECT * FROM retrieval_log").fetchone()

        self.assertIsNotNone(result["historical_context"])
        self.assertEqual(row["backtest_run_id"], "bt_session_1")
        self.assertEqual(row["as_of_date"], fixture["target"])

    def test_jackal_backtest_helper_excludes_future_lessons(self):
        fixture = self._seed_fixture()
        with patch.object(jackal_backtest, "_JACKAL_SESSION_ID", "bt_session_2"):
            jackal_backtest._attach_historical_context_to_backtest_item(
                self._backtest_item(),
                {},
                fixture["target"],
                1,
            )
        with state._connect_orca() as conn:
            row = conn.execute("SELECT top_lessons_json FROM retrieval_log").fetchone()
        top_lessons = json.loads(row["top_lessons_json"])

        self.assertEqual([lesson["ticker"] for lesson in top_lessons], ["AAA"])

    def test_jackal_backtest_adjust_mode_caps_s2_adjustment(self):
        item = self._backtest_item()
        with (
            patch.dict("os.environ", {"HISTORICAL_CONTEXT_MODE": "adjust"}),
            patch.object(
                jackal_historical_context,
                "try_retrieve_historical_context",
                return_value={"mode": "adjust", "win_rate": 1.0, "avg_value": 100.0, "high_quality_count": 5},
            ),
        ):
            result = jackal_backtest._attach_historical_context_to_backtest_item(
                item,
                {"historical_context_features": self._features()},
                "2026-04-03",
                1,
            )

        self.assertEqual(result["historical_adjustment"], 5.0)
        self.assertEqual(result["s2_score"], 55.0)

    def test_no_look_ahead_bias_realistic_simulation(self):
        fixture = self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons(
            analysis_date=fixture["target"],
            as_of_date=fixture["target"],
            top_k=10,
        )

        self.assertTrue(lessons)
        self.assertTrue(all(lesson["analysis_date"] < fixture["target"] for lesson in lessons))

    def _log_payload(self, **overrides) -> dict:
        payload = {
            "source_system": "jackal_backtest",
            "source_event_type": "backtest",
            "source_event_id": "event_1",
            "trading_date": "2026-04-03",
            "as_of_date": "2026-04-03",
            "top_k": 5,
            "quality_filter": "high",
            "signal_family": "momentum_pullback",
            "cluster_id": "cluster_c00",
            "cluster_label": "medium_vix_bullish_riskon_growth",
            "cluster_distance": 0.25,
            "lessons_count": 1,
            "win_rate": 1.0,
            "avg_value": 10.0,
            "high_quality_count": 1,
            "top_lessons_json": [{"lesson_id": "lesson_1", "ticker": "AAA", "lesson_value": 10.0}],
            "mode": "observe",
            "backtest_run_id": "bt_run",
        }
        payload.update(overrides)
        return payload

    def _features(self) -> dict:
        return {
            "vix_level": 18.0,
            "sp500_momentum_5d": 1.0,
            "sp500_momentum_20d": 3.0,
            "nasdaq_momentum_5d": 1.2,
            "nasdaq_momentum_20d": 3.5,
            "regime": "위험선호",
            "dominant_sectors": ["Technology"],
        }

    def _retrieved_lesson(self) -> dict:
        return {
            "lesson_id": "lesson_1",
            "ticker": "AAA",
            "analysis_date": "2026-04-01",
            "signal_family": "momentum_pullback",
            "lesson_value": 10.0,
            "peak_pct": 10.0,
            "peak_day": 3,
            "quality_tier": "high",
            "relevance_score": 0.9,
            "cluster_id": "cluster_c00",
            "cluster_label": "medium_vix_bullish_riskon_growth",
            "target_distance_to_cluster": 0.25,
        }

    def _backtest_item(self) -> dict:
        return {
            "ticker": "AAA",
            "s1_score": 42.0,
            "s2_score": 50.0,
            "tech": {
                "rsi": 30.0,
                "bb_pos": 25.0,
                "change_5d": -4.0,
                "bullish_div": False,
            },
        }


if __name__ == "__main__":
    unittest.main()
