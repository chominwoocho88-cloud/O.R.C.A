"""
orca.paths (DEPRECATED ALIAS)
=============================
이 모듈은 backward-compatible alias입니다.
실제 코드는 shared/paths.py 로 이동됨 (Phase B-2 commit).

신규 코드는 다음 경로 사용 권장:
    from shared.paths import DATA_DIR, MEMORY_FILE, atomic_write_json, ...

ORCA 전용 상수 PACKAGE_DIR은 shared.paths의 ORCA_LEGACY_DIR로 매핑됨.
"""
from __future__ import annotations

import sys as _sys

# wildcard import로 모든 module-level 심볼 가져오기 (mock.patch 호환)
from shared.paths import *  # noqa: F401,F403
from shared import paths as _paths

# 명시적 export (사전 조사 결과의 모든 상수 + 함수)
from shared.paths import (
    REPO_ROOT,
    DATA_DIR,
    REPORTS_DIR,
    ORCA_LEGACY_DIR,
    JACKAL_LEGACY_DIR,
    MEMORY_FILE,
    ACCURACY_FILE,
    SENTIMENT_FILE,
    ROTATION_FILE,
    WEIGHTS_FILE,
    LESSONS_FILE,
    COST_FILE,
    PORTFOLIO_FILE,
    PATTERN_DB_FILE,
    STATE_DB_FILE,
    JACKAL_DB_FILE,
    BASELINE_FILE,
    DATA_FILE,
    BREAKING_FILE,
    DASHBOARD_FILE,
    ensure_dirs,
    atomic_write_text,
    atomic_write_json,
)
from shared.paths import _REPO_ROOT, _atomic_write_text_once  # noqa: F401

# ORCA 전용 alias: PACKAGE_DIR = ORCA_LEGACY_DIR
PACKAGE_DIR = ORCA_LEGACY_DIR
_paths.PACKAGE_DIR = PACKAGE_DIR

__all__ = [
    "PACKAGE_DIR",
    "REPO_ROOT",
    "DATA_DIR",
    "REPORTS_DIR",
    "ORCA_LEGACY_DIR",
    "JACKAL_LEGACY_DIR",
    "MEMORY_FILE",
    "ACCURACY_FILE",
    "SENTIMENT_FILE",
    "ROTATION_FILE",
    "WEIGHTS_FILE",
    "LESSONS_FILE",
    "COST_FILE",
    "PORTFOLIO_FILE",
    "PATTERN_DB_FILE",
    "STATE_DB_FILE",
    "JACKAL_DB_FILE",
    "BASELINE_FILE",
    "DATA_FILE",
    "BREAKING_FILE",
    "DASHBOARD_FILE",
    "ensure_dirs",
    "atomic_write_text",
    "atomic_write_json",
]

_sys.modules[__name__] = _paths
