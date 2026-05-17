"""Phase 11.16 research report contract audit summary tests."""

from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path


def _repo_root() -> Path:
    for path in Path(__file__).resolve().parents:
        if (path / "apps" / "orca").is_dir() and (path / "shared").is_dir():
            return path
    raise RuntimeError("Repository root not found from report audit summary test")


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _import_report():
    sys.modules.pop("apps.orca.research.research_report", None)
    return importlib.import_module("apps.orca.research.research_report")


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
            "tables": {"contract_shadow_audit": 53, "jackal_shadow_signals": 0},
            "contract_shadow_audit": audit,
        },
    }


def _minimal_report(dual_db_state):
    return {
        "generated_at": "2026-05-12T09:10:00+09:00",
        "state_db": "data/orca_state.db",
        "dual_db_state": dual_db_state,
        "orca": {
            "latest": None,
            "summary": {},
            "phase_summary": {},
            "deltas": {
                "final_accuracy": None,
                "judged_count": None,
                "lesson_count": None,
            },
        },
        "jackal_backtest": {
            "latest_evaluable": None,
            "latest_raw": None,
            "summary": {},
            "latest_raw_evaluation_issue": None,
            "latest_raw_issue_classification": {},
            "latest_evaluable_age_hours": "n/a",
            "latest_evaluable_stale": None,
            "source_orca_session_id": None,
            "linked_to_latest_orca": False,
            "deltas": {
                "swing_accuracy": None,
                "d1_accuracy": None,
                "tracked": None,
            },
        },
        "jackal_shadow": {
            "latest_batch": None,
            "rolling_10": {},
            "batch_count_available": 0,
            "state": {},
        },
        "jackal_recommendation_accuracy": {},
        "market_provider_quality": {"latest_backtest": {}, "session": {}},
        "jackal_accuracy_view": {"meta": {}},
        "warnings": [],
        "notes": [],
    }


class Phase11_16ReportAuditSummaryTests(unittest.TestCase):
    def test_summary_formats_pass_count_and_latest_timestamp(self):
        report = _import_report()

        summary = report._format_contract_audit_summary(
            _snapshot(
                {
                    "row_count": 53,
                    "by_validation_status": {"pass": 53},
                    "latest_timestamp": "2026-05-12T09:00:00Z",
                }
            )
        )

        self.assertEqual(
            summary,
            "Contract audit: 53 rows (pass=53, fail=0), latest=2026-05-12T09:00:00Z",
        )

    def test_summary_formats_fail_count(self):
        report = _import_report()

        summary = report._format_contract_audit_summary(
            _snapshot(
                {
                    "row_count": 100,
                    "by_validation_status": {"pass": 95, "fail": 5},
                    "latest_timestamp": "2026-05-12T09:05:00Z",
                }
            )
        )

        self.assertEqual(
            summary,
            "Contract audit: 100 rows (pass=95, fail=5), latest=2026-05-12T09:05:00Z",
        )

    def test_summary_preserves_extra_status_counts(self):
        report = _import_report()

        summary = report._format_contract_audit_summary(
            _snapshot(
                {
                    "row_count": 57,
                    "by_validation_status": {"pass": 53, "warn": 2, "fail": 2},
                    "latest_timestamp": None,
                }
            )
        )

        self.assertEqual(summary, "Contract audit: 57 rows (pass=53, fail=2, warn=2), latest=n/a")

    def test_summary_returns_na_when_audit_key_missing(self):
        report = _import_report()
        snapshot = _snapshot({"row_count": 1})
        snapshot["jackal_state_db"].pop("contract_shadow_audit")

        self.assertEqual(report._format_contract_audit_summary(snapshot), "Contract audit: n/a")

    def test_summary_returns_na_when_audit_is_none(self):
        report = _import_report()

        self.assertEqual(report._format_contract_audit_summary(_snapshot(None)), "Contract audit: n/a")

    def test_summary_returns_zero_rows_without_latest(self):
        report = _import_report()

        self.assertEqual(
            report._format_contract_audit_summary(
                _snapshot(
                    {
                        "row_count": 0,
                        "by_validation_status": {},
                        "latest_timestamp": None,
                    }
                )
            ),
            "Contract audit: 0 rows",
        )

    def test_render_markdown_includes_contract_audit_and_table_rows(self):
        report = _import_report()
        dual_db_state = _snapshot(
            {
                "row_count": 53,
                "by_validation_status": {"pass": 53},
                "latest_timestamp": "2026-05-12T09:00:00Z",
            }
        )

        markdown = report.render_markdown(_minimal_report(dual_db_state))

        self.assertIn("JACKAL table rows", markdown)
        self.assertIn(
            "- Contract audit: 53 rows (pass=53, fail=0), latest=2026-05-12T09:00:00Z",
            markdown,
        )


if __name__ == "__main__":
    unittest.main()
