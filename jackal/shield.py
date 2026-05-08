"""Backward-compatible alias for modules.jackal.pipeline.shield.

Phase D-2 마이그레이션 결과:
- 실제 코드: modules/jackal/pipeline/shield.py
- 이 파일은 옛 호출부 호환을 위한 alias

호출부 변경 시점에 이 alias 제거 가능.
"""

from modules.jackal.pipeline.shield import *  # noqa: F401,F403
from modules.jackal.pipeline.shield import (
    JackalShield,
    _BASE,
    _DAILY_TOKEN_BUDGET,
    _EXCLUDE_DIRS,
    _REPO_ROOT,
    _SCAN_EXTENSIONS,
    _SECRET_PATTERNS,
    _SPIKE_MULTIPLIER,
    _USAGE_LOG,
    log_usage,
)

__all__ = [
    "JackalShield",
    "_BASE",
    "_REPO_ROOT",
    "_DAILY_TOKEN_BUDGET",
    "_SPIKE_MULTIPLIER",
    "_SECRET_PATTERNS",
    "_EXCLUDE_DIRS",
    "_SCAN_EXTENSIONS",
    "_USAGE_LOG",
    "log_usage",
]
