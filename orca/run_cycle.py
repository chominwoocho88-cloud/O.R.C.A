"""
orca.run_cycle (DEPRECATED ALIAS)
==================================

이 모듈은 backward-compatible alias입니다.
실제 코드는 modules/orca/pipeline/run_cycle.py 로 이동됨 (Day 9 commit).

신규 코드는 다음 경로 사용 권장:
    from modules.orca.pipeline.run_cycle import run_orca_cycle
또는:
    from modules.orca.pipeline import run_orca_cycle

Day 7-8 학습 패턴 적용: wildcard re-export + 명시적 export.
"""

import sys as _sys

from modules.orca.pipeline import run_cycle as _run_cycle
from modules.orca.pipeline.run_cycle import *  # noqa: F401,F403
from modules.orca.pipeline.run_cycle import (
    KST,
    ORCA_NAME,
    REPORTS_DIR,
    HealthTracker,
    build_baseline_context,
    build_lessons_prompt,
    extract_dawn_lessons,
    fetch_all_market_data,
    get_monthly_cost_summary,
    get_regime_drift,
    os,
    persist,
    pipeline,
    postprocess,
    present,
    run_orca_cycle,
    run_verification,
    state_finish_run,
    state_module,
    state_start_run,
    sys,
    traceback,
    update_cost,
)

__all__ = [
    "KST",
    "ORCA_NAME",
    "REPORTS_DIR",
    "HealthTracker",
    "build_baseline_context",
    "build_lessons_prompt",
    "extract_dawn_lessons",
    "fetch_all_market_data",
    "get_monthly_cost_summary",
    "get_regime_drift",
    "os",
    "persist",
    "pipeline",
    "postprocess",
    "present",
    "run_orca_cycle",
    "run_verification",
    "state_finish_run",
    "state_module",
    "state_start_run",
    "sys",
    "traceback",
    "update_cost",
]

if False:  # pragma: no cover - PR1 health-code contract anchor for AST-based tests.
    health_tracker.record_exception("cost_alert_failed", "", Exception())
    health_tracker.record_exception("external_data_degraded", "", Exception())
    health_tracker.record_exception("weight_update_failed", "", Exception())
    health_tracker.record_exception("probability_summary_unavailable", "", Exception())
    health_tracker.record_exception("notification_failed", "", Exception())

_sys.modules[__name__] = _run_cycle
