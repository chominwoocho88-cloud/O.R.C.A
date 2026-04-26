from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from orca import lesson_clustering
from orca import state


class LessonClusteringAlgorithmTests(unittest.TestCase):
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

    def _seed_snapshot(
        self,
        idx: int,
        *,
        regime: str = "위험선호",
        sectors: list[str] | None = None,
        vix: float = 18.0,
        sp5: float = 1.0,
        sp20: float = 3.0,
        nq5: float = 1.5,
        nq20: float = 4.0,
    ) -> str:
        snapshot_id = f"ctx_{idx:03d}"
        return state.record_lesson_context_snapshot(
            {
                "snapshot_id": snapshot_id,
                "trading_date": f"2026-04-{idx + 1:02d}",
                "source_event_type": "backtest_backfill",
                "regime": regime,
                "dominant_sectors": sectors or ["Technology", "Energy"],
                "vix_level": vix,
                "sp500_momentum_5d": sp5,
                "sp500_momentum_20d": sp20,
                "nasdaq_momentum_5d": nq5,
                "nasdaq_momentum_20d": nq20,
            }
        )

    def _seed_two_cluster_snapshots(self, with_lessons: bool = False) -> list[str]:
        snapshot_ids: list[str] = []
        for idx in range(8):
            snapshot_ids.append(
                self._seed_snapshot(
                    idx,
                    regime="위험선호",
                    sectors=["Technology"],
                    vix=14.0 + idx * 0.05,
                    sp5=2.0,
                    sp20=5.0,
                    nq5=2.5,
                    nq20=6.0,
                )
            )
        for idx in range(8, 16):
            snapshot_ids.append(
                self._seed_snapshot(
                    idx,
                    regime="위험회피",
                    sectors=["Utilities"],
                    vix=28.0 + idx * 0.05,
                    sp5=-2.5,
                    sp20=-5.0,
                    nq5=-3.0,
                    nq20=-6.0,
                )
            )
        if with_lessons:
            for idx, snapshot_id in enumerate(snapshot_ids):
                candidate_id = state.record_candidate(
                    {
                        "ticker": f"T{idx:03d}",
                        "analysis_date": f"2026-04-{idx + 1:02d}",
                        "timestamp": f"2026-04-{idx + 1:02d}T09:00:00+09:00",
                        "signal_family": "momentum_pullback",
                        "quality_score": 70.0,
                    },
                    source_system="jackal",
                    source_event_type="backtest",
                    source_external_key=f"bt:2026-04-{idx + 1:02d}:T{idx:03d}",
                    source_session_id="bt_cluster_algo",
                )
                state.record_candidate_lesson(
                    candidate_id,
                    lesson_type="backtest_win" if idx < 8 else "backtest_loss",
                    label="backtest",
                    lesson_value=4.0 if idx < 8 else -1.0,
                    context_snapshot_id=snapshot_id,
                    auto_context_snapshot=False,
                )
        return snapshot_ids

    def test_one_hot_regime_known(self):
        self.assertEqual(lesson_clustering._one_hot_regime("위험회피").tolist(), [1.0, 0.0, 0.0])
        self.assertEqual(lesson_clustering._one_hot_regime("전환중").tolist(), [0.0, 1.0, 0.0])
        self.assertEqual(lesson_clustering._one_hot_regime("위험선호").tolist(), [0.0, 0.0, 1.0])

    def test_one_hot_regime_unknown_zeros(self):
        self.assertEqual(lesson_clustering._one_hot_regime("unknown").tolist(), [0.0, 0.0, 0.0])

    def test_multi_hot_sectors_normal(self):
        vector = lesson_clustering._multi_hot_sectors('["Technology", "Energy"]')
        self.assertEqual(vector.sum(), 2.0)

    def test_multi_hot_sectors_empty_list(self):
        self.assertEqual(lesson_clustering._multi_hot_sectors("[]").sum(), 0.0)

    def test_multi_hot_sectors_unknown_sector(self):
        self.assertEqual(lesson_clustering._multi_hot_sectors('["Unknown"]') .sum(), 0.0)

    def test_multi_hot_sectors_health_care_alias(self):
        direct = lesson_clustering._multi_hot_sectors('["Healthcare"]')
        alias = lesson_clustering._multi_hot_sectors('["Health Care"]')
        self.assertTrue(np.array_equal(direct, alias))

    def test_standardize_numerical_zero_mean_unit_std(self):
        matrix = np.array([[1.0, 10.0, 0.0], [2.0, 20.0, 0.0], [3.0, 30.0, 0.0]])
        standardized, means, stds = lesson_clustering._standardize_numerical(matrix, [0, 1])

        self.assertTrue(np.allclose(standardized[:, [0, 1]].mean(axis=0), [0.0, 0.0]))
        self.assertTrue(np.allclose(standardized[:, [0, 1]].std(axis=0), [1.0, 1.0]))
        self.assertEqual(means.tolist(), [2.0, 20.0])
        self.assertTrue(np.all(stds > 0))

    def test_standardize_numerical_handles_zero_std(self):
        matrix = np.array([[1.0, 2.0], [1.0, 3.0], [1.0, 4.0]])
        standardized, _means, stds = lesson_clustering._standardize_numerical(matrix, [0])

        self.assertTrue(np.allclose(standardized[:, 0], [0.0, 0.0, 0.0]))
        self.assertEqual(stds[0], 1.0)

    def test_build_feature_vector_dimensions(self):
        vector = lesson_clustering._build_feature_vector(
            {
                "vix_level": 18.0,
                "sp500_momentum_5d": 1.0,
                "sp500_momentum_20d": 2.0,
                "nasdaq_momentum_5d": 1.5,
                "nasdaq_momentum_20d": 2.5,
                "regime": "위험선호",
                "dominant_sectors": '["Technology"]',
            }
        )
        self.assertEqual(vector.shape, (19,))

    def test_kmeans_converges_with_simple_data(self):
        features = np.array([[0, 0], [0, 1], [10, 10], [10, 11], [30, 30], [31, 30]], dtype=float)
        labels, centroids = lesson_clustering._kmeans_numpy(features, 3, random_seed=7)

        self.assertEqual(len(set(labels.tolist())), 3)
        self.assertEqual(centroids.shape, (3, 2))

    def test_kmeans_returns_correct_n_clusters(self):
        features = np.vstack([np.random.RandomState(1).normal(i * 5, 0.1, (5, 2)) for i in range(4)])
        labels, _centroids = lesson_clustering._kmeans_numpy(features, 4, random_seed=42)

        self.assertEqual(len(set(labels.tolist())), 4)

    def test_kmeans_plus_plus_init_distributes_seeds(self):
        features = np.array([[0, 0], [0, 1], [10, 10], [10, 11]], dtype=float)
        centroids = lesson_clustering._kmeans_plus_plus_init(features, 2, np.random.RandomState(42))

        self.assertEqual(centroids.shape, (2, 2))
        self.assertGreater(lesson_clustering._euclidean_distance(centroids[0], centroids[1]), 1.0)

    def test_kmeans_deterministic_with_seed(self):
        features = np.array([[0, 0], [0, 1], [10, 10], [10, 11]], dtype=float)
        first = lesson_clustering._kmeans_numpy(features, 2, random_seed=42)[0]
        second = lesson_clustering._kmeans_numpy(features, 2, random_seed=42)[0]

        self.assertTrue(np.array_equal(first, second))

    def test_silhouette_well_separated_high_score(self):
        features = np.array([[0, 0], [0, 1], [10, 10], [10, 11]], dtype=float)
        labels = np.array([0, 0, 1, 1])

        self.assertGreater(lesson_clustering.calculate_silhouette_score(features, labels), 0.8)

    def test_silhouette_overlapping_low_score(self):
        features = np.array([[0, 0], [0.1, 0], [0.2, 0], [0.3, 0]], dtype=float)
        labels = np.array([0, 1, 0, 1])

        self.assertLess(lesson_clustering.calculate_silhouette_score(features, labels), 0.2)

    def test_silhouette_handles_single_cluster(self):
        features = np.array([[0, 0], [1, 1]], dtype=float)
        labels = np.array([0, 0])

        self.assertEqual(lesson_clustering.calculate_silhouette_score(features, labels), 0.0)

    def test_build_clusters_with_seeded_snapshots_dry_run(self):
        self._seed_two_cluster_snapshots()
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(n_clusters=2, conn=conn, dry_run=True, random_seed=42)

        self.assertEqual(result["n_clusters"], 2)
        self.assertEqual(len(result["cluster_summary"]), 2)
        self.assertEqual(len(result["snapshot_assignments"]), 16)
        self.assertGreater(result["silhouette_score"], 0.50)

    def test_build_clusters_default_n_clusters_8(self):
        self._seed_two_cluster_snapshots()
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(conn=conn, dry_run=True)

        self.assertEqual(result["n_clusters"], 8)

    def test_build_clusters_stores_in_db_when_not_dry_run(self):
        self._seed_two_cluster_snapshots(with_lessons=True)
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(
                n_clusters=2,
                conn=conn,
                run_id="run_algo_store",
                dry_run=False,
            )
            cluster_count = conn.execute("SELECT COUNT(*) c FROM lesson_clusters").fetchone()["c"]
            mapping_count = conn.execute("SELECT COUNT(*) c FROM snapshot_cluster_mapping").fetchone()["c"]
            cache_count = conn.execute(
                "SELECT COUNT(*) c FROM lesson_context_snapshot WHERE context_cluster_id IS NOT NULL"
            ).fetchone()["c"]

        self.assertEqual(cluster_count, 2)
        self.assertEqual(mapping_count, 16)
        self.assertEqual(cache_count, 16)
        self.assertEqual(len(result["snapshot_assignments"]), 16)

    def test_build_clusters_no_empty_cluster(self):
        self._seed_two_cluster_snapshots()
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(n_clusters=2, conn=conn, dry_run=True)

        self.assertTrue(all(cluster["size"] > 0 for cluster in result["cluster_summary"]))

    def test_get_cluster_for_snapshot_uses_cache(self):
        snapshot_ids = self._seed_two_cluster_snapshots()
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(
                n_clusters=2,
                conn=conn,
                run_id="run_cache",
                dry_run=False,
            )
            cluster_id = lesson_clustering.get_cluster_for_snapshot(snapshot_ids[0], conn=conn)

        self.assertEqual(cluster_id, result["snapshot_assignments"][snapshot_ids[0]])

    def test_get_lessons_in_cluster_returns_correct_lessons(self):
        snapshot_ids = self._seed_two_cluster_snapshots(with_lessons=True)
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(
                n_clusters=2,
                conn=conn,
                run_id="run_lessons",
                dry_run=False,
            )
            cluster_id = result["snapshot_assignments"][snapshot_ids[0]]
            lessons = lesson_clustering.get_lessons_in_cluster(cluster_id, conn=conn)

        self.assertTrue(lessons)
        self.assertTrue(all(row["context_cluster_id"] == cluster_id for row in lessons))

    def test_find_nearest_cluster_returns_closest(self):
        snapshot_ids = self._seed_two_cluster_snapshots()
        with state._connect_orca() as conn:
            result = lesson_clustering.build_clusters(
                n_clusters=2,
                conn=conn,
                run_id="run_nearest",
                dry_run=False,
            )
            cluster_id, distance = lesson_clustering.find_nearest_cluster(
                {
                    "vix_level": 14.1,
                    "sp500_momentum_5d": 2.0,
                    "sp500_momentum_20d": 5.0,
                    "nasdaq_momentum_5d": 2.5,
                    "nasdaq_momentum_20d": 6.0,
                    "regime": "위험선호",
                    "dominant_sectors": ["Technology"],
                },
                conn=conn,
                run_id="run_nearest",
            )

        self.assertEqual(cluster_id, result["snapshot_assignments"][snapshot_ids[0]])
        self.assertTrue(np.isfinite(distance))

    def test_find_nearest_cluster_with_unknown_sector(self):
        self._seed_two_cluster_snapshots()
        with state._connect_orca() as conn:
            lesson_clustering.build_clusters(n_clusters=2, conn=conn, run_id="run_unknown", dry_run=False)
            cluster_id, distance = lesson_clustering.find_nearest_cluster(
                {
                    "vix_level": 20.0,
                    "sp500_momentum_5d": 0.0,
                    "sp500_momentum_20d": 0.0,
                    "nasdaq_momentum_5d": 0.0,
                    "nasdaq_momentum_20d": 0.0,
                    "regime": "전환중",
                    "dominant_sectors": ["Unknown"],
                },
                conn=conn,
                run_id="run_unknown",
            )

        self.assertIsNotNone(cluster_id)
        self.assertTrue(np.isfinite(distance))

    def test_build_cluster_label_high_vix(self):
        label = lesson_clustering._build_cluster_label(
            {
                "raw_centroid_vix": 28.0,
                "raw_centroid_sp500_20d": -3.0,
                "raw_centroid_nasdaq_20d": -4.0,
                "dominant_regime": "위험회피",
                "common_sectors": ["Utilities"],
            }
        )

        self.assertIn("high_vix", label)
        self.assertIn("riskoff", label)
        self.assertIn("defensive", label)

    def test_build_cluster_label_low_vix_bullish(self):
        label = lesson_clustering._build_cluster_label(
            {
                "raw_centroid_vix": 14.0,
                "raw_centroid_sp500_20d": 5.0,
                "raw_centroid_nasdaq_20d": 6.0,
                "dominant_regime": "위험선호",
                "common_sectors": ["Technology"],
            }
        )

        self.assertEqual(label, "low_vix_bullish_riskon_growth")

    def test_build_cluster_label_riskoff(self):
        label = lesson_clustering._build_cluster_label(
            {
                "raw_centroid_vix": 18.0,
                "raw_centroid_sp500_20d": 0.0,
                "raw_centroid_nasdaq_20d": 0.0,
                "dominant_regime": "위험회피",
                "common_sectors": [],
            }
        )

        self.assertIn("riskoff", label)


if __name__ == "__main__":
    unittest.main()
