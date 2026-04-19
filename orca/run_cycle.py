# orca/run_cycle.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-2 (body copy)

Top-level ORCA run orchestration and HealthTracker ownership.
"""
# Allowed imports: .data, .analysis, .pipeline, .postprocess, .persist, .present, .state, .brand
# Forbidden imports: .agents, .notify, .dashboard
# where="orca/main.py::main" preserved for PR 1 health contract.
# Do not change to new module names. Rationale: report JSON field stability.
# Future PR may migrate where values after verifying no downstream consumer
# parses them by value. Tracked in Backlog.

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone

from . import persist, pipeline, postprocess, present
from . import state as state_module
from .analysis import (
    build_baseline_context,
    build_lessons_prompt,
    extract_dawn_lessons,
    get_regime_drift,
    run_verification,
)
from .brand import ORCA_NAME
from .data import fetch_all_market_data, get_monthly_cost_summary, update_cost
from .paths import REPORTS_DIR
from .state import finish_run as state_finish_run
from .state import start_run as state_start_run

KST = timezone(timedelta(hours=9))


class HealthTracker:
    def __init__(self) -> None:
        self._details: list[dict[str, str]] = []
        self._warning_count = 0
        self._soft_fail_count = 0

    @staticmethod
    def _single_line(message: str | None) -> str:
        text = " ".join(str(message or "").split())
        if len(text) <= 160:
            return text
        return text[:157] + "..."

    def _append_detail(
        self,
        code: str,
        where: str,
        *,
        exception_type: str = "",
        message: str | None = None,
    ) -> None:
        self._details.append(
            {
                "code": code,
                "where": where,
                "exception_type": exception_type,
                "message": self._single_line(message),
            }
        )
        self._warning_count += 1
        self._soft_fail_count += 1

    def record(
        self,
        code: str,
        where: str,
        *,
        exception: Exception | None = None,
        message: str | None = None,
    ) -> None:
        self._append_detail(
            code,
            where,
            exception_type=type(exception).__name__ if exception else "",
            message=message or (str(exception) if exception else ""),
        )

    def record_exception(
        self,
        code: str,
        where: str,
        exception: Exception,
        *,
        message: str | None = None,
    ) -> None:
        self.record(code, where, exception=exception, message=message)

    def ingest_state_events(self, events: list[dict]) -> None:
        for event in events or []:
            self._append_detail(
                str(event.get("code", "")),
                str(event.get("where", "")),
                exception_type=str(event.get("exception_type", "")),
                message=str(event.get("message", "")),
            )

    def to_report_payload(self, *, failed: bool = False) -> dict:
        seen: set[str] = set()
        degraded_reasons: list[str] = []
        for detail in self._details:
            code = detail.get("code", "")
            if code and code not in seen:
                seen.add(code)
                degraded_reasons.append(code)

        if failed:
            status = "failed"
        elif self._details:
            status = "degraded"
        else:
            status = "ok"

        return {
            "status": status,
            "degraded_reasons": degraded_reasons,
            "counters": {
                "warnings": self._warning_count,
                "soft_fails": self._soft_fail_count,
            },
            "details": list(self._details),
        }

    def badge_text(self) -> str:
        payload = self.to_report_payload(failed=False)
        if payload["status"] == "ok":
            return ""
        reasons = payload["degraded_reasons"] or ["unknown_failure"]
        return "⚠ degraded: " + ", ".join(reasons)


def run_orca_cycle(*, mode: str, memory: list) -> None:
    today = datetime.now(KST).strftime("%Y-%m-%d")

    run_id = None
    health_tracker = HealthTracker()

    def _ingest_state_health() -> None:
        health_tracker.ingest_state_events(state_module.drain_health_events())

    def _build_minimal_failed_report() -> dict:
        return {
            "status": "failed",
            "health": health_tracker.to_report_payload(failed=True),
            "mode": mode,
            "analysis_date": today,
            "timestamp": datetime.now(KST).isoformat(),
        }

    def _print_health_badge() -> None:
        badge = health_tracker.badge_text()
        if badge:
            present.print_health_badge(badge)

    def _finish_state(status: str, **kwargs):
        if not run_id:
            return
        try:
            state_finish_run(run_id, status, **kwargs)
        except Exception as state_err:
            health_tracker.record_exception(
                "state_db_unavailable",
                "orca/main.py::main",
                state_err,
                message="state_finish_run \uc2e4\ud328",
            )
            present.console.print("[yellow]State DB finish skipped: " + str(state_err) + "[/yellow]")

    try:
        try:
            run_id = state_start_run(
                "orca",
                mode,
                today,
                metadata={
                    "history_size": len(memory),
                    "github_event": os.environ.get("GITHUB_EVENT_NAME", ""),
                },
            )
        except Exception as state_err:
            health_tracker.record_exception(
                "state_db_unavailable",
                "orca/main.py::main",
                state_err,
                message="state_start_run \uc2e4\ud328",
            )
            present.console.print("[yellow]State DB start skipped: " + str(state_err) + "[/yellow]")
            run_id = None

        if mode in ["MORNING", "EVENING"]:
            existing = list(REPORTS_DIR.glob(today + "_" + mode.lower() + ".json")) if REPORTS_DIR.exists() else []
            if existing:
                event = os.environ.get("GITHUB_EVENT_NAME", "")
                if event == "schedule":
                    _finish_state("aborted", metadata={"reason": "duplicate_scheduled_report"})
                    present.console.print("[red]\u26d4 \uc2a4\ucf00\uc904 \uc911\ubcf5 \uac10\uc9c0 \u2014 \uc885\ub8cc[/red]")
                    sys.exit(0)
                else:
                    present.console.print(
                        "[yellow]\u26a0\ufe0f \uc624\ub298 "
                        + mode
                        + " \uc774\ubbf8 \uc874\uc7ac \u2014 \uc218\ub3d9 \uc2e4\ud589\uc73c\ub85c \ub36e\uc5b4\uc4f0\uae30[/yellow]"
                    )

        print("\n=== \uc2e4\uc2dc\uac04 \uc2dc\uc7a5 \ub370\uc774\ud130 \uc218\uc9d1 ===")
        market_data = fetch_all_market_data()
        update_cost(mode)
        print(get_monthly_cost_summary())

        try:
            from .data import load_cost

            _cost = load_cost()
            _mk = datetime.now(KST).strftime("%Y-%m")
            _monthly_usd = _cost.get("monthly_runs", {}).get(_mk, {}).get("estimated_usd", 0)
            if _monthly_usd >= 20.0:
                present.send_generic_notice(
                    "\u26a0\ufe0f <b>"
                    + ORCA_NAME
                    + " \uc6d4 \ube44\uc6a9 \uacbd\uace0</b>\n\n"
                    + "\uc774\ubc88 \ub2ec \ucd94\uc815 \ube44\uc6a9: <b>$"
                    + str(round(_monthly_usd, 2))
                    + " (\uc57d "
                    + f"{round(_monthly_usd*1480):,}"
                    + "\uc6d0)</b>\n"
                    + "\uc784\uacc4\uac12 $20 \ucd08\uacfc"
                )
        except Exception as cost_err:
            health_tracker.record_exception(
                "cost_alert_failed",
                "orca/main.py::main",
                cost_err,
                message="\uc6d4 API \ube44\uc6a9 \uacbd\uace0 \ubc1c\uc1a1 \uc2e4\ud328",
            )

        if market_data.get("data_quality") == "poor":
            msg = "\u26a0\ufe0f \ud575\uc2ec \uc2dc\uc7a5 \ub370\uc774\ud130 \uc218\uc9d1 \uc2e4\ud328 \u2014 \ubd84\uc11d \uc911\ub2e8"
            health_tracker.record(
                "external_data_degraded",
                "orca/main.py::main",
                message="data quality poor",
            )
            minimal_report = _build_minimal_failed_report()
            path = persist.save_report(minimal_report)
            present.console.print("[bold red]" + msg + "[/bold red]")
            _print_health_badge()
            badge = health_tracker.badge_text()
            present.send_generic_notice(
                "\u26a0\ufe0f <b>" + ORCA_NAME + " \ub370\uc774\ud130 \uc624\ub958</b>\n\n" + msg + ("\n\n" + badge if badge else "")
            )
            _finish_state(
                "failed",
                data_quality=market_data.get("data_quality", "poor"),
                report_path=str(path),
                metadata={"reason": "poor_market_data"},
            )
            sys.exit(1)

        lessons_prompt = ""
        if mode == "MORNING":
            lessons_prompt = build_lessons_prompt()
            if lessons_prompt:
                present.console.print("[dim]Lessons injected[/dim]")

        baseline_context = ""
        if mode != "MORNING":
            baseline_context = build_baseline_context(memory)
            present.console.print("[dim]Morning baseline loaded[/dim]" if baseline_context else "[yellow]No baseline \u2014 full analysis[/yellow]")

        if mode == "DAWN":
            todays = persist.get_todays_analyses()
            if todays:
                extract_dawn_lessons(todays, "market outcomes today")

        accuracy = {}
        if mode == "MORNING":
            print("\n=== Verifying yesterday predictions ===")
            accuracy = run_verification()
            try:
                from .analysis import update_weights_from_accuracy

                changes = update_weights_from_accuracy(accuracy)
                if changes:
                    print("  \ud83d\udcca \uac00\uc911\uce58 \uc5c5\ub370\uc774\ud2b8:", " | ".join(changes[:3]))
            except Exception as e:
                health_tracker.record_exception(
                    "weight_update_failed",
                    "orca/main.py::main",
                    e,
                    message="\uac00\uc911\uce58 \uc5c5\ub370\uc774\ud2b8 \uc2e4\ud328",
                )
                print(f"  \uac00\uc911\uce58 \uc5c5\ub370\uc774\ud2b8 \uc2a4\ud0b5: {e}")

        present.send_start_notice()
        hunter, analyst, devil, report = pipeline.run_agent_pipeline(
            today=today,
            mode=mode,
            market_data=market_data,
            memory=memory,
            lessons_prompt=lessons_prompt,
            baseline_context=baseline_context,
            accuracy=accuracy,
        )

        report["analysis_date"] = today
        report["analysis_time"] = datetime.now(KST).strftime("%H:%M KST")
        report["mode"] = mode
        report["data_quality"] = market_data.get("data_quality", "ok")

        drift = get_regime_drift(report.get("market_regime", ""))
        if drift and drift != "STABLE":
            present.console.print("[yellow]Regime drift: " + drift + "[/yellow]")

        report = postprocess.sanitize_korea_claims(report, market_data)

        postprocess.run_candidate_review(
            report=report,
            run_id=run_id,
            analysis_date=today,
            health_tracker=health_tracker,
        )

        print("\n=== JACKAL Probability Summary ===")
        try:
            probability_summary = postprocess.compact_probability_summary(days=90)
            report["jackal_probability_summary"] = probability_summary
            overall = probability_summary.get("overall", {})
            present.console.print(
                "[dim]overall {win_rate}% | effective {effective}% | trusted {trusted} | cautious {cautious}[/dim]".format(
                    win_rate=overall.get("win_rate", 0.0),
                    effective=overall.get("effective_win_rate", overall.get("win_rate", 0.0)),
                    trusted=len(probability_summary.get("trusted_families", [])),
                    cautious=len(probability_summary.get("cautious_families", [])),
                )
            )
        except Exception as prob_err:
            health_tracker.record_exception(
                "probability_summary_unavailable",
                "orca/main.py::main",
                prob_err,
                message="JACKAL probability summary \uc2e4\ud328",
            )
            report["jackal_probability_summary"] = {"error": str(prob_err)}
            present.console.print("[yellow]Probability summary skipped: " + str(prob_err) + "[/yellow]")
        finally:
            _ingest_state_health()

        postprocess.maybe_save_baseline(mode=mode, report=report, market_data=market_data)
        postprocess.run_secondary_analyses(report, market_data)

        persist.save_memory(memory, report)
        prediction_stats = {"count": 0}
        if run_id:
            prediction_stats = persist.record_predictions(
                run_id=run_id,
                report=report,
                health_tracker=health_tracker,
            )

        postprocess.update_pattern_database(persist.load_memory(), health_tracker)

        if mode == "MORNING":
            postprocess.collect_jackal_news(hunter)

        if mode == "MORNING":
            present.maybe_build_dashboard(mode=mode, health_tracker=health_tracker)

        path = persist.persist_final_report(report, health_tracker)
        present.console.print("[dim]Saved: " + str(path) + "[/dim]")

        present.print_report(report, len(memory) + 1)
        _print_health_badge()
        present.send_final_report(report, len(memory) + 1)

        _finish_state(
            "completed",
            data_quality=report.get("data_quality", ""),
            report_path=str(path),
            report_summary=report.get("one_line_summary", ""),
            metadata={
                "market_regime": report.get("market_regime", ""),
                "trend_phase": report.get("trend_phase", ""),
                "consensus_level": report.get("consensus_level", ""),
                "prediction_count": prediction_stats.get("count", 0),
            },
        )

    except Exception as e:
        failed_report = _build_minimal_failed_report()
        failed_path = persist.save_report(failed_report)
        _finish_state("failed", report_path=str(failed_path), metadata={"error": str(e)})
        present.console.print("[bold red]Error: " + str(e) + "[/bold red]")
        _print_health_badge()
        try:
            badge = health_tracker.badge_text()
            present.send_error_notice(str(e) + ("\n" + badge if badge else ""))
        except Exception as notify_err:
            health_tracker.record_exception(
                "notification_failed",
                "orca/main.py::main",
                notify_err,
                message="\uc624\ub958 \uc54c\ub9bc \uc804\uc1a1 \uc2e4\ud328",
            )
        traceback.print_exc()
        sys.exit(1)
