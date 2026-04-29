"""JACKAL accuracy projection diagnostics and backfill helpers."""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from typing import Any

from . import state


def load_latest_jackal_weight_snapshot_metadata() -> dict[str, Any] | None:
    state.init_state_db()
    with state._connect_jackal() as conn:
        row = conn.execute(
            """
            SELECT snapshot_id, source, captured_at, weights_json
              FROM jackal_weight_snapshots
             ORDER BY captured_at DESC
             LIMIT 1
            """
        ).fetchone()
    if not row:
        return None
    weights = None
    if row["weights_json"]:
        try:
            decoded = json.loads(row["weights_json"])
            weights = decoded if isinstance(decoded, dict) else None
        except Exception:
            weights = None
    return {
        "snapshot_id": row["snapshot_id"],
        "source": row["source"],
        "captured_at": row["captured_at"],
        "weights": weights,
        "has_weights": bool(weights),
    }


def _decode_backtest_session_row(row: sqlite3.Row) -> dict[str, Any]:
    def _decode(value: Any) -> Any:
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    return {
        "session_id": row["session_id"],
        "system": row["system"],
        "label": row["label"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "status": row["status"],
        "config": _decode(row["config_json"]),
        "summary": _decode(row["summary_json"]),
    }


def _jackal_backtest_evaluation_issue(session: dict[str, Any] | None) -> str | None:
    if not isinstance(session, dict):
        return "missing_session"
    if session.get("status") != "completed":
        return f"status_{session.get('status') or 'missing'}"
    summary = session.get("summary", {})
    if not isinstance(summary, dict):
        return "missing_summary"
    if summary.get("evaluable") is False:
        return str(summary.get("skip_reason") or "marked_not_evaluable")
    try:
        total_tracked = float(summary.get("total_tracked") or 0)
    except (TypeError, ValueError):
        return "invalid_total_tracked"
    if total_tracked <= 0:
        return "total_tracked_zero"
    if summary.get("swing_accuracy") is None:
        return "missing_swing_accuracy"
    if summary.get("d1_accuracy") is None:
        return "missing_d1_accuracy"
    return None


def find_latest_evaluable_jackal_backtest_session(
    *,
    session_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any] | None:
    state.init_state_db()
    systems = state._candidate_systems("jackal")
    query = """
        SELECT session_id, system, label, started_at, ended_at, status, config_json, summary_json
          FROM backtest_sessions
         WHERE system IN ({system_placeholders})
           AND label = 'backtest'
    """.format(system_placeholders=", ".join("?" for _ in systems))
    params: list[Any] = [*systems]
    if session_id:
        query += " AND session_id = ?"
        params.append(session_id)
    query += " ORDER BY COALESCE(ended_at, started_at) DESC, started_at DESC LIMIT ?"
    params.append(limit)

    with state._connect_orca() as conn:
        rows = conn.execute(query, params).fetchall()

    for row in rows:
        session = _decode_backtest_session_row(row)
        if _jackal_backtest_evaluation_issue(session) is None:
            return session
    return None


def _estimated_correct(total: Any, accuracy: Any) -> float | None:
    total_num = state._metric_number(total)
    accuracy_num = state._metric_number(accuracy)
    if total_num is None or accuracy_num is None:
        return None
    return round(total_num * accuracy_num / 100.0, 3)


def _sum_metric(bucket: Any, key: str) -> float | None:
    if not isinstance(bucket, dict):
        return None
    total = 0.0
    found = False
    for metrics in bucket.values():
        if not isinstance(metrics, dict):
            continue
        value = state._metric_number(metrics.get(key))
        if value is None:
            continue
        total += value
        found = True
    return round(total, 3) if found else None


def _normalize_backtest_accuracy_bucket(
    bucket: Any,
    *,
    source_session_id: str,
    generated_at: str,
) -> dict[str, Any]:
    if not isinstance(bucket, dict):
        return {}
    normalized: dict[str, Any] = {}
    for entity_key, metrics in bucket.items():
        if not isinstance(metrics, dict):
            continue
        payload = deepcopy(metrics)
        if "correct" not in payload and "swing_correct" in payload:
            payload["correct"] = payload.get("swing_correct")
        if "accuracy" not in payload and "swing_accuracy" in payload:
            payload["accuracy"] = payload.get("swing_accuracy")
        payload["sample_count"] = payload.get("total")
        payload["metric"] = payload.get("metric") or "swing_accuracy"
        payload["source_session_id"] = source_session_id
        payload["generated_at"] = generated_at
        normalized[str(entity_key)] = payload
    return normalized


def build_jackal_accuracy_weights_from_backtest_session(
    session: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or state._now_iso()
    summary = session.get("summary", {}) if isinstance(session, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    source_session_id = str(session.get("session_id") or "")
    total_tracked = summary.get("total_tracked")
    swing_accuracy = summary.get("swing_accuracy")
    d1_accuracy = summary.get("d1_accuracy")
    regime_accuracy = summary.get("regime_accuracy", {})
    ticker_accuracy = summary.get("ticker_accuracy", {})

    swing_correct = _sum_metric(regime_accuracy, "swing_correct")
    if swing_correct is None:
        swing_correct = _estimated_correct(total_tracked, swing_accuracy)
    d1_correct = _estimated_correct(total_tracked, d1_accuracy)

    source_payload = {
        "source_type": "jackal_backtest_summary",
        "source_session_id": source_session_id,
        "source_started_at": session.get("started_at"),
        "source_ended_at": session.get("ended_at"),
        "source_orca_session_id": (summary.get("source") or {}).get("orca_session_id")
        if isinstance(summary.get("source"), dict)
        else None,
        "generated_at": generated_at,
    }

    return {
        "system_accuracy": {
            "swing": {
                **source_payload,
                "entity_key": "jackal_backtest",
                "metric": "swing_accuracy",
                "sample_count": total_tracked,
                "total": total_tracked,
                "correct": swing_correct,
                "accuracy": swing_accuracy,
            },
            "d1": {
                **source_payload,
                "entity_key": "jackal_backtest",
                "metric": "d1_accuracy",
                "sample_count": total_tracked,
                "total": total_tracked,
                "correct": d1_correct,
                "accuracy": d1_accuracy,
                "correct_estimated": True,
            },
        },
        "regime_accuracy": _normalize_backtest_accuracy_bucket(
            regime_accuracy,
            source_session_id=source_session_id,
            generated_at=generated_at,
        ),
        "ticker_accuracy": _normalize_backtest_accuracy_bucket(
            ticker_accuracy,
            source_session_id=source_session_id,
            generated_at=generated_at,
        ),
        "backfill_source": {
            **source_payload,
            "total_tracked": total_tracked,
            "swing_accuracy": swing_accuracy,
            "d1_accuracy": d1_accuracy,
        },
    }


def backfill_jackal_accuracy_projection_from_backtest(
    *,
    session_id: str | None = None,
    source: str = "backfill_jackal_backtest",
    dry_run: bool = False,
) -> dict[str, Any]:
    session = find_latest_evaluable_jackal_backtest_session(session_id=session_id)
    if not session:
        return {
            "status": "skipped",
            "reason": "missing_evaluable_backtest_session",
            "source_session_id": session_id,
            "snapshot_id": None,
            "projection_rows": 0,
            "dry_run": dry_run,
        }

    generated_at = state._now_iso()
    weights = build_jackal_accuracy_weights_from_backtest_session(session, generated_at=generated_at)
    source_session_id = str(session.get("session_id") or "")
    snapshot_source = f"{source}:{source_session_id}"
    planned_rows = len(
        state._build_jackal_accuracy_projection_rows(
            "dry_run_snapshot",
            weights,
            source=snapshot_source,
            captured_at=generated_at,
        )
    )
    if dry_run:
        return {
            "status": "planned",
            "reason": "dry_run",
            "source_session_id": source_session_id,
            "snapshot_id": None,
            "projection_rows": planned_rows,
            "dry_run": True,
        }

    snapshot_id = state.record_jackal_weight_snapshot(weights, source=snapshot_source)
    with state._connect_jackal() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM jackal_accuracy_projection WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
    projection_rows = int(row["count"] if row else 0)
    projection_state = describe_jackal_accuracy_projection_state()
    return {
        "status": "backfilled" if projection_rows else "empty",
        "reason": "ok" if projection_rows else "no_projection_rows_generated",
        "source_session_id": source_session_id,
        "snapshot_id": snapshot_id,
        "projection_rows": projection_rows,
        "current_rows": projection_state.get("current_rows"),
        "max_sample_count": projection_state.get("max_sample_count"),
        "dry_run": False,
    }


def describe_jackal_accuracy_projection_state() -> dict[str, Any]:
    state.init_state_db()
    with state._connect_jackal() as conn:
        snapshot_row = conn.execute("SELECT COUNT(*) AS count FROM jackal_weight_snapshots").fetchone()
        projection_row = conn.execute("SELECT COUNT(*) AS count FROM jackal_accuracy_projection").fetchone()
        current_row = conn.execute("SELECT COUNT(*) AS count FROM jackal_accuracy_current").fetchone()
        sample_row = conn.execute("SELECT MAX(total) AS max_total FROM jackal_accuracy_current").fetchone()
        latest_row = conn.execute(
            """
            SELECT snapshot_id, source, captured_at, updated_at
              FROM jackal_accuracy_projection
             ORDER BY captured_at DESC, updated_at DESC
             LIMIT 1
            """
        ).fetchone()
        family_rows = conn.execute(
            """
            SELECT family, scope, COUNT(*) AS row_count,
                   MAX(total) AS max_sample_count,
                   MAX(captured_at) AS latest_captured_at
              FROM jackal_accuracy_current
             GROUP BY family, scope
             ORDER BY family, scope
            """
        ).fetchall()

    snapshot_count = int(snapshot_row["count"] if snapshot_row else 0)
    projection_count = int(projection_row["count"] if projection_row else 0)
    current_count = int(current_row["count"] if current_row else 0)
    max_sample_count = state._metric_number(sample_row["max_total"] if sample_row else None)
    missing_reasons: list[str] = []
    if snapshot_count == 0:
        missing_reasons.append("missing_weight_snapshots")
    if projection_count == 0:
        missing_reasons.append("missing_projection_rows")
    if current_count == 0:
        missing_reasons.append("missing_accuracy_current")
    if max_sample_count is None or max_sample_count <= 0:
        missing_reasons.append("missing_projection_sample")

    latest_projection = None
    if latest_row:
        latest_projection = {
            "snapshot_id": latest_row["snapshot_id"],
            "source": latest_row["source"],
            "captured_at": latest_row["captured_at"],
            "generated_at": latest_row["updated_at"],
        }

    return {
        "snapshot_rows": snapshot_count,
        "projection_rows": projection_count,
        "current_rows": current_count,
        "max_sample_count": max_sample_count,
        "latest_projection": latest_projection,
        "latest_source": latest_projection.get("source") if latest_projection else None,
        "latest_captured_at": latest_projection.get("captured_at") if latest_projection else None,
        "latest_generated_at": latest_projection.get("generated_at") if latest_projection else None,
        "missing_reasons": missing_reasons,
        "by_family_scope": [
            {
                "family": row["family"],
                "scope": row["scope"],
                "row_count": int(row["row_count"] or 0),
                "max_sample_count": state._metric_number(row["max_sample_count"]),
                "latest_captured_at": row["latest_captured_at"],
            }
            for row in family_rows
        ],
    }
