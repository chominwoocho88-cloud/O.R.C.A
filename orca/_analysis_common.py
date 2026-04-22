"""Shared helpers for ORCA analysis submodules."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import atomic_write_json


KST = timezone(timedelta(hours=9))


def _now() -> datetime:
    return datetime.now(KST)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _load(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else {}


def _save(path: Path, data):
    atomic_write_json(path, data)
