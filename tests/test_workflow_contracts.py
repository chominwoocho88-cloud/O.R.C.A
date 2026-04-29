"""Workflow contract smoke tests for Phase 5 state preservation.

These tests lock in the workflow invariants documented in
docs/analysis/2026-04-22_repository_review.md Section 6 P1-2.
If any test fails, a committed workflow contract has drifted and
needs explicit review before workflow edits continue.
"""

from __future__ import annotations

import subprocess
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


def _extract_step_block(path: Path, step_name: str) -> str:
    """Return one workflow step block by its display name."""

    lines = _read_text(path).splitlines()
    marker = f"- name: {step_name}"
    for index, line in enumerate(lines):
        if line.strip() != marker:
            continue
        indent = len(line) - len(line.lstrip())
        block = [line]
        for nested in lines[index + 1 :]:
            nested_indent = len(nested) - len(nested.lstrip())
            if nested_indent == indent and nested.strip().startswith("- name:"):
                break
            block.append(nested)
        return "\n".join(block)
    raise AssertionError(f"Step {step_name!r} not found in {path.name}")


def _extract_workflow_dispatch_block(path: Path) -> str:
    """Return the workflow_dispatch block for UI contract checks."""

    lines = _read_text(path).splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "workflow_dispatch:":
            continue
        indent = len(line) - len(line.lstrip())
        block = [line]
        for nested in lines[index + 1 :]:
            nested_indent = len(nested) - len(nested.lstrip())
            if nested.strip() and nested_indent <= indent:
                break
            block.append(nested)
        return "\n".join(block)
    raise AssertionError(f"workflow_dispatch block not found in {path.name}")


def _line_number_containing(path: Path, needle: str) -> int:
    """Return the 1-based line number containing a workflow contract needle."""

    for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
        if needle in line:
            return line_number
    raise AssertionError(f"{needle!r} not found in {path.name}")


class TestWorkflowConcurrencyContracts(unittest.TestCase):
    """Contract 1: shared concurrency group for state-preserving workflows."""

    EXPECTED_GROUP = "orca-repo-state"
    WORKFLOWS = (
        "db_vacuum.yml",
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
        "jackal_backtest_learning.yml",
        "orca_reset.yml",
        "wave_f_archive.yml",
        "wave_f_backfill.yml",
        "wave_f_clustering.yml",
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
        "jackal_backtest_learning.yml",
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
        "jackal_backtest_learning.yml",
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


class TestTrackerWorkflowQualityContracts(unittest.TestCase):
    def test_tracker_workflow_logs_inputs_and_uploads_quality_artifacts(self):
        text = _read_text(_workflow_path("jackal_tracker.yml"))
        self.assertIn("FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true", text)
        self.assertIn("uses: actions/checkout@v6", text)
        self.assertIn("uses: actions/setup-python@v6", text)
        self.assertIn("uses: actions/upload-artifact@v6", text)
        self.assertIn("Resolve Tracker inputs", text)
        self.assertIn("TRACKER_ARGS", text)
        self.assertIn("TRACKER_WILL_SAVE_RESULTS", text)
        self.assertIn("python -m jackal.tracker ${TRACKER_ARGS}", text)
        self.assertIn("Dry-run persistence skipped", text)
        self.assertIn("state persistence intentionally skipped", text)
        self.assertIn("if: env.TRACKER_WILL_SAVE_RESULTS == 'true'", text)
        self.assertIn("no tracker state changes to commit", text)
        self.assertIn("Commit created:", text)
        self.assertIn("Push succeeded", text)
        self.assertIn("scripts/check_requirements_drift.py", text)
        self.assertIn("scripts/check_jackal_operational_intake.py", text)
        self.assertIn("scripts/audit_quality.py --dry-run", text)
        self.assertIn("name: jackal-tracker-quality", text)


class TestQualityWorkflowNodeRuntimeContracts(unittest.TestCase):
    def test_quality_workflow_uses_node24_action_versions(self):
        text = _read_text(_workflow_path("quality.yml"))
        self.assertIn("uses: actions/checkout@v6", text)
        self.assertIn("uses: actions/setup-python@v6", text)
        self.assertIn("uses: actions/upload-artifact@v6", text)


class TestLowMediumWorkflowNodeRuntimeContracts(unittest.TestCase):
    LOW_MEDIUM_WORKFLOWS = {
        "pages_dashboard.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "orca_backtest.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
            "uses: actions/upload-artifact@v6",
        ),
        "policy_eval.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
            "uses: actions/download-artifact@v8",
            "uses: actions/upload-artifact@v6",
        ),
        "policy_promote.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
            "uses: actions/download-artifact@v8",
            "uses: actions/upload-artifact@v6",
        ),
    }

    LEGACY_NODE20_ACTIONS = (
        "uses: actions/checkout@v4",
        "uses: actions/setup-python@v5",
        "uses: actions/upload-artifact@v4",
        "uses: actions/download-artifact@v4",
    )

    def test_low_medium_workflows_use_node24_action_versions(self):
        for workflow_name, expected_actions in self.LOW_MEDIUM_WORKFLOWS.items():
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                for action in expected_actions:
                    self.assertIn(action, text)
                for legacy_action in self.LEGACY_NODE20_ACTIONS:
                    self.assertNotIn(
                        legacy_action,
                        text,
                        f"{workflow_name} still references {legacy_action}",
                    )


class TestArtifactWorkflowContracts(unittest.TestCase):
    def test_orca_backtest_upload_artifact_contract_is_preserved(self):
        block = _extract_step_block(_workflow_path("orca_backtest.yml"), "Upload research state")
        self.assertIn("uses: actions/upload-artifact@v6", block)
        self.assertIn("name: research-state-${{ github.run_id }}", block)
        self.assertIn("if-no-files-found: warn", block)
        self.assertIn("path: data/orca_state.db", block)
        self.assertIn("retention-days: 90", block)
        self.assertNotIn("data/orca_state.db-wal", block)
        self.assertNotIn("data/orca_state.db-shm", block)

    def test_policy_eval_download_artifact_contract_is_preserved(self):
        block = _extract_step_block(
            _workflow_path("policy_eval.yml"),
            "Download research state artifact",
        )
        self.assertIn("if: ${{ inputs.artifact_name != '' }}", block)
        self.assertIn("uses: actions/download-artifact@v8", block)
        self.assertIn("name: ${{ inputs.artifact_name }}", block)
        self.assertIn("path: .", block)
        self.assertNotIn("run-id:", block)

    def test_policy_eval_upload_artifact_contract_is_preserved(self):
        text = _read_text(_workflow_path("policy_eval.yml"))
        block = _extract_step_block(_workflow_path("policy_eval.yml"), "Upload evaluation artifacts")
        self.assertIn("artifact_name = f\"policy-eval-{os.environ['GITHUB_RUN_ID']}\"", text)
        self.assertIn("uses: actions/upload-artifact@v6", block)
        self.assertIn("name: policy-eval-${{ github.run_id }}", block)
        self.assertIn("if-no-files-found: warn", block)
        for artifact_path in (
            "data/orca_state.db",
            "data/orca_state.db-shm",
            "data/orca_state.db-wal",
            "reports/orca_research_comparison.md",
            "reports/orca_research_comparison.json",
            "reports/orca_research_gate.md",
            "reports/orca_research_gate.json",
        ):
            self.assertIn(artifact_path, block)

    def test_policy_promote_download_artifact_contract_is_preserved(self):
        block = _extract_step_block(
            _workflow_path("policy_promote.yml"),
            "Download policy-eval artifact",
        )
        self.assertIn("if: ${{ inputs.artifact_name != '' }}", block)
        self.assertIn("uses: actions/download-artifact@v8", block)
        self.assertIn("name: ${{ inputs.artifact_name }}", block)
        self.assertIn("path: .", block)
        self.assertNotIn("run-id:", block)

    def test_policy_promote_upload_artifact_contract_is_preserved(self):
        text = _read_text(_workflow_path("policy_promote.yml"))
        block = _extract_step_block(_workflow_path("policy_promote.yml"), "Upload promotion artifacts")
        self.assertIn("artifact_name = f\"policy-promote-{os.environ['GITHUB_RUN_ID']}\"", text)
        self.assertIn("uses: actions/upload-artifact@v6", block)
        self.assertIn("name: policy-promote-${{ github.run_id }}", block)
        self.assertIn("if-no-files-found: warn", block)
        self.assertIn("reports/orca_policy_promotion.md", block)
        self.assertIn("reports/orca_policy_promotion.json", block)

    def test_backtest_policy_handoff_names_are_preserved(self):
        text = _read_text(_workflow_path("orca_backtest.yml"))
        self.assertIn("artifact_name: research-state-${{ github.run_id }}", text)
        self.assertIn("artifact_name: ${{ needs.policy-eval.outputs.artifact_name }}", text)


class TestPolicyWorkflowDependencyContracts(unittest.TestCase):
    POLICY_WORKFLOWS = (
        ("policy_eval.yml", "Build Research Comparison Report"),
        ("policy_promote.yml", "Build policy promotion decision"),
    )

    def test_policy_workflows_install_repo_dependencies_before_running_modules(self):
        for workflow_name, module_step in self.POLICY_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                path = _workflow_path(workflow_name)
                setup_block = _extract_step_block(path, "Setup Python")
                install_block = _extract_step_block(path, "Install dependencies")
                self.assertIn("uses: actions/setup-python@v6", setup_block)
                self.assertIn("cache: pip", setup_block)
                self.assertIn("pip install -r requirements.txt", install_block)
                self.assertLess(
                    _line_number_containing(path, "- name: Install dependencies"),
                    _line_number_containing(path, f"- name: {module_step}"),
                )


class TestHighRiskWorkflowNodeRuntimeContracts(unittest.TestCase):
    HIGH_RISK_WORKFLOWS = {
        "db_vacuum.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "jackal_backtest_learning.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
            "uses: actions/download-artifact@v8",
        ),
        "jackal_scanner.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "orca_daily.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "orca_jackal.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
            "uses: actions/upload-artifact@v6",
        ),
        "orca_reset.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "wave_f_archive.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "wave_f_backfill.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
        "wave_f_clustering.yml": (
            "uses: actions/checkout@v6",
            "uses: actions/setup-python@v6",
        ),
    }

    LEGACY_NODE20_ACTIONS = (
        "uses: actions/checkout@v4",
        "uses: actions/setup-python@v5",
        "uses: actions/upload-artifact@v4",
        "uses: actions/download-artifact@v4",
    )

    def test_high_risk_workflows_use_node24_action_versions(self):
        for workflow_name, expected_actions in self.HIGH_RISK_WORKFLOWS.items():
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                for action in expected_actions:
                    self.assertIn(action, text)
                for legacy_action in self.LEGACY_NODE20_ACTIONS:
                    self.assertNotIn(
                        legacy_action,
                        text,
                        f"{workflow_name} still references {legacy_action}",
                    )


class TestHighRiskWorkflowStatePersistenceContracts(unittest.TestCase):
    HIGH_RISK_COMMIT_WORKFLOWS = (
        "db_vacuum.yml",
        "jackal_backtest_learning.yml",
        "jackal_scanner.yml",
        "orca_daily.yml",
        "orca_jackal.yml",
        "orca_reset.yml",
        "wave_f_archive.yml",
        "wave_f_backfill.yml",
        "wave_f_clustering.yml",
    )

    STANDARD_REBASE_WORKFLOWS = (
        "db_vacuum.yml",
        "jackal_backtest_learning.yml",
        "jackal_scanner.yml",
        "orca_daily.yml",
        "orca_reset.yml",
        "wave_f_archive.yml",
        "wave_f_backfill.yml",
        "wave_f_clustering.yml",
    )

    DB_STATE_WORKFLOW_PATHS = {
        "db_vacuum.yml": ("data/orca_state.db",),
        "jackal_backtest_learning.yml": ("data/orca_state.db", "data/jackal_state.db"),
        "jackal_scanner.yml": ("data/orca_state.db", "data/jackal_state.db"),
        "orca_daily.yml": ("data/orca_state.db", "data/jackal_state.db"),
        "orca_jackal.yml": ("data/orca_state.db", "data/jackal_state.db"),
        "wave_f_archive.yml": ("data/orca_state.db",),
        "wave_f_backfill.yml": ("data/orca_state.db",),
        "wave_f_clustering.yml": ("data/orca_state.db",),
    }

    RESET_STATE_PATHS = (
        "data/accuracy.json",
        "data/memory.json",
        "data/orca_lessons.json",
        "jackal/hunt_log.json",
    )

    def test_high_risk_commit_workflows_keep_write_permissions(self):
        for workflow_name in self.HIGH_RISK_COMMIT_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertIn("contents: write", text)

    def test_high_risk_commit_workflows_keep_repo_state_concurrency(self):
        for workflow_name in self.HIGH_RISK_COMMIT_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                group = _extract_concurrency_group(_workflow_path(workflow_name))
                self.assertEqual(group, "orca-repo-state")

    def test_high_risk_db_state_paths_are_preserved(self):
        for workflow_name, paths in self.DB_STATE_WORKFLOW_PATHS.items():
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                for path in paths:
                    self.assertIn(path, text)

    def test_reset_state_paths_are_preserved(self):
        text = _read_text(_workflow_path("orca_reset.yml"))
        for path in self.RESET_STATE_PATHS:
            self.assertIn(path, text)

    def test_standard_commit_workflows_have_push_safety_logs(self):
        required = (
            "Git status before staging:",
            "Staged state diff:",
            "git diff --cached --name-status",
            "no state changes to commit",
            "Commit created:",
            "git pull --rebase origin main",
            "Initial push failed; rebasing once and retrying",
            "Push succeeded",
            "Git status after push:",
        )
        for workflow_name in self.STANDARD_REBASE_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                for marker in required:
                    self.assertIn(marker, text)

    def test_standard_db_commit_workflows_checkpoint_before_staging(self):
        for workflow_name in self.STANDARD_REBASE_WORKFLOWS:
            if workflow_name == "orca_reset.yml":
                continue
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                checkpoint_idx = text.find("PRAGMA wal_checkpoint(TRUNCATE);")
                staging_idx = text.find("Git status before staging:")
                self.assertTrue(0 <= checkpoint_idx < staging_idx)

    def test_orca_jackal_keeps_replay_push_safety_logs(self):
        text = _read_text(_workflow_path("orca_jackal.yml"))
        for marker in (
            "Git status before staging:",
            "Aligning with origin/main before replaying JACKAL-owned state",
            "git fetch origin main",
            "git reset --hard origin/main",
            "Staged state diff:",
            "git diff --cached --name-status",
            "no state changes to commit",
            "Commit created:",
            "git push origin HEAD:main",
            "Push succeeded",
            "Push failed on attempt",
            "Git status after push:",
        ):
            self.assertIn(marker, text)


class TestHighRiskArtifactContracts(unittest.TestCase):
    def test_learning_artifact_handoff_contract_is_preserved(self):
        block = _extract_step_block(
            _workflow_path("jackal_backtest_learning.yml"),
            "Download preflight ORCA artifact",
        )
        self.assertIn("if: env.USE_ARTIFACT_HANDOFF == 'true'", block)
        self.assertIn("uses: actions/download-artifact@v8", block)
        self.assertIn("name: research-state-${{ github.event.inputs.artifact_run_id }}", block)
        self.assertIn("path: _artifact_handoff/", block)
        self.assertIn("github-token: ${{ github.token }}", block)
        self.assertIn("repository: ${{ github.repository }}", block)
        self.assertIn("run-id: ${{ github.event.inputs.artifact_run_id }}", block)

    def test_jackal_session_quality_artifact_contract_is_preserved(self):
        block = _extract_step_block(
            _workflow_path("orca_jackal.yml"),
            "Upload smoke quality artifacts",
        )
        self.assertIn("uses: actions/upload-artifact@v6", block)
        self.assertIn("if: always()", block)
        self.assertIn("name: jackal-session-quality", block)
        self.assertIn("${{ runner.temp }}/requirements_drift.json", block)
        self.assertIn("${{ runner.temp }}/jackal_operational_intake.json", block)
        self.assertIn("${{ runner.temp }}/orca_audit_smoke.json", block)
        self.assertIn("if-no-files-found: ignore", block)


class TestWorkflowDispatchUiContracts(unittest.TestCase):
    WORKFLOWS_WITH_DISPATCH = (
        "db_vacuum.yml",
        "jackal_backtest_learning.yml",
        "jackal_scanner.yml",
        "jackal_tracker.yml",
        "orca_backtest.yml",
        "orca_daily.yml",
        "orca_jackal.yml",
        "orca_reset.yml",
        "pages_dashboard.yml",
        "policy_eval.yml",
        "policy_promote.yml",
        "quality.yml",
        "wave_f_archive.yml",
        "wave_f_backfill.yml",
        "wave_f_clustering.yml",
    )

    def test_manual_workflow_ui_uses_choice_instead_of_boolean_toggles(self):
        for workflow_name in self.WORKFLOWS_WITH_DISPATCH:
            with self.subTest(workflow=workflow_name):
                block = _extract_workflow_dispatch_block(_workflow_path(workflow_name))
                self.assertNotIn("type: boolean", block)

    def test_policy_eval_dispatch_strict_handles_choice_and_workflow_call_bool(self):
        text = _read_text(_workflow_path("policy_eval.yml"))
        dispatch = _extract_workflow_dispatch_block(_workflow_path("policy_eval.yml"))
        self.assertIn("type: choice", dispatch)
        self.assertIn('default: "true"', dispatch)
        self.assertIn("inputs.strict == true || inputs.strict == 'true'", text)

    def test_wave_f_three_year_dispatch_defaults_are_current(self):
        backfill = _read_text(_workflow_path("wave_f_backfill.yml"))
        clustering = _read_text(_workflow_path("wave_f_clustering.yml"))
        archive = _read_text(_workflow_path("wave_f_archive.yml"))

        self.assertIn('default: "756"', backfill)
        self.assertIn('default: "3869"', backfill)
        self.assertIn("EXPECTED_SNAPSHOTS_VALUE=\"756\"", backfill)
        self.assertIn("EXPECTED_LINKED_LESSONS_VALUE=\"3869\"", backfill)
        self.assertIn("EXPECTED_SNAPSHOTS', '756'", backfill)
        self.assertIn("EXPECTED_LINKED_LESSONS', '3869'", backfill)

        self.assertIn('default: "756"', clustering)
        self.assertIn('default: "3864"', clustering)
        self.assertIn("EXPECTED_SNAPSHOTS_VALUE=\"756\"", clustering)
        self.assertIn("EXPECTED_LINKED_LESSONS_VALUE=\"3864\"", clustering)
        self.assertIn("EXPECTED_SNAPSHOTS', '756'", clustering)
        self.assertIn("EXPECTED_LINKED_LESSONS', '3864'", clustering)
        self.assertIn("if: env.CLUSTER_DRY_RUN != 'true'", clustering)
        self.assertNotIn("inputs.dry_run != true", clustering)
        self.assertIn('default: "0.11"', clustering)
        self.assertIn('MIN_SILHOUETTE_VALUE="0.11"', clustering)

        self.assertIn('default: "3864"', archive)


class TestWorkflowOrcaStateContracts(unittest.TestCase):
    """Contract 4: stateful workflows must keep handling data/orca_state.db."""

    STATEFUL_WORKFLOWS = (
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
        "jackal_backtest_learning.yml",
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
        "db_vacuum.yml",
        "orca_daily.yml",
        "orca_jackal.yml",
        "jackal_tracker.yml",
        "jackal_scanner.yml",
        "jackal_backtest_learning.yml",
        "orca_backtest.yml",
        "orca_reset.yml",
        "pages_dashboard.yml",
        "policy_eval.yml",
        "policy_promote.yml",
        "wave_f_archive.yml",
        "wave_f_backfill.yml",
        "wave_f_clustering.yml",
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


class TestBacktestWorkflowContracts(unittest.TestCase):
    def test_orca_backtest_uses_3year_defaults(self):
        text = _read_text(_workflow_path("orca_backtest.yml"))
        self.assertIn(
            "python -m orca.backtest --months 36 --walk-forward --fail-on-empty-dynamic-fetch",
            text,
        )
        self.assertIn("run_mode:", text)
        self.assertIn("- artifact_verify_only", text)
        self.assertIn("- live_backtest", text)
        self.assertIn("default: artifact_verify_only", text)
        self.assertIn('ORCA_BACKTEST_RUN_MODE="artifact_verify_only"', text)
        self.assertIn("if: env.ORCA_BACKTEST_RUN_MODE == 'live_backtest'", text)
        self.assertIn('default: "36"', text)
        self.assertIn('default: "3869"', text)
        self.assertIn('ORCA_BACKTEST_MONTHS="36"', text)
        self.assertIn('EXPECTED_MIN_CANDIDATES_VALUE="3869"', text)
        self.assertIn('EXPECTED_MIN_LESSONS_VALUE="3869"', text)
        self.assertIn('EXPECTED_MIN_CANDIDATES", "3869"', text)
        self.assertIn('EXPECTED_MIN_LESSONS", "3869"', text)

    def test_orca_backtest_has_upload_verify(self):
        text = _read_text(_workflow_path("orca_backtest.yml"))
        self.assertIn("Checkpoint ORCA DB", text)
        self.assertIn("PRAGMA wal_checkpoint(TRUNCATE);", text)
        self.assertIn("Strict verify before upload", text)
        self.assertIn("candidate_registry(backtest):", text)
        self.assertIn("session_dist", text)
        self.assertIn("Date coverage:", text)
        self.assertIn("Signal family distribution:", text)
        checkpoint_idx = text.find("Checkpoint ORCA DB")
        verify_idx = text.find("Strict verify before upload")
        upload_idx = text.find("Upload research state")
        self.assertTrue(0 <= checkpoint_idx < verify_idx < upload_idx)
        self.assertIn("path: data/orca_state.db", text)
        self.assertNotIn("data/orca_state.db-wal", text)
        self.assertNotIn("data/orca_state.db-shm", text)

    def test_learning_workflow_runs_incremental_and_full_modes(self):
        text = _read_text(_workflow_path("jackal_backtest_learning.yml"))
        self.assertIn('cron: "10 0 * * 1-5"', text)
        self.assertIn('cron: "30 1 1 * *"', text)
        self.assertIn("python -m jackal.backtest", text)
        self.assertIn('--mode "${BACKTEST_MODE}"', text)

    def test_jackal_backtest_learning_supports_artifact_handoff(self):
        text = _read_text(_workflow_path("jackal_backtest_learning.yml"))
        self.assertIn("artifact_run_id:", text)
        self.assertIn("actions: read", text)
        self.assertIn("USE_ARTIFACT_HANDOFF", text)
        self.assertIn("uses: actions/download-artifact@v8", text)
        self.assertIn("github-token: ${{ github.token }}", text)
        self.assertIn("repository: ${{ github.repository }}", text)
        self.assertIn("run-id: ${{ github.event.inputs.artifact_run_id }}", text)
        self.assertIn("_artifact_handoff/", text)
        self.assertIn("_artifact_handoff/data/orca_state.db", text)
        self.assertIn("_artifact_handoff/orca_state.db", text)
        self.assertIn("Checkpoint + verify artifact DB", text)
        self.assertIn("PRAGMA wal_checkpoint(TRUNCATE);", text)
        self.assertIn('Found artifact DB: {path}', text)
        self.assertIn("ARTIFACT_DB_PATH", text)
        self.assertIn("candidate_registry(backtest):", text)
        self.assertIn("assert candidate_count >= 1000", text)
        self.assertIn("Promote artifact DB", text)
        self.assertIn("shutil.copy", text)

    def test_jackal_backtest_learning_mode1_runs_materialization_after_handoff(self):
        text = _read_text(_workflow_path("jackal_backtest_learning.yml"))
        self.assertNotIn("if: env.USE_ARTIFACT_HANDOFF != 'true'", text)
        self.assertIn("trim_workflow_input()", text)
        self.assertIn('MODE="$(trim_workflow_input "$MODE")"', text)
        self.assertIn("Mode 1: Artifact handoff (ORCA refresh skipped)", text)
        self.assertIn("Mode 2: Full rebuild with self-refresh", text)
        self.assertIn("Mode 3: Daily incremental", text)
        self.assertIn("Artifact handoff promotes the ORCA research DB above", text)

    def test_jackal_backtest_learning_mode1_isolated_path(self):
        text = _read_text(_workflow_path("jackal_backtest_learning.yml"))
        self.assertIn("path: _artifact_handoff/", text)
        self.assertIn("Checkpoint + verify artifact DB", text)
        self.assertIn("Promote artifact DB", text)
        self.assertIn('with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8")', text)

    def test_jackal_backtest_learning_mode_2_3_unchanged(self):
        text = _read_text(_workflow_path("jackal_backtest_learning.yml"))
        self.assertIn("Refresh ORCA research session", text)
        self.assertIn("if: env.RUN_ORCA_REFRESH == 'true'", text)
        self.assertIn("Run JACKAL backtest learning", text)
        self.assertIn('--backtest-days "${JACKAL_BACKTEST_DAYS}"', text)
        self.assertIn('--materialize-mode "${JACKAL_MATERIALIZE_MODE}"', text)


class TestPriorityWorkflowUiContracts(unittest.TestCase):
    """Phase 3: high-priority ORCA workflows share the safer dispatch UX."""

    PRIORITY_WORKFLOWS = (
        "orca_backtest.yml",
        "orca_jackal.yml",
        "orca_daily.yml",
        "wave_f_archive.yml",
    )

    def test_priority_workflows_resolve_and_normalize_inputs(self):
        for workflow_name in self.PRIORITY_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertIn("Resolve inputs", text)
                self.assertIn("trim_workflow_input()", text)
                self.assertIn("normalize_bool()", text)

    def test_priority_workflows_use_shared_runtime_env(self):
        for workflow_name in self.PRIORITY_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertIn("PYTHONIOENCODING: utf-8", text)
                self.assertIn('USE_FDR_MAIN: "1"', text)
                self.assertIn('USE_UNIFIED_FETCH: "1"', text)

    def test_priority_workflows_have_preflight_strict_verify_and_checkpoint(self):
        for workflow_name in self.PRIORITY_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertIn("Pre-flight status", text)
                self.assertIn("Strict verify", text)
                self.assertIn("PRAGMA wal_checkpoint(TRUNCATE);", text)

    def test_priority_dispatch_booleans_are_choices_with_string_defaults(self):
        for workflow_name in self.PRIORITY_WORKFLOWS:
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                self.assertNotIn("type: boolean", text)
                if "dry_run:" in text:
                    self.assertIn('default: "true"', text)
                if "force_rebuild:" in text:
                    self.assertIn('default: "false"', text)

    def test_stateful_priority_workflows_commit_after_checkpoint(self):
        for workflow_name in ("orca_jackal.yml", "orca_daily.yml", "wave_f_archive.yml"):
            with self.subTest(workflow=workflow_name):
                text = _read_text(_workflow_path(workflow_name))
                checkpoint_idx = text.find("Checkpoint DB")
                commit_idx = text.find("Commit and push")
                self.assertTrue(0 <= checkpoint_idx < commit_idx)

    def test_orca_daily_yaml_no_heredoc_in_case(self):
        text = _read_text(_workflow_path("orca_daily.yml"))
        case_start = text.find('case "$ORCA_RUN_MODE" in')
        case_end = text.find("          esac", case_start)
        self.assertGreaterEqual(case_start, 0)
        self.assertGreater(case_end, case_start)
        case_block = text[case_start:case_end]
        self.assertNotIn("python - <<", case_block)
        self.assertIn("python scripts/run_weekly_report.py", case_block)
        self.assertIn("python scripts/run_monthly_report.py", case_block)

    def test_run_weekly_script_callable(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_weekly_report.py", "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("DRY RUN weekly report runner OK", result.stdout)

    def test_run_monthly_script_callable(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_monthly_report.py", "--dry-run"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("DRY RUN monthly report runner OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
