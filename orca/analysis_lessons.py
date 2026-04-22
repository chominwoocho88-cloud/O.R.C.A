"""Lesson extraction and prompt helpers extracted from orca.analysis."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta

import anthropic

from ._analysis_common import _load, _now, _save, _today
from .compat import get_orca_env
from .data import load_market_data
from .paths import LESSONS_FILE


API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = get_orca_env("ORCA_MODEL", os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
client = anthropic.Anthropic(api_key=API_KEY)


def load_lessons() -> dict:
    return _load(LESSONS_FILE, {"lessons": [], "total_lessons": 0, "last_updated": ""})


def add_lesson(source: str, category: str, lesson_text: str, severity: str = "medium"):
    data = load_lessons()
    today = _today()
    existing = next((l for l in data["lessons"] if l["date"] == today and l["category"] == category), None)
    if existing:
        existing["lesson"] += " / " + lesson_text
        existing["reinforced"] = existing.get("reinforced", 0) + 1
    else:
        data["lessons"].append(
            {
                "date": today,
                "source": source,
                "category": category,
                "lesson": lesson_text,
                "severity": severity,
                "applied": 0,
                "reinforced": 0,
            }
        )
        data["total_lessons"] += 1

    data["lessons"] = sorted(data["lessons"], key=lambda x: x["date"], reverse=True)[:60]
    data["last_updated"] = today
    _save(LESSONS_FILE, data)


def get_active_lessons(max_lessons: int = 8, current_regime: str = "") -> list:
    """
    [Updated] 3개 파일에서 교훈을 읽고 regime + severity 기반으로 우선순위 결정.
    라이브 시스템용: current_date 필터 없음 (모든 교훈이 과거).
    """
    _data_dir = LESSONS_FILE.parent

    REGIME_SIM = {
        "위험선호": {"위험선호", "전환중", "혼조"},
        "위험회피": {"위험회피", "전환중", "혼조"},
        "전환중": {"전환중", "위험선호", "위험회피", "혼조"},
        "혼조": {"혼조", "전환중", "위험선호", "위험회피"},
    }
    similar = REGIME_SIM.get(current_regime, set())

    today = _today()
    expiry = {"high": 45, "medium": 21, "low": 10}

    def _is_active(l: dict) -> bool:
        days = expiry.get(l.get("severity", "medium"), 21)
        try:
            return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(l["date"], "%Y-%m-%d")).days <= days
        except Exception:
            return True

    def _priority(l: dict) -> float:
        sev_w = {"high": 3.0, "medium": 2.0, "low": 0.5}.get(l.get("severity", "medium"), 1.0)
        if similar and l.get("regime", "") in similar:
            sev_w *= 1.4
        return sev_w + l.get("reinforced", 0) * 0.3

    all_lessons: list = []

    for fname in ("lessons_failure.json", "lessons_strength.json", "lessons_regime.json"):
        try:
            path = _data_dir / fname
            data = _load(path, {"lessons": []})
            for l in data.get("lessons", []):
                if _is_active(l):
                    all_lessons.append(l)
        except Exception:
            pass

    if not all_lessons:
        data = load_lessons()
        all_lessons = [l for l in data.get("lessons", []) if _is_active(l)]

    ranked = sorted(all_lessons, key=_priority, reverse=True)

    top = ranked[:max_lessons]
    try:
        legacy = load_lessons()
        for l in legacy.get("lessons", []):
            if any(l.get("lesson") == t.get("lesson") for t in top):
                l["applied"] = l.get("applied", 0) + 1
        _save(LESSONS_FILE, legacy)
    except Exception:
        pass

    return top


def build_lessons_prompt(max_lessons: int = 6, current_regime: str = "") -> str:
    """
    라이브 시스템용 교훈 프롬프트 빌더.
    regime 기반으로 우선 교훈을 선택하고, VIX/환율 TK 금지 지시를 포함.
    """
    lessons = get_active_lessons(max_lessons, current_regime=current_regime)
    lines = []

    if lessons:
        lines.append("[과거 교훈 — 반드시 반영]")
        for l in lessons:
            sev = "🔴" if l.get("severity") == "high" else "🟡" if l.get("severity") == "medium" else "🟢"
            regime_tag = f"[{l.get('regime','')}] " if l.get("regime") else ""
            lines.append(f"{sev} [{l.get('category','')}] {regime_tag}{l.get('lesson','')[:80]}")
        lines.append("")

    lines.append(
        "🚫 [thesis_killer 필수 규칙] "
        "VIX와 원달러 환율은 thesis_killer 주제로 절대 사용 금지. "
        "나스닥·코스피·반도체(SK하이닉스·삼성전자·엔비디아) 주가 수치만 사용할 것."
    )

    return "\n".join(lines) + "\n\n"


def extract_dawn_lessons(today_analyses: list, actual_news: str):
    if not today_analyses:
        print("No analyses to review")
        return

    try:
        market_data = load_market_data()
    except Exception:
        market_data = {}

    local_lessons = _local_lesson_check(today_analyses, market_data)
    for l in local_lessons:
        add_lesson("dawn", l["category"], l["lesson"], l["severity"])
        print("Local lesson: [" + l["category"] + "] " + l["lesson"][:50])

    summary = [
        {
            "time": a.get("analysis_time", ""),
            "regime": a.get("market_regime", ""),
            "trend": a.get("trend_phase", ""),
            "one_line": a.get("one_line_summary", ""),
            "thesis_killers": a.get("thesis_killers", [])[:2],
        }
        for a in today_analyses
    ]

    market_snapshot = {
        k: market_data.get(k, "N/A")
        for k in [
            "vix",
            "kospi",
            "kospi_change",
            "krw_usd",
            "fear_greed_value",
            "fear_greed_rating",
            "nvda_change",
        ]
    }

    _DAWN_LESSON_SYS = """You are ARIA's self-reflection engine.
Compare today's predictions against actual market data.
Return JSON: {"has_lessons": true/false, "lessons": [{"category":"","lesson":"","severity":"high/medium/low"}]}"""

    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=800,
        system=_DAWN_LESSON_SYS,
        messages=[
            {
                "role": "user",
                "content": "오늘 실제 시장 데이터:\n"
                + json.dumps(market_snapshot, ensure_ascii=False)
                + "\n\nARIA 예측:\n"
                + json.dumps(summary, ensure_ascii=False)
                + "\n\n로컬에서 이미 감지한 오판: "
                + str(len(local_lessons))
                + "개"
                + "\n\n추가로 놓친 오판이 있으면 JSON으로 반환. 없으면 has_lessons:false.",
            }
        ],
    ) as s:
        for ev in s:
            t = getattr(ev, "type", "")
            if t == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type", "") == "text_delta":
                    full += d.text

    raw = re.sub(r"```json|```", "", full).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return
    try:
        data = json.loads(m.group())
        if data.get("has_lessons"):
            for l in data.get("lessons", []):
                add_lesson("dawn_ai", l.get("category", "기타"), l.get("lesson", ""), l.get("severity", "medium"))
                print("AI lesson: [" + l.get("category", "") + "] " + l.get("lesson", "")[:50])
    except Exception as e:
        print("Dawn lesson 파싱 오류: " + str(e))


def extract_monthly_lessons(memory: list, accuracy: dict) -> list:
    """Persist a small set of monthly review lessons."""
    now = _now()
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    monthly_memory = [
        m for m in (memory if isinstance(memory, list) else []) if str(m.get("analysis_date", "")).startswith(last_month)
    ]
    monthly_hist = [
        h for h in (accuracy.get("history", []) if isinstance(accuracy, dict) else []) if str(h.get("date", "")).startswith(last_month)
    ]
    monthly_by_cat = [
        h
        for h in (accuracy.get("history_by_category", []) if isinstance(accuracy, dict) else [])
        if str(h.get("date", "")).startswith(last_month)
    ]

    if not monthly_memory and not monthly_hist:
        print("No monthly data to review")
        return []

    lessons = []

    total = sum(int(h.get("total", 0)) for h in monthly_hist)
    correct = sum(int(h.get("correct", 0)) for h in monthly_hist)
    if total >= 5:
        acc_pct = round(correct / total * 100, 1) if total else 0.0
        if acc_pct < 55:
            lessons.append(
                {
                    "category": "monthly_accuracy",
                    "lesson": (
                        f"Monthly review {last_month}: accuracy fell to {acc_pct}%. "
                        "Reduce strong directional conviction until thesis killers and data quality agree."
                    ),
                    "severity": "high",
                }
            )
        elif acc_pct >= 70:
            lessons.append(
                {
                    "category": "monthly_strength",
                    "lesson": (
                        f"Monthly review {last_month}: accuracy reached {acc_pct}%. "
                        "Keep the regime filters that worked, but do not treat one good month as a permanent edge."
                    ),
                    "severity": "low",
                }
            )

    by_cat = {}
    for snap in monthly_by_cat:
        for cat, stats in snap.get("by_category", {}).items():
            bucket = by_cat.setdefault(cat, {"correct": 0, "total": 0})
            bucket["correct"] += int(stats.get("correct", 0))
            bucket["total"] += int(stats.get("total", 0))

    weak_ranked = []
    for cat, stats in by_cat.items():
        if stats["total"] < 2:
            continue
        cat_acc = stats["correct"] / stats["total"]
        weak_ranked.append((cat_acc, cat, stats))
    weak_ranked.sort(key=lambda x: x[0])
    if weak_ranked and weak_ranked[0][0] <= 0.45:
        cat_acc, cat, stats = weak_ranked[0]
        lessons.append(
            {
                "category": "monthly_weakness",
                "lesson": (
                    f"Monthly review {last_month}: category '{cat}' produced only "
                    f"{cat_acc:.0%} accuracy across {stats['total']} checks. "
                    "Treat it as weak evidence until new validation improves it."
                ),
                "severity": "high" if cat_acc < 0.35 else "medium",
            }
        )

    high_conf_calls = sum(
        1 for item in monthly_memory if str(item.get("confidence_overall", "")).strip().lower() in {"high", "높음"}
    )
    if total >= 5 and high_conf_calls >= max(3, len(monthly_memory) // 2) and correct / max(total, 1) < 0.6:
        lessons.append(
            {
                "category": "monthly_risk",
                "lesson": (
                    f"Monthly review {last_month}: high-confidence calls were too frequent "
                    "relative to realized accuracy. Tighten confidence calibration before issuing strong conviction."
                ),
                "severity": "medium",
            }
        )

    persisted = []
    for lesson in lessons[:3]:
        add_lesson("monthly", lesson["category"], lesson["lesson"], lesson["severity"])
        persisted.append(lesson)
        print("Monthly lesson: [" + lesson["category"] + "] " + lesson["lesson"][:80])

    return persisted


def _local_lesson_check(analyses: list, market_data: dict) -> list:
    lessons = []
    vix = market_data.get("vix")
    sp_chg = market_data.get("sp500_change", "0")
    try:
        sp_chg_f = float(str(sp_chg).replace("%", "").replace("+", ""))
    except Exception:
        sp_chg_f = 0.0

    for a in analyses:
        regime = a.get("market_regime", "")
        conf = a.get("confidence_overall", "")

        if "선호" in regime and sp_chg_f < -2:
            lessons.append(
                {
                    "category": "시장레짐",
                    "lesson": f"위험선호 예측 중 S&P {sp_chg_f:+.1f}% 급락 — 레짐 판단 재검토",
                    "severity": "high",
                }
            )
        if vix and conf == "높음":
            try:
                vix_f = float(str(vix).replace(",", ""))
                if vix_f > 30:
                    lessons.append(
                        {
                            "category": "변동성지수",
                            "lesson": f"VIX {vix_f:.0f} 고공포 구간에서 높음 신뢰도 — 과신 주의",
                            "severity": "medium",
                        }
                    )
            except Exception:
                pass
    return lessons
