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
    try:
        from .historical_context import build_market_features, get_market_historical_context

        market_features = build_market_features(report) or build_market_features(market_data)
        historical_context = get_market_historical_context(
            market_features=market_features,
            top_k=20,
            quality_filter="high",
            recency_decay_days=365,
        )
        if historical_context:
            report["historical_context"] = historical_context
    except Exception:
        # Historical context is report enrichment only; the daily cycle must continue.
        pass
    return hunter, analyst, devil, report
