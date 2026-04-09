import os
import sys
import json
import re
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST          = timezone(timedelta(hours=9))
LESSONS_FILE = Path("aria_lessons.json")
MEMORY_FILE  = Path("memory.json")
API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL        = "claude-sonnet-4-6"

client = anthropic.Anthropic(api_key=API_KEY)


# ── 로드/저장 ──────────────────────────────────────────────────────────────────
def load_lessons():
    if LESSONS_FILE.exists():
        return json.loads(LESSONS_FILE.read_text(encoding="utf-8"))
    return {
        "lessons": [],
        "total_lessons": 0,
        "last_updated": "",
    }


def save_lessons(data):
    LESSONS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_lesson(source, category, lesson_text, severity="medium"):
    """새로운 교훈 추가"""
    data   = load_lessons()
    today  = datetime.now(KST).strftime("%Y-%m-%d")

    # 중복 체크 (같은 날, 같은 카테고리 교훈은 합치기)
    existing = next(
        (l for l in data["lessons"]
         if l["date"] == today and l["category"] == category),
        None
    )
    if existing:
        existing["lesson"] += " / " + lesson_text
        existing["reinforced"] = existing.get("reinforced", 0) + 1
    else:
        data["lessons"].append({
            "date":       today,
            "source":     source,      # dawn / weekly / monthly
            "category":   category,    # 지정학 / 레짐판단 / VIX / 섹터 등
            "lesson":     lesson_text,
            "severity":   severity,    # high / medium / low
            "applied":    0,
            "reinforced": 0,
        })
        data["total_lessons"] += 1

    # 최근 60개만 보존 (오래된 것 제거)
    data["lessons"] = sorted(
        data["lessons"], key=lambda x: x["date"], reverse=True
    )[:60]
    data["last_updated"] = today
    save_lessons(data)


def get_active_lessons(max_lessons=8):
    """오늘 분석에 주입할 교훈 목록 반환 (최신 + 반복된 것 우선)"""
    data    = load_lessons()
    lessons = data.get("lessons", [])
    if not lessons:
        return []

    # 심각도 + 반복 횟수로 정렬
    def priority(l):
        sev_score = 3 if l["severity"] == "high" else 2 if l["severity"] == "medium" else 1
        return sev_score * 2 + l.get("reinforced", 0)

    sorted_lessons = sorted(lessons, key=priority, reverse=True)

    # 적용 횟수 증가
    for l in sorted_lessons[:max_lessons]:
        l["applied"] = l.get("applied", 0) + 1
    save_lessons(data)

    return sorted_lessons[:max_lessons]


def build_lessons_prompt():
    """시스템 프롬프트에 주입할 교훈 텍스트 생성"""
    lessons = get_active_lessons()
    if not lessons:
        return ""

    lines = ["\n\n## ARIA 과거 실수 교훈 (반드시 반영)"]
    lines.append("아래는 과거 분석에서 틀렸던 것들입니다. 이번 분석에서 같은 실수를 반복하지 마세요:\n")

    for i, l in enumerate(lessons, 1):
        sev_mark = "!!!" if l["severity"] == "high" else "!!" if l["severity"] == "medium" else "!"
        lines.append(
            str(i) + ". [" + sev_mark + "] [" + l["category"] + "] " + l["lesson"]
            + " (출처: " + l["source"] + " " + l["date"] + ")"
        )

    return "\n".join(lines)


# ── 새벽 리포트용: 오늘 실수 추출 ─────────────────────────────────────────────
DAWN_LESSON_SYSTEM = """You are ARIA-LessonExtractor.
Compare today's analysis results with what actually happened.
Extract specific lessons learned - what did ARIA predict wrong or miss?

Focus on:
- Wrong regime calls (predicted risk-on but market was risk-off)
- Missed sector moves (predicted outflow but money flowed in)
- VIX/sentiment miscalibration
- Geopolitical misjudgments
- Korea market specific errors

Return ONLY valid JSON. No markdown.
{
  "has_lessons": true/false,
  "lessons": [
    {
      "category": "레짐판단/VIX/섹터/지정학/한국시장/감정지수",
      "lesson": "구체적으로 무엇이 틀렸고 다음에 어떻게 해야 하는가 (한국어, 1-2문장)",
      "severity": "high/medium/low",
      "what_happened": "실제로 무슨 일이 있었나",
      "what_was_predicted": "ARIA가 뭐라고 예측했나"
    }
  ],
  "overall_assessment": "오늘 분석의 전반적 품질 평가"
}"""


def extract_dawn_lessons(today_analyses, actual_news_summary):
    """새벽에 오늘 분석들을 돌아보고 교훈 추출"""
    if not today_analyses:
        print("No analyses to review")
        return

    print("Extracting lessons from today's analyses...")

    # 오늘 분석들 요약
    analyses_summary = []
    for a in today_analyses:
        analyses_summary.append({
            "time":         a.get("analysis_time", ""),
            "regime":       a.get("market_regime", ""),
            "trend":        a.get("trend_phase", ""),
            "one_line":     a.get("one_line_summary", ""),
            "thesis_killers": a.get("thesis_killers", [])[:2],
        })

    payload = {
        "today_analyses":    analyses_summary,
        "actual_news":       actual_news_summary,
        "analysis_date":     datetime.now(KST).strftime("%Y-%m-%d"),
    }

    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=1500,
        system=DAWN_LESSON_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": (
                "Search for today's actual market outcomes and compare with these ARIA predictions:\n"
                + json.dumps(payload, ensure_ascii=False)
                + "\n\nReturn JSON with lessons learned."
            )
        }]
    ) as s:
        for ev in s:
            t = getattr(ev, "type", "")
            if t == "content_block_start":
                blk = getattr(ev, "content_block", None)
                if blk and getattr(blk, "type", "") == "tool_use":
                    q = getattr(blk, "input", {}).get("query", "")
                    print("  Search: " + q)
            elif t == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type", "") == "text_delta":
                    full += d.text

    raw = re.sub(r"```json|```", "", full).strip()
    m   = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        print("No lessons JSON found")
        return

    try:
        result = json.loads(m.group())
    except:
        print("JSON parse error in lessons")
        return

    if not result.get("has_lessons"):
        print("No lessons to record today")
        return

    for lesson in result.get("lessons", []):
        add_lesson(
            source    = "dawn",
            category  = lesson.get("category", "기타"),
            lesson_text = lesson.get("lesson", ""),
            severity  = lesson.get("severity", "medium"),
        )
        print("Lesson added: [" + lesson.get("category", "") + "] " + lesson.get("lesson", "")[:50])

    return result


# ── 주간 리포트용: 주간 패턴 실수 ─────────────────────────────────────────────
def extract_weekly_lessons(memory_data, accuracy_data):
    """주간 리포트에서 반복 실수 패턴 추출"""
    today    = datetime.now(KST)
    week_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")

    week_analyses = [
        m for m in memory_data
        if isinstance(m, dict) and m.get("analysis_date", "") >= week_ago
    ]
    week_accuracy = [
        h for h in accuracy_data.get("history", [])
        if h.get("date", "") >= week_ago
    ]

    if not week_analyses:
        return

    # 레짐 일관성 체크
    regimes = [a.get("market_regime", "") for a in week_analyses]
    unique_regimes = set(regimes)
    if len(unique_regimes) >= 3:
        add_lesson(
            source     = "weekly",
            category   = "레짐판단",
            lesson_text = "이번 주 레짐 판단이 " + str(len(unique_regimes)) + "번 바뀜. 지정학 이슈가 많을 때는 레짐 판단에 더 보수적 접근 필요.",
            severity   = "medium",
        )

    # 정확도 낮은 카테고리
    by_cat = accuracy_data.get("by_category", {})
    for cat, stats in by_cat.items():
        if stats.get("total", 0) >= 3:
            acc = stats["correct"] / stats["total"]
            if acc < 0.4:
                add_lesson(
                    source     = "weekly",
                    category   = cat,
                    lesson_text = cat + " 예측 정확도 " + str(round(acc*100)) + "% - 이 분야 예측 시 신뢰도를 낮추고 반론을 더 강하게 적용할 것.",
                    severity   = "high",
                )

    print("Weekly lessons extracted")


# ── 월간 리포트용: 구조적 편향 추출 ───────────────────────────────────────────
def extract_monthly_lessons(memory_data, accuracy_data):
    """월간 리포트에서 구조적 편향 추출"""
    today       = datetime.now(KST)
    month_start = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    month_analyses = [
        m for m in memory_data
        if isinstance(m, dict) and m.get("analysis_date", "").startswith(month_start)
    ]

    if not month_analyses:
        return

    # 낙관 편향 체크
    risk_on_count = sum(1 for a in month_analyses if "선호" in a.get("market_regime", ""))
    risk_off_count = sum(1 for a in month_analyses if "회피" in a.get("market_regime", ""))
    total = len(month_analyses)

    if total > 0 and risk_on_count / total > 0.7:
        add_lesson(
            source     = "monthly",
            category   = "레짐판단",
            lesson_text = "지난달 위험선호 판단 비율 " + str(round(risk_on_count/total*100)) + "% - 낙관 편향 주의. 다음 달은 하락 시나리오에 더 무게를.",
            severity   = "high",
        )
    elif total > 0 and risk_off_count / total > 0.7:
        add_lesson(
            source     = "monthly",
            category   = "레짐판단",
            lesson_text = "지난달 위험회피 판단 비율 " + str(round(risk_off_count/total*100)) + "% - 비관 편향 주의. 반등 시그널에도 주목할 것.",
            severity   = "medium",
        )

    # 전체 정확도 기반 편향
    total_acc = accuracy_data.get("total", 0)
    correct   = accuracy_data.get("correct", 0)
    if total_acc >= 10:
        acc = correct / total_acc
        if acc < 0.5:
            add_lesson(
                source     = "monthly",
                category   = "전반",
                lesson_text = "지난달 전체 예측 정확도 " + str(round(acc*100)) + "% - 전반적 과신 주의. Devil 에이전트 반론을 더 강하게 반영할 것.",
                severity   = "high",
            )

    print("Monthly lessons extracted")


# ── 텔레그램 교훈 요약 전송 ────────────────────────────────────────────────────
def send_lessons_summary():
    try:
        from aria_telegram import send_message
    except ImportError:
        return

    data    = load_lessons()
    lessons = data.get("lessons", [])[:8]
    total   = data.get("total_lessons", 0)

    if not lessons:
        return

    lines = [
        "<b>📚 ARIA 학습 교훈 현황</b>",
        "누적 교훈: <b>" + str(total) + "개</b>",
        "",
        "━━ 현재 적용 중인 교훈 ━━",
    ]

    for l in lessons:
        sev_emoji = "🔴" if l["severity"] == "high" else "🟡" if l["severity"] == "medium" else "🟢"
        reinforced = l.get("reinforced", 0)
        reinf_str  = " (반복 " + str(reinforced) + "회)" if reinforced > 0 else ""
        lines.append(sev_emoji + " [" + l["category"] + "] " + l["lesson"][:60] + reinf_str)

    lines += [
        "",
        "<i>이 교훈들이 매일 아침 분석에 자동 반영됩니다</i>",
    ]

    send_message("\n".join(lines))


if __name__ == "__main__":
    # 테스트
    add_lesson("dawn", "지정학", "이란 관련 뉴스는 과대해석 경향 있음. 실제 시장 반응은 절반 수준.", "high")
    add_lesson("weekly", "VIX", "VIX 25 이상일 때 위험선호 레짐 판단 금지.", "high")
    lessons = get_active_lessons()
    print("Active lessons: " + str(len(lessons)))
    prompt = build_lessons_prompt()
    print(prompt[:200])
