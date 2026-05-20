"""Inspect JACKAL operational sample intake and backfill readiness.

This script is read-only. It does not create accuracy rows and does not call
live LLM, paid market APIs, or trading/order paths.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apps.orca import state  # noqa: E402  # noqa: E402
from orca.jackal_accuracy_projection import describe_jackal_accuracy_projection_state  # noqa: E402
from orca.jackal_quality import (  # noqa: E402
    backfill_recommendation_accuracy_projection,
    backfill_shadow_batches_from_resolved_signals,
    describe_jackal_recommendation_accuracy_state,
    describe_jackal_shadow_state,
)

KST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _scalar(conn: Any, query: str, params: tuple[Any, ...] = ()) -> Any:
    row = conn.execute(query, params).fetchone()
    return row[0] if row else None


def _table_summary(
    conn: Any,
    table: str,
    *,
    latest_column: str | None = None,
    source_column: str | None = None,
) -> dict[str, Any]:
    count = int(_scalar(conn, f"SELECT COUNT(*) FROM {table}") or 0)
    summary: dict[str, Any] = {"rows": count, "latest_timestamp": None}
    if latest_column:
        summary["latest_timestamp"] = _scalar(conn, f"SELECT MAX({latest_column}) FROM {table}")
    if source_column and latest_column:
        row = conn.execute(
            f"""
            SELECT {source_column} AS source, {latest_column} AS latest_timestamp
              FROM {table}
             ORDER BY {latest_column} DESC
             LIMIT 1
            """
        ).fetchone()
        summary["latest_source"] = row["source"] if row else None
    return summary


def collect_baseline_fallback_summary(
    *,
    audit_log_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Summarize baseline fallback audit JSONL without failing the smoke check."""
    from apps.jackal.baseline_audit import AUDIT_LOG_PATH

    path = audit_log_path or AUDIT_LOG_PATH
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        current = current.replace(tzinfo=KST)
    current = current.astimezone(KST)
    today = current.date()
    week_ago = today - timedelta(days=7)
    summary: dict[str, Any] = {
        "log_exists": False,
        "total_events": 0,
        "today_events": 0,
        "last_7d_events": 0,
        "by_component": {"hunter": 0, "scanner": 0},
        "by_regime_source": {"memory": 0, "fallback": 0, "none": 0},
        "latest_event": None,
        "parse_error_count": 0,
        "status": "ok",
    }

    if not path.exists():
        return summary

    summary["log_exists"] = True
    latest_ts: datetime | None = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        summary["parse_error_count"] += 1
        summary["status"] = "warn"
        return summary

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            summary["parse_error_count"] += 1
            continue
        if not isinstance(entry, dict):
            summary["parse_error_count"] += 1
            continue

        summary["total_events"] += 1
        component = str(entry.get("component") or "")
        if component:
            component_counts = summary["by_component"]
            component_counts[component] = int(component_counts.get(component, 0)) + 1

        source = str(entry.get("regime_source") or "")
        if source:
            source_counts = summary["by_regime_source"]
            source_counts[source] = int(source_counts.get(source, 0)) + 1

        ts_value = entry.get("ts")
        try:
            event_ts = datetime.fromisoformat(str(ts_value))
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=KST)
            event_ts = event_ts.astimezone(KST)
        except (TypeError, ValueError):
            summary["parse_error_count"] += 1
            continue

        event_date = event_ts.date()
        if event_date == today:
            summary["today_events"] += 1
        if event_date >= week_ago:
            summary["last_7d_events"] += 1
        if latest_ts is None or event_ts > latest_ts:
            latest_ts = event_ts
            summary["latest_event"] = entry

    if summary["parse_error_count"] > 0 or summary["today_events"] > 0 or summary["last_7d_events"] > 0:
        summary["status"] = "warn"
    return summary


def collect_operational_intake() -> dict[str, Any]:
    state.init_state_db()
    shadow_state = describe_jackal_shadow_state()
    recommendation_state = describe_jackal_recommendation_accuracy_state()
    projection_state = describe_jackal_accuracy_projection_state()
    shadow_dry_run = backfill_shadow_batches_from_resolved_signals(dry_run=True)
    recommendation_dry_run = backfill_recommendation_accuracy_projection(dry_run=True)

    with state._connect_jackal() as conn:
        tables = {
            "jackal_shadow_signals": _table_summary(conn, "jackal_shadow_signals", latest_column="signal_timestamp"),
            "jackal_shadow_batches": _table_summary(conn, "jackal_shadow_batches", latest_column="recorded_at"),
            "jackal_recommendations": _table_summary(conn, "jackal_recommendations", latest_column="recommended_at"),
            "jackal_accuracy_projection": _table_summary(
                conn,
                "jackal_accuracy_projection",
                latest_column="captured_at",
                source_column="source",
            ),
            "jackal_accuracy_current": _table_summary(
                conn,
                "jackal_accuracy_current",
                latest_column="captured_at",
                source_column="source",
            ),
            "jackal_live_events": _table_summary(conn, "jackal_live_events", latest_column="event_timestamp"),
        }
        tables["jackal_shadow_signals"]["resolved_with_outcome"] = int(
            _scalar(
                conn,
                """
                SELECT COUNT(*)
                  FROM jackal_shadow_signals
                 WHERE status = 'resolved'
                   AND outcome_json IS NOT NULL
                   AND outcome_json != ''
                """,
            )
            or 0
        )
        tables["jackal_recommendations"]["checked_rows"] = int(
            _scalar(conn, "SELECT COUNT(*) FROM jackal_recommendations WHERE outcome_checked = 1") or 0
        )
        tables["jackal_live_events"]["checked_rows"] = int(
            _scalar(conn, "SELECT COUNT(*) FROM jackal_live_events WHERE outcome_checked = 1") or 0
        )

    shadow_rows = int(tables["jackal_shadow_signals"]["rows"] or 0)
    recommendation_rows = int(tables["jackal_recommendations"]["rows"] or 0)
    ready_shadow = shadow_dry_run.get("status") == "planned"
    ready_recommendation = recommendation_dry_run.get("status") == "planned"
    if shadow_rows == 0 and recommendation_rows == 0:
        status = "waiting_for_operational_samples"
    elif ready_shadow or ready_recommendation:
        status = "ready_for_backfill_dry_run"
    else:
        status = "waiting_for_outcomes"

    return {
        "generated_at": _now_iso(),
        "status": status,
        "tables": tables,
        "shadow_state": shadow_state,
        "recommendation_state": recommendation_state,
        "projection_state": projection_state,
        "backfill_readiness": {
            "shadow": shadow_dry_run,
            "recommendation": recommendation_dry_run,
            "safe_non_dry_commands": [
                "python scripts\\backfill_jackal_shadow.py",
                "python scripts\\backfill_jackal_accuracy.py --include-recommendations",
            ],
            "backup_note": "Non-dry backfill scripts copy data/jackal_state.db before writing unless --no-backup is used.",
        },
        "baseline_fallback_audit": collect_baseline_fallback_summary(),
        "post_backfill_verification": {
            "projection_rows": projection_state.get("projection_rows"),
            "current_rows": projection_state.get("current_rows"),
            "latest_source": projection_state.get("latest_source"),
            "projection_missing_reasons": projection_state.get("missing_reasons", []),
            "shadow_missing_reasons": shadow_state.get("missing_reasons", []),
            "recommendation_missing_reasons": recommendation_state.get("missing_reasons", []),
        },
        "note": "Read-only operational intake check. Waiting states are not failures.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    baseline_summary = report.get("baseline_fallback_audit", {})
    by_component = baseline_summary.get("by_component", {})
    by_source = baseline_summary.get("by_regime_source", {})
    latest_event = baseline_summary.get("latest_event")
    latest_event_text = (
        "None"
        if latest_event is None
        else json.dumps(latest_event, ensure_ascii=False, sort_keys=True)
    )
    lines = [
        "# JACKAL Operational Intake",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Status: `{report.get('status')}`",
        f"- Note: {report.get('note')}",
        "",
        "## Row Counts",
        "",
        "| Table | Rows | Latest Timestamp | Extra |",
        "| --- | ---: | --- | --- |",
    ]
    for table, summary in report.get("tables", {}).items():
        extra = []
        if summary.get("latest_source"):
            extra.append(f"source={summary.get('latest_source')}")
        if "resolved_with_outcome" in summary:
            extra.append(f"resolved_with_outcome={summary.get('resolved_with_outcome')}")
        if "checked_rows" in summary:
            extra.append(f"checked_rows={summary.get('checked_rows')}")
        lines.append(
            f"| {table} | {summary.get('rows')} | {summary.get('latest_timestamp') or 'n/a'} | "
            f"{', '.join(extra) or 'n/a'} |"
        )

    readiness = report.get("backfill_readiness", {})
    lines.extend(
        [
            "",
            "## Backfill Readiness",
            "",
            f"- Shadow dry-run: `{json.dumps(readiness.get('shadow', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Recommendation dry-run: `{json.dumps(readiness.get('recommendation', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Backup note: {readiness.get('backup_note')}",
            "",
            "## Baseline Fallback Audit",
            "",
            f"- Status: `{baseline_summary.get('status', 'n/a')}`",
            f"- Log exists: `{baseline_summary.get('log_exists', False)}`",
            f"- Total events: `{baseline_summary.get('total_events', 0)}`",
            f"- Today events: `{baseline_summary.get('today_events', 0)}`",
            f"- Last 7d events: `{baseline_summary.get('last_7d_events', 0)}`",
            f"- By component: hunter=`{by_component.get('hunter', 0)}`, scanner=`{by_component.get('scanner', 0)}`",
            f"- By regime_source: memory=`{by_source.get('memory', 0)}`, "
            f"fallback=`{by_source.get('fallback', 0)}`, none=`{by_source.get('none', 0)}`",
            f"- Latest event: `{latest_event_text}`",
            f"- Parse errors: `{baseline_summary.get('parse_error_count', 0)}`",
            "",
            "## Post-Backfill Verification",
            "",
            f"`{json.dumps(report.get('post_backfill_verification', {}), ensure_ascii=False, sort_keys=True)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_json: Path | None, output_md: Path | None) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check JACKAL operational sample intake.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report = collect_operational_intake()
    write_outputs(
        report,
        output_json=Path(args.output_json) if args.output_json else None,
        output_md=Path(args.output_md) if args.output_md else None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))


if __name__ == "__main__":
    main()
