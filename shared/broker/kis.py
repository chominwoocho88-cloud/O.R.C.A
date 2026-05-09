"""KIS (Korea Investment Securities) API client skeleton.

Phase 8b / Day 11 scope:
- read KIS_CMW_* environment variables
- manage OAuth bearer token
- keep quote/order/investor-flow calls for later phases
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx


PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
PROD_BASE_URL = "https://openapi.koreainvestment.com:9443"

DEFAULT_TIMEOUT = 10.0
TOKEN_REFRESH_MARGIN_SECONDS = 300


class KisError(Exception):
    """Base exception for KIS API integration."""


class KisAuthError(KisError):
    """Raised when KIS authentication cannot be completed."""


def _is_paper_mode() -> bool:
    """Return True when KIS paper-trading mode is enabled."""
    return os.environ.get("KIS_IS_PAPER", "true").lower() == "true"


def get_kis_base_url() -> str:
    """Return the KIS base URL for the configured trading mode."""
    return PAPER_BASE_URL if _is_paper_mode() else PROD_BASE_URL


def _get_app_key() -> str:
    """Read the KIS app key from environment variables."""
    if _is_paper_mode():
        return os.environ.get("KIS_CMW_APP_KEY_PAPER", "")
    return os.environ.get("KIS_CMW_APP_KEY", "")


def _get_app_secret() -> str:
    """Read the KIS app secret from environment variables."""
    if _is_paper_mode():
        return os.environ.get("KIS_CMW_APP_SECRET_PAPER", "")
    return os.environ.get("KIS_CMW_APP_SECRET", "")


def _get_account_number() -> str:
    """Read the KIS account number from environment variables."""
    if _is_paper_mode():
        return os.environ.get("KIS_CMW_ACCOUNT_NUMBER_PAPER", "")
    return os.environ.get("KIS_CMW_ACCOUNT_NUMBER", "")


@dataclass
class KisToken:
    """KIS access token and its absolute expiry timestamp."""

    access_token: str
    expires_at: float

    def is_valid(self, *, now: Optional[float] = None) -> bool:
        """Return False within five minutes of token expiry."""
        current = now if now is not None else time.time()
        return bool(self.access_token) and current < (
            self.expires_at - TOKEN_REFRESH_MARGIN_SECONDS
        )


class KisClient:
    """KIS API client skeleton for authentication and token caching."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        app_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        account_number: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url or get_kis_base_url()
        self.app_key = app_key or _get_app_key()
        self.app_secret = app_secret or _get_app_secret()
        self.account_number = account_number or _get_account_number()
        self.timeout = timeout
        self._token: Optional[KisToken] = None

    def is_configured(self) -> bool:
        """Return whether required KIS credentials are present."""
        return bool(self.app_key and self.app_secret and self.account_number)

    def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a cached token, or request a new one from KIS."""
        if not force_refresh and self._token and self._token.is_valid():
            return self._token.access_token

        if not self.is_configured():
            raise KisAuthError("KIS environment variables are not configured")

        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KisAuthError(f"KIS token request failed: {exc}") from exc

        access_token = data.get("access_token", "")
        expires_in = _coerce_expires_in(data.get("expires_in", 86400))

        if not access_token:
            raise KisAuthError(f"KIS token response missing access_token: {data}")

        self._token = KisToken(
            access_token=access_token,
            expires_at=time.time() + expires_in,
        )
        return access_token


def _coerce_expires_in(value: object) -> float:
    """Convert KIS expires_in values to seconds, defaulting to 24 hours."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 86400.0
