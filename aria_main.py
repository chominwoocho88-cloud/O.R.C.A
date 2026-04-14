"""
aria_main.py — ARIA 메인 오케스트레이터
기존 aria_multi_agent.py 대체
"""
import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel   import Panel
from rich.table   import Table
from rich         import box

from aria_agents   import agent_hunter, agent_analyst, agent_devil, agent_reporter
from aria_analysis import (
    run_sentiment, run_portfolio, run_rotation,
    save_baseline, build_baseline_context, get_regime_drift,
    run_verification, build_lessons_prompt, extract_dawn_lessons,
)
from aria_notify   import (
    send_message, send_start_notification, send_report, send_error,
)
from aria_data     import (
    fetch_all_market_data, update_cost, get_monthly_cost_summary,
)

KST     = timezone(timedelta(hours=9))
from aria_paths import MEMORY_FILE, REPORTS_DIR
MODE    = os.environ.get("ARIA_MODE", "MORNING")
console = Console()


# ══════════════════════════════════════════════════════════════════
# Jackal 연동 유틸
# ══════════════════════════════════════════════════════════════════

def _load_jackal_skills(max_skills: int = 6) -> str:
    """
    jackal/skills/ 에서 학습된 Skill을 읽어 프롬프트 문자열로 반환.
    비용 0 (로컬 파일 읽기). 없으면 빈 문자열.
    """
    skills_dir = Path("jackal/skills")
    if not skills_dir.exists():
        return ""
    lines = []
    for sp in sorted(skills_dir.glob("*.json"))[:max_skills]:
        try:
            s = json.loads(sp.read_text(encoding="utf-8"))
            name    = s.get("name", "")
            trigger = s.get("trigger", "")[:40]
            action  = s.get("action", "")[:50]
            if name:
                lines.append(f"  [{name}] 조건: {trigger} → 판단: {action}")
        except Exception:
            pass
    if not lines:
        return ""
    return "\n\n## Jackal 학습 Skill (이 패턴들을 분석에 반영할 것)\n" + "\n".join(lines)


def _load_jackal_instincts(max_inst: int = 4) -> str:
    """
    jackal/lessons/ 에서 최근 Instinct(실패 패턴)를 읽어 프롬프트 문자열로 반환.
    """
    lessons_dir = Path("jackal/lessons")
    if not lessons_dir.exists():
        return ""
    lines = []
    files = [p for p in sorted(lessons_dir.glob("*.json"), reverse=True)
             if not p.name.startswith(".")][:max_inst]
    for ip in files:
        try:
            inst = json.loads(ip.read_text(encoding="utf-8"))
            warning = inst.get("warning", "")[:50]
            reason  = inst.get("reason", "")[:40]
            if warning:
                lines.append(f"  ⚠️ {warning} (이유: {reason})")
        except Exception:
            pass
    if not lines:
        return ""
    return "\n\n## Jackal 경고 Instinct (과거 실패 패턴 — 주의)\n" + "\n".join(lines)


def _load_jackal_weights() -> dict:
    """jackal/jackal_weights.json 로드. 없으면 빈 딕셔너리."""
    jw_path = Path("jackal/jackal_weights.json")
    if not jw_path.exists():
        return {}
    try:
        return json.loads(jw_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════
# 공통 후처리
# ══════════════════════════════════════════════════════════════════

def sanitize_korea_claims(report: dict, market_data: dict) -> dict:
    """KIS 미연결 시 한국 수급 단정 표현 완화"""
    import re
    kis_connected = False
    if kis_connected:
        return report

    SOFTEN_MAP = {
        r"외국인\s*\d+[개월주일]+\s*연속\s*순매도": "외국인 순매도 흐름 지속 추정(수급 미확인)",
        r"외국인\s*\d+[개월주일]+\s*연속\s*순매수": "외국인 순매수 흐름 추정(수급 미확인)",
        r"외국인\s*누적\s*[+-]?\d+": "외국인 누적 흐름 추정(직접 데이터 미확인)",
        r"기관\s*\d+[조억만]+\s*원\s*순[매도수]": "기관 수급 추정(직접 데이터 미확인)",
        r"수급\s*(악화|개선)\s*확정": "수급 추정",
        r"외국인\s*이탈\s*가속": "외국인 이탈 압력 추정",
        r"(확정|확인됨)(?=.*수급)": "가능성",
    }

    def soften_text(text: str) -> str:
        if not isinstance(text, str):
            return text
        for pattern, replacement in SOFTEN_MAP.items():
            text = re.sub(pattern, replacement, text)
        return text

    def soften_recursive(obj):
        if isinstance(obj, str):   return soften_text(obj)
        if isinstance(obj, list):  return [soften_recursive(i) for i in obj]
        if isinstance(obj, dict):  return {k: soften_recursive(v) for k, v in obj.items()}
        return obj

    return soften_recursive(report)


# ══════════════════════════════════════════════════════════════════
# 메모리 / 리포트 유틸
# ══════════════════════════════════════════════════════════════════

def _now() -> datetime:
    return datetime.now(KST)


def load_memory() -> list:
    if not MEMORY_FILE.exists():
        return []
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print("⚠️ memory.json 손상 감지 (" + str(e) + ") — 빈 메모리로 재시작")
        backup = MEMORY_FILE.with_suffix(".json.bak")
        MEMORY_FILE.rename(backup)
        print("백업 저장: " + str(backup))
        return []


def save_memory(memory: list, analysis: dict):
    memory = [m for m in memory if m.get("analysis_date") != analysis.get("analysis_date")]
    memory = (memory + [analysis])[-90:]
    MEMORY_FILE.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")


def save_report(analysis: dict) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    date = analysis.get("analysis_date", _now().strftime("%Y-%m-%d"))
    mode = analysis.get("mode", "MORNING").lower()
    path = REPORTS_DIR / (date + "_" + mode + ".json")
    path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def get_todays_analyses() -> list:
    today   = _now().strftime("%Y-%m-%d")
    reports = []
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.glob(today + "_*.json"):
            try:
                reports.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
    return reports


# ══════════════════════════════════════════════════════════════════
# 콘솔 출력
# ══════════════════════════════════════════════════════════════════

def print_report(report: dict, run_n: int):
    regime     = report.get("market_regime", "?")
    mode       = report.get("mode", "MORNING")
    mode_label = report.get("mode_label", mode)
    rc = "green" if "선호" in regime else "red" if "회피" in regime else "yellow"

    console.rule("[bold purple]ARIA [" + mode_label + "] #" + str(run_n) + "[/bold purple]")
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

    if report.get("tomorrow_setup") and mode in ["EVENING", "DAWN"]:
        console.print(Panel(report["tomorrow_setup"], title="Tomorrow Setup", border_style="yellow"))

    console.rule()


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="ARIA Multi-Agent")
    parser.add_argument("--history", action="store_true", help="Show analysis history")
    args = parser.parse_args()

    memory = load_memory()

    # ── 히스토리 출력 ──────────────────────────────────────────────
    if args.history:
        if not memory:
            console.print("[dim]No saved analyses[/dim]"); return
        t = Table(title="ARIA History", box=box.ROUNDED)
        t.add_column("Date"); t.add_column("Mode")
        t.add_column("Regime"); t.add_column("Summary")
        for m in reversed(memory[-20:]):
            reg = m.get("market_regime", "")
            col = "green" if "선호" in reg else "red" if "회피" in reg else "yellow"
            t.add_row(m.get("analysis_date",""), m.get("mode",""),
                      "[" + col + "]" + reg + "[/" + col + "]",
                      m.get("one_line_summary","")[:40])
        console.print(t); return

    # ── 분석 실행 ──────────────────────────────────────────────────
    today = _now().strftime("%Y-%m-%d")
    console.print(Panel(
        "[bold]ARIA [" + MODE + "] Analysis Start[/bold]\nHunter → Analyst → Devil → Reporter",
        border_style="purple",
    ))

    try:
        # ── 중복 실행 방어 ─────────────────────────────────────────
        if MODE in ["MORNING", "EVENING"]:
            existing = list(REPORTS_DIR.glob(today + "_" + MODE.lower() + ".json")) if REPORTS_DIR.exists() else []
            if existing:
                event = os.environ.get("GITHUB_EVENT_NAME", "")
                if event == "schedule":
                    console.print("[red]⛔ 스케줄 중복 감지 — 종료 (비용 절약)[/red]")
                    sys.exit(0)
                else:
                    console.print("[yellow]⚠️ 오늘 " + MODE + " 분석이 이미 존재합니다: "
                                  + str(existing[0].name) + "[/yellow]")
                    console.print("[yellow]   수동 실행 — 덮어쓰기 계속 진행[/yellow]")

        # ── 1. 실시간 데이터 수집 ──────────────────────────────────
        print("\n=== 실시간 시장 데이터 수집 ===")
        market_data = fetch_all_market_data()
        update_cost(MODE)
        print(get_monthly_cost_summary())

        # 월 비용 경고
        try:
            from aria_data import load_cost
            _cost = load_cost()
            _mk   = _now().strftime("%Y-%m")
            _monthly_usd = _cost.get("monthly_runs", {}).get(_mk, {}).get("estimated_usd", 0)
            if _monthly_usd >= 20.0:
                send_message(
                    "⚠️ <b>ARIA 월 비용 경고</b>\n\n"
                    "이번 달 추정 비용: <b>$" + str(round(_monthly_usd, 2))
                    + " (약 " + f"{round(_monthly_usd*1480):,}" + "원)</b>\n"
                    "임계값 $20 초과 — 실행 횟수 확인 권장"
                )
        except Exception:
            pass

        # 데이터 품질 불량 시 중단
        if market_data.get("data_quality") == "poor":
            msg = "⚠️ 핵심 시장 데이터 수집 실패 — 분석 신뢰도 불충분으로 오늘 실행 중단"
            console.print("[bold red]" + msg + "[/bold red]")
            send_message("⚠️ <b>ARIA 데이터 오류</b>\n\n" + msg + "\n\nYahoo Finance 응답 불안정. 내일 자동 재시도.")
            return

        # ── 2. 교훈 로드 (MORNING 전용) + Jackal Skill/Instinct 주입 ──
        lessons_prompt = ""
        if MODE == "MORNING":
            lessons_prompt = build_lessons_prompt()
            if lessons_prompt:
                console.print("[dim]ARIA Lessons injected[/dim]")

        # Jackal Skills 주입 (모든 모드 — 비용 0)
        jackal_skills = _load_jackal_skills()
        if jackal_skills:
            lessons_prompt += jackal_skills
            skill_count = jackal_skills.count("\n  [")
            console.print(f"[dim]Jackal Skill {skill_count}개 주입됨[/dim]")

        # Jackal Instincts 주입 (모든 모드 — 비용 0)
        jackal_instincts = _load_jackal_instincts()
        if jackal_instincts:
            lessons_prompt += jackal_instincts
            inst_count = jackal_instincts.count("⚠️")
            console.print(f"[dim]Jackal Instinct {inst_count}개 경고 주입됨[/dim]")

        # ── 3. Baseline 컨텍스트 (MORNING 제외) ───────────────────
        baseline_context = ""
        if MODE != "MORNING":
            baseline_context = build_baseline_context(MODE)
            msg = "[dim]Morning baseline loaded[/dim]" if baseline_context else "[yellow]No baseline — running full analysis[/yellow]"
            console.print(msg)

        # ── 4. DAWN: 오늘 분석 돌아보고 교훈 추출 ─────────────────
        if MODE == "DAWN":
            todays = get_todays_analyses()
            if todays:
                extract_dawn_lessons(todays, "market outcomes today")

        # ── 5. MORNING: 어제 예측 채점 ────────────────────────────
        accuracy = {}
        if MODE == "MORNING":
            print("\n=== Verifying yesterday predictions ===")
            accuracy = run_verification()
            try:
                from aria_analysis import update_weights_from_accuracy
                changes = update_weights_from_accuracy(accuracy)
                if changes:
                    print("  📊 가중치 업데이트:", " | ".join(changes[:3]))
            except Exception as e:
                print(f"  가중치 업데이트 스킵: {e}")

        # ── 6. 4-Agent 파이프라인 ──────────────────────────────────
        send_start_notification()
        hunter  = agent_hunter(today, MODE, market_data)
        analyst = agent_analyst(hunter, MODE, lessons_prompt + baseline_context, memory=memory)
        devil   = agent_devil(analyst, memory, MODE)
        report  = agent_reporter(hunter, analyst, devil, memory, accuracy, MODE)

        # 날짜/시간 강제 오버라이드
        report["analysis_date"] = today
        report["analysis_time"] = _now().strftime("%H:%M KST")
        report["data_quality"]  = market_data.get("data_quality", "ok")

        # Jackal 가중치 기록 (Evolution 추적용)
        jw = _load_jackal_weights()
        if jw:
            report["jackal_weights"] = {
                "fear_greed":   jw.get("fear_greed_weight"),
                "technical":    jw.get("technical_weight"),
                "fundamental":  jw.get("fundamental_weight"),
                "last_updated": jw.get("last_updated", ""),
            }

        # ── 7. 레짐 드리프트 감지 ─────────────────────────────────
        drift = get_regime_drift(report.get("market_regime", ""))
        if drift and drift != "STABLE":
            console.print("[yellow]Regime drift: " + drift + "[/yellow]")

        # ── 7-1. KIS 미연결 표현 완화 ─────────────────────────────
        report = sanitize_korea_claims(report, market_data)

        # ── 8. 출력 및 텔레그램 전송 ──────────────────────────────
        print_report(report, len(memory) + 1)
        send_report(report, len(memory) + 1)

        # ── 9. MORNING: Baseline 저장 ──────────────────────────────
        if MODE == "MORNING":
            save_baseline(report, market_data)
            console.print("[dim]Morning baseline saved[/dim]")

        # ── 10. 서브 분석 ─────────────────────────────────────────
        print("\n=== Sentiment Tracking ===")
        run_sentiment(report, market_data)

        print("\n=== Sector Rotation ===")
        run_rotation(report)

        print("\n=== Portfolio Analysis ===")
        run_portfolio(report, market_data)

        # ── 11. 저장 ──────────────────────────────────────────────
        save_memory(memory, report)
        path = save_report(report)
        console.print("[dim]Saved: " + str(path) + "[/dim]")

        # 패턴 DB 갱신
        try:
            from aria_analysis import update_pattern_db
            updated_memory = load_memory()
            update_pattern_db(updated_memory)
            console.print("[dim]Pattern DB updated[/dim]")
        except Exception as e:
            console.print("[yellow]Pattern DB 갱신 스킵: " + str(e) + "[/yellow]")

        # ── 12. 대시보드 HTML 생성 (MORNING만) ───────────────────
        if MODE == "MORNING":
            try:
                from aria_dashboard import build_dashboard
                build_dashboard()
                console.print("[dim]Dashboard updated[/dim]")
            except Exception as e:
                console.print("[yellow]Dashboard 생성 실패: " + str(e) + "[/yellow]")

    except Exception as e:
        console.print("[bold red]Error: " + str(e) + "[/bold red]")
        try:
            send_error(str(e))
        except Exception:
            pass
        import traceback; traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
