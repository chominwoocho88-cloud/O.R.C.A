"""Build metadata helpers for operational messages."""
from __future__ import annotations

import os


def get_build_info() -> str:
    """Return the short GitHub commit hash, or ``local`` outside Actions."""
    sha = os.environ.get("GITHUB_SHA", "").strip()
    return sha[:7] if sha else "local"


__all__ = ["get_build_info"]
