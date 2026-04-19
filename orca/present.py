# orca/present.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-2 (body copy)

Console rendering, notifier calls, and dashboard hooks.
"""
# Allowed imports: rich, .brand, .notify, .dashboard
# Forbidden imports: .analysis, .state, .persist, .pipeline
# send_generic_notice: thin wrapper only. No composition logic.
# postprocess.py: may import present.console (one-way).
#                 MUST NOT be imported by present.py.

from __future__ import annotations

from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .brand import JACKAL_NAME, ORCA_NAME

console = Console()


def print_history(memory: list) -> None:
    if not memory:
        console.print("[dim]No saved analyses[/dim]"); return
    t = Table(title=ORCA_NAME + " History", box=box.ROUNDED)
    t.add_column("Date"); t.add_column("Mode")
    t.add_column("Regime"); t.add_column("Summary")
    for m in reversed(memory[-20:]):
        reg = m.get("market_regime", "")
        col = "green" if "선호" in reg else "red" if "회피" in reg else "yellow"
        t.add_row(m.get("analysis_date",""), m.get("mode",""),
                  "[" + col + "]" + reg + "[/" + col + "]",
                  m.get("one_line_summary","")[:40])
    console.print(t)


def print_start_banner(mode: str) -> None:
    console.print(Panel(
        "[bold]" + ORCA_NAME + " [" + mode + "] Analysis Start[/bold]\nHunter → Analyst → Devil → Reporter",
        border_style="purple",
    ))


def print_report(report: dict, run_n: int):
    regime     = report.get("market_regime", "?")
    mode       = report.get("mode", "MORNING")
    mode_label = report.get("mode_label", mode)
    rc = "green" if "선호" in regime else "red" if "회피" in regime else "yellow"

    console.rule("[bold purple]" + ORCA_NAME + " [" + mode_label + "] #" + str(run_n) + "[/bold purple]")
    console.print(Panel(
        "[bold]" + report.get("one_line_summary", "") + "[/bold]",
        title="[" + rc + "]" + regime + "[/" + rc + "]  " + report.get("confidence_overall", "")
              + "  " + report.get("analysis_date", ""),
        border_style="purple",
    ))

    tp = report.get("trend_phase", "")
    ts = report.get("trend_strategy", {})
    if tp:
        tc = "green" if "상승" in tp else "red" if "하락" in tp else "yellow"
        console.print(Panel(
            "[bold]" + tp + "[/bold]\n\nStrategy: " + ts.get("recommended", "")
            + "\nCaution: " + ts.get("caution", ""),
            title="Trend", border_style=tc,
        ))

    vi = report.get("volatility_index", {})
    if vi:
        vt = Table(box=box.SIMPLE, show_header=False)
        vt.add_column("", style="dim", width=12)
        vt.add_column("")
        for label, key in [("VIX","vix"),("VKOSPI","vkospi"),("공포탐욕","fear_greed"),("레벨","level")]:
            vt.add_row(label, vi.get(key, "-"))
        console.print(Panel(vt, title="Volatility", border_style="yellow"))

    kr = report.get("korea_focus", {})
    if kr:
        kt = Table(box=box.SIMPLE, show_header=False)
        kt.add_column("", style="dim", width=12)
        kt.add_column("", style="cyan")
        for label, key in [("KRW/USD","krw_usd"),("KOSPI","kospi_flow"),("SK Hynix","sk_hynix"),("Samsung","samsung")]:
            kt.add_row(label, kr.get(key) or "")
        console.print(Panel(kt, title="Korea Market", border_style="cyan"))

    ft = Table(box=box.SIMPLE, show_header=True, header_style="bold", expand=True)
    ft.add_column("Outflow", style="red")
    ft.add_column("Inflow",  style="green")
    out = report.get("outflows", [])
    inp = report.get("inflows", [])
    for i in range(max(len(out), len(inp))):
        oc = ("[bold]" + out[i]["zone"] + "[/bold]\n[dim]" + out[i].get("reason","")[:80] + "[/dim]") if i < len(out) else ""
        ic = ("[bold]" + inp[i]["zone"] + "[/bold]\n[dim]" + inp[i].get("reason","")[:80] + "[/dim]") if i < len(inp) else ""
        ft.add_row(oc, ic)
    console.print(Panel(ft, title="Capital Flow", border_style="blue"))

    candidate_review = report.get("jackal_candidate_review", {})
    if candidate_review.get("reviewed_count"):
        lines = [
            "시장 바이어스: " + candidate_review.get("market_bias_label", ""),
            "분류: aligned {aligned_count} / neutral {neutral_count} / opposed {opposed_count}".format(**candidate_review),
        ]
        for item in candidate_review.get("highlights", [])[:3]:
            lines.append(
                "- {ticker} {alignment}/{review_verdict} ({quality})".format(
                    ticker=item.get("ticker", ""),
                    alignment=item.get("alignment", ""),
                    review_verdict=item.get("review_verdict", ""),
                    quality=item.get("quality_score", "-"),
                )
            )
        console.print(Panel("\n".join(lines), title=JACKAL_NAME + " Candidate Review", border_style="magenta"))

    probability_summary = report.get("jackal_probability_summary", {})
    if probability_summary.get("overall", {}).get("total", 0) > 0:
        overall = probability_summary.get("overall", {})
        lines = [
            "최근 {window}일 overall {win_rate}% | 보수적 {effective}% (n={total})".format(
                window=probability_summary.get("window_days", 90),
                win_rate=overall.get("win_rate", 0.0),
                effective=overall.get("effective_win_rate", overall.get("win_rate", 0.0)),
                total=overall.get("total", 0),
            )
        ]
        skipped = int(probability_summary.get("duplicates_skipped", 0) or 0)
        deduped_rows = int(probability_summary.get("deduped_rows", 0) or 0)
        raw_rows = int(probability_summary.get("raw_rows", deduped_rows) or deduped_rows)
        if raw_rows > 0:
            lines.append(f"표본 정리: raw {raw_rows} → unique {deduped_rows}" + (f" (중복 {skipped} 제거)" if skipped else ""))
        trusted = probability_summary.get("trusted_families", [])
        cautious = probability_summary.get("cautious_families", [])
        if trusted:
            lines.append("신뢰: " + ", ".join(
                f"{item.get('signal_family_label', item.get('signal_family',''))} {item.get('effective_win_rate', item.get('win_rate',0)):.1f}%/{item.get('total',0)}"
                for item in trusted[:3]
            ))
        if cautious:
            lines.append("경계: " + ", ".join(
                f"{item.get('signal_family_label', item.get('signal_family',''))} {item.get('effective_win_rate', item.get('win_rate',0)):.1f}%/{item.get('total',0)}"
                for item in cautious[:3]
            ))
        aligned_best = probability_summary.get("best_aligned_families", [])
        opposed_best = probability_summary.get("best_opposed_families", [])
        if aligned_best:
            lines.append("정합 강점: " + ", ".join(
                f"{item.get('signal_family_label', item.get('signal_family',''))} {item.get('effective_win_rate', item.get('win_rate',0)):.1f}%/{item.get('total',0)}"
                for item in aligned_best[:2]
            ))
        if opposed_best:
            lines.append("역행 강점: " + ", ".join(
                f"{item.get('signal_family_label', item.get('signal_family',''))} {item.get('effective_win_rate', item.get('win_rate',0)):.1f}%/{item.get('total',0)}"
                for item in opposed_best[:2]
            ))
        console.print(Panel("\n".join(lines), title=JACKAL_NAME + " Probability View", border_style="bright_blue"))

    if report.get("tomorrow_setup") and mode in ["EVENING", "DAWN"]:
        console.print(Panel(report["tomorrow_setup"], title="Tomorrow Setup", border_style="yellow"))

    console.rule()


def print_health_badge(badge: str) -> None:
    if badge:
        console.print("[yellow]" + badge + "[/yellow]")


def maybe_build_dashboard(*, mode: str, health_tracker: Any) -> None:
    if mode == "MORNING":
        try:
            from .dashboard import build_dashboard

            build_dashboard()
            console.print("[dim]Dashboard updated[/dim]")
        except Exception as e:
            health_tracker.record_exception(
                "dashboard_generation_failed",
                "orca/main.py::main",
                e,
                message="Dashboard \uc0dd\uc131 \uc2e4\ud328",
            )
            console.print("[yellow]Dashboard \uc2e4\ud328: " + str(e) + "[/yellow]")


def send_start_notice() -> None:
    from .notify import send_start_notification

    send_start_notification()


def send_final_report(report: dict, run_n: int) -> None:
    from .notify import send_report

    send_report(report, run_n)


def send_error_notice(message: str) -> None:
    from .notify import send_error

    send_error(message)


def send_generic_notice(text: str) -> bool:
    """Generic Telegram send. Thin wrapper around notify.send_message."""
    from .notify import send_message

    return send_message(text)
