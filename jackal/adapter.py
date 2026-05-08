"""Backward-compatible alias for modules.jackal.pipeline.adapter.

Phase D-1 마이그레이션 결과:
- 실제 코드: modules/jackal/pipeline/adapter.py
- 이 파일은 옛 호출부 호환을 위한 alias

호출부 변경 시점에 이 alias 제거 가능.
"""

from modules.jackal.pipeline.adapter import *  # noqa: F401,F403
from modules.jackal.pipeline.adapter import (
    JACKAL_NEWS,
    ORCA_BASELINE,
    ORCA_MEMORY,
    _JACKAL_DIR,
    _JACKAL_WEIGHTS,
    _REPO_ROOT,
    _get_fallback_regime,
    get_orca_inflows,
    get_orca_regime,
    load_orca_context,
    orca_baseline_exists,
)

__all__ = [
    "_JACKAL_DIR",
    "_REPO_ROOT",
    "ORCA_BASELINE",
    "ORCA_MEMORY",
    "JACKAL_NEWS",
    "_JACKAL_WEIGHTS",
    "_get_fallback_regime",
    "load_orca_context",
    "orca_baseline_exists",
    "get_orca_regime",
    "get_orca_inflows",
]
