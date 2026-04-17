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


def _find_latest_orca_sessions() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for label in ("walk_forward", "backtest"):
        sessions = list_backtest_sessions("orca", label=label, limit=2)
        if sessions:
            latest = sessions[0]
            previous = sessions[1] if len(sessions) > 1 else None
            return latest, previous
    return None, None


def _find_latest_jackal_sessions() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    sessions = list_backtest_sessions("jackal", label="backtest", limit=2)
    if not sessions:
        return None, None
    return sessions[0], (sessions[1] if len(sessions) > 1 else None)


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
    signal_swing = list_jackal_accuracy_projection(family="signal", scope="swing", limit=200)
    signal_d1 = list_jackal_accuracy_projection(family="signal", scope="d1", limit=200)
    ticker_overall = list_jackal_accuracy_projection(family="ticker", scope="overall", limit=200)
    regime_overall = list_jackal_accuracy_projection(family="regime", scope="overall", limit=200)
    devil_overall = list_jackal_accuracy_projection(family="devil", scope="overall", limit=50)
    rec_regime = list_jackal_accuracy_projection(family="recommendation", scope="regime", limit=200)
    rec_inflow = list_jackal_accuracy_projection(family="recommendation", scope="inflow", limit=200)

    snapshot = {
        "meta": {
            "minimum_sample": min_total,
            "limit": limit,
            "backfill_rows": backfill_rows,
            "available_rows": {
                "signal_swing": len(signal_swing),
                "signal_d1": len(signal_d1),
                "ticker": len(ticker_overall),
                "regime": len(regime_overall),
                "devil": len(devil_overall),
                "recommendation_regime": len(rec_regime),
                "recommendation_inflow": len(rec_inflow),
            },
        },
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
    accuracy_view = _build_accuracy_snapshot()

    warnings: list[str] = []
    if not orca_latest:
        warnings.append(f"No completed {ORCA_NAME} research session found.")
    if not jackal_latest:
        warnings.append(f"No completed {JACKAL_NAME} research session found.")
    if orca_latest and jackal_latest and linked_orca_session_id and linked_orca_session_id != orca_latest["session_id"]:
        warnings.append(
            f"Latest {JACKAL_NAME} backtest is linked to an older {ORCA_NAME} research session, not the latest one."
        )
    if shadow_roll_10["batch_count"] == 0:
        warnings.append(f"No {JACKAL_NAME} shadow batch history recorded yet.")
    if not accuracy_view["signal_swing_leaders"]:
        warnings.append(f"No SQL-projected {JACKAL_NAME} swing signal accuracy snapshot with enough samples yet.")
    if not accuracy_view["ticker_laggards"]:
        warnings.append(f"No SQL-projected {JACKAL_NAME} ticker accuracy snapshot with enough samples yet.")
    if not accuracy_view["recommendation_regime_leaders"]:
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
        "orca": orca_section,
        "jackal_backtest": {
            "latest": jackal_latest,
            "previous": jackal_prev,
            "summary": jackal_summary,
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
        },
        "jackal_accuracy_view": accuracy_view,
        "warnings": warnings,
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    orca = report["orca"]
    jackal = report["jackal_backtest"]
    shadow = report["jackal_shadow"]
    accuracy_view = report.get("jackal_accuracy_view", {})
    warnings = report["warnings"]

    orca_summary = orca.get("summary", {})
    jackal_summary = jackal.get("summary", {})
    phase_summary = orca.get("phase_summary", {})
    latest_shadow = shadow.get("latest_batch") or {}
    rolling_10 = shadow.get("rolling_10") or {}
    accuracy_meta = accuracy_view.get("meta", {})

    lines = [
        f"# {ORCA_NAME} vs {JACKAL_NAME} Research Comparison",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- State DB: `{report['state_db']}`",
        "",
        "## Snapshot",
        "",
        "| Area | Metric | Latest | Delta |",
        "| --- | --- | ---: | ---: |",
        f"| {ORCA_NAME} | Final accuracy | {_fmt_value(orca_summary.get('final_accuracy'), '%')} | {_fmt_delta(orca['deltas'].get('final_accuracy'))} |",
        f"| {ORCA_NAME} | Judged count | {_fmt_value(orca_summary.get('judged_count'))} | {_fmt_delta(orca['deltas'].get('judged_count'), '')} |",
        f"| {ORCA_NAME} | Lesson count | {_fmt_value(orca_summary.get('lesson_count'))} | {_fmt_delta(orca['deltas'].get('lesson_count'), '')} |",
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
        f"- Session: `{(jackal.get('latest') or {}).get('session_id', 'n/a')}`",
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
        "",
        f"## {JACKAL_NAME} Accuracy View",
        "",
        f"- Projection source: `jackal_accuracy_current`",
        f"- Minimum sample filter: `{accuracy_meta.get('minimum_sample', 'n/a')}`",
        f"- Backfilled latest snapshot rows this run: `{accuracy_meta.get('backfill_rows', 0)}`",
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

