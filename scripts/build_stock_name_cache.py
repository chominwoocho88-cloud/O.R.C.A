"""Build the Korean stock-name cache for KOSPI and KOSDAQ tickers.

Phase 8i.1 keeps the runtime lookup path unchanged and pre-populates
``data/stock_name_cache.json`` so JACKAL alerts can render Korean names
without a first-use listing fetch.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.market_data.stock_name import CACHE_PATH


MARKET_SUFFIXES = {
    "KOSPI": ".KS",
    "KOSDAQ": ".KQ",
}


def build_cache(
    refresh: bool = False,
    *,
    fdr_module: Any | None = None,
    cache_path: Path | None = None,
) -> dict[str, Any]:
    """Build or refresh the Korean stock-name cache.

    Args:
        refresh: When true, rebuild from scratch. Otherwise merge with the
            existing cache.
        fdr_module: Optional FinanceDataReader-compatible module for tests.
        cache_path: Optional cache path for tests.

    Returns:
        A stats dictionary describing added rows and provider errors.
    """
    if fdr_module is None:
        import FinanceDataReader as fdr_module

    target_path = Path(cache_path or CACHE_PATH)
    cache: dict[str, str] = {}

    if not refresh and target_path.exists():
        try:
            loaded = json.loads(target_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cache = {str(k): str(v) for k, v in loaded.items() if _clean(v)}
            print(f"[existing] loaded {len(cache)} cached names")
        except Exception as exc:
            print(f"[warning] failed to load existing cache: {exc}")

    stats: dict[str, Any] = {
        "kospi_total": 0,
        "kospi_added": 0,
        "kosdaq_total": 0,
        "kosdaq_added": 0,
        "errors": [],
    }

    for market, suffix in MARKET_SUFFIXES.items():
        total_key = f"{market.lower()}_total"
        added_key = f"{market.lower()}_added"
        try:
            print(f"[{market}] StockListing fetch...")
            listing = fdr_module.StockListing(market)
            stats[total_key] = len(listing)
            added = _merge_listing(cache, listing, suffix=suffix, refresh=refresh)
            stats[added_key] = added
            print(f"[{market}] added {added}/{stats[total_key]}")
        except Exception as exc:
            message = f"{market}: {exc}"
            stats["errors"].append(message)
            print(f"[error] {message}")

    if cache:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[saved] {target_path}: {len(cache)} names")

    meta = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "stats": stats,
        "total_cached": len(cache),
    }
    meta_path = target_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[saved] {meta_path}")

    return stats


def _merge_listing(cache: dict[str, str], listing: Any, *, suffix: str, refresh: bool) -> int:
    added = 0
    for _, row in listing.iterrows():
        code = _normalise_code(_get_row_value(row, "Code"))
        name = _clean(_get_row_value(row, "Name"))
        if not code or not name:
            continue

        ticker = f"{code}{suffix}"
        if refresh or ticker not in cache:
            if ticker not in cache:
                added += 1
            cache[ticker] = name
    return added


def _get_row_value(row: Any, key: str) -> Any:
    if hasattr(row, "get"):
        return row.get(key)
    try:
        return row[key]
    except Exception:
        return None


def _normalise_code(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(6)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build KOSPI/KOSDAQ Korean name cache")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild the cache from scratch instead of merging with the existing file",
    )
    args = parser.parse_args(argv)

    stats = build_cache(refresh=args.refresh)

    print("\n=== final stats ===")
    print(f"KOSPI: {stats['kospi_added']}/{stats['kospi_total']}")
    print(f"KOSDAQ: {stats['kosdaq_added']}/{stats['kosdaq_total']}")
    if stats["errors"]:
        print(f"errors: {stats['errors']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
