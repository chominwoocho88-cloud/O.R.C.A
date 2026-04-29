"""JACKAL shadow, recommendation, and raw-session quality diagnostics."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import state

KST = timezone(timedelta(hours=9))


def _now() -> datetime:
    return datetime.now(KST)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def describe_jackal_shadow_state() -> dict[str, Any]:
    state.init_state_db()
    batches = state.list_jackal_shadow_batches(20)
    rolling_10 = _rolling_shadow_stats(batches, 10)
    with state._connect_jackal() as conn:
        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM jackal_shadow_signals GROUP BY status"
        ).fetchall()
        signal_count = conn.execute("SELECT COUNT(*) AS count FROM jackal_shadow_signals").fetchone()["count"]
        resolved_with_outcome = conn.execute(
            """
            SELECT COUNT(*) AS count
              FROM jackal_shadow_signals
             WHERE status = 'resolved'
               AND outcome_json IS NOT NULL
               AND outcome_json != ''
            """
        ).fetchone()["count"]

    status_counts = {str(row["status"]): int(row["count"]) for row in status_rows}
    missing_reasons: list[str] = []
    if int(signal_count or 0) == 0:
        missing_reasons.append("missing_shadow_signals")
    if not batches:
        missing_reasons.append("missing_shadow_batches")
    if int(resolved_with_outcome or 0) == 0:
        missing_reasons.append("missing_resolved_shadow_outcomes")

    return {
        "signal_rows": int(signal_count or 0),
        "signal_status_counts": status_counts,
        "resolved_with_outcome": int(resolved_with_outcome or 0),
        "batch_rows": len(batches),
        "latest_batch": batches[0] if batches else None,
        "rolling_10": rolling_10,
        "missing_reasons": missing_reasons,
        "backfill_possible": int(resolved_with_outcome or 0) > 0,
    }


def _rolling_shadow_stats(batches: list[dict[str, Any]], size: int) -> dict[str, Any]:
    window = batches[:size]
    prev = batches[size:size * 2]

    def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(int(item.get("total") or 0) for item in rows)
        worked = sum(int(item.get("worked") or 0) for item in rows)
        rate = round(worked / total * 100, 1) if total > 0 else 0.0
        return {"batch_count": len(rows), "total": total, "worked": worked, "rate": rate}

    current = _aggregate(window)
    previous = _aggregate(prev)
    current["delta_vs_prev"] = (
        round(current["rate"] - previous["rate"], 1) if previous["batch_count"] else None
    )
    return current


def backfill_shadow_batches_from_resolved_signals(*, dry_run: bool = False) -> dict[str, Any]:
    state.init_state_db()
    with state._connect_jackal() as conn:
        rows = conn.execute(
            """
            SELECT shadow_id, outcome_json
              FROM jackal_shadow_signals
             WHERE status = 'resolved'
               AND outcome_json IS NOT NULL
               AND outcome_json != ''
            """
        ).fetchall()

    total = 0
    worked = 0
    source_ids: list[str] = []
    for row in rows:
        try:
            outcome = json.loads(row["outcome_json"] or "{}")
        except Exception:
            outcome = {}
        if "shadow_swing_ok" not in outcome:
            continue
        total += 1
        worked += int(bool(outcome.get("shadow_swing_ok")))
        source_ids.append(row["shadow_id"])

    if total == 0:
        return {
            "status": "skipped",
            "reason": "missing_resolved_shadow_outcomes",
            "total": 0,
            "worked": 0,
            "dry_run": dry_run,
        }
    if dry_run:
        return {
            "status": "planned",
            "reason": "dry_run",
            "total": total,
            "worked": worked,
            "dry_run": True,
        }

    batch = state.record_jackal_shadow_accuracy_batch(
        total,
        worked,
        metadata={
            "source": "backfill_jackal_shadow",
            "source_signal_count": total,
            "source_shadow_ids": source_ids[:200],
        },
    )
    return {
        "status": "backfilled",
        "reason": "ok",
        "total": total,
        "worked": worked,
        "dry_run": False,
        "batch": batch.get("last_batch"),
    }


def describe_jackal_recommendation_accuracy_state() -> dict[str, Any]:
    state.init_state_db()
    with state._connect_jackal() as conn:
        rec_total = conn.execute("SELECT COUNT(*) AS count FROM jackal_recommendations").fetchone()["count"]
        checked = conn.execute(
            "SELECT COUNT(*) AS count FROM jackal_recommendations WHERE outcome_checked = 1"
        ).fetchone()["count"]
        projection_rows = conn.execute(
            "SELECT COUNT(*) AS count FROM jackal_accuracy_projection WHERE family = 'recommendation'"
        ).fetchone()["count"]
        current_rows = conn.execute(
            "SELECT COUNT(*) AS count FROM jackal_accuracy_current WHERE family = 'recommendation'"
        ).fetchone()["count"]
        max_sample = conn.execute(
            "SELECT MAX(total) AS max_total FROM jackal_accuracy_current WHERE family = 'recommendation'"
        ).fetchone()["max_total"]

    missing_reasons: list[str] = []
    if int(rec_total or 0) == 0:
        missing_reasons.append("missing_recommendation_samples")
    if int(checked or 0) == 0:
        missing_reasons.append("missing_recommendation_outcomes")
    if int(projection_rows or 0) == 0:
        missing_reasons.append("missing_recommendation_projection_rows")
    if int(current_rows or 0) == 0:
        missing_reasons.append("missing_recommendation_current_rows")

    return {
        "recommendation_rows": int(rec_total or 0),
        "checked_rows": int(checked or 0),
        "projection_rows": int(projection_rows or 0),
        "current_rows": int(current_rows or 0),
        "max_sample_count": float(max_sample) if max_sample is not None else None,
        "missing_reasons": missing_reasons,
        "backfill_possible": int(checked or 0) > 0,
    }


def build_recommendation_accuracy_weights() -> dict[str, Any]:
    state.init_state_db()
    with state._connect_jackal() as conn:
        rows = conn.execute(
            """
            SELECT ticker, outcome_correct, payload_json
              FROM jackal_recommendations
             WHERE outcome_checked = 1
               AND outcome_correct IS NOT NULL
            """
        ).fetchall()

    by_regime: dict[str, dict[str, int]] = {}
    by_inflow: dict[str, dict[str, int]] = {}
    by_ticker: dict[str, dict[str, int]] = {}
    generated_at = _now().isoformat()

    def add(bucket: dict[str, dict[str, int]], key: str, correct: bool) -> None:
        if not key:
            return
        item = bucket.setdefault(key, {"correct": 0, "total": 0})
        item["total"] += 1
        item["correct"] += int(correct)

    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        correct = bool(row["outcome_correct"])
        add(by_ticker, str(row["ticker"] or payload.get("ticker") or ""), correct)
        add(by_regime, str(payload.get("orca_regime") or ""), correct)
        for inflow in payload.get("orca_inflows") or []:
            add(by_inflow, str(inflow), correct)

    def finalize(bucket: dict[str, dict[str, int]]) -> dict[str, dict[str, Any]]:
        return {
            key: {
                "correct": value["correct"],
                "total": value["total"],
                "accuracy": round(value["correct"] / value["total"] * 100, 1) if value["total"] else 0.0,
                "sample_count": value["total"],
                "source": "jackal_recommendations",
                "generated_at": generated_at,
            }
            for key, value in bucket.items()
        }

    return {
        "recommendation_accuracy": {
            "by_regime": finalize(by_regime),
            "by_inflow": finalize(by_inflow),
            "by_ticker": finalize(by_ticker),
        },
        "backfill_source": {"source_type": "jackal_recommendations", "generated_at": generated_at},
    }


def backfill_recommendation_accuracy_projection(*, dry_run: bool = False) -> dict[str, Any]:
    weights = build_recommendation_accuracy_weights()
    rec = weights.get("recommendation_accuracy", {})
    row_count = sum(len(value) for value in rec.values() if isinstance(value, dict))
    if row_count == 0:
        return {
            "status": "skipped",
            "reason": "missing_recommendation_samples",
            "projection_rows": 0,
            "dry_run": dry_run,
        }
    if dry_run:
        return {"status": "planned", "reason": "dry_run", "projection_rows": row_count, "dry_run": True}
    snapshot_id = state.record_jackal_weight_snapshot(weights, source="backfill_jackal_recommendations")
    return {
        "status": "backfilled",
        "reason": "ok",
        "projection_rows": row_count,
        "snapshot_id": snapshot_id,
        "dry_run": False,
    }


def classify_latest_raw_jackal_session(
    raw_session: dict[str, Any] | None,
    evaluable_session: dict[str, Any] | None,
    *,
    stale_hours: float = 168.0,
) -> dict[str, Any]:
    issue = _jackal_raw_issue(raw_session)
    ended = _parse_dt((evaluable_session or {}).get("ended_at") or (evaluable_session or {}).get("started_at"))
    age_hours = round((_now() - ended).total_seconds() / 3600.0, 1) if ended else None
    stale = bool(age_hours is None or age_hours > stale_hours)

    severity = "pass"
    reason = issue or "ok"
    if issue == "total_tracked_zero" and _looks_like_incremental_noop(raw_session):
        reason = "incremental_no_new_data"
        severity = "info" if not stale else "warn"
    elif issue:
        severity = "warn"
    if stale:
        severity = "warn"
        reason = f"{reason};latest_evaluable_stale"

    return {
        "issue": issue,
        "reason": reason,
        "severity": severity,
        "latest_evaluable_age_hours": age_hours,
        "stale_hours": stale_hours,
        "latest_evaluable_stale": stale,
    }


def _jackal_raw_issue(session: dict[str, Any] | None) -> str | None:
    if not isinstance(session, dict):
        return "missing_session"
    if session.get("status") != "completed":
        return f"status_{session.get('status') or 'missing'}"
    summary = session.get("summary", {})
    if not isinstance(summary, dict):
        return "missing_summary"
    try:
        total_tracked = float(summary.get("total_tracked") or 0)
    except Exception:
        return "invalid_total_tracked"
    if total_tracked <= 0:
        return "total_tracked_zero"
    return None


def _looks_like_incremental_noop(session: dict[str, Any] | None) -> bool:
    summary = (session or {}).get("summary", {})
    if not isinstance(summary, dict):
        return False
    if summary.get("skip_reason") in {"skipped_no_new_data", "incremental_no_new_data"}:
        return True
    return (
        summary.get("selection_mode") == "incremental"
        and int(summary.get("backtest_days") or 0) == 0
        and int(summary.get("materialized_candidates") or 0) == 0
        and int(summary.get("materialized_outcomes") or 0) == 0
    )
