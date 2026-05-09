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
    """KIS API client for authentication and domestic market data calls."""

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

    def get_current_price(self, ticker: str) -> dict:
        """Fetch current domestic stock price from KIS."""
        code = self._normalize_ticker(ticker)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self._auth_headers("FHKST01010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KisError(f"KIS current price request failed: {exc}") from exc

        _raise_for_kis_error(data)
        output = data.get("output", {}) or {}

        try:
            return {
                "ticker": code,
                "price": _to_float(output.get("stck_prpr")),
                "change": _to_float(output.get("prdy_ctrt")),
                "volume": _to_int(output.get("acml_vol")),
                "source": "kis",
                "timestamp": output.get("stck_bsop_date", ""),
            }
        except (TypeError, ValueError) as exc:
            raise KisError(f"KIS current price response invalid: {output}") from exc

    def get_daily_history(
        self,
        ticker: str,
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Fetch daily domestic stock OHLCV history from KIS."""
        code = self._normalize_ticker(ticker)
        url = (
            f"{self.base_url}"
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        )
        headers = self._auth_headers("FHKST03010100")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start_date,
            "FID_INPUT_DATE_2": end_date,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KisError(f"KIS daily history request failed: {exc}") from exc

        _raise_for_kis_error(data)
        rows = data.get("output2", []) or []

        result = []
        for row in rows:
            try:
                result.append(
                    {
                        "date": row.get("stck_bsop_date", ""),
                        "open": _to_float(row.get("stck_oprc")),
                        "high": _to_float(row.get("stck_hgpr")),
                        "low": _to_float(row.get("stck_lwpr")),
                        "close": _to_float(row.get("stck_clpr")),
                        "volume": _to_int(row.get("acml_vol")),
                        "source": "kis",
                    }
                )
            except (AttributeError, TypeError, ValueError):
                continue
        return result

    def _normalize_ticker(self, ticker: str) -> str:
        """Normalize yfinance-style Korean tickers to KIS six-digit codes."""
        value = str(ticker or "").strip()
        upper = value.upper()
        if upper.endswith(".KS") or upper.endswith(".KQ"):
            return value[:-3]
        return value.zfill(6)

    def _auth_headers(self, tr_id: str) -> dict[str, str]:
        """Build KIS REST headers for an authenticated request."""
        token = self.get_token()
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }


def _coerce_expires_in(value: object) -> float:
    """Convert KIS expires_in values to seconds, defaulting to 24 hours."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 86400.0


def _raise_for_kis_error(data: dict) -> None:
    """Raise KisError when KIS reports an application-level error."""
    if data.get("rt_cd") != "0":
        raise KisError(f"KIS API error: {data.get('msg1', 'unknown')}")


def _to_float(value: object) -> float:
    """Convert KIS numeric string fields to float."""
    return float(value or 0)


def _to_int(value: object) -> int:
    """Convert KIS numeric string fields to int."""
    return int(float(value or 0))
