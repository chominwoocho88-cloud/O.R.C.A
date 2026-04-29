"""
Generate a cross-system research comparison report from the SQLite state spine.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .brand import JACKAL_NAME, ORCA_NAME
from .dual_db_snapshot import collect_dual_db_state
from .jackal_accuracy_projection import describe_jackal_accuracy_projection_state
from .jackal_quality import (
    classify_latest_raw_jackal_session,
    describe_jackal_recommendation_accuracy_state,
    describe_jackal_shadow_state,
)
from .market_fetch import get_provider_quality_summary
from .paths import REPORTS_DIR, STATE_DB_FILE, atomic_write_json, atomic_write_text
from .state import (
    list_backtest_days,
    list_backtest_sessions,
    list_jackal_accuracy_projection,
    list_jackal_shadow_batches,
    rebuild_latest_jackal_accuracy_projection,
)

KST = timezone(timedelta(hours=9))
DEFAULT_MD = REPORTS_DIR / "orca_research_comparison.md"
DEFAULT_JSON = REPORTS_DIR / "orca_research_comparison.json"
JACKAL_RESEARCH_STATUSES = ("completed", "skipped_no_new_data", "skipped")


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _safe_delta(current: float | int | None, previous: float | int | None) -> float | None:
    if current is None or previous is None:
        return None
    return round(float(current) - float(previous), 1)


def _fmt_delta(delta: float | None, suffix: str = "pp") -> str:
    if delta is None:
        return "n/a"
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f}{suffix}"


def _fmt_value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _provider_quality_from_orca_summary(summary: dict[str, Any]) -> dict[str, Any]:
    dynamic = summary.get("dynamic_fetch", {}) if isinstance(summary, dict) else {}
    if not isinstance(dynamic, dict):
        dynamic = {}
    stats = dynamic.get("fetch_stats", {}) if isinstance(dynamic.get("fetch_stats"), dict) else {}
    failures = int(stats.get("failed") or 0)
    total = int(stats.get("total") or 0)
    failure_rate = round(failures / total * 100, 1) if total else None
    warning = str(dynamic.get("warning") or "")
    status = "no_history"
    if total:
        status = "degraded" if failures or dynamic.get("empty_extension_warning") or warning else "ok"
    return {
        "status": status,
        "source": "latest_orca_backtest.dynamic_fetch" if dynamic else "missing",
        "fetch_stats": stats,
        "fetch_sources": dynamic.get("fetch_sources", {}),
        "failure_rate": failure_rate,
        "warning": warning,
        "data_source": summary.get("data_source") or dynamic.get("data_source"),
        "effective_trading_days": summary.get("effective_trading_days") or dynamic.get("effective_trading_days"),
    }


def _sanitize_orca_summary(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    clean = dict(summary)
    lesson_count = clean.get("lesson_count")
    if lesson_count is None:
        lesson_count = clean.get("_lessons_applied")
    if lesson_count is not None:
        clean["lesson_count"] = lesson_count
    clean.pop("generated_lesson_count", None)
    return clean


def _sanitize_orca_session(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(session, dict):
        return None
    clean = dict(session)
    clean["summary"] = _sanitize_orca_summary(clean.get("summary"))
    return clean


def _find_latest_orca_sessions() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for label in ("walk_forward", "backtest"):
        sessions = list_backtest_sessions("orca", label=label, limit=2)
        if sessions:
            latest = sessions[0]
            previous = sessions[1] if len(sessions) > 1 else None
            return latest, previous
    return None, None


def _find_latest_jackal_sessions() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    sessions = [
        session
        for session in _list_jackal_backtest_sessions(limit=20)
        if _jackal_session_evaluation_issue(session) is None
    ]
    if not sessions:
        return None, None
    return sessions[0], (sessions[1] if len(sessions) > 1 else None)


def _session_sort_key(session: dict[str, Any]) -> str:
    return str(session.get("ended_at") or session.get("started_at") or "")


def _list_jackal_backtest_sessions(limit: int = 10) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for status in JACKAL_RESEARCH_STATUSES:
        for session in list_backtest_sessions("jackal", label="backtest", status=status, limit=limit):
            session_id = str(session.get("session_id") or "")
            if session_id and session_id in seen:
                continue
            if session_id:
                seen.add(session_id)
            sessions.append(session)
    sessions.sort(key=_session_sort_key, reverse=True)
    return sessions[:limit]


def _find_latest_raw_jackal_session() -> dict[str, Any] | None:
    sessions = _list_jackal_backtest_sessions(limit=1)
    return sessions[0] if sessions else None


def _jackal_session_evaluation_issue(session: dict[str, Any] | None) -> str | None:
    if not isinstance(session, dict):
        return "missing_session"
    status = session.get("status")
    if status != "completed":
        return f"status_{status or 'missing'}"
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


def _phase_summary(session_id: str) -> dict[str, Any]:
    days = list_backtest_days(session_id)
    phase_counts: dict[str, int] = {}
    analysis_dates = []
    for row in days:
        phase = row.get("phase_label") or "default"
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        if row.get("analysis_date"):
            analysis_dates.append(row["analysis_date"])

    return {
        "day_count": len(days),
        "phase_counts": phase_counts,
        "date_range": {
            "start": min(analysis_dates) if analysis_dates else None,
            "end": max(analysis_dates) if analysis_dates else None,
        },
    }


def _rolling_shadow_stats(batches: list[dict[str, Any]], size: int) -> dict[str, Any]:
    window = batches[:size]
    prev = batches[size:size * 2]

    def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = sum(item["total"] for item in rows)
        worked = sum(item["worked"] for item in rows)
        rate = round(worked / total * 100, 1) if total > 0 else 0.0
        return {
            "batch_count": len(rows),
            "total": total,
            "worked": worked,
            "rate": rate,
        }

    current = _aggregate(window)
    previous = _aggregate(prev)
    current["delta_vs_prev"] = _safe_delta(current["rate"], previous["rate"] if previous["batch_count"] else None)
    return current


def _rank_accuracy_rows(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    min_total: int,
    descending: bool,
) -> list[dict[str, Any]]:
    filtered = [
        row for row in rows
        if row.get("accuracy") is not None and (row.get("total") or 0) >= min_total
    ]
    filtered.sort(
        key=lambda row: (
            float(row.get("accuracy") or 0.0),
            float(row.get("total") or 0.0),
            str(row.get("entity_key", "")),
        ),
        reverse=descending,
    )
    return [
        {
            "entity_key": row.get("entity_key"),
            "accuracy": row.get("accuracy"),
            "total": row.get("total"),
            "source": row.get("source"),
            "captured_at": row.get("captured_at"),
            "metrics": row.get("metrics", {}),
        }
        for row in filtered[:limit]
    ]


def _build_accuracy_snapshot(min_total: int = 3, limit: int = 5) -> dict[str, Any]:
    backfill_rows = rebuild_latest_jackal_accuracy_projection()
    projection_state = describe_jackal_accuracy_projection_state()
    system_swing = list_jackal_accuracy_projection(family="system", scope="swing", limit=20)
    system_d1 = list_jackal_accuracy_projection(family="system", scope="d1", limit=20)
    signal_swing = list_jackal_accuracy_projection(family="signal", scope="swing", limit=200)
    signal_d1 = list_jackal_accuracy_projection(family="signal", scope="d1", limit=200)
    ticker_overall = list_jackal_accuracy_projection(family="ticker", scope="overall", limit=200)
    regime_overall = list_jackal_accuracy_projection(family="regime", scope="overall", limit=200)
    devil_overall = list_jackal_accuracy_projection(family="devil", scope="overall", limit=50)
    rec_regime = list_jackal_accuracy_projection(family="recommendation", scope="regime", limit=200)
    rec_inflow = list_jackal_accuracy_projection(family="recommendation", scope="inflow", limit=200)
    available_rows = {
        "system_swing": len(system_swing),
        "system_d1": len(system_d1),
        "signal_swing": len(signal_swing),
        "signal_d1": len(signal_d1),
        "ticker": len(ticker_overall),
        "regime": len(regime_overall),
        "devil": len(devil_overall),
        "recommendation_regime": len(rec_regime),
        "recommendation_inflow": len(rec_inflow),
    }

    snapshot = {
        "meta": {
            "minimum_sample": min_total,
            "limit": limit,
            "backfill_rows": backfill_rows,
            "available_rows": available_rows,
            "total_current_rows": projection_state.get("current_rows", sum(available_rows.values())),
            "total_projection_rows": projection_state.get("projection_rows", 0),
            "snapshot_rows": projection_state.get("snapshot_rows", 0),
            "max_sample_count": projection_state.get("max_sample_count"),
            "latest_projection": projection_state.get("latest_projection"),
            "latest_source": projection_state.get("latest_source"),
            "latest_captured_at": projection_state.get("latest_captured_at"),
            "latest_generated_at": projection_state.get("latest_generated_at"),
            "missing_reasons": projection_state.get("missing_reasons", []),
            "by_family_scope": projection_state.get("by_family_scope", []),
        },
        "system_swing_accuracy": _rank_accuracy_rows(
            system_swing, limit=limit, min_total=min_total, descending=True
        ),
        "system_d1_accuracy": _rank_accuracy_rows(
            system_d1, limit=limit, min_total=min_total, descending=True
        ),
        "signal_swing_leaders": _rank_accuracy_rows(
            signal_swing, limit=limit, min_total=min_total, descending=True
        ),
        "signal_d1_leaders": _rank_accuracy_rows(
            signal_d1, limit=limit, min_total=min_total, descending=True
        ),
        "ticker_laggards": _rank_accuracy_rows(
            ticker_overall, limit=limit, min_total=min_total, descending=False
        ),
        "regime_laggards": _rank_accuracy_rows(
            regime_overall, limit=limit, min_total=min_total, descending=False
        ),
        "devil_verdicts": _rank_accuracy_rows(
            devil_overall, limit=limit, min_total=min_total, descending=True
        ),
        "recommendation_regime_leaders": _rank_accuracy_rows(
            rec_regime, limit=limit, min_total=min_total, descending=True
        ),
        "recommendation_regime_laggards": _rank_accuracy_rows(
            rec_regime, limit=limit, min_total=min_total, descending=False
        ),
        "recommendation_inflow_leaders": _rank_accuracy_rows(
            rec_inflow, limit=limit, min_total=min_total, descending=True
        ),
    }
    return snapshot


def _fmt_accuracy_entries(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "n/a"
    return " | ".join(
        f"{entry['entity_key']} {_fmt_value(entry.get('accuracy'), '%')} (n={_fmt_value(entry.get('total'))})"
        for entry in entries
    )


def _write_report_outputs(markdown_path: Path, json_path: Path, report: dict[str, Any]) -> None:
    markdown = render_markdown(report)
    atomic_write_json(json_path, report)
    atomic_write_text(markdown_path, markdown)


def build_report() -> dict[str, Any]:
    generated_at = _now_iso()
    orca_latest, orca_prev = _find_latest_orca_sessions()
    orca_latest = _sanitize_orca_session(orca_latest)
    orca_prev = _sanitize_orca_session(orca_prev)
    jackal_latest_raw = _find_latest_raw_jackal_session()
    jackal_latest, jackal_prev = _find_latest_jackal_sessions()
    shadow_batches = list_jackal_shadow_batches(20)

    orca_summary = orca_latest["summary"] if orca_latest else {}
    orca_prev_summary = orca_prev["summary"] if orca_prev else {}
    orca_phases = _phase_summary(orca_latest["session_id"]) if orca_latest else {}

    jackal_summary = jackal_latest["summary"] if jackal_latest else {}
    jackal_prev_summary = jackal_prev["summary"] if jackal_prev else {}

    source_info = jackal_summary.get("source", {}) if isinstance(jackal_summary, dict) else {}
    linked_orca_session_id = source_info.get("orca_session_id") or source_info.get("session_id")

    shadow_latest = shadow_batches[0] if shadow_batches else None
    shadow_roll_10 = _rolling_shadow_stats(shadow_batches, 10)
    shadow_state = describe_jackal_shadow_state()
    recommendation_state = describe_jackal_recommendation_accuracy_state()
    raw_issue_classification = classify_latest_raw_jackal_session(jackal_latest_raw, jackal_latest)
    provider_quality = {
        "latest_backtest": _provider_quality_from_orca_summary(orca_summary),
        "session": get_provider_quality_summary(),
    }
    accuracy_view = _build_accuracy_snapshot()

    warnings: list[str] = []
    notes: list[str] = []
    if not orca_latest:
        warnings.append(f"No completed {ORCA_NAME} research session found.")
    raw_jackal_issue = _jackal_session_evaluation_issue(jackal_latest_raw)
    raw_jackal_session_id = (jackal_latest_raw or {}).get("session_id")
    representative_jackal_session_id = (jackal_latest or {}).get("session_id")
    if not jackal_latest:
        warnings.append(f"No completed evaluable {JACKAL_NAME} research session found.")
    if jackal_latest_raw and raw_jackal_issue and raw_jackal_session_id != representative_jackal_session_id:
        raw_message = (
            f"Latest raw {JACKAL_NAME} backtest is not used as representative accuracy "
            f"because it is not evaluable: {raw_issue_classification.get('reason') or raw_jackal_issue}."
        )
        if raw_issue_classification.get("severity") == "info":
            notes.append(raw_message)
        else:
            warnings.append(raw_message)
    if orca_latest and jackal_latest and linked_orca_session_id and linked_orca_session_id != orca_latest["session_id"]:
        warnings.append(
            f"Latest {JACKAL_NAME} backtest is linked to an older {ORCA_NAME} research session, not the latest one."
        )
    for reason in shadow_state.get("missing_reasons", []):
        warnings.append(f"{JACKAL_NAME} shadow state is incomplete: {reason}.")
    for reason in recommendation_state.get("missing_reasons", []):
        warnings.append(f"{JACKAL_NAME} recommendation accuracy state is incomplete: {reason}.")
    if provider_quality["latest_backtest"].get("status") == "degraded":
        warnings.append(f"Market provider quality is degraded: {provider_quality['latest_backtest'].get('warning') or 'provider failures recorded'}.")
    accuracy_meta = accuracy_view.get("meta", {})
    for reason in accuracy_meta.get("missing_reasons", []) if isinstance(accuracy_meta, dict) else []:
        warnings.append(f"{JACKAL_NAME} accuracy projection state is incomplete: {reason}.")
    if not accuracy_view.get("system_swing_accuracy") and not accuracy_view.get("signal_swing_leaders"):
        warnings.append(f"No SQL-projected {JACKAL_NAME} swing accuracy snapshot with enough samples yet.")
    if not accuracy_view.get("ticker_laggards"):
        warnings.append(f"No SQL-projected {JACKAL_NAME} ticker accuracy snapshot with enough samples yet.")
    if not accuracy_view.get("recommendation_regime_leaders"):
        warnings.append(f"No SQL-projected {JACKAL_NAME} recommendation regime accuracy snapshot with enough samples yet.")

    orca_section = {
        "latest": orca_latest,
        "previous": orca_prev,
        "summary": orca_summary,
        "phase_summary": orca_phases,
        "deltas": {
            "final_accuracy": _safe_delta(
                orca_summary.get("final_accuracy"),
                orca_prev_summary.get("final_accuracy"),
            ),
            "lesson_count": _safe_delta(
                orca_summary.get("lesson_count"),
                orca_prev_summary.get("lesson_count"),
            ),
            "judged_count": _safe_delta(
                orca_summary.get("judged_count"),
                orca_prev_summary.get("judged_count"),
            ),
        },
    }
    report = {
        "generated_at": generated_at,
        "state_db": str(STATE_DB_FILE),
        "dual_db_state": collect_dual_db_state(),
        "orca": orca_section,
        "jackal_backtest": {
            "latest": jackal_latest,
            "latest_evaluable": jackal_latest,
            "latest_raw": jackal_latest_raw,
            "previous": jackal_prev,
            "summary": jackal_summary,
            "latest_raw_evaluation_issue": raw_jackal_issue,
            "latest_raw_issue_classification": raw_issue_classification,
            "latest_evaluable_age_hours": raw_issue_classification.get("latest_evaluable_age_hours"),
            "latest_evaluable_stale": raw_issue_classification.get("latest_evaluable_stale"),
            "using_latest_raw_as_representative": bool(
                raw_jackal_session_id
                and representative_jackal_session_id
                and raw_jackal_session_id == representative_jackal_session_id
            ),
            "source_orca_session_id": linked_orca_session_id,
            "linked_to_latest_orca": bool(
                orca_latest and linked_orca_session_id and linked_orca_session_id == orca_latest["session_id"]
            ),
            "deltas": {
                "swing_accuracy": _safe_delta(
                    jackal_summary.get("swing_accuracy"),
                    jackal_prev_summary.get("swing_accuracy"),
                ),
                "d1_accuracy": _safe_delta(
                    jackal_summary.get("d1_accuracy"),
                    jackal_prev_summary.get("d1_accuracy"),
                ),
                "tracked": _safe_delta(
                    jackal_summary.get("total_tracked"),
                    jackal_prev_summary.get("total_tracked"),
                ),
            },
        },
        "jackal_shadow": {
            "latest_batch": shadow_latest,
            "rolling_10": shadow_roll_10,
            "batch_count_available": len(shadow_batches),
            "state": shadow_state,
        },
        "jackal_recommendation_accuracy": recommendation_state,
        "jackal_accuracy_view": accuracy_view,
        "market_provider_quality": provider_quality,
        "warnings": warnings,
        "notes": notes,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    orca = report["orca"]
    jackal = report["jackal_backtest"]
    shadow = report["jackal_shadow"]
    recommendation = report.get("jackal_recommendation_accuracy", {})
    provider_quality = report.get("market_provider_quality", {})
    accuracy_view = report.get("jackal_accuracy_view", {})
    dual_db_state = report.get("dual_db_state", {})
    warnings = report["warnings"]

    orca_summary = orca.get("summary", {})
    jackal_summary = jackal.get("summary", {})
    phase_summary = orca.get("phase_summary", {})
    latest_shadow = shadow.get("latest_batch") or {}
    rolling_10 = shadow.get("rolling_10") or {}
    shadow_state = shadow.get("state", {})
    provider_latest = provider_quality.get("latest_backtest", {})
    provider_session = provider_quality.get("session", {})
    accuracy_meta = accuracy_view.get("meta", {})
    orca_db = dual_db_state.get("orca_state_db", {})
    jackal_db = dual_db_state.get("jackal_state_db", {})
    jackal_tables = jackal_db.get("tables") or {}

    lines = [
        f"# {ORCA_NAME} vs {JACKAL_NAME} Research Comparison",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- State DB: `{report['state_db']}`",
        f"- ORCA DB snapshot: `{orca_db.get('path', 'n/a')}` "
        f"(exists={orca_db.get('exists')}, size={orca_db.get('size_bytes')}, mtime={orca_db.get('mtime_iso')})",
        f"- JACKAL DB snapshot: `{jackal_db.get('path', 'n/a')}` "
        f"(exists={jackal_db.get('exists')}, size={jackal_db.get('size_bytes')}, mtime={jackal_db.get('mtime_iso')})",
        f"- JACKAL table rows: `{json.dumps(jackal_tables, ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Snapshot",
        "",
        "| Area | Metric | Latest | Delta |",
        "| --- | --- | ---: | ---: |",
        f"| {ORCA_NAME} | Final accuracy | {_fmt_value(orca_summary.get('final_accuracy'), '%')} | {_fmt_delta(orca['deltas'].get('final_accuracy'))} |",
        f"| {ORCA_NAME} | Judged count | {_fmt_value(orca_summary.get('judged_count'))} | {_fmt_delta(orca['deltas'].get('judged_count'), '')} |",
        f"| {ORCA_NAME} | Applied lessons | {_fmt_value(orca_summary.get('lesson_count'))} | {_fmt_delta(orca['deltas'].get('lesson_count'), '')} |",
        f"| {JACKAL_NAME} | Swing accuracy | {_fmt_value(jackal_summary.get('swing_accuracy'), '%')} | {_fmt_delta(jackal['deltas'].get('swing_accuracy'))} |",
        f"| {JACKAL_NAME} | D1 accuracy | {_fmt_value(jackal_summary.get('d1_accuracy'), '%')} | {_fmt_delta(jackal['deltas'].get('d1_accuracy'))} |",
        f"| {JACKAL_NAME} | Tracked picks | {_fmt_value(jackal_summary.get('total_tracked'))} | {_fmt_delta(jackal['deltas'].get('tracked'), '')} |",
        f"| Shadow | Latest batch rate | {_fmt_value(latest_shadow.get('rate'), '%')} | n/a |",
        f"| Shadow | Rolling 10 rate | {_fmt_value(rolling_10.get('rate'), '%')} | {_fmt_delta(rolling_10.get('delta_vs_prev'))} |",
        "",
        f"## {ORCA_NAME} Research",
        "",
        f"- Session: `{(orca.get('latest') or {}).get('session_id', 'n/a')}`",
        f"- Label: `{(orca.get('latest') or {}).get('label', 'n/a')}`",
        f"- Date range: `{(phase_summary.get('date_range') or {}).get('start', 'n/a')}` -> `{(phase_summary.get('date_range') or {}).get('end', 'n/a')}`",
        f"- Stored day rows: `{phase_summary.get('day_count', 0)}`",
        f"- Phase counts: `{json.dumps(phase_summary.get('phase_counts', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Strong areas: `{json.dumps(orca_summary.get('strong_areas', []), ensure_ascii=False)}`",
        f"- Weak areas: `{json.dumps(orca_summary.get('weak_areas', []), ensure_ascii=False)}`",
        "",
        f"## {JACKAL_NAME} Backtest",
        "",
        f"- Representative evaluable session: `{(jackal.get('latest_evaluable') or {}).get('session_id', 'n/a')}`",
        f"- Latest raw session: `{(jackal.get('latest_raw') or {}).get('session_id', 'n/a')}` "
        f"(status=`{(jackal.get('latest_raw') or {}).get('status', 'n/a')}`, "
        f"issue=`{jackal.get('latest_raw_evaluation_issue') or 'none'}`, "
        f"classification=`{(jackal.get('latest_raw_issue_classification') or {}).get('reason', 'n/a')}`)",
        f"- Latest evaluable age: `{jackal.get('latest_evaluable_age_hours', 'n/a')}` hours "
        f"(stale=`{jackal.get('latest_evaluable_stale')}`)",
        f"- Source {ORCA_NAME} session: `{jackal.get('source_orca_session_id') or 'n/a'}`",
        f"- Linked to latest {ORCA_NAME}: `{jackal.get('linked_to_latest_orca')}`",
        f"- Pipeline: `{jackal_summary.get('pipeline', 'n/a')}`",
        f"- Backtest days: `{jackal_summary.get('backtest_days', 'n/a')}`",
        f"- Funnel totals: `{json.dumps(jackal_summary.get('funnel_totals', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        f"## {JACKAL_NAME} Shadow",
        "",
        f"- Latest batch: `{latest_shadow.get('recorded_at', 'n/a')}`",
        f"- Latest batch outcome: `{latest_shadow.get('worked', 'n/a')}/{latest_shadow.get('total', 'n/a')}`",
        f"- Rolling 10 batches: `{rolling_10.get('worked', 0)}/{rolling_10.get('total', 0)}`",
        f"- Batch count available: `{shadow.get('batch_count_available', 0)}`",
        f"- Shadow signal rows: `{shadow_state.get('signal_rows', 0)}`",
        f"- Shadow missing reasons: `{json.dumps(shadow_state.get('missing_reasons', []), ensure_ascii=False)}`",
        f"- Shadow source path: `{shadow_state.get('source_path', 'n/a')}`",
        f"- Shadow outcome path: `{shadow_state.get('outcome_path', 'n/a')}`",
        "",
        f"## {JACKAL_NAME} Recommendation Accuracy",
        "",
        f"- Recommendation rows: `{recommendation.get('recommendation_rows', 0)}`",
        f"- Checked recommendation rows: `{recommendation.get('checked_rows', 0)}`",
        f"- Recommendation projection/current rows: `{recommendation.get('projection_rows', 0)}` / `{recommendation.get('current_rows', 0)}`",
        f"- Recommendation missing reasons: `{json.dumps(recommendation.get('missing_reasons', []), ensure_ascii=False)}`",
        f"- Recommendation source path: `{recommendation.get('source_path', 'n/a')}`",
        f"- Recommendation outcome path: `{recommendation.get('outcome_path', 'n/a')}`",
        "",
        "## Market Provider Quality",
        "",
        f"- Latest backtest provider status: `{provider_latest.get('status', 'n/a')}`",
        f"- Latest backtest fetch stats: `{json.dumps(provider_latest.get('fetch_stats', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Latest backtest fetch sources: `{json.dumps(provider_latest.get('fetch_sources', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- Current process provider status: `{provider_session.get('status', 'n/a')}`",
        f"- Current process provider stats: `{json.dumps(provider_session.get('stats', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        f"## {JACKAL_NAME} Accuracy View",
        "",
        f"- Projection source: `jackal_accuracy_current`",
        f"- Minimum sample filter: `{accuracy_meta.get('minimum_sample', 'n/a')}`",
        f"- Backfilled latest snapshot rows this run: `{accuracy_meta.get('backfill_rows', 0)}`",
        f"- Current projection rows: `{accuracy_meta.get('total_current_rows', 0)}`",
        f"- Stored projection rows: `{accuracy_meta.get('total_projection_rows', 0)}`",
        f"- Weight snapshots: `{accuracy_meta.get('snapshot_rows', 0)}`",
        f"- Latest projection source: `{accuracy_meta.get('latest_source') or 'n/a'}`",
        f"- Latest projection captured/generated: `{accuracy_meta.get('latest_captured_at') or 'n/a'}` / `{accuracy_meta.get('latest_generated_at') or 'n/a'}`",
        f"- Max projection sample count: `{accuracy_meta.get('max_sample_count') or 'n/a'}`",
        f"- Projection missing reasons: `{json.dumps(accuracy_meta.get('missing_reasons', []), ensure_ascii=False)}`",
        f"- System swing accuracy: `{_fmt_accuracy_entries(accuracy_view.get('system_swing_accuracy', []))}`",
        f"- System D1 accuracy: `{_fmt_accuracy_entries(accuracy_view.get('system_d1_accuracy', []))}`",
        f"- Best swing signals: `{_fmt_accuracy_entries(accuracy_view.get('signal_swing_leaders', []))}`",
        f"- Best D1 signals: `{_fmt_accuracy_entries(accuracy_view.get('signal_d1_leaders', []))}`",
        f"- Weakest tickers: `{_fmt_accuracy_entries(accuracy_view.get('ticker_laggards', []))}`",
        f"- Weakest regimes: `{_fmt_accuracy_entries(accuracy_view.get('regime_laggards', []))}`",
        f"- Devil verdict accuracy: `{_fmt_accuracy_entries(accuracy_view.get('devil_verdicts', []))}`",
        f"- Best recommendation regimes: `{_fmt_accuracy_entries(accuracy_view.get('recommendation_regime_leaders', []))}`",
        f"- Weak recommendation regimes: `{_fmt_accuracy_entries(accuracy_view.get('recommendation_regime_laggards', []))}`",
        f"- Best recommendation inflows: `{_fmt_accuracy_entries(accuracy_view.get('recommendation_inflow_leaders', []))}`",
        "",
        "## Watch Items",
        "",
    ]

    if warnings:
        lines.extend([f"- {warning}" for warning in warnings])
    else:
        lines.append("- No structural warnings in the latest research snapshot.")

    notes = report.get("notes", [])
    if notes:
        lines.extend(["", "## Notes", ""])
        lines.extend([f"- {note}" for note in notes])

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Generate {ORCA_NAME}/{JACKAL_NAME} research comparison report.")
    parser.add_argument("--output-md", default=str(DEFAULT_MD))
    parser.add_argument("--output-json", default=str(DEFAULT_JSON))
    args = parser.parse_args()

    report = build_report()
    output_md = Path(args.output_md)
    output_json = Path(args.output_json)

    _write_report_outputs(output_md, output_json, report)

    print(f"Research comparison report saved: {output_md}")
    print(f"Research comparison data saved: {output_json}")


if __name__ == "__main__":
    main()

