from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import state


class LessonClusteringSchemaTests(unittest.TestCase):
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

    def _seed_snapshot(self, snapshot_id: str = "ctx_test", trading_date: str = "2026-04-20") -> str:
        return state.record_lesson_context_snapshot(
            {
                "snapshot_id": snapshot_id,
                "trading_date": trading_date,
                "source_event_type": "backtest_backfill",
                "regime": "위험선호",
                "dominant_sectors": ["Technology", "Energy"],
                "vix_level": 18.5,
                "sp500_momentum_5d": 1.2,
                "sp500_momentum_20d": 3.4,
                "nasdaq_momentum_5d": 1.5,
                "nasdaq_momentum_20d": 4.1,
            }
        )

    def _seed_cluster(self, cluster_id: str = "cluster_001", run_id: str = "run_cluster_1") -> str:
        with state._connect_orca() as conn:
            return state.record_lesson_cluster(
                conn,
                {
                    "cluster_id": cluster_id,
                    "cluster_label": "low_vix_growth",
                    "size": 12,
                    "representative_snapshot_id": "ctx_test",
                    "centroid_vix": 18.5,
                    "centroid_sp500_5d": 1.2,
                    "centroid_sp500_20d": 3.4,
                    "centroid_nasdaq_5d": 1.5,
                    "centroid_nasdaq_20d": 4.1,
                    "dominant_regime": "위험선호",
                    "common_sectors": ["Technology", "Energy"],
                    "silhouette_score": 0.21,
                    "within_variance": 1.8,
                    "avg_outcome_score": 4.2,
                    "win_rate": 0.72,
                    "sample_count": 60,
                    "algorithm": "kmeans",
                    "n_clusters_total": 8,
                    "random_seed": 42,
                    "run_id": run_id,
                    "created_at": "2026-04-20T09:00:00+09:00",
                },
            )

    def _seed_lesson_for_snapshot(self, snapshot_id: str) -> str:
        candidate_id = state.record_candidate(
            {
                "ticker": "NVDA",
                "analysis_date": "2026-04-20",
                "timestamp": "2026-04-20T09:00:00+09:00",
                "signal_family": "momentum_pullback",
                "quality_score": 72.0,
                "price_at_scan": 100.0,
            },
            source_system="jackal",
            source_event_type="backtest",
            source_external_key="bt:2026-04-20:NVDA",
            source_session_id="bt_schema",
        )
        return state.record_candidate_lesson(
            candidate_id,
            lesson_type="backtest_win",
            label="backtest win",
            lesson_value=4.0,
            lesson={"analysis_date": "2026-04-20"},
            context_snapshot_id=snapshot_id,
            auto_context_snapshot=False,
        )

    def test_migrate_creates_lesson_clusters_table(self):
        with state._connect_orca() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='lesson_clusters'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_migrate_creates_snapshot_cluster_mapping_table(self):
        with state._connect_orca() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='snapshot_cluster_mapping'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_migrate_adds_context_cluster_id_column(self):
        with state._connect_orca() as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(lesson_context_snapshot)")}
        self.assertIn("context_cluster_id", columns)

    def test_migrate_idempotent(self):
        state.init_state_db()
        state.init_state_db()
        with state._connect_orca() as conn:
            columns = [row["name"] for row in conn.execute("PRAGMA table_info(lesson_context_snapshot)")]
        self.assertEqual(columns.count("context_cluster_id"), 1)

    def test_record_lesson_cluster_inserts(self):
        self._seed_snapshot()
        cluster_id = self._seed_cluster()
        with state._connect_orca() as conn:
            cluster = state.get_cluster_by_id(conn, cluster_id)

        self.assertEqual(cluster["cluster_label"], "low_vix_growth")
        self.assertEqual(cluster["size"], 12)
        self.assertEqual(cluster["common_sectors"], ["Technology", "Energy"])

    def test_record_lesson_cluster_updates_existing(self):
        self._seed_snapshot()
        self._seed_cluster()
        with state._connect_orca() as conn:
            state.record_lesson_cluster(
                conn,
                {
                    "cluster_id": "cluster_001",
                    "cluster_label": "updated_label",
                    "size": 20,
                    "common_sectors": ["Utilities"],
                    "run_id": "run_cluster_1",
                },
            )
            cluster = state.get_cluster_by_id(conn, "cluster_001")

        self.assertEqual(cluster["cluster_label"], "updated_label")
        self.assertEqual(cluster["size"], 20)
        self.assertEqual(cluster["common_sectors"], ["Utilities"])

    def test_assign_snapshot_to_cluster_updates_cache(self):
        snapshot_id = self._seed_snapshot()
        cluster_id = self._seed_cluster()
        with state._connect_orca() as conn:
            state.assign_snapshot_to_cluster(conn, snapshot_id, cluster_id, 0.42, "run_cluster_1")
            row = conn.execute(
                "SELECT context_cluster_id FROM lesson_context_snapshot WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            mapping = conn.execute(
                "SELECT distance_to_centroid FROM snapshot_cluster_mapping WHERE snapshot_id=? AND run_id=?",
                (snapshot_id, "run_cluster_1"),
            ).fetchone()

        self.assertEqual(row["context_cluster_id"], cluster_id)
        self.assertEqual(mapping["distance_to_centroid"], 0.42)

    def test_get_active_clusters_filters_by_run_id(self):
        self._seed_snapshot()
        self._seed_cluster("cluster_old", "run_old")
        self._seed_cluster("cluster_new", "run_new")
        with state._connect_orca() as conn:
            old = state.get_active_clusters(conn, "run_old")
            new = state.get_active_clusters(conn, "run_new")

        self.assertEqual([row["cluster_id"] for row in old], ["cluster_old"])
        self.assertEqual([row["cluster_id"] for row in new], ["cluster_new"])

    def test_get_latest_run_id(self):
        self._seed_snapshot()
        self._seed_cluster("cluster_old", "run_old")
        with state._connect_orca() as conn:
            state.record_lesson_cluster(
                conn,
                {
                    "cluster_id": "cluster_new",
                    "cluster_label": "new",
                    "size": 1,
                    "run_id": "run_new",
                    "created_at": "2026-04-21T09:00:00+09:00",
                    "updated_at": "2026-04-21T09:00:00+09:00",
                },
            )
            latest = state.get_latest_run_id(conn)

        self.assertEqual(latest, "run_new")

    def test_get_snapshots_in_cluster(self):
        first = self._seed_snapshot("ctx_a", "2026-04-20")
        second = self._seed_snapshot("ctx_b", "2026-04-21")
        cluster_id = self._seed_cluster()
        with state._connect_orca() as conn:
            state.assign_snapshot_to_cluster(conn, first, cluster_id, 0.1, "run_cluster_1")
            state.assign_snapshot_to_cluster(conn, second, cluster_id, 0.2, "run_cluster_1")
            snapshots = state.get_snapshots_in_cluster(conn, cluster_id)

        self.assertEqual(snapshots, ["ctx_a", "ctx_b"])

    def test_get_lessons_in_cluster_joins_correctly(self):
        snapshot_id = self._seed_snapshot()
        lesson_id = self._seed_lesson_for_snapshot(snapshot_id)
        cluster_id = self._seed_cluster()
        with state._connect_orca() as conn:
            state.assign_snapshot_to_cluster(conn, snapshot_id, cluster_id, 0.1, "run_cluster_1")
            lessons = state.get_lessons_in_cluster(conn, cluster_id)

        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["lesson_id"], lesson_id)
        self.assertEqual(lessons[0]["ticker"], "NVDA")
        self.assertEqual(lessons[0]["context_cluster_id"], cluster_id)

    def test_clear_clustering_data_specific_run(self):
        snapshot_id = self._seed_snapshot()
        self._seed_cluster("cluster_old", "run_old")
        self._seed_cluster("cluster_new", "run_new")
        with state._connect_orca() as conn:
            state.assign_snapshot_to_cluster(conn, snapshot_id, "cluster_old", 0.3, "run_old")
            state.assign_snapshot_to_cluster(conn, snapshot_id, "cluster_new", 0.1, "run_new")
            result = state.clear_clustering_data(conn, "run_new")
            remaining_clusters = state.get_active_clusters(conn, "run_old")
            cache = conn.execute(
                "SELECT context_cluster_id FROM lesson_context_snapshot WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()["context_cluster_id"]

        self.assertEqual(result["clusters_deleted"], 1)
        self.assertEqual(result["mappings_deleted"], 1)
        self.assertEqual([row["cluster_id"] for row in remaining_clusters], ["cluster_old"])
        self.assertEqual(cache, "cluster_old")

    def test_clear_clustering_data_all_runs(self):
        snapshot_id = self._seed_snapshot()
        cluster_id = self._seed_cluster()
        with state._connect_orca() as conn:
            state.assign_snapshot_to_cluster(conn, snapshot_id, cluster_id, 0.3, "run_cluster_1")
            result = state.clear_clustering_data(conn)
            clusters = conn.execute("SELECT COUNT(*) c FROM lesson_clusters").fetchone()["c"]
            mappings = conn.execute("SELECT COUNT(*) c FROM snapshot_cluster_mapping").fetchone()["c"]
            cache = conn.execute(
                "SELECT context_cluster_id FROM lesson_context_snapshot WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()["context_cluster_id"]

        self.assertEqual(result["clusters_deleted"], 1)
        self.assertEqual(result["mappings_deleted"], 1)
        self.assertEqual(clusters, 0)
        self.assertEqual(mappings, 0)
        self.assertIsNone(cache)

    def test_existing_lessons_and_snapshots_unaffected_before_clustering(self):
        snapshot_id = self._seed_snapshot()
        lesson_id = self._seed_lesson_for_snapshot(snapshot_id)
        with state._connect_orca() as conn:
            clusters = conn.execute("SELECT COUNT(*) c FROM lesson_clusters").fetchone()["c"]
            mappings = conn.execute("SELECT COUNT(*) c FROM snapshot_cluster_mapping").fetchone()["c"]
            snapshot = state.get_lesson_context_snapshot(snapshot_id, conn=conn)
            lesson = conn.execute(
                "SELECT lesson_id, context_snapshot_id FROM candidate_lessons WHERE lesson_id=?",
                (lesson_id,),
            ).fetchone()

        self.assertEqual(clusters, 0)
        self.assertEqual(mappings, 0)
        self.assertIsNone(snapshot["context_cluster_id"])
        self.assertEqual(lesson["context_snapshot_id"], snapshot_id)


if __name__ == "__main__":
    unittest.main()
