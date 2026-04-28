from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orca import lesson_archive_store
from orca import state


class DbArchiveMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_db = Path(self.tmpdir) / "orca_state.db"
        self.jackal_db = Path(self.tmpdir) / "jackal_state.db"
        self.cold_db = Path(self.tmpdir) / "archive" / "lesson_archive_cold.db"
        self.patchers = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch.object(lesson_archive_store, "COLD_ARCHIVE_DB_FILE", self.cold_db),
        ]
        for patcher in self.patchers:
            patcher.start()
        state.init_state_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _seed_snapshot_cluster_lesson(self) -> tuple[str, str, str]:
        snapshot_id = state.record_lesson_context_snapshot(
            {
                "snapshot_id": "ctx_archive_maint",
                "trading_date": "2026-04-20",
                "source_event_type": "backtest_backfill",
                "regime": "risk_on",
                "dominant_sectors": ["Technology"],
            }
        )
        candidate_id = state.record_candidate(
            {
                "ticker": "NVDA",
                "analysis_date": "2026-04-20",
                "timestamp": "2026-04-20T09:00:00+09:00",
                "signal_family": "momentum_pullback",
            },
            source_system="jackal",
            source_event_type="backtest",
            source_external_key="archive-maint:NVDA",
            source_session_id="bt_archive_maint",
        )
        lesson_id = state.record_candidate_lesson(
            candidate_id,
            lesson_type="backtest_win",
            label="backtest",
            lesson_value=5.0,
            lesson={"ticker": "NVDA"},
            context_snapshot_id=snapshot_id,
            auto_context_snapshot=False,
        )
        with state._connect_orca() as conn:
            state.record_lesson_cluster(
                conn,
                {
                    "cluster_id": "cluster_archive_maint",
                    "cluster_label": "medium_vix_growth",
                    "size": 1,
                    "representative_snapshot_id": snapshot_id,
                    "run_id": "cluster_run_archive_maint",
                    "created_at": "2026-04-20T09:00:00+09:00",
                },
            )
            state.assign_snapshot_to_cluster(
                conn,
                snapshot_id,
                "cluster_archive_maint",
                0.2,
                "cluster_run_archive_maint",
            )
        return snapshot_id, candidate_id, lesson_id

    def _record_archive(self, archive_id: str, lesson_id: str, run_id: str) -> None:
        with state._connect_orca() as conn:
            state.record_lesson_archive(
                conn,
                archive_id,
                lesson_id,
                "cluster_archive_maint",
                run_id,
                "high",
                0.9,
                1.0,
                1.0,
                1.0,
                1.0,
                1.0,
                5.0,
                5.0,
                3,
                "momentum_pullback",
                "NVDA",
                "2026-04-20",
            )
            archived_at = "2026-04-01T09:00:00+09:00" if "old" in run_id else "2026-04-28T09:00:00+09:00"
            conn.execute("UPDATE lesson_archive SET archived_at=?, updated_at=? WHERE archive_id=?", (archived_at, archived_at, archive_id))

    def _cold_count(self, table: str) -> int:
        conn = sqlite3.connect(self.cold_db)
        try:
            return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        finally:
            conn.close()

    def test_archive_migration_to_cold(self):
        _snapshot_id, _candidate_id, lesson_id = self._seed_snapshot_cluster_lesson()
        self._record_archive("archive_old", lesson_id, "archive_run_old")
        self._record_archive("archive_latest", lesson_id, "archive_run_latest")
        session_id = state.start_backtest_session("orca", "walk_forward")
        state.record_backtest_day(session_id, "2026-04-20", "Final Pass", analysis={"ok": True}, results=[{"ticker": "NVDA"}])
        state.record_backtest_pick_results(session_id, "jackal", "2026-04-20", "Final Pass", [{"ticker": "NVDA"}])
        with state._connect_orca() as conn:
            state.record_retrieval_log(
                conn,
                {
                    "log_id": "log_cold",
                    "source_system": "jackal_backtest",
                    "source_event_type": "backtest",
                    "trading_date": "2026-04-20",
                    "top_k": 5,
                    "lessons_count": 1,
                    "top_lessons_json": [{"lesson_id": lesson_id}],
                    "mode": "observe",
                },
            )
            result = lesson_archive_store.migrate_to_cold(conn, cold_db_path=self.cold_db)
            hot_counts = {
                "archives": conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0],
                "logs": conn.execute("SELECT COUNT(*) FROM retrieval_log").fetchone()[0],
                "days": conn.execute("SELECT COUNT(*) FROM backtest_daily_results").fetchone()[0],
                "picks": conn.execute("SELECT COUNT(*) FROM backtest_pick_results").fetchone()[0],
            }

        self.assertEqual(result["moved"]["lesson_archive"], 1)
        self.assertEqual(result["moved"]["retrieval_log"], 1)
        self.assertEqual(result["moved"]["backtest_daily_results"], 1)
        self.assertEqual(result["moved"]["backtest_pick_results"], 1)
        self.assertEqual(hot_counts, {"archives": 1, "logs": 0, "days": 0, "picks": 0})
        self.assertEqual(self._cold_count("lesson_archive"), 1)
        self.assertEqual(self._cold_count("retrieval_log"), 1)
        self.assertEqual(self._cold_count("backtest_daily_results"), 1)
        self.assertEqual(self._cold_count("backtest_pick_results"), 1)

    def test_archive_search_across_hot_cold(self):
        _snapshot_id, _candidate_id, lesson_id = self._seed_snapshot_cluster_lesson()
        self._record_archive("archive_old", lesson_id, "archive_run_old")
        self._record_archive("archive_latest", lesson_id, "archive_run_latest")
        with state._connect_orca() as conn:
            lesson_archive_store.migrate_to_cold(conn, cold_db_path=self.cold_db, include_retrieval_logs=False, include_backtest_results=False)
            archives = state.get_archives_for_lesson(conn, lesson_id)
            cluster_archives = state.get_archives_for_cluster(conn, "cluster_archive_maint", run_id="archive_run_old")

        self.assertEqual({row["archive_id"] for row in archives}, {"archive_old", "archive_latest"})
        self.assertEqual([row["archive_id"] for row in cluster_archives], ["archive_old"])

    def test_vacuum_no_data_loss(self):
        _snapshot_id, _candidate_id, lesson_id = self._seed_snapshot_cluster_lesson()
        self._record_archive("archive_old", lesson_id, "archive_run_old")
        self._record_archive("archive_latest", lesson_id, "archive_run_latest")
        with state._connect_orca() as conn:
            before_total = conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0]
            lesson_archive_store.migrate_to_cold(conn, cold_db_path=self.cold_db, include_retrieval_logs=False, include_backtest_results=False)
            lesson_archive_store.vacuum_sqlite_database(self.state_db)
            lesson_archive_store.vacuum_sqlite_database(self.cold_db)
            after_hot = conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0]

        self.assertEqual(before_total, 2)
        self.assertEqual(after_hot + self._cold_count("lesson_archive"), 2)


if __name__ == "__main__":
    unittest.main()
