"""
Build a promotion decision from the latest research gate result.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .paths import REPORTS_DIR, atomic_write_json, atomic_write_text

KST = timezone(timedelta(hours=9))
DEFAULT_GATE_JSON = REPORTS_DIR / "orca_research_gate.json"
DEFAULT_PROMOTION_MD = REPORTS_DIR / "orca_policy_promotion.md"
DEFAULT_PROMOTION_JSON = REPORTS_DIR / "orca_policy_promotion.json"


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _load_gate(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Missing research gate: {path}\n"
            "Run `python -m orca.research_gate` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _write_decision_outputs(markdown_path: Path, json_path: Path, decision: dict) -> None:
    markdown = render_markdown(decision)
    atomic_write_json(json_path, decision)
    atomic_write_text(markdown_path, markdown)


def build_decision(gate: dict) -> dict:
    status = gate.get("status", "warn")
    if status == "pass":
        decision = "promote_candidate"
        rationale = "Research gate passed with no blocking regression."
        next_actions = [
            "Prepare policy versioning metadata.",
            "Run challenger vs incumbent comparison on the same state DB.",
            "Require human approval before production promotion.",
        ]
    elif status == "warn":
        decision = "hold_manual_review"
        rationale = "Research gate has warnings or insufficient history."
        next_actions = [
            "Review missing history and linked session dependencies.",
            "Re-run policy evaluation after one more completed research cycle.",
            "Do not auto-promote while warnings remain.",
        ]
    else:
        decision = "blocked_regression"
        rationale = "Research gate detected a blocking regression."
        next_actions = [
            "Inspect failed gate checks and compare against the previous session.",
            "Keep current production policy pinned.",
            "Open a regression review before any policy promotion.",
        ]

    return {
        "generated_at": _now_iso(),
        "source_gate_generated_at": gate.get("generated_at"),
        "gate_status": status,
        "decision": decision,
        "rationale": rationale,
        "checks": gate.get("checks", []),
        "report_warnings": gate.get("report_warnings", []),
        "next_actions": next_actions,
        "note": "This workflow does not mutate production policy yet. It only records a promotion decision artifact.",
    }


def render_markdown(decision: dict) -> str:
    lines = [
        "# Policy Promotion Decision",
        "",
        f"- Generated: `{decision['generated_at']}`",
        f"- Source gate generated: `{decision.get('source_gate_generated_at', 'n/a')}`",
        f"- Gate status: `{decision['gate_status']}`",
        f"- Decision: `{decision['decision']}`",
        "",
        "## Rationale",
        "",
        f"- {decision['rationale']}",
        "",
        "## Next Actions",
        "",
    ]
    lines.extend([f"- {item}" for item in decision.get("next_actions", [])])
    lines.extend(
        [
            "",
            "## Note",
            "",
            f"- {decision['note']}",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a policy promotion decision artifact.")
    parser.add_argument("--gate-json", default=str(DEFAULT_GATE_JSON))
    parser.add_argument("--output-md", default=str(DEFAULT_PROMOTION_MD))
    parser.add_argument("--output-json", default=str(DEFAULT_PROMOTION_JSON))
    args = parser.parse_args()

    gate = _load_gate(Path(args.gate_json))
    decision = build_decision(gate)
    _write_decision_outputs(Path(args.output_md), Path(args.output_json), decision)

    print(f"Policy promotion report saved: {args.output_md}")
    print(f"Policy promotion data saved: {args.output_json}")
    print(f"Policy promotion decision: {decision['decision']}")


if __name__ == "__main__":
    main()

