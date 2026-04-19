# orca/present.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-1 (skeleton only, no logic)

Console rendering, notifier calls, and dashboard hooks.
"""
# Allowed imports: rich, .brand, .notify, .dashboard
# Forbidden imports: .analysis, .state, .persist, .pipeline
# postprocess.py: may import present.console (one-way).
#                 MUST NOT be imported by present.py.

from __future__ import annotations

from typing import Any

from rich.console import Console

console = Console()


def print_history(memory: list) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def print_start_banner(mode: str) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def print_report(report: dict, run_n: int):
    raise NotImplementedError("Step 2-1 skeleton only")


def print_health_badge(badge: str) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def maybe_build_dashboard(*, mode: str, health_tracker: Any) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def send_start_notice() -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def send_final_report(report: dict, run_n: int) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def send_error_notice(message: str) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")
