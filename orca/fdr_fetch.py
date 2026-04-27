"""FinanceDataReader fetch adapter for Wave H.

FDR is used as a temporary primary daily OHLCV provider while Korean market
data is unstable through yfinance and before the KIS API is available.
"""
from __future__ import annotations

import re
import sys
from typing import Any

import pandas as pd

try:
    import FinanceDataReader as fdr
except Exception:  # pragma: no cover - optional runtime dependency
    fdr = None


class FDRTickerNotSupportedError(ValueError):
    """Raised when a yfinance-style ticker has no safe FDR mapping."""


_FDR_TICKER_MAP: dict[str, str | None] = {
    "^VIX": "VIX",
    "^GSPC": "US500",
    "^IXIC": "IXIC",
    "^KS11": "KS11",
    "USDKRW=X": "USD/KRW",
    "KRW=X": "USD/KRW",
    "USD/KRW": "USD/KRW",
    "^TNX": None,
    "^IRX": None,
}

_KNOWN_FDR_INDEXES = {"KS11", "KQ11", "KOSPI", "KOSDAQ", "VIX", "US500", "IXIC"}


def fetch_fdr_history(
    ticker: str,
    start: str | None = None,
    end: str | None = None,
    conn=None,
) -> pd.DataFrame | None:
    """Fetch historical daily data from FinanceDataReader.

    Returns a yfinance-compatible DataFrame with a naive DatetimeIndex, or
    ``None`` when FDR is unavailable or the provider returns no usable data.
    Unsupported tickers raise ``FDRTickerNotSupportedError`` so callers can
    immediately continue to the next provider.
    """
    del conn  # reserved for future cache/KIS compatibility

    fdr_ticker = _convert_ticker_for_fdr(ticker)
    if not fdr_ticker:
        raise FDRTickerNotSupportedError(f"FDR unsupported ticker: {ticker}")

    if fdr is None:
        sys.stderr.write("WARN: FinanceDataReader is not installed; skipping FDR fetch\n")
        return None

    try:
        if start and end:
            data = fdr.DataReader(fdr_ticker, start, end)
        elif start:
            data = fdr.DataReader(fdr_ticker, start)
        else:
            data = fdr.DataReader(fdr_ticker)
        return _normalize_fdr_dataframe(data)
    except Exception as exc:
        sys.stderr.write(f"WARN: FDR fetch failed for {ticker} ({fdr_ticker}): {exc}\n")
        return None


def is_fdr_supported(ticker: str) -> bool:
    """Return whether this yfinance-style ticker has a safe FDR mapping."""
    return _convert_ticker_for_fdr(ticker) is not None


def _convert_ticker_for_fdr(ticker: str) -> str | None:
    """Convert yfinance-style tickers to FinanceDataReader symbols."""
    normalized = str(ticker or "").strip()
    if not normalized:
        return None

    upper = normalized.upper()
    if upper in _FDR_TICKER_MAP:
        return _FDR_TICKER_MAP[upper]

    if _is_korean_ticker(upper):
        return upper.split(".", 1)[0]

    if upper in _KNOWN_FDR_INDEXES:
        return upper

    if _is_currency_ticker(upper):
        if upper in {"USDKRW=X", "KRW=X", "USD/KRW"}:
            return "USD/KRW"
        return None

    if upper.startswith("^"):
        return None

    if re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", upper):
        return upper

    return None


def _is_korean_ticker(ticker: str) -> bool:
    """Return whether a ticker is a Korean stock/ETF style symbol."""
    upper = str(ticker or "").strip().upper()
    return upper.endswith(".KS") or upper.endswith(".KQ") or (upper.isdigit() and len(upper) == 6)


def _is_index_ticker(ticker: str) -> bool:
    """Return whether a ticker is a known index symbol for this adapter."""
    upper = str(ticker or "").strip().upper()
    return upper.startswith("^") or upper in _KNOWN_FDR_INDEXES


def _is_currency_ticker(ticker: str) -> bool:
    """Return whether a ticker is a currency pair style symbol."""
    upper = str(ticker or "").strip().upper()
    return "=X" in upper or "/" in upper


def _normalize_fdr_dataframe(data: Any) -> pd.DataFrame | None:
    """Normalize FDR output to yfinance-compatible OHLCV columns."""
    if data is None or getattr(data, "empty", False):
        return None

    frame = data.copy() if hasattr(data, "copy") else pd.DataFrame(data)
    if frame.empty:
        return None

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(-1)

    rename: dict[Any, str] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower().replace("_", " ")
        if normalized == "open":
            rename[column] = "Open"
        elif normalized == "high":
            rename[column] = "High"
        elif normalized == "low":
            rename[column] = "Low"
        elif normalized == "close":
            rename[column] = "Close"
        elif normalized == "volume":
            rename[column] = "Volume"
        elif normalized == "change":
            rename[column] = "Change"
    frame = frame.rename(columns=rename)

    if "Close" not in frame.columns:
        return None

    try:
        frame.index = pd.to_datetime(frame.index)
        if getattr(frame.index, "tz", None) is not None:
            frame.index = frame.index.tz_localize(None)
    except Exception:
        pass

    ordered = [column for column in ("Open", "High", "Low", "Close", "Volume", "Change") if column in frame.columns]
    rest = [column for column in frame.columns if column not in ordered]
    return frame[ordered + rest]

