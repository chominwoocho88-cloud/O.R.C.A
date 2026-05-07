"""shared.market_data: 시장 데이터 수집 어댑터.

사용:
    from shared.market_data.fetch import fetch_daily_history, ...
"""

from shared.market_data.fetch import (
    fetch_daily_history,
    fetch_daily_history_batch,
    fetch_latest_close,
    fetch_put_call_ratio,
    fetch_put_call_ratio_summary,
    get_fetch_stats,
    get_provider_quality_summary,
    reset_fetch_stats,
    _last_fetch_source,
)

__all__ = [
    "fetch_daily_history",
    "fetch_daily_history_batch",
    "fetch_latest_close",
    "fetch_put_call_ratio",
    "fetch_put_call_ratio_summary",
    "get_fetch_stats",
    "get_provider_quality_summary",
    "reset_fetch_stats",
    "_last_fetch_source",
]
