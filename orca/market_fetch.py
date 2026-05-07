"""
orca.market_fetch (DEPRECATED ALIAS)
=====================================

이 모듈은 backward-compatible alias입니다.
실제 코드는 shared/market_data/fetch.py 로 이동됨 (Day 6 commit).

신규 코드는 다음 경로 사용 권장:
    from shared.market_data.fetch import fetch_daily_history
또는:
    from shared.market_data import fetch_daily_history

이 alias는 호출부 마이그레이션 완료 후 제거 예정.
"""

import sys as _sys

from shared.market_data import fetch as _fetch
from shared.market_data.fetch import *  # noqa: F401,F403
from shared.market_data.fetch import (
    fetch_daily_history,
    fetch_daily_history_batch,
    fetch_latest_close,
    fetch_put_call_ratio,
    fetch_put_call_ratio_summary,
    get_fetch_stats,
    get_provider_quality_summary,
    reset_fetch_stats,
    _download_direct,
    _extract_batch_ticker_frame,
    _is_korean_market_ticker,
    _last_fetch_source,
    _normalize_history_frame,
    _option_expiries,
    _pcr_signal,
    _record_fetch_source,
    _record_provider_attempt,
    _record_provider_issue,
    _resolve_use_fallback,
    _sum_option_column,
    _try_alpha_vantage_history,
    _try_fdr_history,
    _use_fdr_main,
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
    "_download_direct",
    "_extract_batch_ticker_frame",
    "_is_korean_market_ticker",
    "_last_fetch_source",
    "_normalize_history_frame",
    "_option_expiries",
    "_pcr_signal",
    "_record_fetch_source",
    "_record_provider_attempt",
    "_record_provider_issue",
    "_resolve_use_fallback",
    "_sum_option_column",
    "_try_alpha_vantage_history",
    "_try_fdr_history",
    "_use_fdr_main",
]

_sys.modules[__name__] = _fetch
