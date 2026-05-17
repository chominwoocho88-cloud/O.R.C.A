"""
shared.paths
============

O.R.C.A 전체에서 사용하는 중앙 경로 정의.

ORCA + JACKAL 공유 데이터 (data/*) 와 JACKAL legacy 데이터 (jackal/*) 를
명시적으로 분리해서 관리한다.

repo root는 환경변수 ORCA_REPO_ROOT 우선, 없으면 이 파일의 부모로 fallback.

사용:
    from shared.paths import DATA_DIR, JACKAL_LEGACY_DIR, MEMORY_FILE

    memory = json.load(open(MEMORY_FILE))

호환성:
    orca.paths는 Phase B-2에서 이 모듈의 alias로 변환 예정.
    JACKAL 호출부는 Phase B-3 ~ B-5에서 이 모듈 사용으로 마이그레이션.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4


def _resolve_repo_root() -> Path:
    """repo root 결정.

    1. 환경변수 ORCA_REPO_ROOT 있으면 사용 (테스트/로컬에서 override 가능)
    2. 없으면 이 파일 (shared/paths.py) 의 부모의 부모 (= repo root)
    """
    env_root = os.environ.get("ORCA_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[1]  # shared/ -> repo/


# ===== Repo 구조 =====
REPO_ROOT = _resolve_repo_root()
DATA_DIR = REPO_ROOT / "data"
REPORTS_DIR = REPO_ROOT / "reports"

# Legacy 모듈 디렉토리 (데이터 파일이 있는 위치)
ORCA_LEGACY_DIR = REPO_ROOT / "orca"
JACKAL_LEGACY_DIR = REPO_ROOT / "jackal"

# orca.paths compatibility (Phase B-2 alias 준비)
PACKAGE_DIR = ORCA_LEGACY_DIR
_REPO_ROOT = REPO_ROOT


# ===== ORCA 공유 데이터 파일 (data/*) =====
MEMORY_FILE = DATA_DIR / "memory.json"
ACCURACY_FILE = DATA_DIR / "accuracy.json"
SENTIMENT_FILE = DATA_DIR / "sentiment.json"
ROTATION_FILE = DATA_DIR / "rotation.json"
WEIGHTS_FILE = DATA_DIR / "orca_weights.json"
LESSONS_FILE = DATA_DIR / "orca_lessons.json"
COST_FILE = DATA_DIR / "orca_cost.json"
PATTERN_DB_FILE = DATA_DIR / "pattern_db.json"

# ===== State DB =====
STATE_DB_FILE = DATA_DIR / "orca_state.db"
JACKAL_DB_FILE = DATA_DIR / "jackal_state.db"

# ===== ORCA -> JACKAL 인터페이스 =====
BASELINE_FILE = DATA_DIR / "morning_baseline.json"
DATA_FILE = DATA_DIR / "orca_market_data.json"
BREAKING_FILE = DATA_DIR / "breaking_sent.json"

# ===== JACKAL -> ORCA 인터페이스 =====
JACKAL_NEWS_FILE = DATA_DIR / "jackal_news.json"
JACKAL_WATCHLIST_FILE = DATA_DIR / "jackal_watchlist.json"

# ===== JACKAL legacy 디렉토리 (jackal/*) =====
# 이 파일들은 JACKAL 모듈 내부 상태이며 jackal/ 에 그대로 유지된다.
# Phase B-3 ~ B-5에서 jackal/ 코드가 이 상수를 import하도록 마이그레이션.
JACKAL_WEIGHTS_FILE = JACKAL_LEGACY_DIR / "jackal_weights.json"
# DEPRECATED: jackal_usage_log.json migrated to data/llm_log.jsonl.
# This constant is preserved for backward compatibility and will be removed
# in a future sprint after operational validation.
JACKAL_USAGE_LOG_FILE = JACKAL_LEGACY_DIR / "jackal_usage_log.json"
JACKAL_HUNT_LOG_FILE = JACKAL_LEGACY_DIR / "hunt_log.json"
JACKAL_HUNT_COOLDOWN_FILE = JACKAL_LEGACY_DIR / "hunt_cooldown.json"

# ===== Reports =====
DASHBOARD_FILE = REPORTS_DIR / "dashboard.html"

# ===== LLM 로그 =====
LLM_LOG_FILE = DATA_DIR / "llm_log.jsonl"


def ensure_dirs() -> None:
    """필수 디렉토리가 없으면 생성."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_text_once(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    _atomic_write_text_once(path, text, encoding=encoding)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


__all__ = [
    # Repo 구조
    "REPO_ROOT",
    "DATA_DIR",
    "REPORTS_DIR",
    "ORCA_LEGACY_DIR",
    "JACKAL_LEGACY_DIR",
    "PACKAGE_DIR",
    # ORCA 데이터
    "MEMORY_FILE",
    "ACCURACY_FILE",
    "SENTIMENT_FILE",
    "ROTATION_FILE",
    "WEIGHTS_FILE",
    "LESSONS_FILE",
    "COST_FILE",
    "PATTERN_DB_FILE",
    # State DB
    "STATE_DB_FILE",
    "JACKAL_DB_FILE",
    # ORCA -> JACKAL
    "BASELINE_FILE",
    "DATA_FILE",
    "BREAKING_FILE",
    # JACKAL -> ORCA
    "JACKAL_NEWS_FILE",
    "JACKAL_WATCHLIST_FILE",
    # JACKAL legacy
    "JACKAL_WEIGHTS_FILE",
    "JACKAL_USAGE_LOG_FILE",
    "JACKAL_HUNT_LOG_FILE",
    "JACKAL_HUNT_COOLDOWN_FILE",
    # Reports
    "DASHBOARD_FILE",
    # LLM
    "LLM_LOG_FILE",
    # Function
    "ensure_dirs",
    "atomic_write_text",
    "atomic_write_json",
]
