from __future__ import annotations

import contextlib
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import state
from scripts import build_lesson_clusters


class BuildLessonClustersCliTests(unittest.TestCase):
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

    def _run_cli(self, args: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = build_lesson_clusters.main(args)
        return code, output.getvalue()

    def _seed_snapshots(self, with_lessons: bool = False) -> list[str]:
        snapshot_ids: list[str] = []
        for idx in range(6):
            snapshot_ids.append(
                state.record_lesson_context_snapshot(
                    {
                        "snapshot_id": f"ctx_on_{idx}",
                        "trading_date": f"2026-04-{idx + 1:02d}",
                        "source_event_type": "backtest_backfill",
                        "regime": "위험선호",
                        "dominant_sectors": ["Technology"],
                        "vix_level": 14.0 + idx * 0.05,
                        "sp500_momentum_5d": 2.0,
                        "sp500_momentum_20d": 5.0,
                        "nasdaq_momentum_5d": 2.5,
                        "nasdaq_momentum_20d": 6.0,
                    }
                )
            )
        for idx in range(6):
            snapshot_ids.append(
                state.record_lesson_context_snapshot(
                    {
                        "snapshot_id": f"ctx_off_{idx}",
                        "trading_date": f"2026-04-{idx + 7:02d}",
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
            )
        if with_lessons:
            for idx, snapshot_id in enumerate(snapshot_ids):
                candidate_id = state.record_candidate(
                    {
                        "ticker": f"T{idx:03d}",
                        "analysis_date": f"2026-04-{idx + 1:02d}",
                        "timestamp": f"2026-04-{idx + 1:02d}T09:00:00+09:00",
                        "signal_family": "context_cluster_test",
                        "quality_score": 70.0,
                    },
                    source_system="jackal",
                    source_event_type="backtest",
                    source_external_key=f"cluster-cli:{idx}",
                    source_session_id="cluster_cli_test",
                )
                state.record_candidate_lesson(
                    candidate_id,
                    lesson_type="backtest_win",
                    label="backtest",
                    lesson_value=1.0,
                    context_snapshot_id=snapshot_id,
                    auto_context_snapshot=False,
                )
        return snapshot_ids

    def _cluster_counts(self) -> tuple[int, int, int]:
        with state._connect_orca() as conn:
            clusters = conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0]
            mappings = conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0]
            cached = conn.execute(
                "SELECT COUNT(*) FROM lesson_context_snapshot WHERE context_cluster_id IS NOT NULL"
            ).fetchone()[0]
        return clusters, mappings, cached

    def test_cli_dry_run_no_db_changes(self):
        self._seed_snapshots()

        code, output = self._run_cli(
            [
                "--n-clusters",
                "2",
                "--expected-snapshots",
                "12",
                "--expected-linked-lessons",
                "12",
            ]
        )

        self.assertEqual(code, 0, output)
        self.assertIn("MODE: DRY RUN", output)
        self.assertEqual(self._cluster_counts(), (0, 0, 0))

    def test_cli_source_event_type_filters_snapshots(self):
        self._seed_snapshots()
        state.record_lesson_context_snapshot(
            {
                "snapshot_id": "ctx_legacy_backtest",
                "trading_date": "2026-04-20",
                "source_event_type": "backtest",
                "regime": "?꾪뿕?좏샇",
                "dominant_sectors": ["Technology"],
                "vix_level": 14.0,
                "sp500_momentum_5d": 2.0,
                "sp500_momentum_20d": 5.0,
                "nasdaq_momentum_5d": 2.5,
                "nasdaq_momentum_20d": 6.0,
            }
        )

        code, output = self._run_cli(
            [
                "--n-clusters",
                "2",
                "--source-event-type",
                "backtest_backfill",
                "--expected-snapshots",
                "12",
            ]
        )

        self.assertEqual(code, 0, output)
        self.assertIn("clustering source: backtest_backfill", output)
        self.assertIn("Assignments: 12", output)

    def test_cli_execute_creates_clusters_and_backup(self):
        self._seed_snapshots(with_lessons=True)

        code, output = self._run_cli(
            [
                "--execute",
                "--force-rebuild",
                "--n-clusters",
                "2",
                "--run-id",
                "run_cli_a",
                "--expected-snapshots",
                "12",
                "--expected-linked-lessons",
                "12",
            ]
        )

        self.assertEqual(code, 0, output)
        self.assertEqual(self._cluster_counts(), (2, 12, 12))
        backups = list(self.state_db.parent.glob("orca_state.db.backup-pre-clustering-*"))
        self.assertEqual(len(backups), 1)

    def test_cli_execute_refuses_existing_run_without_force_rebuild(self):
        self._seed_snapshots()
        first_code, first_output = self._run_cli(
            ["--execute", "--force-rebuild", "--n-clusters", "2", "--run-id", "run_cli_a", "--no-backup"]
        )
        self.assertEqual(first_code, 0, first_output)

        second_code, second_output = self._run_cli(
            ["--execute", "--n-clusters", "2", "--run-id", "run_cli_b", "--no-backup"]
        )

        self.assertEqual(second_code, 1)
        self.assertIn("Existing clustering run found", second_output)
        with state._connect_orca() as conn:
            self.assertEqual(state.get_latest_run_id(conn), "run_cli_a")

    def test_cli_force_rebuild_replaces_existing_run(self):
        self._seed_snapshots()
        first_code, first_output = self._run_cli(
            ["--execute", "--force-rebuild", "--n-clusters", "2", "--run-id", "run_cli_a", "--no-backup"]
        )
        self.assertEqual(first_code, 0, first_output)

        second_code, second_output = self._run_cli(
            ["--execute", "--force-rebuild", "--n-clusters", "2", "--run-id", "run_cli_b", "--no-backup"]
        )

        self.assertEqual(second_code, 0, second_output)
        with state._connect_orca() as conn:
            run_ids = [
                row["run_id"]
                for row in conn.execute("SELECT DISTINCT run_id FROM lesson_clusters ORDER BY run_id")
            ]
        self.assertEqual(run_ids, ["run_cli_b"])
        self.assertEqual(self._cluster_counts(), (2, 12, 12))

    def test_cli_dry_run_verify_failure_returns_nonzero_without_writes(self):
        self._seed_snapshots()

        code, output = self._run_cli(
            ["--n-clusters", "2", "--min-silhouette", "2.0"]
        )

        self.assertEqual(code, 1)
        self.assertIn("FAIL clustering verification", output)
        self.assertEqual(self._cluster_counts(), (0, 0, 0))

    def test_workflow_declares_safe_manual_inputs(self):
        workflow = Path(".github/workflows/wave_f_clustering.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("dry_run", workflow)
        self.assertNotIn("type: boolean", workflow)
        self.assertIn('default: "true"', workflow)
        self.assertIn("n_clusters", workflow)
        self.assertIn("source_event_type", workflow)
        self.assertIn("type: choice", workflow)
        self.assertIn("CLUSTER_SOURCE_EVENT_TYPE", workflow)
        self.assertIn("Resolve inputs", workflow)
        self.assertIn("force_rebuild", workflow)
        self.assertIn('default: "756"', workflow)
        self.assertIn('default: "3864"', workflow)
        self.assertIn('default: "0.11"', workflow)
        self.assertIn("scripts/build_lesson_clusters.py", workflow)


if __name__ == "__main__":
    unittest.main()
