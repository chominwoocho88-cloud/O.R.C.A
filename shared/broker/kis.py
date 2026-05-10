"""KIS (Korea Investment Securities) API client skeleton.

Phase 8b / Day 11 scope:
- read KIS_CMW_* environment variables
- manage OAuth bearer token
- keep quote/order/investor-flow calls for later phases
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx


PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
PROD_BASE_URL = "https://openapi.koreainvestment.com:9443"

DEFAULT_TIMEOUT = 10.0
TOKEN_REFRESH_MARGIN_SECONDS = 300
TOKEN_CACHE_PATH = Path("data/kis_token.json")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
)


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


def _get_user_agent() -> str:
    """Read the KIS User-Agent override, or use the official sample default."""
    return os.environ.get("KIS_USER_AGENT", DEFAULT_USER_AGENT)


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


def _is_cacheable_credentials(app_key: str = "", app_secret: str = "") -> bool:
    """Return whether credentials look like real KIS keys worth file-caching."""
    if not app_key and not app_secret:
        return True
    return len(str(app_key).strip()) >= 20 and len(str(app_secret).strip()) >= 40


def _cache_fingerprint(value: str) -> str:
    """Return a short, non-secret fingerprint for cache scoping."""
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _load_token_from_file(
    *, app_key: str = "", base_url: str = ""
) -> Optional[KisToken]:
    """Load a valid token from the file cache, returning None on any miss."""
    try:
        if not TOKEN_CACHE_PATH.exists():
            return None
        data = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        if app_key and data.get("app_key_hash") != _cache_fingerprint(app_key):
            return None
        if base_url and data.get("base_url") not in ("", base_url):
            return None
        token = KisToken(
            access_token=str(data.get("access_token", "")),
            expires_at=float(data.get("expires_at", 0)),
        )
        if token.is_valid():
            return token
    except Exception:
        return None
    return None


def _save_token_to_file(
    token: KisToken,
    *,
    app_key: str = "",
    app_secret: str = "",
    base_url: str = "",
) -> None:
    """Save a token to the file cache; failures stay non-fatal."""
    try:
        if not _is_cacheable_credentials(app_key, app_secret):
            return
        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(
            json.dumps(
                {
                    "access_token": token.access_token,
                    "expires_at": token.expires_at,
                    "app_key_hash": _cache_fingerprint(app_key),
                    "base_url": base_url,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


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

    @property
    def cano(self) -> str:
        """Return the 8-digit KIS account number prefix (CANO)."""
        cleaned = self._clean_account_number()
        return cleaned[:8] if len(cleaned) >= 8 else cleaned

    @property
    def acnt_prdt_cd(self) -> str:
        """Return the 2-digit KIS account product code, defaulting to 01."""
        cleaned = self._clean_account_number()
        if len(cleaned) >= 10:
            return cleaned[8:10]
        return "01"

    def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a cached token, or request a new one from KIS."""
        if not force_refresh and self._token and self._token.is_valid():
            return self._token.access_token

        if not force_refresh:
            cached = _load_token_from_file(
                app_key=self.app_key,
                base_url=self.base_url,
            )
            if cached:
                self._token = cached
                return cached.access_token

        if not self.is_configured():
            raise KisAuthError("KIS environment variables are not configured")

        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User-Agent": _get_user_agent(),
        }

        try:
            resp = httpx.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
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
        _save_token_to_file(
            self._token,
            app_key=self.app_key,
            app_secret=self.app_secret,
            base_url=self.base_url,
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

    def get_investor_flow(self, ticker: str) -> dict:
        """Fetch per-stock foreign/institution investor flow from KIS."""
        code = self._normalize_ticker(ticker)
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-investor"
        headers = self._auth_headers("FHKST01010900")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": code,
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KisError(f"KIS investor flow request failed: {exc}") from exc

        _raise_for_kis_error(data)
        output = data.get("output", []) or []
        if isinstance(output, list):
            if not output:
                raise KisError("KIS investor flow response missing output")
            row = output[0]
        else:
            row = output

        try:
            return {
                "ticker": code,
                "foreign_buy": _to_int(row.get("frgn_buy_qty")),
                "foreign_sell": _to_int(row.get("frgn_seln_qty")),
                "foreign_net": _to_int(row.get("frgn_ntby_qty")),
                "institution_buy": _to_int(row.get("orgn_buy_qty")),
                "institution_sell": _to_int(row.get("orgn_seln_qty")),
                "institution_net": _to_int(row.get("orgn_ntby_qty")),
                "individual_net": _to_int(row.get("prsn_ntby_qty")),
                "date": row.get("stck_bsop_date", ""),
                "source": "kis",
            }
        except (AttributeError, TypeError, ValueError) as exc:
            raise KisError(f"KIS investor flow response invalid: {row}") from exc

    def get_foreign_institution_total(self, market: str = "0000") -> list[dict]:
        """Fetch foreign/institution aggregate rankings from KIS HTS 0440."""
        url = (
            f"{self.base_url}"
            "/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        )
        headers = self._auth_headers("FHPTJ04400000")
        params = {
            "FID_COND_MRKT_DIV_CODE": "V",
            "FID_COND_SCR_DIV_CODE": "16449",
            "FID_INPUT_ISCD": market,
            "FID_DIV_CLS_CODE": "0",
            "FID_RANK_SORT_CLS_CODE": "0",
            "FID_ETC_CLS_CODE": "0",
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KisError(f"KIS foreign/institution total request failed: {exc}") from exc

        _raise_for_kis_error(data)
        output = data.get("output", []) or []

        result = []
        for row in output:
            try:
                result.append(
                    {
                        "ticker": row.get("mksc_shrn_iscd", ""),
                        "name": row.get("hts_kor_isnm", ""),
                        "foreign_net": _to_int(row.get("frgn_ntby_qty")),
                        "institution_net": _to_int(row.get("orgn_ntby_qty")),
                        "source": "kis",
                    }
                )
            except (AttributeError, TypeError, ValueError):
                continue
        return result

    def get_volume_rank(self, market: str = "KOSPI", limit: int = 20) -> list[dict]:
        """Fetch domestic volume ranking from KIS, returning an empty list on miss."""
        if not self.is_configured():
            return []

        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/volume-rank"
        headers = self._auth_headers("FHPST01710000")
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": _ranking_market_code(market),
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "0000000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "1000000",
            "FID_VOL_CNT": "100000",
            "FID_INPUT_DATE_1": "",
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            _raise_for_kis_error(data)
        except (httpx.HTTPError, ValueError, KisError):
            return []

        rows = _response_rows(data.get("output", []))
        result = []
        for idx, row in enumerate(rows[: max(limit, 0)], start=1):
            if not isinstance(row, dict):
                continue
            ticker = _first_value(row, "mksc_shrn_iscd", "stck_shrn_iscd", "pdno")
            if not ticker:
                continue
            try:
                result.append(
                    {
                        "ticker": ticker,
                        "name": _first_value(row, "hts_kor_isnm", "prdt_name", "stck_kor_isnm"),
                        "current_price": _to_float(_first_value(row, "stck_prpr", "prpr")),
                        "volume": _to_int(_first_value(row, "acml_vol", "cntg_vol", "vol")),
                        "change_rate": _to_float(_first_value(row, "prdy_ctrt", "fluctuation_rate")),
                        "volume_rank": _to_int(_first_value(row, "data_rank", "rank") or idx),
                        "source": "kis",
                    }
                )
            except (TypeError, ValueError):
                continue
        return result

    def get_fluctuation(
        self,
        market: str = "KOSPI",
        limit: int = 20,
        direction: str = "up",
    ) -> list[dict]:
        """Fetch domestic price fluctuation ranking from KIS, returning [] on miss."""
        if not self.is_configured():
            return []

        url = f"{self.base_url}/uapi/domestic-stock/v1/ranking/fluctuation"
        headers = self._auth_headers("FHPST01700000")
        direction_key = str(direction or "up").lower()
        if direction_key == "down":
            rsfl_rate1, rsfl_rate2 = "-100", "0"
        else:
            rsfl_rate1, rsfl_rate2 = "0", "100"
        params = {
            "fid_rsfl_rate2": rsfl_rate2,
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20170",
            "fid_input_iscd": _ranking_market_code(market),
            "fid_rank_sort_cls_code": "0000",
            "fid_input_cnt_1": str(max(limit, 0)),
            "fid_prc_cls_code": "0",
            "fid_input_price_1": "0",
            "fid_input_price_2": "1000000",
            "fid_vol_cnt": "100000",
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": rsfl_rate1,
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            _raise_for_kis_error(data)
        except (httpx.HTTPError, ValueError, KisError):
            return []

        rows = _response_rows(data.get("output", []))
        result = []
        for idx, row in enumerate(rows[: max(limit, 0)], start=1):
            if not isinstance(row, dict):
                continue
            ticker = _first_value(row, "stck_shrn_iscd", "mksc_shrn_iscd", "pdno")
            if not ticker:
                continue
            try:
                result.append(
                    {
                        "ticker": ticker,
                        "name": _first_value(row, "hts_kor_isnm", "prdt_name", "stck_kor_isnm"),
                        "current_price": _to_float(_first_value(row, "stck_prpr", "prpr")),
                        "change_rate": _to_float(_first_value(row, "prdy_ctrt", "fluctuation_rate")),
                        "volume": _to_int(_first_value(row, "acml_vol", "cntg_vol", "vol")),
                        "fluctuation_rank": _to_int(_first_value(row, "data_rank", "rank") or idx),
                        "direction": "down" if direction_key == "down" else "up",
                        "source": "kis",
                    }
                )
            except (TypeError, ValueError):
                continue
        return result

    def get_account_balance(
        self,
        *,
        afhr_flpr_yn: str = "N",
        inqr_dvsn: str = "01",
        unpr_dvsn: str = "01",
        fund_sttl_icld_yn: str = "N",
        fncg_amt_auto_rdpt_yn: str = "N",
        prcs_dvsn: str = "00",
    ) -> dict | None:
        """Fetch domestic account balance through KIS, returning None on miss."""
        if not self.is_configured():
            return None

        tr_id = "VTTC8434R" if _is_paper_mode() else "TTTC8434R"
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = self._auth_headers(tr_id)
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "AFHR_FLPR_YN": afhr_flpr_yn,
            "INQR_DVSN": inqr_dvsn,
            "UNPR_DVSN": unpr_dvsn,
            "FUND_STTL_ICLD_YN": fund_sttl_icld_yn,
            "FNCG_AMT_AUTO_RDPT_YN": fncg_amt_auto_rdpt_yn,
            "PRCS_DVSN": prcs_dvsn,
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

        try:
            resp = httpx.get(url, headers=headers, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        if data.get("rt_cd") != "0":
            return None

        holdings = []
        for item in data.get("output1", []) or []:
            if not isinstance(item, dict):
                continue
            try:
                quantity = _to_int(item.get("hldg_qty"))
                if quantity == 0:
                    continue
                holdings.append(
                    {
                        "ticker": item.get("pdno", ""),
                        "name": item.get("prdt_name", ""),
                        "quantity": quantity,
                        "avg_price": _to_float(item.get("pchs_avg_pric")),
                        "current_price": _to_float(item.get("prpr")),
                        "valuation": _to_float(item.get("evlu_amt")),
                        "profit_loss": _to_float(item.get("evlu_pfls_amt")),
                        "profit_pct": _to_float(item.get("evlu_pfls_rt")),
                    }
                )
            except (TypeError, ValueError):
                continue

        output2 = data.get("output2", {}) or {}
        if isinstance(output2, list):
            summary_raw = output2[0] if output2 else {}
        elif isinstance(output2, dict):
            summary_raw = output2
        else:
            summary_raw = {}

        try:
            summary = {
                "total_valuation": _to_float(summary_raw.get("tot_evlu_amt")),
                "total_purchase": _to_float(summary_raw.get("pchs_amt_smtl_amt")),
                "total_profit": _to_float(summary_raw.get("evlu_pfls_smtl_amt")),
                "cash_balance": _to_float(summary_raw.get("dnca_tot_amt")),
                "total_assets": _to_float(summary_raw.get("tot_asst_amt")),
            }
        except (AttributeError, TypeError, ValueError):
            summary = {
                "total_valuation": 0.0,
                "total_purchase": 0.0,
                "total_profit": 0.0,
                "cash_balance": 0.0,
                "total_assets": 0.0,
            }

        return {
            "holdings": holdings,
            "summary": summary,
            "source": "kis",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _normalize_ticker(self, ticker: str) -> str:
        """Normalize yfinance-style Korean tickers to KIS six-digit codes."""
        value = str(ticker or "").strip()
        upper = value.upper()
        if upper.endswith(".KS") or upper.endswith(".KQ"):
            return value[:-3]
        return value.zfill(6)

    def _clean_account_number(self) -> str:
        """Normalize account number variants without exposing the value."""
        return str(self.account_number or "").strip().replace("-", "").replace(" ", "")

    def _auth_headers(self, tr_id: str, tr_cont: str = "") -> dict[str, str]:
        """Build KIS REST headers for an authenticated request."""
        token = self.get_token()
        return {
            "Content-Type": "application/json",
            "Accept": "text/plain",
            "charset": "UTF-8",
            "User-Agent": _get_user_agent(),
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
            "tr_cont": tr_cont,
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


def _ranking_market_code(market: str) -> str:
    """Map human market names to KIS ranking input codes."""
    value = str(market or "").strip().upper()
    return {
        "KOSPI": "0001",
        "KS": "0001",
        "KOSDAQ": "1001",
        "KQ": "1001",
        "KOSPI200": "2001",
        "ALL": "0000",
    }.get(value, value or "0000")


def _response_rows(value: object) -> list[dict]:
    """Normalize KIS output values into a row list."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _first_value(row: dict, *keys: str) -> object:
    """Return the first present value from a KIS response row."""
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _to_float(value: object) -> float:
    """Convert KIS numeric string fields to float."""
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return float(value or 0)


def _to_int(value: object) -> int:
    """Convert KIS numeric string fields to int."""
    if isinstance(value, str):
        value = value.replace(",", "").strip()
    return int(float(value or 0))
