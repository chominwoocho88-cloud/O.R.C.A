"""Environment helpers for ORCA runtime configuration."""

from __future__ import annotations

import os


def get_orca_env(name: str, default: str | None = None) -> str | None:
    """Read an ORCA environment variable with an optional default."""
    return os.environ.get(name, default)


def get_orca_flag(name: str, default: bool = False) -> bool:
    value = get_orca_env(name, None)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

