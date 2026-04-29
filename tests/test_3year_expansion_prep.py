from __future__ import annotations

import importlib
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jackal import backtest
from jackal import backtest_materialization as materialization
from orca import state


ROOT = Path(__file__).resolve().parents[1]


def _workflow_text(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8-sig")


class JackalExpansionConfigTests(unittest.TestCase):
    def test_jackal_backtest_days_env_override(self):
        with patch.dict("os.environ", {"JACKAL_BACKTEST_DAYS": "756"}, clear=False):
            module = importlib.reload(backtest)
        try:
            self.assertEqual(module.BACKTEST_DAYS, 756)
        finally:
            with patch.dict("os.environ", {}, clear=True):
                importlib.reload(backtest)

    def test_jackal_history_days_env_override(self):
        with patch.dict("os.environ", {"JACKAL_HISTORY_DAYS": "1200"}, clear=False):
            module = importlib.reload(backtest)
        try:
            self.assertEqual(module.JACKAL_HISTORY_DAYS, 1200)
            self.assertEqual(module.YF_HISTORY_PERIOD, "1200d")
        finally:
            with patch.dict("os.environ", {}, clear=True):
                importlib.reload(backtest)

    def test_jackal_defaults_preserved(self):
        with patch.dict("os.environ", {}, clear=True):
            module = importlib.reload(backtest)
        self.assertEqual(module.BACKTEST_DAYS, 252)
        self.assertEqual(module.JACKAL_HISTORY_DAYS, 750)
        self.assertEqual(module.YF_HISTORY_PERIOD, "750d")


class MaterializationAddMissingTests(unittest.TestCase):
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

    def _daily_pick(self, ticker: str = "NVDA") -> list[dict]:
        return [
            {
                "rank_index": 1,
                "ticker": ticker,
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

    def _materialize(self, **overrides):
        kwargs = {
            "session_id": "bt_jackal_3y",
            "source_session_id": "bt_orca_3y",
            "analysis_date": "2025-01-03",
            "regime": "위험선호",
            "inflows": ["semiconductor"],
            "outflows": ["utilities"],
            "inflows_text": "semiconductor",
            "market_note": "risk on",
            "daily_picks": self._daily_pick(),
            "tracking_days": 10,
            "auto_context_snapshot": False,
        }
        kwargs.update(overrides)
        return materialization.materialize_backtest_day(**kwargs)

    def test_materialize_add_missing_mode_skips_existing_candidate(self):
        first = self._materialize(materialize_mode="replace")
        second = self._materialize(materialize_mode="add_missing")

        self.assertEqual(first["candidates"], 1)
        self.assertEqual(second["candidates"], 0)
        self.assertEqual(second["skipped_existing"], 1)
        with state._connect_orca() as conn:
            candidate_count = conn.execute("SELECT COUNT(*) FROM candidate_registry").fetchone()[0]
            lesson_count = conn.execute("SELECT COUNT(*) FROM candidate_lessons").fetchone()[0]
        self.assertEqual(candidate_count, 1)
        self.assertEqual(lesson_count, 1)

    def test_materialize_fail_on_duplicate_raises(self):
        self._materialize(materialize_mode="replace")
        with self.assertRaises(ValueError):
            self._materialize(materialize_mode="fail_on_duplicate")

    def test_record_backtest_lesson_no_auto_snapshot(self):
        self._materialize(materialize_mode="replace", auto_context_snapshot=False)
        with state._connect_orca() as conn:
            row = conn.execute(
                "SELECT context_snapshot_id FROM candidate_lessons"
            ).fetchone()
        self.assertIsNone(row["context_snapshot_id"])

    def test_invalid_materialize_mode_raises(self):
        with self.assertRaises(ValueError):
            self._materialize(materialize_mode="unknown")


class ExpansionWorkflowContractTests(unittest.TestCase):
    def test_orca_backtest_workflow_has_3year_inputs_by_default(self):
        text = _workflow_text("orca_backtest.yml")
        self.assertIn("run_mode:", text)
        self.assertIn("artifact_verify_only", text)
        self.assertIn("live_backtest", text)
        self.assertIn("months:", text)
        self.assertIn('default: "36"', text)
        self.assertIn("walk_forward:", text)
        self.assertIn("ORCA_BACKTEST_MONTHS", text)
        self.assertIn("--months $ORCA_BACKTEST_MONTHS", text)
        self.assertIn('default: "3869"', text)
        self.assertIn("USE_UNIFIED_FETCH", text)
        self.assertIn("ALPHA_VANTAGE_SLEEP_SECONDS: \"0.8\"", text)

    def test_jackal_learning_workflow_has_3year_inputs(self):
        text = _workflow_text("jackal_backtest_learning.yml")
        self.assertIn("backtest_days:", text)
        self.assertIn("history_days:", text)
        self.assertIn("materialize_mode:", text)
        self.assertIn("type: choice", text)
        self.assertIn("- add_missing", text)
        self.assertIn("auto_context_snapshot:", text)
        self.assertIn("--backtest-days \"${JACKAL_BACKTEST_DAYS}\"", text)
        self.assertIn("--history-days \"${JACKAL_HISTORY_DAYS}\"", text)
        self.assertIn("--materialize-mode \"${JACKAL_MATERIALIZE_MODE}\"", text)
        self.assertIn("--auto-context-snapshot \"${JACKAL_AUTO_CONTEXT_SNAPSHOT}\"", text)

    def test_jackal_learning_workflow_trims_manual_inputs(self):
        text = _workflow_text("jackal_backtest_learning.yml")
        self.assertIn("trim_workflow_input()", text)
        self.assertIn('MODE="$(trim_workflow_input "$MODE")"', text)
        self.assertIn('ARTIFACT_RUN_ID="$(trim_workflow_input "$ARTIFACT_RUN_ID")"', text)
        self.assertIn('JACKAL_MATERIALIZE_MODE_VALUE="$(trim_workflow_input "$JACKAL_MATERIALIZE_MODE_VALUE")"', text)

    def test_jackal_learning_artifact_handoff_still_runs_materialization(self):
        text = _workflow_text("jackal_backtest_learning.yml")
        self.assertIn("USE_ARTIFACT_HANDOFF", text)
        self.assertIn("Promote artifact DB", text)
        self.assertIn("Run JACKAL backtest learning", text)
        self.assertNotIn("if: env.USE_ARTIFACT_HANDOFF != 'true'", text)

    def test_wave_f_backfill_expected_counts_are_dynamic(self):
        text = _workflow_text("wave_f_backfill.yml")
        self.assertIn("expected_snapshots:", text)
        self.assertIn("expected_linked_lessons:", text)
        self.assertIn("EXPECTED_SNAPSHOTS", text)
        self.assertIn("EXPECTED_LINKED_LESSONS", text)
        self.assertIn("Resolve inputs", text)
        self.assertIn("trim_workflow_input()", text)
        self.assertIn("normalize_bool()", text)
        self.assertIn("BACKFILL_CLEANUP", text)
        self.assertNotIn("if: ${{ inputs.cleanup == true", text)

    def test_wave_f_clustering_append_mode(self):
        text = _workflow_text("wave_f_clustering.yml")
        self.assertIn("append_mode:", text)
        self.assertIn("--append", text)
        self.assertIn("source_event_type:", text)
        self.assertIn("type: choice", text)
        self.assertIn("Resolve inputs", text)
        self.assertIn("trim_workflow_input()", text)
        self.assertIn("--source-event-type", text)
        self.assertIn("CLUSTER_SOURCE_EVENT_TYPE", text)
        self.assertIn("EXPECTED_SNAPSHOTS", text)
        self.assertIn("EXPECTED_LINKED_LESSONS", text)

    def test_wave_f_archive_append_mode(self):
        text = _workflow_text("wave_f_archive.yml")
        self.assertIn("append_mode:", text)
        self.assertIn("expected_archive_count:", text)
        self.assertIn("--append", text)
        self.assertIn("EXPECTED_ARCHIVE_COUNT", text)


class ExpansionCliContractTests(unittest.TestCase):
    def test_cluster_cli_supports_append_mode(self):
        text = (ROOT / "scripts" / "build_lesson_clusters.py").read_text(encoding="utf-8")
        self.assertIn("--append", text)
        self.assertIn("preserving existing runs", text)
        self.assertIn("mutually exclusive", text)

    def test_archive_cli_supports_append_mode(self):
        text = (ROOT / "scripts" / "build_lesson_archive.py").read_text(encoding="utf-8")
        self.assertIn("--append", text)
        self.assertIn("preserving existing archive rows", text)
        self.assertIn("mutually exclusive", text)


if __name__ == "__main__":
    unittest.main()
