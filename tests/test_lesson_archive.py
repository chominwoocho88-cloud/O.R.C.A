from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import lesson_archive
from orca import lesson_retrieval
from orca import state


class LessonArchiveTests(unittest.TestCase):
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

    def _seed_archive_fixture(self) -> dict[str, list[str] | str]:
        run_id = "cluster_run_archive_test"
        cluster_ids = ["c00", "c01"]
        snapshots = ["ctx_arch_0", "ctx_arch_1"]
        lesson_ids: list[str] = []

        for idx, snapshot_id in enumerate(snapshots):
            state.record_lesson_context_snapshot(
                {
                    "snapshot_id": snapshot_id,
                    "trading_date": f"2026-04-0{idx + 1}",
                    "source_event_type": "backtest_backfill",
                    "regime": "위험선호" if idx == 0 else "위험회피",
                    "dominant_sectors": ["Technology"] if idx == 0 else ["Utilities"],
                    "vix_level": 16.0 if idx == 0 else 28.0,
                    "sp500_momentum_5d": 2.0 if idx == 0 else -2.0,
                    "sp500_momentum_20d": 4.0 if idx == 0 else -4.0,
                    "nasdaq_momentum_5d": 2.5 if idx == 0 else -2.5,
                    "nasdaq_momentum_20d": 5.0 if idx == 0 else -5.0,
                }
            )

        with state._connect_orca() as conn:
            for idx, cluster_id in enumerate(cluster_ids):
                state.record_lesson_cluster(
                    conn,
                    {
                        "cluster_id": cluster_id,
                        "cluster_label": "low_vix_growth" if idx == 0 else "high_vix_defensive",
                        "size": 1,
                        "representative_snapshot_id": snapshots[idx],
                        "centroid_vix": 16.0 if idx == 0 else 28.0,
                        "centroid_sp500_5d": 2.0 if idx == 0 else -2.0,
                        "centroid_sp500_20d": 4.0 if idx == 0 else -4.0,
                        "centroid_nasdaq_5d": 2.5 if idx == 0 else -2.5,
                        "centroid_nasdaq_20d": 5.0 if idx == 0 else -5.0,
                        "dominant_regime": "위험선호" if idx == 0 else "위험회피",
                        "common_sectors": ["Technology"] if idx == 0 else ["Utilities"],
                        "silhouette_score": 0.2,
                        "within_variance": 1.0,
                        "algorithm": "kmeans",
                        "n_clusters_total": 2,
                        "random_seed": 42,
                        "run_id": run_id,
                        "created_at": f"2026-04-0{idx + 1}T09:00:00+09:00",
                    },
                )
                state.assign_snapshot_to_cluster(
                    conn,
                    snapshots[idx],
                    cluster_id,
                    0.3 if idx == 0 else 1.2,
                    run_id,
                )
            conn.commit()

        rows = [
            ("AAA", snapshots[0], 12.0, "momentum_pullback", 12.0, 2),
            ("BBB", snapshots[0], 5.0, "momentum_pullback", 5.0, 6),
            ("CCC", snapshots[0], -2.0, "panic_rebound", -2.0, 3),
            ("DDD", snapshots[1], 8.0, "defensive_rebound", 8.0, 4),
            ("EEE", snapshots[1], 1.0, "defensive_rebound", 1.0, 18),
            ("FFF", snapshots[1], -6.0, "panic_rebound", -6.0, 5),
        ]
        for idx, (ticker, snapshot_id, value, family, peak_pct, peak_day) in enumerate(rows):
            analysis_date = "2026-04-01" if snapshot_id == snapshots[0] else "2026-04-02"
            candidate_id = state.record_candidate(
                {
                    "ticker": ticker,
                    "analysis_date": analysis_date,
                    "timestamp": f"{analysis_date}T09:00:00+09:00",
                    "signal_family": family,
                    "quality_score": 70.0,
                },
                source_system="jackal",
                source_event_type="backtest",
                source_external_key=f"archive:{idx}:{ticker}",
                source_session_id="archive_test",
            )
            lesson_id = state.record_candidate_lesson(
                candidate_id,
                lesson_type="backtest_win" if value > 0 else "backtest_loss",
                label="backtest win" if value > 0 else "backtest loss",
                lesson_value=value,
                lesson={
                    "analysis_date": analysis_date,
                    "ticker": ticker,
                    "signal_family": family,
                    "peak_pct": peak_pct,
                    "peak_day": peak_day,
                    "signals_fired": [family],
                },
                context_snapshot_id=snapshot_id,
                auto_context_snapshot=False,
            )
            lesson_ids.append(lesson_id)

        return {"run_id": run_id, "clusters": cluster_ids, "snapshots": snapshots, "lessons": lesson_ids}

    def test_migrate_creates_lesson_archive_with_full_columns(self):
        with state._connect_orca() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(lesson_archive)")}

        self.assertIn("quality_score", columns)
        self.assertIn("cluster_fit_score", columns)
        self.assertIn("analysis_date", columns)

    def test_migrate_idempotent(self):
        state.init_state_db()
        state.init_state_db()
        with state._connect_orca() as conn:
            columns = [row["name"] for row in conn.execute("PRAGMA table_info(lesson_archive)")]

        self.assertEqual(columns.count("quality_score"), 1)

    def test_migrate_drops_old_skeleton(self):
        with state._connect_orca() as conn:
            conn.execute("DROP TABLE lesson_archive")
            conn.execute(
                """
                CREATE TABLE lesson_archive (
                    archive_id TEXT PRIMARY KEY,
                    cluster_id TEXT,
                    lesson_id TEXT,
                    quality_tier TEXT,
                    relevance_score REAL,
                    archived_at TEXT
                )
                """
            )
            conn.commit()

        state.init_state_db()
        with state._connect_orca() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(lesson_archive)")}

        self.assertIn("quality_score", columns)
        self.assertNotIn("relevance_score", columns)

    def test_indexes_created(self):
        with state._connect_orca() as conn:
            indexes = {row["name"] for row in conn.execute("PRAGMA index_list(lesson_archive)")}

        self.assertIn("idx_archive_cluster_quality", indexes)
        self.assertIn("idx_archive_lesson_id", indexes)
        self.assertIn("idx_archive_run_id", indexes)

    def test_component_scores_handle_outliers_and_edges(self):
        values = [-10.0, 0.0, 2.0, 5.0, 63.06]

        self.assertEqual(lesson_archive._calculate_outcome_percentile(63.06, values), 1.0)
        self.assertEqual(lesson_archive._calculate_win_score(1.0, "x"), 1.0)
        self.assertEqual(lesson_archive._calculate_win_score(-1.0, "x"), 0.0)
        self.assertEqual(lesson_archive._calculate_speed_score(3, 4.0), 1.0)
        self.assertEqual(lesson_archive._calculate_speed_score(20, 4.0), 0.2)
        self.assertEqual(lesson_archive._calculate_speed_score(2, -1.0), 0.0)
        self.assertGreater(lesson_archive._calculate_cluster_fit_score(0.1), 0.9)
        self.assertEqual(lesson_archive._calculate_cluster_fit_score(9.0), 0.0)

    def test_signal_score_known_and_unknown_family(self):
        self._seed_archive_fixture()
        with state._connect_orca() as conn:
            known = lesson_archive._calculate_signal_score("momentum_pullback", conn)
            unknown = lesson_archive._calculate_signal_score("missing_family", conn)

        self.assertEqual(known, 1.0)
        self.assertEqual(unknown, 0.5)

    def test_composite_score_weighted(self):
        score = lesson_archive._composite_quality_score(
            outcome_percentile=1.0,
            win_score=1.0,
            speed_score=0.7,
            signal_score=0.8,
            cluster_fit_score=0.5,
        )

        self.assertAlmostEqual(score, 0.885)

    def test_classify_tier_boundaries(self):
        self.assertEqual(lesson_archive._classify_tier(0.8), "high")
        self.assertEqual(lesson_archive._classify_tier(0.5), "medium")
        self.assertEqual(lesson_archive._classify_tier(0.2), "low")

    def test_build_archive_dry_run_does_not_write(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=True,
            )
            rows = conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0]

        self.assertEqual(result["archive_count"], 6)
        self.assertEqual(rows, 0)
        self.assertEqual(sum(result["tier_distribution"].values()), 6)

    def test_build_archive_execute_writes_rows(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=False,
            )
            rows = conn.execute(
                "SELECT COUNT(*) FROM lesson_archive WHERE run_id=?",
                (result["archive_run_id"],),
            ).fetchone()[0]

        self.assertEqual(result["archive_count"], 6)
        self.assertEqual(rows, 6)

    def test_build_archive_tier_distribution_has_all_rows(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=True,
            )

        self.assertEqual(sum(result["tier_distribution"].values()), 6)
        self.assertGreater(result["avg_quality_score"], 0)
        self.assertTrue(result["cluster_summary"])

    def test_build_archive_uses_canonical_backfill_snapshot_for_legacy_backtest_link(self):
        run_id = "cluster_run_canonical_archive"
        state.record_lesson_context_snapshot(
            {
                "snapshot_id": "ctx_legacy_direct",
                "trading_date": "2026-04-03",
                "source_event_type": "backtest",
                "dominant_sectors": ["Technology"],
                "vix_level": 20.0,
                "sp500_momentum_5d": 1.0,
                "sp500_momentum_20d": 2.0,
                "nasdaq_momentum_5d": 1.0,
                "nasdaq_momentum_20d": 2.0,
            }
        )
        state.record_lesson_context_snapshot(
            {
                "snapshot_id": "ctx_canonical_backfill",
                "trading_date": "2026-04-03",
                "source_event_type": "backtest_backfill",
                "dominant_sectors": ["Utilities"],
                "vix_level": 28.0,
                "sp500_momentum_5d": -1.0,
                "sp500_momentum_20d": -2.0,
                "nasdaq_momentum_5d": -1.0,
                "nasdaq_momentum_20d": -2.0,
            }
        )
        with state._connect_orca() as conn:
            state.record_lesson_cluster(
                conn,
                {
                    "cluster_id": "cluster_canonical",
                    "cluster_label": "canonical",
                    "size": 1,
                    "representative_snapshot_id": "ctx_canonical_backfill",
                    "run_id": run_id,
                    "algorithm": "kmeans",
                    "n_clusters_total": 1,
                    "random_seed": 42,
                },
            )
            state.assign_snapshot_to_cluster(
                conn,
                "ctx_canonical_backfill",
                "cluster_canonical",
                0.2,
                run_id,
            )
            conn.commit()
        candidate_id = state.record_candidate(
            {
                "ticker": "AAA",
                "analysis_date": "2026-04-03",
                "timestamp": "2026-04-03T09:00:00+09:00",
                "signal_family": "momentum_pullback",
                "quality_score": 70.0,
            },
            source_system="jackal",
            source_event_type="backtest",
            source_external_key="canonical-archive",
            source_session_id="archive_test",
        )
        state.record_candidate_lesson(
            candidate_id,
            lesson_type="backtest_win",
            label="backtest win",
            lesson_value=4.0,
            lesson={"analysis_date": "2026-04-03", "peak_pct": 4.0, "peak_day": 3},
            context_snapshot_id="ctx_legacy_direct",
            auto_context_snapshot=False,
        )

        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=run_id,
                conn=conn,
                dry_run=True,
            )

        self.assertEqual(result["archive_count"], 1)
        self.assertEqual(result["cluster_summary"][0]["cluster_id"], "cluster_canonical")

    def test_record_and_get_lesson_archive(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            archive_id = state.record_lesson_archive(
                conn,
                "arch_one",
                fixture["lessons"][0],
                fixture["clusters"][0],
                "archive_run_one",
                "high",
                0.9,
                1.0,
                1.0,
                1.0,
                0.8,
                0.9,
                12.0,
                12.0,
                2,
                "momentum_pullback",
                "AAA",
                "2026-04-01",
            )
            row = state.get_lesson_archive(conn, archive_id)

        self.assertEqual(row["quality_tier"], "high")
        self.assertEqual(row["lesson_value"], 12.0)

    def test_get_archives_for_cluster_filters_quality(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=False,
            )
            high = state.get_archives_for_cluster(
                conn,
                fixture["clusters"][0],
                run_id=result["archive_run_id"],
                quality_tier="high",
            )

        self.assertTrue(all(row["quality_tier"] == "high" for row in high))

    def test_clear_lesson_archive_specific_run(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=False,
            )
            cleared = state.clear_lesson_archive(conn, result["archive_run_id"])
            remaining = conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0]

        self.assertEqual(cleared["archives_deleted"], 6)
        self.assertEqual(remaining, 0)

    def test_latest_archive_run_id_with_default_tuple_factory(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=False,
            )
        conn = sqlite3.connect(self.state_db)
        try:
            latest = state.get_latest_archive_run_id(conn)
        finally:
            conn.close()

        self.assertEqual(latest, result["archive_run_id"])

    def test_retrieval_uses_archive_quality_when_available(self):
        fixture = self._seed_archive_fixture()
        with state._connect_orca() as conn:
            result = lesson_archive.build_lesson_archive(
                cluster_run_id=fixture["run_id"],
                conn=conn,
                dry_run=False,
            )
            lessons = lesson_retrieval.retrieve_similar_lessons(
                snapshot_id=fixture["snapshots"][0],
                top_k=3,
                conn=conn,
            )

        self.assertTrue(lessons)
        self.assertTrue(all(item["archive_run_id"] == result["archive_run_id"] for item in lessons))
        self.assertTrue(all(item["quality_score"] is not None for item in lessons))


if __name__ == "__main__":
    unittest.main()
