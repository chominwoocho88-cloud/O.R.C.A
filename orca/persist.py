# orca/persist.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-1 (skeleton only, no logic)

Report, memory, and prediction persistence helpers.
"""
# Allowed imports: .paths, .state, .learning_policy
# Forbidden imports: .analysis, .notify, .dashboard, .agents, .present

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_memory() -> list:
    raise NotImplementedError("Step 2-1 skeleton only")


def save_memory(memory: list, analysis: dict):
    raise NotImplementedError("Step 2-1 skeleton only")


def save_report(analysis: dict) -> Path:
    raise NotImplementedError("Step 2-1 skeleton only")


def get_todays_analyses() -> list:
    raise NotImplementedError("Step 2-1 skeleton only")


def record_predictions(*, run_id: str | None, report: dict, health_tracker: Any) -> dict:
    raise NotImplementedError("Step 2-1 skeleton only")


def persist_final_report(report: dict, health_tracker: Any) -> Path:
    raise NotImplementedError("Step 2-1 skeleton only")
