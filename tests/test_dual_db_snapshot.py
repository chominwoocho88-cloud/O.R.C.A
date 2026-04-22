"""Dual-DB snapshot coverage for P1-3 report payload expansion."""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


JACKAL_TABLES = (
    "jackal_shadow_signals",
    "jackal_live_events",
    "jackal_shadow_batches",
    "jackal_weight_snapshots",
    "jackal_recommendations",
    "jackal_accuracy_projection",
    "jackal_cooldowns",
)


def _import_module(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _create_empty_jackal_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        for table_name in JACKAL_TABLES:
            connection.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()


class TestDualDBSnapshotHelper(unittest.TestCase):
    """Low-level snapshot structure and degradation semantics."""

    def test_missing_db_files_report_exists_false_and_none_metadata(self):
        snapshot = _import_module("orca.dual_db_snapshot")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            snapshot,
            "STATE_DB_FILE",
            Path(tmpdir) / "missing_orca_state.db",
        ), patch.object(
            snapshot,
            "JACKAL_DB_FILE",
            Path(tmpdir) / "missing_jackal_state.db",
        ):
            payload = snapshot.collect_dual_db_state()

        self.assertFalse(payload["orca_state_db"]["exists"], "Missing ORCA DB should report exists=False")
        self.assertIsNone(payload["orca_state_db"]["size_bytes"], "Missing ORCA DB size should be None")
        self.assertIsNone(payload["orca_state_db"]["mtime_iso"], "Missing ORCA DB mtime should be None")
        self.assertFalse(payload["jackal_state_db"]["exists"], "Missing JACKAL DB should report exists=False")
        self.assertIsNone(payload["jackal_state_db"]["tables"], "Missing JACKAL DB tables should be None")
        self.assertNotIn("error", payload["jackal_state_db"], "Missing JACKAL DB should not report corruption")

    def test_empty_jackal_db_reports_zero_counts_and_mtime(self):
        snapshot = _import_module("orca.dual_db_snapshot")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            snapshot,
            "STATE_DB_FILE",
            Path(tmpdir) / "orca_state.db",
        ), patch.object(
            snapshot,
            "JACKAL_DB_FILE",
            Path(tmpdir) / "jackal_state.db",
        ):
            sqlite3.connect(snapshot.STATE_DB_FILE).close()
            _create_empty_jackal_db(snapshot.JACKAL_DB_FILE)

            payload = snapshot.collect_dual_db_state()

        self.assertTrue(payload["orca_state_db"]["exists"], "Existing ORCA DB should report exists=True")
        self.assertIsInstance(payload["orca_state_db"]["size_bytes"], int, "ORCA DB size must be an int")
        self.assertGreaterEqual(payload["orca_state_db"]["size_bytes"], 0, "ORCA DB size must be non-negative")
        self.assertIsNotNone(payload["orca_state_db"]["mtime_iso"], "ORCA DB mtime should be present")
        datetime.fromisoformat(payload["orca_state_db"]["mtime_iso"])

        jackal_db = payload["jackal_state_db"]
        self.assertTrue(jackal_db["exists"], "Existing JACKAL DB should report exists=True")
        self.assertIsInstance(jackal_db["size_bytes"], int, "JACKAL DB size must be an int")
        self.assertIsNotNone(jackal_db["mtime_iso"], "JACKAL DB mtime should be present")
        datetime.fromisoformat(jackal_db["mtime_iso"])
        self.assertEqual(
            jackal_db["tables"],
            {table_name: 0 for table_name in JACKAL_TABLES},
            "Empty JACKAL DB should report zero rows for every tracked table",
        )

    def test_corrupt_jackal_db_reports_error_and_no_table_counts(self):
        snapshot = _import_module("orca.dual_db_snapshot")

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            snapshot,
            "STATE_DB_FILE",
            Path(tmpdir) / "orca_state.db",
        ), patch.object(
            snapshot,
            "JACKAL_DB_FILE",
            Path(tmpdir) / "jackal_state.db",
        ):
            sqlite3.connect(snapshot.STATE_DB_FILE).close()
            snapshot.JACKAL_DB_FILE.write_text("not-a-sqlite-db", encoding="utf-8")

            payload = snapshot.collect_dual_db_state()

        jackal_db = payload["jackal_state_db"]
        self.assertTrue(jackal_db["exists"], "Corrupt JACKAL DB file should still report exists=True")
        self.assertIsNone(jackal_db["tables"], "Corrupt JACKAL DB should report tables=None")
        self.assertIn("error", jackal_db, "Corrupt JACKAL DB should surface an error field")
        self.assertTrue(jackal_db["error"], "Corrupt JACKAL DB error field should not be empty")


class TestDualDBSnapshotIntegration(unittest.TestCase):
    """Append-only integration into daily and research reports."""

    def test_save_report_appends_dual_db_state_without_removing_pr5_fields(self):
        persist = _import_module("orca.persist")
        snapshot = {
            "orca_state_db": {
                "path": "data/orca_state.db",
                "exists": True,
                "size_bytes": 100,
                "mtime_iso": "2026-04-22T09:00:00+09:00",
            },
            "jackal_state_db": {
                "path": "data/jackal_state.db",
                "exists": True,
                "size_bytes": 200,
                "mtime_iso": "2026-04-22T09:00:01+09:00",
                "tables": {table_name: 0 for table_name in JACKAL_TABLES},
            },
        }

        with tempfile.TemporaryDirectory() as tmpdir, patch.object(
            persist,
            "REPORTS_DIR",
            Path(tmpdir),
        ), patch.object(
            persist,
            "collect_dual_db_state",
            return_value=snapshot,
        ):
            path = persist.save_report(
                {
                    "analysis_date": "2026-04-22",
                    "mode": "MORNING",
                    "data_quality": "poor",
                    "failed_sources": ["yahoo"],
                }
            )
            report = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(report["data_quality"], "poor", "save_report must preserve the original data_quality")
        self.assertEqual(
            report["failed_sources"],
            ["yahoo"],
            "save_report must preserve the original failed_sources list",
        )
        self.assertEqual(report["dual_db_state"], snapshot, "save_report must append the collected dual_db_state")

    def test_research_report_keeps_legacy_state_db_and_adds_dual_db_state(self):
        research_report = _import_module("orca.research_report")
        snapshot = {
            "orca_state_db": {
                "path": "data/orca_state.db",
                "exists": True,
                "size_bytes": 100,
                "mtime_iso": "2026-04-22T09:00:00+09:00",
            },
            "jackal_state_db": {
                "path": "data/jackal_state.db",
                "exists": True,
                "size_bytes": 200,
                "mtime_iso": "2026-04-22T09:00:01+09:00",
                "tables": {table_name: 0 for table_name in JACKAL_TABLES},
            },
        }
        accuracy_view = {
            "meta": {"minimum_sample": 3, "backfill_rows": 0},
            "signal_swing_leaders": [],
            "signal_d1_leaders": [],
            "ticker_laggards": [],
            "regime_laggards": [],
            "devil_verdicts": [],
            "recommendation_regime_leaders": [],
            "recommendation_regime_laggards": [],
            "recommendation_inflow_leaders": [],
        }

        with patch.object(
            research_report,
            "collect_dual_db_state",
            return_value=snapshot,
        ), patch.object(
            research_report,
            "_find_latest_orca_sessions",
            return_value=(None, None),
        ), patch.object(
            research_report,
            "_find_latest_jackal_sessions",
            return_value=(None, None),
        ), patch.object(
            research_report,
            "list_jackal_shadow_batches",
            return_value=[],
        ), patch.object(
            research_report,
            "_build_accuracy_snapshot",
            return_value=accuracy_view,
        ):
            report = research_report.build_report()
            markdown = research_report.render_markdown(report)

        self.assertIn("state_db", report, "Research comparison must keep the legacy state_db field")
        self.assertIn("dual_db_state", report, "Research comparison must add dual_db_state")
        self.assertEqual(report["dual_db_state"], snapshot, "Research comparison dual_db_state payload drifted")
        self.assertIn("ORCA DB snapshot", markdown, "Markdown report should surface the ORCA DB snapshot line")
        self.assertIn("JACKAL table rows", markdown, "Markdown report should surface JACKAL table counts")


if __name__ == "__main__":
    unittest.main()
