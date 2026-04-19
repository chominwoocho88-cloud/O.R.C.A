# orca/persist.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-2 (body copy)

Report, memory, and prediction persistence helpers.
"""
# Allowed imports: .paths, .state, .learning_policy
# Allowed local imports: .present.console (one-way, singleton only)
# Forbidden imports: .analysis, .notify, .dashboard, .agents
# where="orca/main.py::main" preserved for PR 1 health contract.
# Do not change to new module names. Rationale: report JSON field stability.
# Future PR may migrate where values after verifying no downstream consumer
# parses them by value. Tracked in Backlog.

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import state as state_module
from .learning_policy import describe_policy
from .paths import MEMORY_FILE, REPORTS_DIR, atomic_write_json
from .state import record_report_predictions

KST = timezone(timedelta(hours=9))


def load_memory() -> list:
    if not MEMORY_FILE.exists():
        return []
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("\u26a0\ufe0f memory.json \uc190\uc0c1 \uac10\uc9c0 (" + str(e) + ") \u2014 \ube48 \uba54\ubaa8\ub9ac\ub85c \uc7ac\uc2dc\uc791")
        backup = MEMORY_FILE.with_suffix(".json.bak")
        MEMORY_FILE.rename(backup)
        print("\ubc31\uc5c5 \uc800\uc7a5: " + str(backup))
        return []


def save_memory(memory: list, analysis: dict):
    memory = [m for m in memory if m.get("analysis_date") != analysis.get("analysis_date")]
    new_memory = memory + [analysis]

    if len(new_memory) > 90:
        overflow = new_memory[:-90]
        archive_file = MEMORY_FILE.with_name("memory_archive.json")
        archived: list = []
        if archive_file.exists():
            try:
                archived = json.loads(archive_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(
                    f"\u26a0\ufe0f memory_archive.json \ub85c\ub4dc \uc2e4\ud328 ({exc}) \u2014 \uc0c8\ub85c \uc791\uc131",
                    file=sys.stderr,
                )
        archived.extend(overflow)
        atomic_write_json(archive_file, archived[-365:])

    atomic_write_json(MEMORY_FILE, new_memory[-90:])


def save_report(analysis: dict) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    date = analysis.get("analysis_date", datetime.now(KST).strftime("%Y-%m-%d"))
    mode = analysis.get("mode", "MORNING").lower()
    path = REPORTS_DIR / (date + "_" + mode + ".json")
    atomic_write_json(path, analysis)
    return path


def get_todays_analyses() -> list:
    today = datetime.now(KST).strftime("%Y-%m-%d")
    reports = []
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.glob(today + "_*.json"):
            try:
                reports.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
    return reports


def record_predictions(*, run_id: str | None, report: dict, health_tracker: Any) -> dict:
    from .present import console

    prediction_stats = {"count": 0}
    if not run_id:
        return prediction_stats

    try:
        prediction_stats = record_report_predictions(run_id, report)
        console.print("[dim]State DB predictions: " + str(prediction_stats.get("count", 0)) + "[/dim]")
    except Exception as state_err:
        health_tracker.record_exception(
            "state_db_unavailable",
            "orca/main.py::main",
            state_err,
            message="report prediction \uc800\uc7a5 \uc2e4\ud328",
        )
        console.print("[yellow]State DB prediction save skipped: " + str(state_err) + "[/yellow]")
    finally:
        health_tracker.ingest_state_events(state_module.drain_health_events())
    return prediction_stats


def persist_final_report(report: dict, health_tracker: Any) -> Path:
    report["learning_policy"] = describe_policy()
    report["health"] = health_tracker.to_report_payload(failed=False)
    path = save_report(report)
    return path
