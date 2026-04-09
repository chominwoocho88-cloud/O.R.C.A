import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST           = timezone(timedelta(hours=9))
MEMORY_FILE   = Path("memory.json")
ACCURACY_FILE = Path("accuracy.json")
SENTIMENT_FILE = Path("sentiment.json")


def now_kst():
    return datetime.now(KST)


def load_json(path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def get_week_data():
    today = now_kst()
    week_ago = today - timedelta(days=7)
    week_ago_str = week_ago.strftime("%Y-%m-%d")

    memory    = load_json(MEMORY_FILE) if MEMORY_FILE.exists() else []
    accuracy  = load_json(ACCURACY_FILE)
    sentiment = load_json(SENTIMENT_FILE)

    if isinstance(memory, list):
        week_memory = [m for m in memory if m.get("analysis_date", "") >= week_ago_str]
    else:
        week_memory = []

    week_accuracy = [h for h in accuracy.get("history", []) if h.get("date", "") >= week_ago_str]
    week_sentiment = [h for h in sentiment.get("history", []) if h.get("date", "") >= week_ago_str]

    return week_memory, week_accuracy, week_sentiment, accuracy


def analyze_growth(week_memory, week_accuracy, week_sentiment, accuracy):
    result = {}

    # 예측 정확도
    if week_accuracy:
        total = sum(h.get("total", 0) for h in week_accuracy)
        correct = sum(h.get("correct", 0) for h in week_accuracy)
        result["week_accuracy"] = round(correct / total * 100, 1) if total > 0 else 0
        result["week_total"] = total
        result["week_correct"] = correct
    else:
        result["week_accuracy"] = 0
        result["week_total"] = 0
        result["week_correct"] = 0

    # 지난주 정확도 (비교용)
    all_history = accuracy.get("history", [])
    if len(all_history) >= 14:
        prev_week = all_history[-14:-7]
        prev_total = sum(h.get("total", 0) for h in prev_week)
        prev_correct = sum(h.get("correct", 0) for h in prev_week)
        result["prev_accuracy"] = round(prev_correct / prev_total * 100, 1) if prev_total > 0 else 0
    else:
        result["prev_accuracy"] = 0

    result["accuracy_change"] = round(result["week_accuracy"] - result["prev_accuracy"], 1)

    # 강점/약점
    result["strong_areas"] = accuracy.get("strong_areas", [])
    result["weak_areas"]   = accuracy.get("weak_areas", [])

    # 카테고리별 이번주 성과
    cat_stats = {}
    for h in week_accuracy:
        insight = h.get("pattern_insight", "")
        if insight:
            result["latest_insight"] = insight

    result["by_category"] = accuracy.get("by_category", {})

    # 감정지수 추이
    if week_sentiment:
        scores = [h.get("score", 50) for h in week_sentiment]
        result["sentiment_avg"]  = round(sum(scores) / len(scores), 1)
        result["sentiment_min"]  = min(scores)
        result["sentiment_max"]  = max(scores)
        result["sentiment_days"] = week_sentiment
    else:
        result["sentiment_avg"]  = 50
        result["sentiment_min"]  = 50
        result["sentiment_max"]  = 50
        result["sentiment_days"] = []

    # 지난주 감정 평균
    sentiment_all = load_json(SENTIMENT_FILE).get("history", [])
    if len(sentiment_all) >= 14:
        prev_scores = [h.get("score", 50) for h in sentiment_all[-14:-7]]
        result["prev_sentiment_avg"] = round(sum(prev_scores) / len(prev_scores), 1)
    else:
        result["prev_sentiment_avg"] = 50

    result["sentiment_change"] = round(result["sentiment_avg"] - result["prev_sentiment_avg"], 1)

    # 포트폴리오 위험 흐름
    risk_levels = []
    for m in week_memory:
        regime = m.get("market_regime", "")
        trend  = m.get("trend_phase", "")
        date   = m.get("analysis_date", "")
        if "회피" in regime or "하락" in trend:
            risk_levels.append({"date": date, "level": "높음"})
        elif "선호" in regime or "상승" in trend:
            risk_levels.append({"date": date, "level": "낮음"})
        else:
            risk_levels.append({"date": date, "level": "보통"})

    result["risk_levels"] = risk_levels
    high_risk_days = [r for r in risk_levels if r["level"] == "높음"]
    result["most_risky_day"] = high_risk_days[-1]["date"] if high_risk_days else None

    # 레짐 분포
    regimes = [m.get("market_regime", "") for m in week_memory]
    result["dominant_regime"] = max(set(regimes), key=regimes.count) if regimes else "데이터 없음"

    # 누적 분석 일수
    result["total_days"] = len(load_json(MEMORY_FILE)) if MEMORY_FILE.exists() else 0

    return result


def make_sentiment_bar(days):
    if not days:
        return "데이터 없음"
    lines = []
    day_names = ["월", "화", "수", "목", "금", "토", "일"]
    for h in days[-7:]:
        score = h.get("score", 50)
        emoji = h.get("emoji", "😐")
        date  = h.get("date", "")
        try:
            d = datetime.strptime(date, "%Y-%m-%d")
            day = day_names[d.weekday()]
        except:
            day = date[-2:]
        lines.append(day + " " + str(score) + emoji)
    return "  ".join(lines)


def send_weekly_report():
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    week_memory, week_accuracy, week_sentiment, accuracy = get_week_data()
    g = analyze_growth(week_memory, week_accuracy, week_sentiment, accuracy)

    # 정확도 변화 화살표
    acc_arrow = "+" + str(g["accuracy_change"]) if g["accuracy_change"] > 0 else str(g["accuracy_change"])
    acc_emoji = "📈" if g["accuracy_change"] > 0 else "📉" if g["accuracy_change"] < 0 else "➡️"

    # 감정지수 변화
    sent_arrow = "+" + str(g["sentiment_change"]) if g["sentiment_change"] > 0 else str(g["sentiment_change"])

    lines = [
        "<b>📊 ARIA 주간 성장 리포트</b>",
        "<code>" + now_kst().strftime("%Y-%m-%d") + " (주간)</code>",
        "",
        "━━ 이번 주 예측 성과 ━━",
        acc_emoji + " 정확도: <b>" + str(g["week_accuracy"]) + "%</b>",
        "   지난주 " + str(g["prev_accuracy"]) + "% → " + acc_arrow + "%p",
        "   적중: " + str(g["week_correct"]) + "/" + str(g["week_total"]) + "개",
        "",
    ]

    if g["strong_areas"]:
        lines.append("━━ 잘 맞추는 분야 ━━")
        for s in g["strong_areas"][:3]:
            lines.append("✅ " + s)
        lines.append("")

    if g["weak_areas"]:
        lines.append("━━ 아직 약한 분야 ━━")
        for w in g["weak_areas"][:3]:
            lines.append("❌ " + w)
        lines.append("")

    if g.get("latest_insight"):
        lines += [
            "━━ ARIA 자기반성 ━━",
            "<i>" + g["latest_insight"][:100] + "</i>",
            "",
        ]

    # 감정지수 추이
    sent_bar = make_sentiment_bar(g["sentiment_days"])
    lines += [
        "━━ 감정지수 추이 ━━",
        "<code>" + sent_bar + "</code>",
        "평균: " + str(g["sentiment_avg"]) + " (지난주 대비 " + sent_arrow + ")",
        "",
    ]

    # 포트폴리오 위험 흐름
    lines.append("━━ 포트폴리오 위험 흐름 ━━")
    lines.append("지배 레짐: " + g["dominant_regime"])
    if g["most_risky_day"]:
        lines.append("위험 집중일: " + g["most_risky_day"])

    risk_summary = {}
    for r in g["risk_levels"]:
        lv = r["level"]
        risk_summary[lv] = risk_summary.get(lv, 0) + 1
    for lv, cnt in risk_summary.items():
        emoji = "🔴" if lv == "높음" else "🟢" if lv == "낮음" else "🟡"
        lines.append(emoji + " " + lv + ": " + str(cnt) + "일")

    lines += [
        "",
        "<code>ARIA v" + str(g["total_days"]) + " — 누적 " + str(g["total_days"]) + "일째 성장 중</code>",
    ]

    send_message("\n".join(lines))
    print("Weekly report sent")


if __name__ == "__main__":
    send_weekly_report()
