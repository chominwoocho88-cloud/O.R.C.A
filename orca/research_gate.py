"""
Evaluate the latest research comparison report and decide whether regression gates pass.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .paths import REPORTS_DIR, atomic_write_json, atomic_write_text

KST = timezone(timedelta(hours=9))
DEFAULT_REPORT_JSON = REPORTS_DIR / "orca_research_comparison.json"
DEFAULT_GATE_MD = REPORTS_DIR / "orca_research_gate.md"
DEFAULT_GATE_JSON = REPORTS_DIR / "orca_research_gate.json"


DEFAULT_THRESHOLDS = {
    "orca_final_accuracy_min_delta": -5.0,
    "jackal_swing_accuracy_min_delta": -5.0,
    "jackal_d1_accuracy_min_delta": -5.0,
    "shadow_rolling_10_min_rate": 45.0,
    "orca_judged_count_min": 100,
    "jackal_total_tracked_min": 100,
    "shadow_rolling_10_min_batches": 10,
    "jackal_projection_rows_min": 1,
}


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"Missing research report: {path}\n"
            "Run `python -m orca.research_report` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _write_gate_outputs(markdown_path: Path, json_path: Path, gate: dict[str, Any]) -> None:
    markdown = render_markdown(gate)
    atomic_write_json(json_path, gate)
    atomic_write_text(markdown_path, markdown)


def _check_delta(
    name: str,
    delta: float | None,
    minimum: float,
    *,
    current: float | None = None,
) -> dict[str, Any]:
    if delta is None:
        return {
            "name": name,
            "status": "warn",
            "reason": "insufficient_history",
            "current": current,
            "delta": delta,
            "threshold": minimum,
        }
    status = "pass" if delta >= minimum else "fail"
    return {
        "name": name,
        "status": status,
        "reason": "ok" if status == "pass" else "regression_exceeded",
        "current": current,
        "delta": delta,
        "threshold": minimum,
    }


def _check_minimum(
    name: str,
    value: float | None,
    minimum: float,
    *,
    sample_count: int | None = None,
) -> dict[str, Any]:
    if sample_count is not None and sample_count == 0:
        return {
            "name": name,
            "status": "warn",
            "reason": "insufficient_history",
            "current": value,
            "threshold": minimum,
            "sample_count": sample_count,
        }
    if value is None:
        return {
            "name": name,
            "status": "warn",
            "reason": "missing_value",
            "current": value,
            "threshold": minimum,
            "sample_count": sample_count,
        }
    status = "pass" if value >= minimum else "fail"
    return {
        "name": name,
        "status": status,
        "reason": "ok" if status == "pass" else "below_floor",
        "current": value,
        "threshold": minimum,
        "sample_count": sample_count,
    }


def _check_sample_count(
    name: str,
    value: float | int | None,
    minimum: float | int,
    *,
    status_on_shortfall: str = "warn",
) -> dict[str, Any]:
    if value is None:
        return {
            "name": name,
            "status": "warn",
            "reason": "missing_value",
            "current": value,
            "threshold": minimum,
            "sample_count": value,
        }
    try:
        current = float(value)
    except (TypeError, ValueError):
        return {
            "name": name,
            "status": "warn",
            "reason": "invalid_value",
            "current": value,
            "threshold": minimum,
            "sample_count": value,
        }
    if current < float(minimum):
        return {
            "name": name,
            "status": status_on_shortfall,
            "reason": "insufficient_sample",
            "current": value,
            "threshold": minimum,
            "sample_count": value,
        }
    return {
        "name": name,
        "status": "pass",
        "reason": "ok",
        "current": value,
        "threshold": minimum,
        "sample_count": value,
    }


def _check_boolean(name: str, value: bool, *, warn_if_missing: bool = False) -> dict[str, Any]:
    if warn_if_missing and value is False:
        return {
            "name": name,
            "status": "warn",
            "reason": "missing_dependency",
            "current": value,
        }
    return {
        "name": name,
        "status": "pass" if value else "fail",
        "reason": "ok" if value else "mismatch",
        "current": value,
    }


def evaluate_report(report: dict[str, Any], thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    cfg = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        cfg.update(thresholds)

    orca = report.get("orca", {})
    jackal = report.get("jackal_backtest", {})
    shadow = report.get("jackal_shadow", {})
    accuracy_view = report.get("jackal_accuracy_view", {})
    warnings = report.get("warnings", [])

    orca_summary = orca.get("summary", {})
    jackal_summary = jackal.get("summary", {})
    rolling_shadow = shadow.get("rolling_10", {})
    accuracy_meta = accuracy_view.get("meta", {}) if isinstance(accuracy_view, dict) else {}
    available_projection_rows = accuracy_meta.get("total_current_rows")
    if available_projection_rows is None:
        available_rows = accuracy_meta.get("available_rows", {}) if isinstance(accuracy_meta, dict) else {}
        if isinstance(available_rows, dict):
            available_projection_rows = sum(int(value or 0) for value in available_rows.values())

    checks = [
        _check_delta(
            "orca_final_accuracy_delta",
            orca.get("deltas", {}).get("final_accuracy"),
            cfg["orca_final_accuracy_min_delta"],
            current=orca_summary.get("final_accuracy"),
        ),
        _check_delta(
            "jackal_swing_accuracy_delta",
            jackal.get("deltas", {}).get("swing_accuracy"),
            cfg["jackal_swing_accuracy_min_delta"],
            current=jackal_summary.get("swing_accuracy"),
        ),
        _check_delta(
            "jackal_d1_accuracy_delta",
            jackal.get("deltas", {}).get("d1_accuracy"),
            cfg["jackal_d1_accuracy_min_delta"],
            current=jackal_summary.get("d1_accuracy"),
        ),
        _check_sample_count(
            "orca_judged_count_minimum",
            orca_summary.get("judged_count"),
            cfg["orca_judged_count_min"],
        ),
        _check_sample_count(
            "jackal_total_tracked_minimum",
            jackal_summary.get("total_tracked"),
            cfg["jackal_total_tracked_min"],
        ),
        _check_minimum(
            "jackal_shadow_rolling_10_rate",
            rolling_shadow.get("rate"),
            cfg["shadow_rolling_10_min_rate"],
            sample_count=rolling_shadow.get("batch_count"),
        ),
        _check_sample_count(
            "jackal_shadow_rolling_10_batch_count",
            rolling_shadow.get("batch_count"),
            cfg["shadow_rolling_10_min_batches"],
        ),
        _check_sample_count(
            "jackal_projection_rows_available",
            available_projection_rows,
            cfg["jackal_projection_rows_min"],
        ),
        _check_boolean(
            "jackal_linked_to_latest_orca",
            bool(jackal.get("linked_to_latest_orca")),
            warn_if_missing=not bool(jackal.get("latest")) or not bool(orca.get("latest")),
        ),
    ]

    latest_raw_issue = jackal.get("latest_raw_evaluation_issue")
    if latest_raw_issue and not jackal.get("using_latest_raw_as_representative"):
        checks.append(
            {
                "name": "jackal_latest_raw_evaluable",
                "status": "warn",
                "reason": str(latest_raw_issue),
                "current": False,
            }
        )

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warn_count = sum(1 for item in checks if item["status"] == "warn")

    status = "fail" if fail_count else "warn" if warn_count or warnings else "pass"
    summary = {
        "generated_at": _now_iso(),
        "source_report_generated_at": report.get("generated_at"),
        "status": status,
        "fail_count": fail_count,
        "warn_count": warn_count + len(warnings),
        "thresholds": cfg,
        "checks": checks,
        "report_warnings": warnings,
    }
    return summary


def render_markdown(gate: dict[str, Any]) -> str:
    lines = [
        "# Research Gate Result",
        "",
        f"- Generated: `{gate['generated_at']}`",
        f"- Source report generated: `{gate.get('source_report_generated_at', 'n/a')}`",
        f"- Overall status: `{gate['status']}`",
        f"- Fail count: `{gate['fail_count']}`",
        f"- Warn count: `{gate['warn_count']}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Current | Delta | Threshold | Reason |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]

    for item in gate.get("checks", []):
        current = item.get("current")
        delta = item.get("delta")
        threshold = item.get("threshold")
        current_str = "n/a" if current is None else f"{current}"
        delta_str = "n/a" if delta is None else f"{delta:+.1f}"
        threshold_str = "n/a" if threshold is None else f"{threshold}"
        lines.append(
            f"| {item['name']} | {item['status']} | {current_str} | {delta_str} | {threshold_str} | {item['reason']} |"
        )

    weak_checks = [item for item in gate.get("checks", []) if item.get("status") != "pass"]
    lines.extend(
        [
            "",
            "## Reliability Notes",
            "",
        ]
    )
    if weak_checks:
        lines.extend(
            [
                f"- `{item['name']}` is `{item['status']}` because `{item.get('reason', 'unknown')}`."
                for item in weak_checks
            ]
        )
    else:
        lines.append("- Minimum sample and dependency checks passed.")

    lines.extend(
        [
            "",
            "## Report Warnings",
            "",
        ]
    )

    warnings = gate.get("report_warnings", [])
    if warnings:
        lines.extend([f"- {warning}" for warning in warnings])
    else:
        lines.append("- No report warnings.")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate research regression gates.")
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_GATE_MD))
    parser.add_argument("--output-json", default=str(DEFAULT_GATE_JSON))
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when gate status is fail.")
    args = parser.parse_args()

    report_path = Path(args.report_json)
    report = _load_json(report_path)
    gate = evaluate_report(report)

    output_md = Path(args.output_md)
    output_json = Path(args.output_json)
    _write_gate_outputs(output_md, output_json, gate)

    print(f"Research gate report saved: {output_md}")
    print(f"Research gate data saved: {output_json}")
    print(f"Research gate status: {gate['status']}")

    if args.strict and gate["status"] == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()

