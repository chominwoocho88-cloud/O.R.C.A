"""Phase 11.17 audit quality contract audit summary tests."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


def _repo_root() -> Path:
    for path in Path(__file__).resolve().parents:
        if (path / "scripts").is_dir() and (path / "shared").is_dir():
            return path
    raise RuntimeError("Repository root not found from audit quality summary test")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _import_audit_quality():
    sys.modules.pop("scripts.audit_quality", None)
    return importlib.import_module("scripts.audit_quality")


def _snapshot(audit):
    return {
        "orca_state_db": {
            "path": "data/orca_state.db",
            "exists": True,
            "size_bytes": 100,
            "mtime_iso": "2026-05-12T09:00:00+09:00",
        },
        "jackal_state_db": {
            "path": "data/jackal_state.db",
            "exists": True,
            "size_bytes": 200,
            "mtime_iso": "2026-05-12T09:00:01+09:00",
            "tables": {"contract_shadow_audit": 65, "jackal_shadow_signals": 0},
            "contract_shadow_audit": audit,
        },
    }


def _snapshot_without_audit_key():
    snapshot = _snapshot({"row_count": 1})
    snapshot["jackal_state_db"].pop("contract_shadow_audit")
    return snapshot


def _audit_with_snapshot(snapshot):
    return {
        "generated_at": "2026-05-12T09:10:00+09:00",
        "status": "pass",
        "dry_run": True,
        "note": "test",
        "checks": {
            "commands": [],
            "json_parse": {"status": "pass", "checked": 0, "error_count": 0},
            "sqlite_integrity": [],
            "requirements_drift": {"status": "pass", "drift_count": 0, "missing_count": 0},
            "research_artifacts": [],
        },
        "metrics": {
            "dual_db_state": snapshot,
            "live_accuracy": {},
            "orca_latest_evaluable_backtest": None,
            "jackal_latest_raw_backtest": None,
            "jackal_latest_raw_issue": None,
            "jackal_latest_evaluable_backtest": None,
            "jackal_projection_state": {},
            "jackal_shadow_state": {},
            "jackal_recommendation_accuracy": {},
            "jackal_operational_intake": {},
            "market_provider_quality": {"latest_backtest": {}},
            "jackal_row_counts": {},
            "prediction_status_counts": {},
        },
    }


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, _query):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        return cursor


class Phase11_17AuditQualitySummaryTests(unittest.TestCase):
    def test_markdown_includes_normal_contract_audit_summary(self):
        audit_quality = _import_audit_quality()
        markdown = audit_quality.render_markdown(
            _audit_with_snapshot(
                _snapshot(
                    {
                        "row_count": 65,
                        "by_validation_status": {"pass": 65},
                        "latest_timestamp": "2026-05-12T09:00:00Z",
                    }
                )
            )
        )

        self.assertIn(
            "- Contract audit: 65 rows (pass=65, fail=0), latest=2026-05-12T09:00:00Z",
            markdown,
        )

    def test_markdown_reports_na_when_audit_key_missing(self):
        audit_quality = _import_audit_quality()

        markdown = audit_quality.render_markdown(_audit_with_snapshot(_snapshot_without_audit_key()))

        self.assertIn("- Contract audit: n/a", markdown)

    def test_markdown_reports_na_when_audit_is_none(self):
        audit_quality = _import_audit_quality()

        markdown = audit_quality.render_markdown(_audit_with_snapshot(_snapshot(None)))

        self.assertIn("- Contract audit: n/a", markdown)

    def test_markdown_reports_zero_rows(self):
        audit_quality = _import_audit_quality()

        markdown = audit_quality.render_markdown(
            _audit_with_snapshot(
                _snapshot(
                    {
                        "row_count": 0,
                        "by_validation_status": {},
                        "latest_timestamp": None,
                    }
                )
            )
        )

        self.assertIn("- Contract audit: 0 rows", markdown)

    def test_markdown_preserves_extra_status_counts(self):
        audit_quality = _import_audit_quality()

        markdown = audit_quality.render_markdown(
            _audit_with_snapshot(
                _snapshot(
                    {
                        "row_count": 67,
                        "by_validation_status": {"pass": 65, "warn": 2},
                        "latest_timestamp": None,
                    }
                )
            )
        )

        self.assertIn("- Contract audit: 67 rows (pass=65, fail=0, warn=2), latest=n/a", markdown)

    def test_existing_audit_quality_markdown_flow_is_preserved(self):
        audit_quality = _import_audit_quality()

        markdown = audit_quality.render_markdown(_audit_with_snapshot(_snapshot(None)))

        self.assertIn("## Accuracy State", markdown)
        self.assertIn("JACKAL row counts", markdown)
        self.assertIn("Prediction status counts", markdown)

    def test_collect_state_metrics_includes_dual_db_state(self):
        audit_quality = _import_audit_quality()
        snapshot = _snapshot(
            {
                "row_count": 65,
                "by_validation_status": {"pass": 65},
                "latest_timestamp": "2026-05-12T09:00:00Z",
            }
        )

        with patch.object(audit_quality, "_read_json", return_value={}), patch.object(
            audit_quality.research_report,
            "_find_latest_orca_sessions",
            return_value=(None, None),
        ), patch.object(
            audit_quality.research_report,
            "_find_latest_raw_jackal_session",
            return_value=None,
        ), patch.object(
            audit_quality.research_report,
            "_find_latest_jackal_sessions",
            return_value=(None, None),
        ), patch.object(
            audit_quality.research_report,
            "_jackal_session_evaluation_issue",
            return_value=None,
        ), patch.object(
            audit_quality.research_report,
            "_provider_quality_from_orca_summary",
            return_value={},
        ), patch.object(
            audit_quality.research_report,
            "collect_dual_db_state",
            return_value=snapshot,
        ), patch.object(
            audit_quality,
            "describe_jackal_accuracy_projection_state",
            return_value={},
        ), patch.object(
            audit_quality,
            "describe_jackal_shadow_state",
            return_value={},
        ), patch.object(
            audit_quality,
            "describe_jackal_recommendation_accuracy_state",
            return_value={},
        ), patch.object(
            audit_quality,
            "get_provider_quality_summary",
            return_value={},
        ), patch.object(
            audit_quality,
            "collect_operational_intake",
            return_value={},
        ), patch.object(
            audit_quality,
            "_table_count",
            return_value=0,
        ), patch.object(
            audit_quality.state,
            "_connect_orca",
            return_value=_FakeConnection(),
        ), patch.object(
            audit_quality.state,
            "_connect_jackal",
            return_value=_FakeConnection(),
        ):
            metrics = audit_quality.collect_state_metrics()

        self.assertEqual(metrics["dual_db_state"], snapshot)


if __name__ == "__main__":
    unittest.main()
