"""Context snapshot helpers for Wave F Phase 1."""
from __future__ import annotations

import json
import sqlite3
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import yfinance as yf
except Exception:  # pragma: no cover - degraded runtime fallback
    yf = None

from .paths import BASELINE_FILE
from . import context_market_data
from . import state


VALID_SOURCE_EVENT_TYPES = {
    "live",
    "backtest",
    "backtest_backfill",
    "walk_forward",
    "scan",
    "hunt",
    "shadow",
}

BACKFILL_SOURCE_EVENT_TYPE = "backtest_backfill"

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communication Services",
}

MARKET_TICKERS = ("^VIX", "^GSPC", "^IXIC", *SECTOR_ETFS.keys())
_LOOKBACK_BUFFER_DAYS = 90


def get_existing_snapshot(
    trading_date: str,
    source_event_type: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    return state.find_lesson_context_snapshot(
        trading_date,
        source_event_type,
        conn=conn,
    )


def get_or_create_context_snapshot(
    trading_date: str,
    source_event_type: str,
    source_session_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Return an existing context snapshot for the date or create a new one."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    try:
        existing = get_existing_snapshot(
            trading_date,
            source_event_type,
            conn=conn,
        )
        if existing:
            return str(existing["snapshot_id"])

        snapshot_data = _build_snapshot_data(trading_date, conn)
        snapshot_id = state.record_lesson_context_snapshot(
            {
                "snapshot_id": f"ctx_{uuid4().hex}",
                "created_at": datetime.now().isoformat(),
                "trading_date": trading_date,
                "regime": snapshot_data.get("regime"),
                "regime_confidence": snapshot_data.get("regime_confidence"),
                "vix_level": snapshot_data.get("vix_level"),
                "vix_delta_7d": snapshot_data.get("vix_delta_7d"),
                "sp500_momentum_5d": snapshot_data.get("sp500_momentum_5d"),
                "sp500_momentum_20d": snapshot_data.get("sp500_momentum_20d"),
                "nasdaq_momentum_5d": snapshot_data.get("nasdaq_momentum_5d"),
                "nasdaq_momentum_20d": snapshot_data.get("nasdaq_momentum_20d"),
                "dominant_sectors": snapshot_data.get("dominant_sectors", []),
                "source_event_type": source_event_type,
                "source_session_id": source_session_id,
            },
            conn=conn,
        )
        if own_conn:
            conn.commit()
        return snapshot_id
    finally:
        if own_conn and conn is not None:
            conn.close()


def _build_snapshot_data(trading_date: str, conn: sqlite3.Connection) -> dict[str, Any]:
    """Build the minimum viable Wave F context snapshot for one trading date."""
    market_data = _fetch_market_data_for_date(trading_date)
    regime, confidence = _fetch_regime_for_date(trading_date, conn, market_data=market_data)
    return {
        "regime": regime,
        "regime_confidence": confidence,
        **market_data,
        "dominant_sectors": _compute_dominant_sectors(trading_date),
    }


def _normalize_regime_value(regime: str | None) -> str | None:
    if not regime:
        return None
    try:
        from .backtest import _normalize_regime

        normalized = _normalize_regime(str(regime))
    except Exception:
        normalized = str(regime).strip()
    return normalized or None


def _map_confidence_to_score(confidence: str | None) -> float | None:
    value = str(confidence or "").strip().lower()
    if not value:
        return None
    mapping = {
        "낮음": 0.33,
        "low": 0.33,
        "보통": 0.67,
        "medium": 0.67,
        "med": 0.67,
        "높음": 1.0,
        "high": 1.0,
    }
    return mapping.get(value)


def _load_json_file(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fetch_regime_for_date(
    trading_date: str,
    conn: sqlite3.Connection,
    *,
    market_data: dict[str, Any] | None = None,
) -> tuple[str | None, float | None]:
    regime, confidence = _fetch_regime_from_orca_report(trading_date, conn)
    if regime:
        return regime, confidence

    regime, confidence = _fetch_regime_from_baseline(trading_date)
    if regime:
        return regime, confidence

    regime, confidence = _heuristic_regime(market_data or _fetch_market_data_for_date(trading_date))
    return regime, confidence


def _fetch_regime_from_orca_report(
    trading_date: str,
    conn: sqlite3.Connection,
) -> tuple[str | None, float | None]:
    row = conn.execute(
        """
        SELECT d.analysis_json
          FROM backtest_daily_results d
          JOIN backtest_sessions s
            ON s.session_id = d.session_id
         WHERE s.system = 'orca'
           AND s.status = 'completed'
           AND d.analysis_date = ?
         ORDER BY s.started_at DESC,
                  CASE
                      WHEN d.phase_label = 'Final Pass' THEN 0
                      WHEN d.phase_label = 'Final' THEN 1
                      ELSE 2
                  END,
                  d.created_at DESC
         LIMIT 1
        """,
        (trading_date,),
    ).fetchone()
    if not row or not row["analysis_json"]:
        return None, None
    try:
        analysis = json.loads(row["analysis_json"])
    except Exception:
        return None, None
    regime = _normalize_regime_value(analysis.get("market_regime"))
    confidence = _map_confidence_to_score(analysis.get("confidence_overall"))
    return regime, confidence


def _fetch_regime_from_baseline(trading_date: str) -> tuple[str | None, float | None]:
    baseline = _load_json_file(BASELINE_FILE)
    if not isinstance(baseline, dict):
        return None, None
    if str(baseline.get("date", "")) != trading_date:
        return None, None
    regime = _normalize_regime_value(baseline.get("market_regime"))
    confidence = _map_confidence_to_score(
        baseline.get("confidence") or baseline.get("confidence_overall")
    )
    return regime, confidence


def _heuristic_regime(market_data: dict[str, Any]) -> tuple[str | None, float | None]:
    vix = market_data.get("vix_level")
    sp20 = market_data.get("sp500_momentum_20d")
    nq20 = market_data.get("nasdaq_momentum_20d")
    if vix is None and sp20 is None and nq20 is None:
        return None, None
    if vix is not None and vix >= 25:
        return "위험회피", 0.45
    if vix is not None and vix >= 20:
        return "전환중", 0.4
    if (sp20 or 0.0) > 0 and (nq20 or 0.0) > 0:
        return "위험선호", 0.4
    return "혼조", 0.35


def _fetch_market_data_for_date(trading_date: str) -> dict[str, Any]:
    """Fetch historical market context for ``trading_date``.

    ``orca.data.fetch_yahoo_data`` is current-only, so Phase 1.1 uses the same
    Yahoo source directly for historical lookbacks.
    """
    vix_points = _fetch_history_points("^VIX", trading_date, lookback_days=30)
    sp_points = _fetch_history_points("^GSPC", trading_date, lookback_days=40)
    nq_points = _fetch_history_points("^IXIC", trading_date, lookback_days=40)
    return {
        "vix_level": _latest_close(vix_points),
        "vix_delta_7d": _absolute_delta(vix_points, 7),
        "sp500_momentum_5d": _percent_change(sp_points, 5),
        "sp500_momentum_20d": _percent_change(sp_points, 20),
        "nasdaq_momentum_5d": _percent_change(nq_points, 5),
        "nasdaq_momentum_20d": _percent_change(nq_points, 20),
    }


def _compute_dominant_sectors(trading_date: str, top_n: int = 3) -> list[str]:
    scored: list[tuple[str, float]] = []
    for ticker, label in SECTOR_ETFS.items():
        points = _fetch_history_points(ticker, trading_date, lookback_days=15)
        change = _percent_change(points, 5)
        if change is None or change <= 0:
            continue
        scored.append((label, change))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [label for label, _score in scored[:top_n]]


def backfill_lessons_context(
    limit: int | None = None,
    skip_existing: bool = True,
    dry_run: bool = False,
    verbose: bool = False,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Backfill context snapshots for existing backtest lessons.

    ``limit`` is measured in distinct trading dates, not lessons. Dry-run mode
    avoids both DB writes and network calls.
    """
    started = time.time()
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()

    try:
        groups = _load_backfill_lesson_groups(conn, skip_existing=skip_existing)
        total_lessons = _count_backtest_lessons(conn)
        sorted_dates = sorted(groups)
        if limit is not None:
            sorted_dates = sorted_dates[: max(0, int(limit))]

        selected_lesson_total = sum(len(groups[date]["lesson_ids"]) for date in sorted_dates)
        summary: dict[str, Any] = {
            "lessons_total": total_lessons,
            "lessons_processed": 0,
            "lessons_skipped": total_lessons,
            "snapshots_created": 0,
            "snapshots_reused": 0,
            "failed_dates": [],
            "duration_seconds": 0.0,
            "dates_total": len(groups),
            "dates_processed": 0,
            "dry_run": bool(dry_run),
        }

        if verbose:
            print(f"Backfill target dates: {len(sorted_dates)} / {len(groups)}")
            print(f"Backfill target lessons: {selected_lesson_total} / {total_lessons}")

        if dry_run or not sorted_dates:
            existing_count = 0
            for trading_date in sorted_dates:
                if state.find_lesson_context_snapshot(
                    trading_date,
                    BACKFILL_SOURCE_EVENT_TYPE,
                    conn=conn,
                ):
                    existing_count += 1
            summary["snapshots_reused"] = existing_count
            summary["snapshots_created"] = len(sorted_dates) - existing_count
            summary["lessons_processed"] = selected_lesson_total
            summary["lessons_skipped"] = total_lessons - selected_lesson_total
            summary["dates_processed"] = len(sorted_dates)
            summary["duration_seconds"] = round(time.time() - started, 3)
            return summary

        cached_data = _fetch_historical_market_data_range(sorted_dates[0], sorted_dates[-1])

        for index, trading_date in enumerate(sorted_dates, start=1):
            group = groups[trading_date]
            lesson_ids = group["lesson_ids"]
            try:
                existing = None
                if skip_existing:
                    existing = state.find_lesson_context_snapshot(
                        trading_date,
                        BACKFILL_SOURCE_EVENT_TYPE,
                        conn=conn,
                    )
                if existing:
                    snapshot_id = str(existing["snapshot_id"])
                    summary["snapshots_reused"] += 1
                else:
                    metrics = _compute_metrics_for_date(trading_date, cached_data)
                    snapshot_id = state.record_lesson_context_snapshot(
                        {
                            "snapshot_id": f"ctx_{uuid4().hex}",
                            "created_at": datetime.now().isoformat(),
                            "trading_date": trading_date,
                            "regime": group.get("regime"),
                            "regime_confidence": None,
                            **metrics,
                            "source_event_type": BACKFILL_SOURCE_EVENT_TYPE,
                            "source_session_id": group.get("source_session_id"),
                        },
                        conn=conn,
                    )
                    summary["snapshots_created"] += 1

                _update_lessons_context_snapshot(conn, lesson_ids, snapshot_id)
                summary["lessons_processed"] += len(lesson_ids)
                summary["dates_processed"] += 1
                if verbose:
                    print(
                        f"[{index}/{len(sorted_dates)}] {trading_date}: "
                        f"{len(lesson_ids)} lessons -> {snapshot_id}"
                    )
            except Exception as exc:
                summary["failed_dates"].append(
                    {"date": trading_date, "reason": f"{type(exc).__name__}: {exc}"}
                )
                if verbose:
                    print(f"[{index}/{len(sorted_dates)}] {trading_date}: failed ({exc})")

        summary["lessons_skipped"] = total_lessons - summary["lessons_processed"]
        summary["duration_seconds"] = round(time.time() - started, 3)
        if own_conn:
            conn.commit()
        return summary
    finally:
        if own_conn and conn is not None:
            conn.close()


def verify_backfill_completeness(
    expected_snapshots: int = 252,
    expected_linked_lessons: int = 1260,
    require_market_metrics: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Verify that Wave F Phase 1.3 backfill produced complete data."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    try:
        snapshots_backfill = int(
            conn.execute(
                """
                SELECT COUNT(*)
                  FROM lesson_context_snapshot
                 WHERE source_event_type = ?
                """,
                (BACKFILL_SOURCE_EVENT_TYPE,),
            ).fetchone()[0]
        )
        snapshots_total = int(
            conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot").fetchone()[0]
        )
        lessons_linked = int(
            conn.execute(
                """
                SELECT COUNT(*)
                  FROM candidate_lessons l
                  JOIN candidate_registry c
                    ON c.candidate_id = l.candidate_id
                 WHERE c.source_event_type = 'backtest'
                   AND l.context_snapshot_id IS NOT NULL
                """
            ).fetchone()[0]
        )
        lessons_unlinked = int(
            conn.execute(
                """
                SELECT COUNT(*)
                  FROM candidate_lessons l
                  JOIN candidate_registry c
                    ON c.candidate_id = l.candidate_id
                 WHERE c.source_event_type = 'backtest'
                   AND l.context_snapshot_id IS NULL
                """
            ).fetchone()[0]
        )
        metric_counts = _backfill_metric_counts(conn)

        failures: list[str] = []
        if snapshots_backfill < expected_snapshots:
            failures.append(
                f"backtest_backfill snapshots {snapshots_backfill} < {expected_snapshots}"
            )
        if lessons_linked < expected_linked_lessons:
            failures.append(
                f"linked backtest lessons {lessons_linked} < {expected_linked_lessons}"
            )
        if lessons_unlinked != 0:
            failures.append(f"unlinked backtest lessons remain: {lessons_unlinked}")

        if require_market_metrics:
            required_metrics = {
                "vix_filled": "vix_level",
                "sp500_5d_filled": "sp500_momentum_5d",
                "sp500_20d_filled": "sp500_momentum_20d",
                "nasdaq_5d_filled": "nasdaq_momentum_5d",
                "nasdaq_20d_filled": "nasdaq_momentum_20d",
                "sectors_filled": "dominant_sectors",
            }
            for key, label in required_metrics.items():
                if metric_counts[key] < snapshots_backfill:
                    failures.append(
                        f"{label} filled {metric_counts[key]} < snapshots {snapshots_backfill}"
                    )

        return {
            "passed": not failures,
            "failures": failures,
            "snapshots_total": snapshots_total,
            "snapshots_backfill": snapshots_backfill,
            "lessons_linked": lessons_linked,
            "lessons_unlinked": lessons_unlinked,
            **metric_counts,
        }
    finally:
        if own_conn and conn is not None:
            conn.close()


def cleanup_backfill_data(
    conn: sqlite3.Connection | None = None,
    verbose: bool = False,
) -> dict[str, int]:
    """Remove Phase 1.3 backfill data while preserving schema and live snapshots."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    try:
        lessons_unlinked = int(
            conn.execute(
                """
                SELECT COUNT(*)
                  FROM candidate_lessons
                 WHERE context_snapshot_id IN (
                       SELECT snapshot_id
                         FROM lesson_context_snapshot
                        WHERE source_event_type = ?
                 )
                """,
                (BACKFILL_SOURCE_EVENT_TYPE,),
            ).fetchone()[0]
        )
        snapshots_deleted = int(
            conn.execute(
                """
                SELECT COUNT(*)
                  FROM lesson_context_snapshot
                 WHERE source_event_type = ?
                """,
                (BACKFILL_SOURCE_EVENT_TYPE,),
            ).fetchone()[0]
        )
        conn.execute(
            """
            UPDATE candidate_lessons
               SET context_snapshot_id = NULL
             WHERE context_snapshot_id IN (
                   SELECT snapshot_id
                     FROM lesson_context_snapshot
                    WHERE source_event_type = ?
             )
            """,
            (BACKFILL_SOURCE_EVENT_TYPE,),
        )
        conn.execute(
            """
            DELETE FROM lesson_context_snapshot
             WHERE source_event_type = ?
            """,
            (BACKFILL_SOURCE_EVENT_TYPE,),
        )
        if own_conn:
            conn.commit()
        if verbose:
            print(f"Unlinked lessons: {lessons_unlinked}")
            print(f"Deleted snapshots: {snapshots_deleted}")
        return {
            "lessons_unlinked": lessons_unlinked,
            "snapshots_deleted": snapshots_deleted,
        }
    finally:
        if own_conn and conn is not None:
            conn.close()


def _backfill_metric_counts(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN vix_level IS NOT NULL THEN 1 ELSE 0 END) AS vix_filled,
            SUM(CASE WHEN sp500_momentum_5d IS NOT NULL THEN 1 ELSE 0 END) AS sp500_5d_filled,
            SUM(CASE WHEN sp500_momentum_20d IS NOT NULL THEN 1 ELSE 0 END) AS sp500_20d_filled,
            SUM(CASE WHEN nasdaq_momentum_5d IS NOT NULL THEN 1 ELSE 0 END) AS nasdaq_5d_filled,
            SUM(CASE WHEN nasdaq_momentum_20d IS NOT NULL THEN 1 ELSE 0 END) AS nasdaq_20d_filled,
            SUM(
                CASE
                    WHEN dominant_sectors IS NOT NULL
                     AND dominant_sectors != ''
                     AND dominant_sectors != '[]'
                    THEN 1
                    ELSE 0
                END
            ) AS sectors_filled
          FROM lesson_context_snapshot
         WHERE source_event_type = ?
        """,
        (BACKFILL_SOURCE_EVENT_TYPE,),
    ).fetchone()
    return {
        "vix_filled": int(row["vix_filled"] or 0),
        "sp500_5d_filled": int(row["sp500_5d_filled"] or 0),
        "sp500_20d_filled": int(row["sp500_20d_filled"] or 0),
        "nasdaq_5d_filled": int(row["nasdaq_5d_filled"] or 0),
        "nasdaq_20d_filled": int(row["nasdaq_20d_filled"] or 0),
        "sectors_filled": int(row["sectors_filled"] or 0),
    }


def _count_backtest_lessons(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
              FROM candidate_lessons l
              JOIN candidate_registry c
                ON c.candidate_id = l.candidate_id
             WHERE c.source_event_type = 'backtest'
            """
        ).fetchone()[0]
    )


def _load_backfill_lesson_groups(
    conn: sqlite3.Connection,
    *,
    skip_existing: bool,
) -> dict[str, dict[str, Any]]:
    query = """
        SELECT l.lesson_id,
               l.lesson_json,
               l.context_snapshot_id,
               c.analysis_date,
               c.source_session_id
          FROM candidate_lessons l
          JOIN candidate_registry c
            ON c.candidate_id = l.candidate_id
         WHERE c.source_event_type = 'backtest'
    """
    if skip_existing:
        query += " AND l.context_snapshot_id IS NULL"
    query += " ORDER BY c.analysis_date ASC, l.lesson_id ASC"

    grouped: dict[str, dict[str, Any]] = {}
    for row in conn.execute(query).fetchall():
        payload = _safe_json(row["lesson_json"])
        trading_date = str(
            payload.get("analysis_date") or row["analysis_date"] or ""
        ).strip()[:10]
        if not trading_date:
            continue
        group = grouped.setdefault(
            trading_date,
            {
                "lesson_ids": [],
                "regimes": Counter(),
                "source_session_ids": Counter(),
            },
        )
        group["lesson_ids"].append(str(row["lesson_id"]))
        regime = _normalize_regime_value(payload.get("regime"))
        if regime:
            group["regimes"][regime] += 1
        source_session_id = str(row["source_session_id"] or "").strip()
        if source_session_id:
            group["source_session_ids"][source_session_id] += 1

    for group in grouped.values():
        group["regime"] = _counter_mode(group.pop("regimes"))
        group["source_session_id"] = _counter_mode(group.pop("source_session_ids"))
    return grouped


def _counter_mode(counter: Counter) -> str | None:
    if not counter:
        return None
    return counter.most_common(1)[0][0]


def _safe_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except Exception:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _update_lessons_context_snapshot(
    conn: sqlite3.Connection,
    lesson_ids: list[str],
    snapshot_id: str,
) -> None:
    if not lesson_ids:
        return
    placeholders = ", ".join("?" for _ in lesson_ids)
    conn.execute(
        f"""
        UPDATE candidate_lessons
           SET context_snapshot_id = ?
         WHERE lesson_id IN ({placeholders})
        """,
        [snapshot_id, *lesson_ids],
    )


def _fetch_historical_market_data_range(
    min_date: str,
    max_date: str,
    buffer_days: int = 90,
) -> dict[str, list[tuple[str, float]]]:
    return context_market_data.fetch_historical_market_data_range(
        MARKET_TICKERS,
        min_date,
        max_date,
        buffer_days=buffer_days,
    )


def _compute_metrics_for_date(
    trading_date: str,
    cached_data: dict[str, Any],
) -> dict[str, Any]:
    """Compute snapshot metrics from cached data without network calls."""
    vix_points = _points_until(cached_data.get("^VIX", []), trading_date)
    sp_points = _points_until(cached_data.get("^GSPC", []), trading_date)
    nq_points = _points_until(cached_data.get("^IXIC", []), trading_date)
    return {
        "vix_level": _latest_close(vix_points),
        "vix_delta_7d": _absolute_delta(vix_points, 7),
        "sp500_momentum_5d": _percent_change(sp_points, 5),
        "sp500_momentum_20d": _percent_change(sp_points, 20),
        "nasdaq_momentum_5d": _percent_change(nq_points, 5),
        "nasdaq_momentum_20d": _percent_change(nq_points, 20),
        "dominant_sectors": _compute_dominant_sectors_from_cache(
            trading_date,
            cached_data,
        ),
    }


def _compute_dominant_sectors_from_cache(
    trading_date: str,
    cached_data: dict[str, Any],
    top_n: int = 3,
) -> list[str]:
    scored: list[tuple[str, float]] = []
    for ticker, label in SECTOR_ETFS.items():
        points = _points_until(cached_data.get(ticker, []), trading_date)
        change = _percent_change(points, 5)
        if change is not None and change > 0:
            scored.append((label, change))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [label for label, _score in scored[:top_n]]


def _points_until(points_or_frame: Any, trading_date: str) -> list[tuple[str, float]]:
    points = (
        points_or_frame
        if isinstance(points_or_frame, list)
        else context_market_data._points_from_frame(points_or_frame)
    )
    return [(date, value) for date, value in points if str(date)[:10] <= trading_date]


def _fetch_history_points(
    ticker: str,
    trading_date: str,
    *,
    lookback_days: int,
) -> list[tuple[str, float]]:
    if yf is None:
        return []
    try:
        end_date = datetime.fromisoformat(trading_date) + timedelta(days=1)
    except ValueError:
        return []
    start_date = end_date - timedelta(days=max(_LOOKBACK_BUFFER_DAYS, lookback_days * 4))
    try:
        history = yf.Ticker(ticker).history(
            start=start_date.date().isoformat(),
            end=end_date.date().isoformat(),
            interval="1d",
            auto_adjust=False,
        )
    except Exception:
        return []
    if history is None:
        return []
    return context_market_data._points_from_frame(history)


def _latest_close(points: list[tuple[str, float]]) -> float | None:
    if not points:
        return None
    return round(points[-1][1], 4)


def _absolute_delta(points: list[tuple[str, float]], offset: int) -> float | None:
    if len(points) <= offset:
        return None
    current = points[-1][1]
    prior = points[-(offset + 1)][1]
    return round(current - prior, 4)


def _percent_change(points: list[tuple[str, float]], offset: int) -> float | None:
    if len(points) <= offset:
        return None
    current = points[-1][1]
    prior = points[-(offset + 1)][1]
    if prior == 0:
        return None
    return round(((current - prior) / prior) * 100.0, 4)
