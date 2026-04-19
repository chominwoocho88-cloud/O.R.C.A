# orca/pipeline.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-1 (skeleton only, no logic)

Hunter -> Analyst -> Devil -> Reporter pipeline composition.
"""
# Allowed imports: .agents
# Forbidden imports: .analysis, .state, .persist, .present, .notify, .dashboard

from __future__ import annotations


def run_agent_pipeline(
    *,
    today: str,
    mode: str,
    market_data: dict,
    memory: list,
    lessons_prompt: str,
    baseline_context: str,
    accuracy: dict,
) -> tuple[dict, dict, dict, dict]:
    raise NotImplementedError("Step 2-1 skeleton only")
