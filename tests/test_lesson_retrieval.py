from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import lesson_clustering
from orca import lesson_retrieval
from orca import state


class LessonRetrievalTests(unittest.TestCase):
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
        ids: dict[str, str] = {}
        values_on = [-1.0, 1.0, 3.0, 8.0, 12.0, 63.06]
        values_off = [-5.0, -2.0, 0.5, 2.0, 4.0, 6.0]
        for idx, value in enumerate(values_on):
            snapshot_id = f"ctx_on_{idx}"
            analysis_date = f"2026-04-{idx + 1:02d}"
            state.record_lesson_context_snapshot(
                {
                    "snapshot_id": snapshot_id,
                    "trading_date": analysis_date,
                    "source_event_type": "backtest_backfill",
                    "regime": "위험선호",
                    "dominant_sectors": ["Technology", "Communication Services"],
                    "vix_level": 14.0 + idx * 0.05,
                    "sp500_momentum_5d": 2.0,
                    "sp500_momentum_20d": 5.0,
                    "nasdaq_momentum_5d": 2.5,
                    "nasdaq_momentum_20d": 6.0,
                }
            )
            signal_family = "momentum_pullback" if idx % 2 == 0 else "panic_rebound"
            candidate_id = self._seed_candidate(
                idx,
                analysis_date,
                signal_family=signal_family,
                source_external_key=f"retrieval:on:{idx}",
            )
            state.record_candidate_lesson(
                candidate_id,
                lesson_type="backtest_win" if value > 0 else "backtest_loss",
                label="backtest",
                lesson_value=value,
                lesson={
                    "analysis_date": analysis_date,
                    "ticker": f"ON{idx}",
                    "signal_family": signal_family,
                    "signals_fired": ["rsi_oversold", "momentum_dip"],
                    "peak_pct": value,
                    "peak_day": idx + 1,
                },
                context_snapshot_id=snapshot_id,
                auto_context_snapshot=False,
            )
            ids[f"on_candidate_{idx}"] = candidate_id
            ids[f"on_snapshot_{idx}"] = snapshot_id

        for idx, value in enumerate(values_off):
            snapshot_id = f"ctx_off_{idx}"
            analysis_date = f"2026-05-{idx + 1:02d}"
            state.record_lesson_context_snapshot(
                {
                    "snapshot_id": snapshot_id,
                    "trading_date": analysis_date,
                    "source_event_type": "backtest_backfill",
                    "regime": "위험회피",
                    "dominant_sectors": ["Utilities"],
                    "vix_level": 28.0 + idx * 0.05,
                    "sp500_momentum_5d": -2.5,
                    "sp500_momentum_20d": -5.0,
                    "nasdaq_momentum_5d": -3.0,
                    "nasdaq_momentum_20d": -6.0,
                }
            )
            candidate_id = self._seed_candidate(
                idx + 10,
                analysis_date,
                signal_family="defensive_rebound",
                source_external_key=f"retrieval:off:{idx}",
            )
            state.record_candidate_lesson(
                candidate_id,
                lesson_type="backtest_win" if value > 0 else "backtest_loss",
                label="backtest",
                lesson_value=value,
                lesson={
                    "analysis_date": analysis_date,
                    "ticker": f"OFF{idx}",
                    "signal_family": "defensive_rebound",
                    "signals_fired": ["panic_flush"],
                    "peak_pct": value,
                    "peak_day": idx + 1,
                },
                context_snapshot_id=snapshot_id,
                auto_context_snapshot=False,
            )
            ids[f"off_snapshot_{idx}"] = snapshot_id

        with state._connect_orca() as conn:
            lesson_clustering.build_clusters(
                n_clusters=2,
                conn=conn,
                run_id="run_retrieval",
                dry_run=False,
                random_seed=42,
            )
        return ids

    def _seed_candidate(
        self,
        idx: int,
        analysis_date: str,
        *,
        signal_family: str,
        source_external_key: str,
    ) -> str:
        return state.record_candidate(
            {
                "ticker": f"T{idx:03d}",
                "analysis_date": analysis_date,
                "timestamp": f"{analysis_date}T09:00:00+09:00",
                "signal_family": signal_family,
                "quality_score": 70.0,
            },
            source_system="jackal",
            source_event_type="backtest",
            source_external_key=source_external_key,
            source_session_id="retrieval_test",
        )

    def _riskon_features(self) -> dict:
        return {
            "vix_level": 14.2,
            "sp500_momentum_5d": 2.0,
            "sp500_momentum_20d": 5.0,
            "nasdaq_momentum_5d": 2.5,
            "nasdaq_momentum_20d": 6.0,
            "regime": "위험선호",
            "dominant_sectors": ["Technology", "Communication Services"],
        }

    def test_resolve_context_no_input_raises(self):
        with self.assertRaises(ValueError):
            lesson_retrieval.retrieve_similar_lessons()

    def test_resolve_context_unknown_snapshot_raises(self):
        self._seed_fixture()
        with self.assertRaises(LookupError):
            lesson_retrieval.retrieve_similar_lessons(snapshot_id="missing")

    def test_retrieve_with_snapshot_id_returns_top_k(self):
        ids = self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons(
            snapshot_id=ids["on_snapshot_0"],
            top_k=3,
        )

        self.assertEqual(len(lessons), 3)
        self.assertTrue(all(item["cluster_id"] == lessons[0]["cluster_id"] for item in lessons))

    def test_retrieve_with_candidate_id_uses_candidate_context(self):
        ids = self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons(
            candidate_id=ids["on_candidate_0"],
            top_k=4,
        )

        self.assertEqual(len(lessons), 4)
        self.assertTrue(any(item["signal_score"] == 1.0 for item in lessons))

    def test_retrieve_with_analysis_date(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons(
            analysis_date="2026-04-02",
            top_k=2,
        )

        self.assertEqual(len(lessons), 2)
        self.assertTrue(all(item["cluster_label"] for item in lessons))

    def test_retrieve_for_features_direct(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=3,
        )

        self.assertEqual(len(lessons), 3)
        self.assertTrue(all(item["ticker"].startswith("ON") for item in lessons))

    def test_retrieve_returns_descending_relevance(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=6,
        )
        scores = [item["relevance_score"] for item in lessons]

        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_retrieve_includes_required_fields(self):
        self._seed_fixture()
        lesson = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=1,
        )[0]

        for key in [
            "lesson_id",
            "ticker",
            "signal_family",
            "lesson_value",
            "quality_tier",
            "relevance_score",
            "quality_score",
            "context_score",
            "signal_score",
            "recency_score",
            "cluster_id",
            "cluster_label",
            "analysis_date",
            "signals_fired",
            "peak_pct",
            "peak_day",
            "distance_to_centroid",
        ]:
            self.assertIn(key, lesson)

    def test_retrieve_with_quality_filter_high(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=10,
            quality_filter="high",
        )

        self.assertGreaterEqual(len(lessons), 1)
        self.assertTrue(all(item["quality_tier"] == "high" for item in lessons))

    def test_retrieve_with_quality_filter_low(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=10,
            quality_filter="low",
        )

        self.assertGreaterEqual(len(lessons), 1)
        self.assertTrue(all(item["quality_tier"] == "low" for item in lessons))

    def test_retrieve_with_signal_family_filter(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=10,
            signal_family="momentum_pullback",
        )

        self.assertGreaterEqual(len(lessons), 1)
        self.assertTrue(all(item["signal_family"] == "momentum_pullback" for item in lessons))

    def test_retrieve_no_filter_returns_multiple_quality_tiers(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=10,
        )
        tiers = {item["quality_tier"] for item in lessons}

        self.assertGreaterEqual(len(tiers), 2)

    def test_retrieve_as_of_date_excludes_future_lessons(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=10,
            as_of_date="2026-04-04",
        )

        self.assertTrue(lessons)
        self.assertTrue(all(item["analysis_date"] < "2026-04-04" for item in lessons))

    def test_retrieve_without_as_of_date_includes_all_cluster_lessons(self):
        self._seed_fixture()
        lessons = lesson_retrieval.retrieve_similar_lessons_for_features(
            self._riskon_features(),
            top_k=20,
        )

        self.assertEqual(len(lessons), 6)

    def test_quality_score_handles_outlier(self):
        values = [-1.0, 1.0, 3.0, 8.0, 12.0, 63.06]

        self.assertEqual(lesson_retrieval._calculate_quality_score(63.06, values), 1.0)
        self.assertLess(lesson_retrieval._calculate_quality_score(-1.0, values), 0.34)

    def test_context_signal_recency_and_relevance_scores(self):
        self.assertGreater(
            lesson_retrieval._calculate_context_score("c1", "c1", 0.1),
            0.9,
        )
        self.assertEqual(lesson_retrieval._calculate_context_score("c2", "c1", 0.1), 0.0)
        self.assertEqual(lesson_retrieval._calculate_signal_score("a", "a"), 1.0)
        self.assertEqual(lesson_retrieval._calculate_signal_score("a", "b"), 0.0)
        self.assertEqual(lesson_retrieval._calculate_signal_score(None, "b"), 0.5)
        self.assertEqual(
            lesson_retrieval._calculate_recency_score("2026-01-01", "2026-04-01", None),
            1.0,
        )
        self.assertLess(
            lesson_retrieval._calculate_recency_score("2025-04-01", "2026-04-01", 365),
            1.0,
        )
        self.assertAlmostEqual(
            lesson_retrieval._calculate_relevance_score(1.0, 1.0, 1.0, 1.0),
            1.0,
        )

    def test_allow_create_snapshot_false_raises_when_missing(self):
        self._seed_fixture()

        with self.assertRaises(LookupError):
            lesson_retrieval.retrieve_similar_lessons(
                analysis_date="2026-09-01",
                allow_create_snapshot=False,
            )

    def test_read_only_retrieval_does_not_change_db_counts(self):
        self._seed_fixture()
        with state._connect_orca() as conn:
            before = {
                "snapshots": conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot").fetchone()[0],
                "clusters": conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0],
                "mappings": conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0],
                "lessons": conn.execute("SELECT COUNT(*) FROM candidate_lessons").fetchone()[0],
            }

        lesson_retrieval.retrieve_similar_lessons_for_features(self._riskon_features(), top_k=5)

        with state._connect_orca() as conn:
            after = {
                "snapshots": conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot").fetchone()[0],
                "clusters": conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0],
                "mappings": conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0],
                "lessons": conn.execute("SELECT COUNT(*) FROM candidate_lessons").fetchone()[0],
            }

        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
