"""
orca_analysis.py — ARIA analysis facade + seam-preserving verification wrappers
포함: verifier · weights update · backward-compatible re-exports

[수정]
- MODEL: 환경변수 ORCA_MODEL 지원
- run_verification: [-1] 인덱스 제거, ORCA_FORCE_VERIFY 환경변수 추가
- P2-2 wave 1: market/review/lessons/patterns 를 submodule 로 분리
- P2-2 wave 2: verification cluster 를 analysis_verification 으로 이동
  하되 test patch seam 은 wrapper + dependency injection 으로 보존
"""

from __future__ import annotations

import os
import sys

import anthropic

from ._analysis_common import KST, _load, _now, _save, _today
from .analysis_lessons import (
    add_lesson,
    build_lessons_prompt,
    extract_dawn_lessons,
    extract_monthly_lessons,
    get_active_lessons,
    load_lessons,
)
from .analysis_market import (
    build_baseline_context,
    calculate_sentiment,
    get_regime_drift,
    get_sentiment_weights,
    load_weights,
    run_portfolio,
    run_rotation,
    run_sentiment,
    save_baseline,
)
from .analysis_patterns import (
    build_compact_history,
    get_pattern_context,
    update_pattern_db,
)
from .analysis_review import (
    _REVIEW_SCORE_WEIGHTS,
    normalize_candidate_review_payload,
    review_recent_candidates,
)
from .analysis_verification import (
    _VERIFIER_SYSTEM,
    _ai_verify_impl,
    _compare_change,
    _compare_level,
    _direction_flags,
    _extract_numeric_thresholds,
    _metric_float,
    _send_verification_report_impl,
    _verify_price,
    run_verification_impl,
    update_weights_from_accuracy_impl,
)
from .compat import get_orca_env, get_orca_flag
from .data import load_market_data
from .learning_policy import MIN_SAMPLES, suggest_weight_delta
from .notify_transport import _format_accuracy_display, send_message
from .paths import ACCURACY_FILE, MEMORY_FILE, WEIGHTS_FILE
from .state import resolve_verification_outcomes


os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = get_orca_env("ORCA_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
client = anthropic.Anthropic(api_key=API_KEY)


def update_weights_from_accuracy(accuracy_data: dict) -> list:
    """Compatibility wrapper that keeps the analysis.py patch seam stable."""
    return update_weights_from_accuracy_impl(
        accuracy_data,
        load_weights_fn=load_weights,
        now_fn=_now,
        today_fn=_today,
        save_fn=_save,
        weights_file=WEIGHTS_FILE,
        min_samples=MIN_SAMPLES,
        suggest_weight_delta_fn=suggest_weight_delta,
    )


def _ai_verify(unclear: list) -> list:
    """Compatibility wrapper that keeps the analysis.py patch seam stable."""
    return _ai_verify_impl(
        unclear,
        client=client,
        model=MODEL,
        verifier_system=_VERIFIER_SYSTEM,
    )


def _send_verification_report(results, accuracy, today_acc, dir_acc=0):
    """Compatibility wrapper that keeps the analysis.py patch seam stable."""
    return _send_verification_report_impl(
        results,
        accuracy,
        today_acc,
        dir_acc,
        format_accuracy_fn=_format_accuracy_display,
        today_fn=_today,
        send_message_fn=send_message,
    )


def run_verification() -> dict:
    """Compatibility wrapper that keeps the analysis.py patch seam stable."""
    return run_verification_impl(
        load_fn=_load,
        memory_file=MEMORY_FILE,
        accuracy_file=ACCURACY_FILE,
        today_fn=_today,
        flag_fn=get_orca_flag,
        load_market_data_fn=load_market_data,
        verify_price_fn=_verify_price,
        ai_verify_fn=_ai_verify,
        update_weights_fn=update_weights_from_accuracy,
        resolve_outcomes_fn=resolve_verification_outcomes,
        save_fn=_save,
        send_report_fn=_send_verification_report,
    )


__all__ = [
    "KST",
    "_REVIEW_SCORE_WEIGHTS",
    "_VERIFIER_SYSTEM",
    "_ai_verify",
    "_compare_change",
    "_compare_level",
    "_direction_flags",
    "_extract_numeric_thresholds",
    "_load",
    "_metric_float",
    "_save",
    "_send_verification_report",
    "_today",
    "_verify_price",
    "add_lesson",
    "build_baseline_context",
    "build_compact_history",
    "build_lessons_prompt",
    "calculate_sentiment",
    "extract_dawn_lessons",
    "extract_monthly_lessons",
    "get_active_lessons",
    "get_orca_flag",
    "get_pattern_context",
    "get_regime_drift",
    "get_sentiment_weights",
    "load_lessons",
    "load_market_data",
    "load_weights",
    "normalize_candidate_review_payload",
    "resolve_verification_outcomes",
    "review_recent_candidates",
    "run_portfolio",
    "run_rotation",
    "run_sentiment",
    "run_verification",
    "save_baseline",
    "send_message",
    "update_pattern_db",
    "update_weights_from_accuracy",
]
