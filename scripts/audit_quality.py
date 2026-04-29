"""One-command quality audit for ORCA/JACKAL state, tests, and research gates."""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orca import research_report, state  # noqa: E402
from orca.jackal_accuracy_projection import describe_jackal_accuracy_projection_state  # noqa: E402
from orca.jackal_quality import (  # noqa: E402
    describe_jackal_recommendation_accuracy_state,
    describe_jackal_shadow_state,
)
from orca.market_fetch import get_provider_quality_summary  # noqa: E402

KST = timezone(timedelta(hours=9))
JSON_SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules"}


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _tail(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[-limit:]


def _run_command(name: str, args: list[str], *, timeout: int = 180) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
        )
        status = "pass" if proc.returncode == 0 else "fail"
        return {
            "name": name,
            "status": status,
            "command": args,
            "returncode": proc.returncode,
            "duration_sec": round(time.time() - started, 2),
            "stdout_tail": _tail(proc.stdout or ""),
            "stderr_tail": _tail(proc.stderr or ""),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "fail",
            "command": args,
            "returncode": None,
            "duration_sec": round(time.time() - started, 2),
            "stdout_tail": _tail(exc.stdout or ""),
            "stderr_tail": _tail(exc.stderr or ""),
            "reason": "timeout",
        }


def _skipped_command(name: str, args: list[str], reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "status": "skipped",
        "command": args,
        "returncode": None,
        "duration_sec": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "reason": reason,
    }


def parse_json_files() -> dict[str, Any]:
    checked = 0
    errors: list[dict[str, str]] = []
    for path in ROOT.rglob("*.json"):
        if any(part in JSON_SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        checked += 1
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({"path": str(path.relative_to(ROOT)), "error": str(exc)})
    return {
        "status": "pass" if not errors else "fail",
        "checked": checked,
        "error_count": len(errors),
        "errors": errors,
    }


def sqlite_integrity_checks() -> list[dict[str, Any]]:
    targets = [
        ROOT / "data" / "orca_state.db",
        ROOT / "data" / "jackal_state.db",
        ROOT / "data" / "archive" / "lesson_archive_cold.db",
    ]
    results: list[dict[str, Any]] = []
    for path in targets:
        if not path.exists():
            results.append({"path": str(path.relative_to(ROOT)), "status": "warn", "result": "missing"})
            continue
        try:
            conn = sqlite3.connect(path)
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                value = row[0] if row else "missing_result"
            finally:
                conn.close()
            results.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "status": "pass" if value == "ok" else "fail",
                    "result": value,
                }
            )
        except Exception as exc:
            results.append({"path": str(path.relative_to(ROOT)), "status": "fail", "result": str(exc)})
    return results


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _table_count(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return None


def collect_state_metrics() -> dict[str, Any]:
    live_accuracy = _read_json(ROOT / "data" / "accuracy.json")
    total = live_accuracy.get("total") or 0
    correct = live_accuracy.get("correct") or 0
    live_rate = round(float(correct) / float(total) * 100.0, 1) if total else None

    orca_latest, _orca_previous = research_report._find_latest_orca_sessions()
    jackal_latest_raw = research_report._find_latest_raw_jackal_session()
    jackal_latest_evaluable, _jackal_previous = research_report._find_latest_jackal_sessions()

    prediction_counts: dict[str, int] = {}
    candidate_counts: dict[str, Any] = {}
    with state._connect_orca() as conn:
        for row in conn.execute("SELECT status, COUNT(*) AS count FROM predictions GROUP BY status").fetchall():
            prediction_counts[str(row["status"])] = int(row["count"])
        candidate_counts["candidate_registry"] = _table_count(conn, "candidate_registry")
        candidate_counts["candidate_outcomes"] = _table_count(conn, "candidate_outcomes")
        candidate_counts["outcomes_by_horizon"] = {
            str(row["horizon_label"]): int(row["count"])
            for row in conn.execute(
                "SELECT horizon_label, COUNT(*) AS count FROM candidate_outcomes GROUP BY horizon_label"
            ).fetchall()
        }

    jackal_counts: dict[str, int | None] = {}
    with state._connect_jackal() as conn:
        for name in (
            "jackal_accuracy_current",
            "jackal_accuracy_projection",
            "jackal_weight_snapshots",
            "jackal_shadow_batches",
            "jackal_shadow_signals",
            "jackal_live_events",
            "jackal_recommendations",
        ):
            jackal_counts[name] = _table_count(conn, name)

    return {
        "live_accuracy": {
            "total": total,
            "correct": correct,
            "accuracy": live_rate,
        },
        "orca_latest_evaluable_backtest": orca_latest,
        "jackal_latest_raw_backtest": jackal_latest_raw,
        "jackal_latest_raw_issue": research_report._jackal_session_evaluation_issue(jackal_latest_raw),
        "jackal_latest_evaluable_backtest": jackal_latest_evaluable,
        "jackal_projection_state": describe_jackal_accuracy_projection_state(),
        "jackal_shadow_state": describe_jackal_shadow_state(),
        "jackal_recommendation_accuracy": describe_jackal_recommendation_accuracy_state(),
        "market_provider_quality": {
            "latest_backtest": research_report._provider_quality_from_orca_summary(
                (orca_latest or {}).get("summary", {}) if isinstance(orca_latest, dict) else {}
            ),
            "session": get_provider_quality_summary(),
        },
        "jackal_row_counts": jackal_counts,
        "prediction_status_counts": prediction_counts,
        "candidate_counts": candidate_counts,
    }


def run_research_artifacts(*, dry_run: bool) -> list[dict[str, Any]]:
    commands: list[tuple[str, list[str]]] = []
    with tempfile.TemporaryDirectory(prefix="orca_audit_") as tmp:
        tmpdir = Path(tmp)
        report_md = tmpdir / "report.md"
        report_json = tmpdir / "report.json"
        gate_md = tmpdir / "gate.md"
        gate_json = tmpdir / "gate.json"
        promote_md = tmpdir / "promote.md"
        promote_json = tmpdir / "promote.json"
        commands = [
            (
                "research_report",
                [
                    sys.executable,
                    "-m",
                    "orca.research_report",
                    "--output-md",
                    str(report_md),
                    "--output-json",
                    str(report_json),
                ],
            ),
            (
                "research_gate",
                [
                    sys.executable,
                    "-m",
                    "orca.research_gate",
                    "--report-json",
                    str(report_json),
                    "--output-md",
                    str(gate_md),
                    "--output-json",
                    str(gate_json),
                ],
            ),
            (
                "policy_promote",
                [
                    sys.executable,
                    "-m",
                    "orca.policy_promote",
                    "--gate-json",
                    str(gate_json),
                    "--output-md",
                    str(promote_md),
                    "--output-json",
                    str(promote_json),
                ],
            ),
        ]
        if dry_run:
            return [_skipped_command(name, args, "dry_run") for name, args in commands]
        return [_run_command(name, args, timeout=120) for name, args in commands]


def build_audit(*, dry_run: bool = False) -> dict[str, Any]:
    command_specs = [
        ("compileall", [sys.executable, "-m", "compileall", "-q", "orca", "jackal", "scripts", "tests"], 120),
        ("unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests"], 300),
        ("pip_check", [sys.executable, "-m", "pip", "check"], 120),
    ]
    if dry_run:
        command_checks = [
            _skipped_command(name, args, "dry_run")
            for name, args, _timeout in command_specs
        ]
    else:
        command_checks = [
            _run_command(name, args, timeout=timeout)
            for name, args, timeout in command_specs
        ]

    json_check = parse_json_files()
    sqlite_checks = sqlite_integrity_checks()
    metrics = collect_state_metrics()
    artifact_checks = run_research_artifacts(dry_run=dry_run)

    failures = [
        item
        for item in [*command_checks, *artifact_checks]
        if item.get("status") == "fail"
    ]
    if json_check["status"] == "fail":
        failures.append({"name": "json_parse", "status": "fail"})
    failures.extend(item for item in sqlite_checks if item.get("status") == "fail")

    warnings = []
    warnings.extend(item for item in [*command_checks, *artifact_checks] if item.get("status") == "skipped")
    warnings.extend(item for item in sqlite_checks if item.get("status") == "warn")

    return {
        "generated_at": _now_iso(),
        "root": str(ROOT),
        "status": "fail" if failures else "warn" if warnings else "pass",
        "dry_run": dry_run,
        "checks": {
            "commands": command_checks,
            "json_parse": json_check,
            "sqlite_integrity": sqlite_checks,
            "research_artifacts": artifact_checks,
        },
        "metrics": metrics,
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "note": "System quality audit only. No live LLM, paid market API, or trading/order action is performed.",
    }


def _session_line(session: dict[str, Any] | None, metric_keys: tuple[str, ...]) -> str:
    if not session:
        return "`n/a`"
    summary = session.get("summary", {}) if isinstance(session.get("summary"), dict) else {}
    metrics = ", ".join(f"{key}={summary.get(key, 'n/a')}" for key in metric_keys)
    return f"`{session.get('session_id', 'n/a')}` ({metrics})"


def render_markdown(audit: dict[str, Any]) -> str:
    metrics = audit.get("metrics", {})
    projection_state = metrics.get("jackal_projection_state", {})
    shadow_state = metrics.get("jackal_shadow_state", {})
    recommendation = metrics.get("jackal_recommendation_accuracy", {})
    provider_quality = metrics.get("market_provider_quality", {})
    provider_latest = provider_quality.get("latest_backtest", {})
    lines = [
        "# ORCA/JACKAL Quality Audit",
        "",
        f"- Generated: `{audit.get('generated_at')}`",
        f"- Status: `{audit.get('status')}`",
        f"- Dry run: `{audit.get('dry_run')}`",
        f"- Note: {audit.get('note')}",
        "",
        "## Command Checks",
        "",
        "| Check | Status | Return | Seconds | Reason |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in audit.get("checks", {}).get("commands", []):
        lines.append(
            f"| {item['name']} | {item['status']} | {item.get('returncode', 'n/a')} | "
            f"{item.get('duration_sec', 'n/a')} | {item.get('reason', '')} |"
        )
    lines.extend(
        [
            "",
            "## Data Checks",
            "",
            f"- JSON parse: `{audit['checks']['json_parse']['status']}` "
            f"({audit['checks']['json_parse']['checked']} files, {audit['checks']['json_parse']['error_count']} errors)",
            f"- SQLite integrity: `{json.dumps(audit['checks']['sqlite_integrity'], ensure_ascii=False)}`",
            f"- Research artifact checks: `{json.dumps(audit['checks']['research_artifacts'], ensure_ascii=False)}`",
            "",
            "## Accuracy State",
            "",
            f"- Live accuracy: `{json.dumps(metrics.get('live_accuracy', {}), ensure_ascii=False)}`",
            f"- ORCA latest evaluable: {_session_line(metrics.get('orca_latest_evaluable_backtest'), ('final_accuracy', 'judged_count'))}",
            f"- JACKAL latest raw: {_session_line(metrics.get('jackal_latest_raw_backtest'), ('total_tracked', 'swing_accuracy', 'd1_accuracy'))}",
            f"- JACKAL latest raw issue: `{metrics.get('jackal_latest_raw_issue')}`",
            f"- JACKAL latest evaluable: {_session_line(metrics.get('jackal_latest_evaluable_backtest'), ('total_tracked', 'swing_accuracy', 'd1_accuracy'))}",
            f"- JACKAL projection/current: rows=`{projection_state.get('projection_rows')}`/"
            f"`{projection_state.get('current_rows')}`, snapshots=`{projection_state.get('snapshot_rows')}`, "
            f"max_sample=`{projection_state.get('max_sample_count')}`, latest_source=`{projection_state.get('latest_source')}`",
            f"- JACKAL projection missing reasons: `{json.dumps(projection_state.get('missing_reasons', []), ensure_ascii=False)}`",
            f"- JACKAL shadow: signals=`{shadow_state.get('signal_rows')}`, batches=`{shadow_state.get('batch_rows')}`, "
            f"missing=`{json.dumps(shadow_state.get('missing_reasons', []), ensure_ascii=False)}`",
            f"- JACKAL recommendation accuracy: rows=`{recommendation.get('recommendation_rows')}`, checked=`{recommendation.get('checked_rows')}`, "
            f"projection/current=`{recommendation.get('projection_rows')}`/`{recommendation.get('current_rows')}`, "
            f"missing=`{json.dumps(recommendation.get('missing_reasons', []), ensure_ascii=False)}`",
            f"- Market provider quality: status=`{provider_latest.get('status')}`, "
            f"failure_rate=`{provider_latest.get('failure_rate')}`, stats=`{json.dumps(provider_latest.get('fetch_stats', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- JACKAL row counts: `{json.dumps(metrics.get('jackal_row_counts', {}), ensure_ascii=False, sort_keys=True)}`",
            f"- Prediction status counts: `{json.dumps(metrics.get('prediction_status_counts', {}), ensure_ascii=False, sort_keys=True)}`",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(audit: dict[str, Any], *, output_json: Path | None, output_md: Path | None) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_markdown(audit), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the ORCA/JACKAL quality audit.")
    parser.add_argument("--output-json", help="Write machine-readable audit JSON.")
    parser.add_argument("--output-md", help="Write human-readable audit Markdown.")
    parser.add_argument("--dry-run", action="store_true", help="Skip command/artifact execution but collect state metrics.")
    args = parser.parse_args(argv)

    audit = build_audit(dry_run=args.dry_run)
    write_outputs(
        audit,
        output_json=Path(args.output_json) if args.output_json else None,
        output_md=Path(args.output_md) if args.output_md else None,
    )
    print(render_markdown(audit))
    if audit["status"] == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()
