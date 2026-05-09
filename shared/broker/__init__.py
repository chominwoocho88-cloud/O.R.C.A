"""Broker API clients shared by ORCA and JACKAL."""

import os
from typing import Optional

from shared.broker import kis as _kis_module
from shared.broker.kis import (
    KisAuthError,
    KisClient,
    KisError,
    KisToken,
    get_kis_base_url,
)

_shared_client: Optional[KisClient] = None
_shared_client_key: tuple[object, str, str, str, str] | None = None


def _current_client_key() -> tuple[object, str, str, str, str]:
    return (
        _kis_module.KisClient,
        os.environ.get("KIS_IS_PAPER", "true"),
        os.environ.get("KIS_CMW_APP_KEY_PAPER", ""),
        os.environ.get("KIS_CMW_APP_SECRET_PAPER", ""),
        os.environ.get("KIS_CMW_ACCOUNT_NUMBER_PAPER", ""),
    )


def get_shared_kis_client() -> KisClient:
    """Return the shared KIS client for the current process."""
    global _shared_client, _shared_client_key
    key = _current_client_key()
    if _shared_client is None or _shared_client_key != key:
        _shared_client = _kis_module.KisClient()
        _shared_client_key = key
    return _shared_client


def reset_shared_kis_client() -> None:
    """Reset the shared KIS client, primarily for tests."""
    global _shared_client, _shared_client_key
    _shared_client = None
    _shared_client_key = None


__all__ = [
    "KisAuthError",
    "KisClient",
    "KisError",
    "KisToken",
    "get_shared_kis_client",
    "get_kis_base_url",
    "reset_shared_kis_client",
]
