"""Korean stock display-name lookup with a small persistent cache."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.paths import DATA_DIR, atomic_write_json


CACHE_PATH = DATA_DIR / "stock_name_cache.json"
KOREAN_SUFFIXES = (".KS", ".KQ")


def get_stock_name(ticker: str) -> str | None:
    """Return a Korean stock name for KOSPI/KOSDAQ tickers when available."""
    ticker = str(ticker or "").strip().upper()
    if not _is_korean_ticker(ticker):
        return None

    cache = _load_cache()
    cached = _clean_name(cache.get(ticker))
    if cached:
        return cached

    try:
        name = _fetch_from_fdr(ticker)
    except Exception:
        name = None
    if name:
        cache[ticker] = name
        _save_cache(cache)
    return name


def format_stock_display(ticker: str, fallback_name: str | None = None) -> str:
    """Format display label as ``name (ticker)`` with safe ticker fallback."""
    ticker = str(ticker or "").strip()
    fallback = _clean_name(fallback_name)
    name = get_stock_name(ticker) if _is_korean_ticker(ticker) else None
    display_name = name or fallback
    if display_name and display_name != ticker:
        return f"{display_name} ({ticker})"
    return ticker


def _is_korean_ticker(ticker: str) -> bool:
    return str(ticker or "").upper().endswith(KOREAN_SUFFIXES)


def _load_cache() -> dict[str, str]:
    if not CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: dict[str, str]) -> None:
    atomic_write_json(Path(CACHE_PATH), dict(sorted(cache.items())))


def _fetch_from_fdr(ticker: str) -> str | None:
    code = str(ticker or "").split(".", 1)[0].zfill(6)
    suffix = str(ticker or "").upper()[-3:]
    markets = ("KOSDAQ", "KOSPI") if suffix == ".KQ" else ("KOSPI", "KOSDAQ")
    for market in markets:
        name = _lookup_fdr_market(code, market)
        if name:
            return name
    return None


@lru_cache(maxsize=2)
def _fdr_listing(market: str) -> Any:
    import FinanceDataReader as fdr

    return fdr.StockListing(market)


def _lookup_fdr_market(code: str, market: str) -> str | None:
    try:
        listing = _fdr_listing(market)
        match = listing[listing["Code"].astype(str).str.zfill(6) == code]
        if match.empty:
            return None
        return _clean_name(match.iloc[0].get("Name"))
    except Exception:
        return None


def _clean_name(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
