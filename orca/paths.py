"""Central path management for ORCA runtime and report artifacts."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = PACKAGE_DIR.parent
DATA_DIR = _REPO_ROOT / "data"
REPORTS_DIR = _REPO_ROOT / "reports"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)


ensure_dirs()

# Canonical persistent tracked data
MEMORY_FILE = DATA_DIR / "memory.json"
ACCURACY_FILE = DATA_DIR / "accuracy.json"
SENTIMENT_FILE = DATA_DIR / "sentiment.json"
ROTATION_FILE = DATA_DIR / "rotation.json"
WEIGHTS_FILE = DATA_DIR / "orca_weights.json"
LESSONS_FILE = DATA_DIR / "orca_lessons.json"
COST_FILE = DATA_DIR / "orca_cost.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
PATTERN_DB_FILE = DATA_DIR / "pattern_db.json"
STATE_DB_FILE = DATA_DIR / "orca_state.db"

# Runtime / ephemeral files
BASELINE_FILE = DATA_DIR / "morning_baseline.json"
DATA_FILE = DATA_DIR / "orca_market_data.json"
BREAKING_FILE = DATA_DIR / "breaking_sent.json"

# Output files
DASHBOARD_FILE = REPORTS_DIR / "dashboard.html"

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

