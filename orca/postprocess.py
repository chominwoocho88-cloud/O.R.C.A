# orca/postprocess.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-1 (skeleton only, no logic)

Report post-processing and secondary analysis hooks.
"""
# Allowed imports: .analysis, .state, .learning_policy, .paths, .agents (local import only), .present.console
# Forbidden imports: .notify, .persist
# postprocess.py: may import present.console (one-way).
#                 MUST NOT be imported by present.py.

from __future__ import annotations

from typing import Any

from .learning_policy import MIN_SAMPLES


def sanitize_korea_claims(report: dict, market_data: dict) -> dict:
    raise NotImplementedError("Step 2-1 skeleton only")


def compact_probability_summary(*, days: int = 90, min_samples: int = MIN_SAMPLES) -> dict:
    raise NotImplementedError("Step 2-1 skeleton only")


def run_candidate_review(
    *,
    report: dict,
    run_id: str | None,
    analysis_date: str,
    health_tracker: Any,
) -> dict:
    raise NotImplementedError("Step 2-1 skeleton only")


def maybe_save_baseline(*, mode: str, report: dict, market_data: dict) -> bool:
    raise NotImplementedError("Step 2-1 skeleton only")


def run_secondary_analyses(report: dict, market_data: dict) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def update_pattern_database(memory: list) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")


def collect_jackal_news(hunter_data: dict) -> None:
    raise NotImplementedError("Step 2-1 skeleton only")
