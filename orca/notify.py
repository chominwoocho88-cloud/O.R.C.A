"""
orca_notify.py — ORCA 알림 모듈 통합
포함: telegram · weekly · monthly · breaking · calendar
"""
import os
import sys
import json
import re
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .analysis import get_active_lessons, load_lessons
from .brand import ORCA_FULL_NAME, ORCA_NAME
from .compat import get_orca_env
from .notify_transport import _format_accuracy_display, send_message

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST = timezone(timedelta(hours=9))

from .paths import (
    MEMORY_FILE, ACCURACY_FILE, SENTIMENT_FILE,
    ROTATION_FILE, BREAKING_FILE, LESSONS_FILE, atomic_write_json,
)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_S = "claude-haiku-4-5-20251001"   # 캘린더/속보용 가벼운 모델
client  = anthropic.Anthropic(api_key=API_KEY)


def _now() -> datetime:
    return datetime.now(KST)

def _today() -> str:
    return _now().strftime("%Y-%m-%d")

def _load(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default if default is not None else {}

def _save(path: Path, data):
    atomic_write_json(path, data)


def _dashboard_url() -> str:
    explicit = os.environ.get("ORCA_DASHBOARD_URL", "").strip()
    if explicit:
        return explicit

    repo = os.environ.get("GH_REPO", "").strip()
    if "/" not in repo:
        return ""

    owner, name = repo.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name:
        return ""
    return f"https://{owner}.github.io/{name}/reports/dashboard.html"


def _build_health_badge(report: dict) -> str:
    health = report.get("health") or {}
    status = health.get("status") or "ok"
    if status == "ok":
        return ""
    reasons = health.get("degraded_reasons") or ["unknown_failure"]
    return "⚠ degraded: " + ", ".join(reasons)


def _build_historical_context_lines(report: dict) -> list[str]:
    historical_context = report.get("historical_context") or {}
    if not historical_context:
        return []
    cluster_label = historical_context.get("cluster_label") or historical_context.get("cluster_id") or "-"
    win_rate = _safe_float(historical_context.get("win_rate")) * 100
    avg_value = _safe_float(historical_context.get("avg_value"))
    lines = [
        "",
        "━━ 📊 Historical Context ━━",
        "Cluster: " + str(cluster_label),
        f"Win rate: {win_rate:.0f}% | Avg value: {avg_value:+.2f}%",
    ]
    examples = historical_context.get("top_lessons") or []
    if examples:
        sample = examples[0]
        lines.append(
            "Top: {ticker} {value:+.2f}% [{tier}]".format(
                ticker=sample.get("ticker") or "-",
                value=_safe_float(sample.get("lesson_value")),
                tier=sample.get("quality_tier") or "-",
            )
        )
    return lines


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════


def make_buttons() -> dict:
    return {
        "inline_keyboard": [[
            {"text": "🔄 지금 분석",  "callback_data": "run_now"},
            {"text": "📋 히스토리",   "callback_data": "history"},
            {"text": "🧠 성장리뷰",   "callback_data": "review"},
            {"text": "📚 학습현황",   "callback_data": "lessons"},
        ]]
    }


def send_error(message: str) -> bool:
    return send_message(
        "⚠️ <b>" + ORCA_NAME + " 오류</b>\n\n<code>" + message + "</code>\n\n"
        + "<i>" + _now().strftime("%Y-%m-%d %H:%M KST") + "</i>"
    )


def send_start_notification() -> bool:
    mode = get_orca_env("ORCA_MODE", "MORNING")
    labels = {"MORNING":"🌅 아침 풀분석","AFTERNOON":"☀️ 오후 업데이트",
              "EVENING":"🌆 저녁 마감","DAWN":"🌙 새벽 글로벌"}
    return send_message(
        "⚙️ <b>" + ORCA_NAME + " 분석 시작</b> " + labels.get(mode, mode) + "\n"
        + "<i>" + _now().strftime("%Y-%m-%d %H:%M KST") + "</i>\n"
        + "Hunter → Analyst → Devil → Reporter..."
    )


def send_report(report: dict, run_number: int) -> bool:
    mode       = report.get("mode", "MORNING")
    regime     = report.get("market_regime", "?")
    confidence = report.get("confidence_overall", "?")
    date       = report.get("analysis_date", "")
    time_      = report.get("analysis_time", "")
    summary    = report.get("one_line_summary", "")
    mode_label = report.get("mode_label", "")

    regime_emoji = "🟢" if "선호" in regime else "🔴" if "회피" in regime else "🟡"
    mode_icon    = {"MORNING":"🌅","AFTERNOON":"☀️","EVENING":"🌆","DAWN":"🌙"}.get(mode, "📊")

    header = [
        mode_icon + " <b>" + ORCA_NAME + " " + (mode_label or mode) + " #" + str(run_number) + "</b>",
        "<code>" + date + " " + time_ + "</code>", "",
        regime_emoji + " <b>" + regime + "</b>  신뢰도: " + confidence, "",
        "💡 <i>" + summary + "</i>", "",
    ]

    builders = {
        "MORNING":   _build_morning,
        "AFTERNOON": _build_afternoon,
        "EVENING":   _build_evening,
        "DAWN":      _build_dawn,
    }
    lines = header + builders.get(mode, _build_morning)(report)
    lines += _build_historical_context_lines(report)
    dash_url = _dashboard_url()
    if dash_url:
        lines += ["", f"📊 <a href=\"{dash_url}\">대시보드 보기</a>"]
    lines += [
        "<code>" + ORCA_NAME + " | " + ORCA_FULL_NAME + "</code>",
    ]
    badge = _build_health_badge(report)
    if badge:
        lines.append(badge)
    return send_message("\n".join(lines), reply_markup=make_buttons())


def _build_morning(report: dict) -> list:
    lines = []
    kr = report.get("korea_focus", {})
    if kr:
        lines += [
            "🇰🇷 <b>한국 시장</b>",
            "  원/달러: <code>" + kr.get("krw_usd", "-") + "</code>",
            "  코스피:  <code>" + kr.get("kospi_flow", "-") + "</code>",
            "  SK하이닉스: <code>" + kr.get("sk_hynix", "-") + "</code>",
            "  삼성전자:   <code>" + kr.get("samsung", "-") + "</code>",
            "  <i>" + kr.get("assessment", "") + "</i>", "",
        ]
    for o in report.get("outflows", [])[:3]:
        lines += ["▼ <b>" + o.get("zone","") + "</b> [" + o.get("severity","") + "]",
                  "  <i>" + o.get("reason","")[:70] + "</i>"]
    if report.get("outflows"): lines.append("")
    for i in report.get("inflows", [])[:3]:
        lines += ["▲ <b>" + i.get("zone","") + "</b> [" + i.get("momentum","") + "]",
                  "  <i>" + i.get("reason","")[:70] + "</i>"]
    if report.get("inflows"): lines.append("")
    for tk in report.get("thesis_killers", [])[:3]:
        lines += ["🎯 [" + tk.get("timeframe","") + "] <b>" + tk.get("event","") + "</b>",
                  "  ✓ " + tk.get("confirms_if","")[:50],
                  "  ✗ " + tk.get("invalidates_if","")[:50]]
    if report.get("thesis_killers"): lines.append("")
    for idx, a in enumerate(report.get("actionable_watch", [])[:3], 1):
        lines.append("📌 " + str(idx) + ". " + a)

    candidate_review = report.get("jackal_candidate_review", {})
    if candidate_review.get("reviewed_count", 0) > 0:
        breakdown = candidate_review.get("review_verdict_breakdown", {})
        lines += [
            "",
            "━━ 🐺 JACKAL 후보 리뷰 ━━",
            "시장 바이어스: " + candidate_review.get("market_bias_label", ""),
            "분류: aligned {a} / neutral {n} / opposed {o}".format(
                a=candidate_review.get("aligned_count", 0),
                n=candidate_review.get("neutral_count", 0),
                o=candidate_review.get("opposed_count", 0),
            ),
        ]
        if sum(int(breakdown.get(key, 0) or 0) for key in ("strong_aligned", "aligned", "neutral", "opposed", "strong_opposed")) > 0:
            lines.append(
                "정밀: SA {sa} / A {a} / N {n} / O {o} / SO {so}".format(
                    sa=breakdown.get("strong_aligned", 0),
                    a=breakdown.get("aligned", 0),
                    n=breakdown.get("neutral", 0),
                    o=breakdown.get("opposed", 0),
                    so=breakdown.get("strong_opposed", 0),
                )
            )
        avg_conf = candidate_review.get("average_review_confidence", "")
        if avg_conf:
            lines.append("평균 확신도: " + avg_conf)
        for item in candidate_review.get("highlights", [])[:3]:
            reasons = item.get("alignment_reason_codes", [])[:2]
            reason_suffix = " [" + ", ".join(reasons) + "]" if reasons else ""
            lines.append(
                "• {ticker} {alignment}/{verdict} ({quality}){suffix}".format(
                    ticker=item.get("ticker", ""),
                    alignment=item.get("alignment", ""),
                    verdict=item.get("review_verdict", ""),
                    quality=item.get("quality_score", "-"),
                    suffix=reason_suffix,
                )
            )

    lessons = get_active_lessons(max_lessons=3)
    if lessons:
        lines += ["", "━━ 🧠 오늘 반영된 교훈 ━━"]
        for l in lessons:
            lines.append(("🔴" if l["severity"]=="high" else "🟡")
                          + " [" + l["category"] + "] " + l["lesson"][:50])
    return lines


def _build_afternoon(report: dict) -> list:
    lines = ["━━ 오후 업데이트 ━━", ""]
    outflows = report.get("outflows", [])
    inflows  = report.get("inflows", [])
    if outflows: lines.append("▼ " + outflows[0].get("zone","") + " — " + outflows[0].get("reason","")[:50])
    if inflows:  lines.append("▲ " + inflows[0].get("zone","") + " — " + inflows[0].get("reason","")[:50])
    if report.get("actionable_watch"): lines.append("📌 " + report["actionable_watch"][0])
    kr = report.get("korea_focus", {})
    if kr.get("krw_usd"):
        lines += ["", "원/달러: <code>" + kr["krw_usd"] + "</code>  코스피: <code>" + kr.get("kospi_flow","-") + "</code>"]
    tks = report.get("thesis_killers", [])
    if tks:
        lines += ["", "🎯 <b>" + tks[0].get("event","") + "</b>",
                  "  ✓ " + tks[0].get("confirms_if","")[:50]]
    return lines


def _build_evening(report: dict) -> list:
    lines = ["━━ 오늘 총정리 ━━", ""]
    tomorrow = report.get("tomorrow_setup", "")
    if tomorrow: lines += ["🌙 <b>내일 준비</b>", "<i>" + tomorrow[:100] + "</i>", ""]
    counters = report.get("counterarguments", [])
    if counters:
        lines.append("⚔️ <b>주요 리스크</b>")
        for c in counters[:2]: lines.append("• " + c.get("against","")[:50])
        lines.append("")
    tails = report.get("tail_risks", [])
    if tails: lines.append("☠️ " + str(tails[0])[:60])
    return lines


def _build_dawn(report: dict) -> list:
    lines = ["━━ 새벽 글로벌 브리핑 ━━", ""]
    inflows  = report.get("inflows", [])
    outflows = report.get("outflows", [])
    if inflows:  lines.append("▲ " + inflows[0].get("zone","") + " — " + inflows[0].get("reason","")[:60])
    if outflows: lines.append("▼ " + outflows[0].get("zone","") + " — " + outflows[0].get("reason","")[:60])
    lines.append("")
    tomorrow = report.get("tomorrow_setup", "")
    if tomorrow: lines += ["📋 <b>오늘 아침 준비</b>", "<i>" + tomorrow[:100] + "</i>"]
    return lines


def send_lessons_status() -> bool:
    try:
        _data_dir = LESSONS_FILE.parent

        # ── 3파일 합산 통계 ────────────────────────────────────────
        def _load_file(fname):
            p = _data_dir / fname
            if not p.exists():
                return []
            try:
                return json.loads(p.read_text(encoding="utf-8")).get("lessons", [])
            except Exception:
                return []

        f_lessons = _load_file("lessons_failure.json")
        s_lessons = _load_file("lessons_strength.json")
        r_lessons = _load_file("lessons_regime.json")
        all_lessons = f_lessons + s_lessons + r_lessons

        # 레거시 파일 fallback
        if not all_lessons:
            data = load_lessons()
            all_lessons = data.get("lessons", [])

        if not all_lessons:
            return send_message("📚 <b>학습 현황</b>\n\n아직 누적된 교훈이 없습니다.")

        last_updated = max((l.get("date","") for l in all_lessons), default="없음")
        total = len(all_lessons)

        # ── 헤더 + 파일별 분류 요약 ────────────────────────────────
        lines = [
            "📚 <b>" + ORCA_NAME + " 학습 현황 (3-파일 시스템)</b>",
            f"누적 교훈: <b>{total}개</b>",
            f"  🔴 실패: {len(f_lessons)}개 / 🟢 강점: {len(s_lessons)}개 / 🔵 레짐: {len(r_lessons)}개",
            f"마지막 업데이트: {last_updated}", "",
            "━━ 현재 적용 중인 교훈 (상위 8개) ━━",
        ]

        # severity + regime 유사도 기준 정렬
        def _pri(l):
            return (3 if l.get("severity")=="high" else 2 if l.get("severity")=="medium" else 1)
        sorted_lessons = sorted(all_lessons, key=_pri, reverse=True)

        for l in sorted_lessons[:8]:
            em = "🔴" if l.get("severity")=="high" else "🟡" if l.get("severity")=="medium" else "🟢"
            regime_tag = f"[{l.get('regime','')}] " if l.get("regime") else ""
            st = f"적용 {l.get('applied',0)}회"
            if l.get("reinforced",0) > 0:
                st += f" | 반복 {l['reinforced']}회"
            lines += [
                f"{em} <b>[{l.get('category','')}]</b> {regime_tag}{l.get('source','')} {l.get('date','')}",
                f"  {l.get('lesson','')[:70]}",
                f"  <i>{st}</i>", "",
            ]

        # ── 카테고리별 집계 ────────────────────────────────────────
        cats = {}
        for l in all_lessons:
            cats[l.get("category","기타")] = cats.get(l.get("category","기타"), 0) + 1
        if cats:
            lines.append("━━ 카테고리별 교훈 수 ━━")
            for cat, cnt in sorted(cats.items(), key=lambda x: x[1], reverse=True):
                bar = "█" * min(cnt, 5) + "░" * (5 - min(cnt, 5))
                lines.append(f"<code>{cat.ljust(8)} [{bar}] {cnt}개</code>")

        lines += ["", "<i>교훈은 매일 새벽 자동 추출되어 아침 분석에 반영됩니다</i>"]
        return send_message("\n".join(lines))
    except Exception as e:
        return send_message(f"오류: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY
# ══════════════════════════════════════════════════════════════════════════════
def send_weekly_report():
    now      = _now()
    week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")

    memory    = _load(MEMORY_FILE, [])
    accuracy  = _load(ACCURACY_FILE, {})
    sentiment = _load(SENTIMENT_FILE, {})

    wm  = [m for m in (memory if isinstance(memory,list) else []) if m.get("analysis_date","") >= week_ago]
    wa  = [h for h in accuracy.get("history",[]) if h.get("date","") >= week_ago]
    ws  = [h for h in sentiment.get("history",[]) if h.get("date","") >= week_ago]
    all_hist = accuracy.get("history",[])
    s_hist   = sentiment.get("history",[])

    total   = sum(h.get("total",0) for h in wa)
    correct = sum(h.get("correct",0) for h in wa)
    week_acc = _format_accuracy_display(correct, total)
    prev_acc = _format_accuracy_display(0, 0)
    if len(all_hist) >= 14:
        pw = all_hist[-14:-7]
        pt, pc = sum(h.get("total",0) for h in pw), sum(h.get("correct",0) for h in pw)
        prev_acc = _format_accuracy_display(pc, pt)

    sc = [h.get("score",50) for h in ws]
    sent_avg  = round(sum(sc)/len(sc),1) if sc else 50
    prev_sent = 50
    if len(s_hist) >= 14:
        ps = [h.get("score",50) for h in s_hist[-14:-7]]
        prev_sent = round(sum(ps)/len(ps),1) if ps else 50

    day_names = ["월","화","수","목","금","토","일"]
    bar_parts = []
    for h in ws[-7:]:
        try:
            d   = datetime.strptime(h.get("date",""), "%Y-%m-%d")
            day = day_names[d.weekday()]
        except Exception:
            day = h.get("date","")[-2:]
        bar_parts.append(day + " " + str(h.get("score",50)) + h.get("emoji","😐"))
    sent_bar = "  ".join(bar_parts) if bar_parts else "데이터 없음"

    regimes = [m.get("market_regime","") for m in wm]
    dom_reg = max(set(regimes), key=regimes.count) if regimes else "데이터 없음"

    risk_counts = {}
    for m in wm:
        lv = ("높음" if "회피" in m.get("market_regime","") or "하락" in m.get("trend_phase","")
              else "낮음" if "선호" in m.get("market_regime","") or "상승" in m.get("trend_phase","")
              else "보통")
        risk_counts[lv] = risk_counts.get(lv, 0) + 1

    acc_chg = None
    if week_acc["has_data"] and prev_acc["has_data"]:
        acc_chg = round(float(week_acc["pct"]) - float(prev_acc["pct"]), 1)
    sent_chg = round(sent_avg - prev_sent, 1)
    lines = [
        "<b>📊 " + ORCA_NAME + " 주간 성장 리포트</b>",
        "<code>" + now.strftime("%Y-%m-%d") + " (주간)</code>", "",
        "━━ 이번 주 예측 성과 ━━",
        ("📈" if acc_chg and acc_chg > 0 else "📉" if acc_chg and acc_chg < 0 else "➡️")
        + " 정확도: <b>" + str(week_acc["pct_text"]) + "</b>",
    ]
    if week_acc["has_data"]:
        if prev_acc["has_data"] and acc_chg is not None:
            lines.append(
                "   지난주 "
                + str(prev_acc["pct_text"])
                + " → "
                + ("+" if acc_chg >= 0 else "")
                + str(acc_chg)
                + "%p"
            )
        else:
            lines.append("   지난주 N/A → 비교 불가")
        lines.append("   적중: " + str(week_acc["count_text"]))
    else:
        lines.append("   검증 데이터 없음")
    lines.append("")
    strong = accuracy.get("strong_areas",[])
    weak   = accuracy.get("weak_areas",[])
    if strong:
        lines.append("━━ 잘 맞추는 분야 ━━")
        for s in strong[:3]: lines.append("✅ " + s)
        lines.append("")
    if weak:
        lines.append("━━ 아직 약한 분야 ━━")
        for w in weak[:3]: lines.append("❌ " + w)
        lines.append("")
    lines += [
        "━━ 감정지수 추이 ━━",
        "<code>" + sent_bar + "</code>",
        "평균: " + str(sent_avg) + " (지난주 대비 " + ("+" if sent_chg >= 0 else "") + str(sent_chg) + ")", "",
        "━━ 포트폴리오 위험 흐름 ━━",
        "지배 레짐: " + dom_reg,
    ]
    for lv, cnt in risk_counts.items():
        em = "🔴" if lv == "높음" else "🟢" if lv == "낮음" else "🟡"
        lines.append(em + " " + lv + ": " + str(cnt) + "일")
    lines += ["", "<code>" + ORCA_NAME + " — 누적 " + str(len(memory if isinstance(memory,list) else [])) + "일째 성장 중</code>"]
    send_message("\n".join(lines))
    print("Weekly report sent")


# ══════════════════════════════════════════════════════════════════════════════
# MONTHLY
# ══════════════════════════════════════════════════════════════════════════════
def send_monthly_report():
    now         = _now()
    last_month  = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    memory    = _load(MEMORY_FILE, [])
    accuracy  = _load(ACCURACY_FILE, {})
    sentiment = _load(SENTIMENT_FILE, {})
    rotation  = _load(ROTATION_FILE, {})

    mm = [m for m in (memory if isinstance(memory,list) else []) if m.get("analysis_date","").startswith(last_month)]
    ma = [h for h in accuracy.get("history",[]) if h.get("date","").startswith(last_month)]
    ms = [h for h in sentiment.get("history",[]) if h.get("date","").startswith(last_month)]

    total   = sum(h.get("total",0) for h in ma)
    correct = sum(h.get("correct",0) for h in ma)
    month_acc = _format_accuracy_display(correct, total)

    regimes = [m.get("market_regime","") for m in mm]
    reg_cnt = {}
    for r in regimes: reg_cnt[r] = reg_cnt.get(r, 0) + 1
    trends  = [m.get("trend_phase","") for m in mm]
    trn_cnt = {}
    for t in trends: trn_cnt[t] = trn_cnt.get(t, 0) + 1

    sc       = [h.get("score",50) for h in ms]
    sent_avg = round(sum(sc)/len(sc),1) if sc else 50
    sent_min = min(sc) if sc else 50
    sent_max = max(sc) if sc else 50
    min_day  = ms[sc.index(sent_min)].get("date","") if sc else ""
    max_day  = ms[sc.index(sent_max)].get("date","") if sc else ""

    ranking = rotation.get("ranking",[])
    t_all   = _load(ACCURACY_FILE,{}).get("total",0)
    c_all   = _load(ACCURACY_FILE,{}).get("correct",0)
    cumulative_acc = _format_accuracy_display(c_all, t_all)

    lines = [
        "<b>📊 " + ORCA_NAME + " " + last_month + " 월간 리포트</b>", "",
        "━━ 이달의 분석 성과 ━━",
        "분석 일수: <b>" + str(len(mm)) + "일</b>",
        ("📈" if month_acc["has_data"] and float(month_acc["pct"]) >= 65 else "📉" if month_acc["has_data"] and float(month_acc["pct"]) < 50 else "➡️")
        + " 예측 정확도: <b>" + str(month_acc["pct_text"]) + "</b>",
        "   " + str(month_acc["count_text"]),
        "누적 정확도: " + str(cumulative_acc["pct_text"]), "",
        "━━ 이달의 시장 특성 ━━",
        "지배 레짐: <b>" + (max(reg_cnt, key=reg_cnt.get) if reg_cnt else "") + "</b>",
        "분포: " + " | ".join(k + " " + str(v) + "일" for k, v in reg_cnt.items()),
        "추세: " + " | ".join(k + " " + str(v) + "일" for k, v in trn_cnt.items()), "",
        "━━ 감정지수 ━━",
        "평균: <b>" + str(sent_avg) + "</b>",
        "최저: " + str(sent_min) + " (" + min_day + ")",
        "최고: " + str(sent_max) + " (" + max_day + ")", "",
        "━━ 섹터 로테이션 ━━",
    ]
    if ranking:
        lines.append("🔥 강세: " + " > ".join(r[0] for r in ranking[:3]))
        lines.append("❄️ 약세: " + " > ".join(r[0] for r in ranking[-3:]))
    strong = _load(ACCURACY_FILE,{}).get("strong_areas",[])
    weak   = _load(ACCURACY_FILE,{}).get("weak_areas",[])
    lines += ["", "━━ " + ORCA_NAME + " 성장 현황 ━━"]
    if strong: lines.append("💪 강점: " + ", ".join(strong[:3]))
    if weak:   lines.append("📚 개선중: " + ", ".join(weak[:3]))
    lines += ["", "<code>" + ORCA_NAME + " 누적 분석 " + str(len(memory if isinstance(memory,list) else [])) + "일 | 계속 성장 중</code>"]
    send_message("\n".join(lines))
    print("Monthly report sent for " + last_month)


# ══════════════════════════════════════════════════════════════════════════════
# BREAKING NEWS
# ══════════════════════════════════════════════════════════════════════════════
_BREAKING_SYS = """You are a financial breaking news detector.
Search for urgent financial news from the last 2 hours.
Return ONLY valid JSON. No markdown.
{"has_breaking":true,"breaking_news":[{"headline":"","severity":"critical/high/medium","impact":"","affected_assets":[],"source_hint":""}],"summary":""}"""


def check_breaking_news():
    now_str   = _now().strftime("%Y-%m-%d %H:%M")
    today_str = _today()
    sent      = _load(BREAKING_FILE, {"sent_today":[], "last_check":""})
    today_sent = [s for s in sent.get("sent_today",[]) if s.startswith(today_str)]
    if len(today_sent) >= 5:
        print("Daily breaking news limit reached (5)"); return

    print("Checking breaking news at " + now_str)
    full = ""
    with client.messages.stream(
        model=MODEL_S, max_tokens=1000, system=_BREAKING_SYS,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user",
                   "content": "Search major financial breaking news in last 2 hours: " + now_str + ". Return JSON."}]
    ) as s:
        for ev in s:
            if getattr(ev, "type", "") == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type", "") == "text_delta":
                    full += d.text

    if not full.strip(): return
    m = re.search(r"\{[\s\S]*\}", re.sub(r"```json|```","",full).strip())
    if not m: return
    try:
        data = json.loads(m.group())
    except Exception: return
    if not data.get("has_breaking"): print("No breaking news"); return

    new_alerts = []
    for news in data.get("breaking_news", []):
        headline = news.get("headline","")
        if news.get("severity") not in ["critical","high"]: continue
        if any(headline[:30] in s for s in sent.get("sent_today",[])):  continue
        new_alerts.append(news)

    if not new_alerts: print("No new high/critical news"); return

    for news in new_alerts:
        em  = "🚨" if news.get("severity") == "critical" else "⚠️"
        aff = ", ".join(news.get("affected_assets",[]))
        lines = [em + " <b>" + ORCA_NAME + " 긴급 속보</b>", "<code>" + now_str + "</code>", "",
                 "<b>" + news.get("headline","") + "</b>", "",
                 "영향: " + news.get("impact","")]
        if aff: lines.append("관련 자산: " + aff)
        send_message("\n".join(lines))
        print("Breaking alert: " + news.get("headline","")[:50])
        sent.setdefault("sent_today",[]).append(today_str + " " + news.get("headline","")[:30])

    sent["last_check"] = now_str
    _save(BREAKING_FILE, sent)


# ══════════════════════════════════════════════════════════════════════════════
# CALENDAR
# ══════════════════════════════════════════════════════════════════════════════
_CALENDAR_SYS = """You are a financial calendar agent.
Search for this week's major economic events and data releases.
Focus on: US FOMC/CPI/NFP, Korea BOK, major semiconductor earnings, geopolitical events.
Return ONLY valid JSON. No markdown.
{"week_start":"YYYY-MM-DD","week_end":"YYYY-MM-DD","events":[{"date":"","day":"월/화/수/목/금","time":"","event":"","importance":"high/medium/low","expected":"","previous":"","market_impact":"","affected_assets":[]}],"week_summary":"","key_watch":""}"""


def send_calendar_report():
    week_str = _now().strftime("%Y-%m-%d")
    print("Fetching economic calendar for week of " + week_str)

    full = ""
    with client.messages.stream(
        model=MODEL_S, max_tokens=2000, system=_CALENDAR_SYS,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user",
                   "content": "Search economic calendar events for week of " + week_str + ". Include US and Korea. Return JSON."}]
    ) as s:
        for ev in s:
            t = getattr(ev, "type", "")
            if t == "content_block_start":
                blk = getattr(ev, "content_block", None)
                if blk and getattr(blk, "type","") == "tool_use":
                    print("  Search: " + getattr(blk, "input", {}).get("query",""))
            elif t == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type","") == "text_delta":
                    full += d.text

    raw = re.sub(r"```json|```","",full).strip()
    m   = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        print("No calendar JSON"); return {}
    try:
        cal = re.sub(r",\s*([}\]])", r"\1", m.group())
        cal += "]" * (cal.count("[") - cal.count("]"))
        cal += "}" * (cal.count("{") - cal.count("}"))
        calendar = json.loads(cal)
    except Exception as e:
        print("Calendar parse error: " + str(e)); return {}

    events      = calendar.get("events", [])
    high_events = [e for e in events if e.get("importance") == "high"]
    other       = [e for e in events if e.get("importance") != "high"]

    lines = [
        "<b>📅 이번 주 경제 캘린더</b>",
        "<code>" + calendar.get("week_start","") + " ~ " + calendar.get("week_end","") + "</code>", "",
        "<b>" + calendar.get("week_summary","") + "</b>", "",
        "━━ 핵심 이벤트 ━━",
    ]
    for e in high_events[:6]:
        lines += ["🔴 <b>[" + e.get("day","") + "] " + e.get("event","") + "</b>",
                  "   " + e.get("time","") + " | " + e.get("market_impact","")[:50]]
        if e.get("expected"): lines.append("   예상: " + e["expected"])
    if other:
        lines += ["", "━━ 기타 일정 ━━"]
        for e in other[:4]: lines.append("⚪ [" + e.get("day","") + "] " + e.get("event",""))
    if calendar.get("key_watch"):
        lines += ["", "👀 <b>이번 주 핵심 관전 포인트</b>", "<i>" + calendar["key_watch"] + "</i>"]

    send_message("\n".join(lines))
    print("Calendar report sent")
    return calendar


# ══════════════════════════════════════════════════════════════════════════════
# 직접 실행
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "weekly":    send_weekly_report()
    elif cmd == "monthly": send_monthly_report()
    elif cmd == "breaking": check_breaking_news()
    elif cmd == "calendar": send_calendar_report()
    else:
        ok = send_message("✅ " + ORCA_NAME + " 텔레그램 연결 성공!", reply_markup=make_buttons())
        print("OK" if ok else "FAIL")


