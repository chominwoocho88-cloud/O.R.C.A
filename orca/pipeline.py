# orca/pipeline.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-2 (body copy)

Hunter -> Analyst -> Devil -> Reporter pipeline composition.
"""
# Allowed imports: .agents
# Forbidden imports: .analysis, .state, .persist, .present, .notify, .dashboard

from __future__ import annotations

from .agents import agent_analyst, agent_devil, agent_hunter, agent_reporter


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
    hunter  = agent_hunter(today, mode, market_data)
    analyst = agent_analyst(hunter, mode, lessons_prompt + baseline_context, memory=memory)
    devil   = agent_devil(analyst, memory, mode)
    report  = agent_reporter(hunter, analyst, devil, memory, accuracy, mode)
    return hunter, analyst, devil, report
