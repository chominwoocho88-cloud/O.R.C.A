"""Workflow contract smoke tests for Phase 5 state preservation.

These tests lock in the workflow invariants documented in
docs/analysis/2026-04-22_repository_review.md Section 6 P1-2.
If any test fails, a committed workflow contract has drifted and
needs explicit review before workflow edits continue.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKFLOW_DIR = ROOT / ".github" / "workflows"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _workflow_path(name: str) -> Path:
    return WORKFLOW_DIR / name


def _extract_concurrency_group(path: Path) -> str | None:
    """Extract concurrency.group with a lightweight line scan.

    This intentionally avoids external YAML parsers so the test remains
    dependency-free and focused on drift detection.
    """

    lines = _read_text(path).splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "concurrency:":
            continue
        for nested in lines[index + 1 :]:
            if nested.strip() and not nested.startswith((" ", "\t")):
                break
            stripped = nested.strip()
            if stripped.startswith("group:"):
                return stripped.split(":", 1)[1].strip().strip("'\"")
        return None
    return None


class TestWorkflowConcurrencyContracts(unittest.TestCase):
    """Contract 1: shared concurrency group for state-preserving workflows."""

    EXPECTED_GROUP = "orca-repo-state"
    WORKFLOWS = (
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
        "orca_reset.yml",
    )

    def test_concurrency_group_stays_orca_repo_state(self):
        for workflow_name in self.WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                group = _extract_concurrency_group(_workflow_path(workflow_name))
                self.assertEqual(
                    group,
                    self.EXPECTED_GROUP,
                    f"Workflow concurrency drift in {workflow_name}: "
                    f"group={group!r}, expected {self.EXPECTED_GROUP!r}",
                )


class TestWorkflowCheckpointContracts(unittest.TestCase):
    """Contract 2: stateful workflows must checkpoint jackal_state.db."""

    STATEFUL_WORKFLOWS = (
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
    )

    def test_stateful_workflows_call_checkpoint_jackal_db(self):
        for workflow_name in self.STATEFUL_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                count = text.count("checkpoint_jackal_db")
                self.assertGreaterEqual(
                    count,
                    1,
                    f"Phase 5 drift in {workflow_name}: checkpoint_jackal_db missing",
                )


class TestWorkflowJackalStateContracts(unittest.TestCase):
    """Contract 3: stateful workflows must reference data/jackal_state.db."""

    STATEFUL_WORKFLOWS = (
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
    )

    def test_stateful_workflows_include_jackal_state_db(self):
        for workflow_name in self.STATEFUL_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertIn(
                    "data/jackal_state.db",
                    text,
                    f"Phase 5 drift in {workflow_name}: data/jackal_state.db is missing",
                )


class TestWorkflowOrcaStateContracts(unittest.TestCase):
    """Contract 4: stateful workflows must keep handling data/orca_state.db."""

    STATEFUL_WORKFLOWS = (
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
    )

    def test_stateful_workflows_preserve_orca_state_db_handling(self):
        for workflow_name in self.STATEFUL_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertIn(
                    "data/orca_state.db",
                    text,
                    f"Phase 5 drift in {workflow_name}: data/orca_state.db handling is missing",
                )


class TestWorkflowPresenceContracts(unittest.TestCase):
    """Contract 5: core workflow file set must remain present."""

    REQUIRED_WORKFLOWS = {
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
        "orca_backtest.yml",
        "orca_reset.yml",
        "pages_dashboard.yml",
        "policy_eval.yml",
        "policy_promote.yml",
    }

    def test_required_workflow_files_exist(self):
        actual = {path.name for path in WORKFLOW_DIR.glob("*.yml")}
        missing = sorted(self.REQUIRED_WORKFLOWS - actual)
        self.assertTrue(
            self.REQUIRED_WORKFLOWS.issubset(actual),
            f"Workflow file set drifted. Missing required workflows: {missing}. "
            f"Actual files: {sorted(actual)}",
        )


class TestResearchWorkflowNonCommitContracts(unittest.TestCase):
    """Contract 6: research/policy workflows stay artifact-only."""

    NON_COMMIT_WORKFLOWS = (
        "orca_backtest.yml",
        "policy_eval.yml",
    )

    def test_research_and_policy_eval_workflows_do_not_commit_or_push(self):
        for workflow_name in self.NON_COMMIT_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertNotIn(
                    "git commit",
                    text,
                    f"Research workflow drift in {workflow_name}: found forbidden 'git commit'",
                )
                self.assertNotIn(
                    "git push",
                    text,
                    f"Research workflow drift in {workflow_name}: found forbidden 'git push'",
                )


if __name__ == "__main__":
    unittest.main()
