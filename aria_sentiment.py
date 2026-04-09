import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST            = timezone(timedelta(hours=9))
SENTIMENT_FILE = Path("sentiment.json")


def now_kst():
    return datetime.now(KST)


def calculate_sentiment(report):
    score = 50

    regime     = report.get("market_regime", "")
    trend      = report.get("trend_phase", "")
    vi         = report.get("volatility_index", {})
    outflows   = report.get("outflows", [])
    inflows    = report.get("inflows", [])
    counters   = report.get("counterarguments", [])

    if "선호" in regime:
        score += 15
    elif "회피" in regime:
        score -= 15

    if "상승" in trend:
        score += 10
    elif "하락" in trend:
        score -= 10

    vix_level = vi.get("level", "")
    if "극단공포" in vix_level:
        score -= 20
    elif "공포" in vix_level:
        score -= 10
    elif "극단탐욕" in vix_level:
        score += 20
    elif "탐욕" in vix_level:
        score += 10

    if len(inflows) > len(outflows):
        score += 5
    elif len(outflows) > len(inflows):
        score -= 5

    high_risk = sum(1 for c in counters if c.get("risk_level") == "높음")
    score -= high_risk * 3

    score = max(0, min(100, score))

    if score <= 20:
        level = "극단공포"
        emoji = "😱"
    elif score <= 40:
        level = "공포"
        emoji = "😰"
    elif score <= 60:
        level = "중립"
        emoji = "😐"
    elif score <= 80:
        level = "탐욕"
        emoji = "😏"
    else:
        level = "극단탐욕"
        emoji = "🤑"

    return {
        "date":      now_kst().strftime("%Y-%m-%d"),
        "score":     score,
        "level":     level,
        "emoji":     emoji,
        "regime":    regime,
        "trend":     trend,
        "vix_level": vix_level,
    }


def analyze_trend(history):
    if len(history) < 2:
        return {"direction": "neutral", "change": 0, "avg_7d": 50}

    recent = history[-7:]
    scores = [h["score"] for h in recent]

    half      = len(scores) // 2
    first_avg = sum(scores[:half]) / max(half, 1)
    second_avg = sum(scores[half:]) / max(len(scores) - half, 1)
    change    = round(second_avg - first_avg, 1)

    if change > 5:
        direction = "improving"
    elif change < -5:
        direction = "deteriorating"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "change":    change,
        "avg_7d":    round(sum(scores) / len(scores), 1),
        "min_7d":    min(scores),
        "max_7d":    max(scores),
    }


def load_sentiment():
    if SENTIMENT_FILE.exists():
        return json.loads(SENTIMENT_FILE.read_text(encoding="utf-8"))
    return {"history": [], "current": None}


def save_sentiment(data):
    SENTIMENT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_sentiment(report):
    data    = load_sentiment()
    today   = calculate_sentiment(report)
    history = data.get("history", [])

    history = [h for h in history if h["date"] != today["date"]]
    history.append(today)
    history = history[-90:]

    trend = analyze_trend(history)
    data  = {"history": history, "current": today, "trend": trend}
    save_sentiment(data)
    return data


def make_ascii_chart(history, days=14):
    recent = history[-days:]
    if not recent:
        return "No data"
    lines = []
    for h in recent:
        score     = h["score"]
        bar_len   = int(score / 5)
        bar       = "#" * bar_len
        date_short = h["date"][5:]
        lines.append(date_short + " [" + bar.ljust(20) + "] " + str(score) + " " + h["emoji"])
    return "\n".join(lines)


def send_sentiment_report(data):
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    current = data.get("current", {})
    trend   = data.get("trend", {})
    history = data.get("history", [])

    score = current.get("score", 50)
    level = current.get("level", "")
    emoji = current.get("emoji", "")

    if trend.get("direction") == "improving":
        arrow = "up"
    elif trend.get("direction") == "deteriorating":
        arrow = "down"
    else:
        arrow = "stable"

    chart = make_ascii_chart(history)

    lines = [
        "<b>" + emoji + " ARIA 시장 감정지수</b>",
        "<code>" + current.get("date", "") + "</code>",
        "",
        "오늘 점수: <b>" + str(score) + "/100</b> (" + level + ")",
        "7일 평균: " + str(trend.get("avg_7d", "-")) + " [" + arrow + "]",
        "7일 변화: " + str(trend.get("change", 0)) + "점",
        "",
        "<pre>" + chart + "</pre>",
    ]

    if score <= 25:
        lines += ["", "<i>극단 공포 구간 - 역사적으로 분할매수 기회</i>"]
    elif score >= 75:
        lines += ["", "<i>극단 탐욕 구간 - 리스크 관리 주의</i>"]

    send_message("\n".join(lines))
    print("Sentiment report sent")


def run_sentiment(report):
    data = update_sentiment(report)
    send_sentiment_report(data)
    return data


if __name__ == "__main__":
    test = {
        "market_regime": "위험회피",
        "trend_phase": "하락추세",
        "volatility_index": {"level": "공포"},
        "outflows": [{}, {}, {}],
        "inflows": [{}],
        "counterarguments": [{"risk_level": "높음"}],
    }
    result = run_sentiment(test)
    print("Score: " + str(result["current"]["score"]) + " / " + result["current"]["level"])
