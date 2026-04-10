import os
import sys
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST            = timezone(timedelta(hours=9))
SENTIMENT_FILE = Path("sentiment.json")


def now_kst():
    return datetime.now(KST)


def parse_vix_number(vix_str):
    """VIX 문자열에서 실제 숫자 추출"""
    if not vix_str:
        return None
    m = re.search(r"(\d+\.?\d*)", str(vix_str))
    return float(m.group(1)) if m else None


def get_vix_penalty(vix_val, vkospi_val):
    """VIX/VKOSPI 실제 수치 기반 강제 패널티"""
    penalty = 0
    notes   = []

    if vix_val:
        if vix_val >= 35:
            penalty -= 25
            notes.append("VIX " + str(vix_val) + " 극단공포")
        elif vix_val >= 25:
            penalty -= 15
            notes.append("VIX " + str(vix_val) + " 공포")
        elif vix_val >= 20:
            penalty -= 5
            notes.append("VIX " + str(vix_val) + " 경계")
        elif vix_val <= 15:
            penalty += 10
            notes.append("VIX " + str(vix_val) + " 안정")

    if vkospi_val:
        if vkospi_val >= 50:
            penalty -= 20
            notes.append("VKOSPI " + str(vkospi_val) + " 극단공포")
        elif vkospi_val >= 35:
            penalty -= 12
            notes.append("VKOSPI " + str(vkospi_val) + " 공포")
        elif vkospi_val >= 25:
            penalty -= 5
            notes.append("VKOSPI " + str(vkospi_val) + " 경계")

    return penalty, notes


def calculate_sentiment(report):
    """7개 요소 + VIX 실수치 강제 반영 + 학습 가중치 적용"""

    # 학습 가중치 로드
    try:
        from aria_weights import get_sentiment_weights
        sw = get_sentiment_weights()
    except ImportError:
        sw = {k: 1.0 for k in ["시장레짐","추세방향","변동성지수","자금흐름","반론강도","한국시장","숨은시그널"]}

    regime   = report.get("market_regime", "")
    trend    = report.get("trend_phase", "")
    vi       = report.get("volatility_index", {})
    outflows = report.get("outflows", [])
    inflows  = report.get("inflows", [])
    counters = report.get("counterarguments", [])
    korea    = report.get("korea_focus", {})
    hidden   = report.get("hidden_signals", [])

    components = {}

    # VIX 실제 수치 파싱
    vix_val    = parse_vix_number(vi.get("vix", ""))
    vkospi_val = parse_vix_number(vi.get("vkospi", ""))
    vix_penalty, vix_notes = get_vix_penalty(vix_val, vkospi_val)

    # 1. 시장 레짐 (가중치 적용)
    if "선호" in regime:
        raw = 20
    elif "회피" in regime:
        raw = -20
    elif "전환" in regime:
        raw = 5
    else:
        raw = 0
    # VIX가 공포 구간이면 레짐 긍정 점수 상쇄
    if vix_penalty < -10 and raw > 0:
        raw = raw // 2
    components["시장레짐"] = {
        "score":  round(raw * sw.get("시장레짐", 1.0)),
        "reason": regime[:25] if regime else "데이터없음"
    }

    # 2. 추세 방향
    if "상승" in trend:
        raw = 15
    elif "하락" in trend:
        raw = -15
    else:
        raw = 0
    components["추세방향"] = {
        "score":  round(raw * sw.get("추세방향", 1.0)),
        "reason": trend if trend else "데이터없음"
    }

    # 3. 변동성 지수 (VIX 실수치 우선)
    vix_level = vi.get("level", "")
    if vix_penalty != 0:
        raw    = max(-20, min(20, vix_penalty))
        reason = " / ".join(vix_notes[:2]) if vix_notes else vix_level
    else:
        if "극단공포" in vix_level:
            raw = -20
        elif "공포" in vix_level:
            raw = -10
        elif "극단탐욕" in vix_level:
            raw = 20
        elif "탐욕" in vix_level:
            raw = 10
        else:
            raw = 0
        reason = vix_level if vix_level else "데이터없음"
    components["변동성지수"] = {
        "score":  round(raw * sw.get("변동성지수", 1.5)),
        "reason": reason[:30]
    }

    # 4. 자금 흐름
    out_count  = len(outflows)
    in_count   = len(inflows)
    high_out   = sum(1 for o in outflows if o.get("severity") == "높음")
    strong_in  = sum(1 for i in inflows  if i.get("momentum") == "강함")
    raw        = (strong_in * 5) - (high_out * 5) + (in_count - out_count) * 2
    raw        = max(-15, min(15, raw))
    components["자금흐름"] = {
        "score":  round(raw * sw.get("자금흐름", 1.0)),
        "reason": "유입" + str(in_count) + " / 유출" + str(out_count)
    }

    # 5. 반론 강도
    high_risk = sum(1 for c in counters if c.get("risk_level") == "높음")
    mid_risk  = sum(1 for c in counters if c.get("risk_level") == "보통")
    raw       = -(high_risk * 4 + mid_risk * 2)
    raw       = max(-10, raw)
    components["반론강도"] = {
        "score":  round(raw * sw.get("반론강도", 0.8)),
        "reason": "고위험" + str(high_risk) + " / 중위험" + str(mid_risk)
    }

    # 6. 한국시장
    raw      = 0
    kr_notes = []
    krw      = korea.get("krw_usd", "")
    kospi    = korea.get("kospi_flow", "")
    if "약세" in krw or "하락" in krw:
        raw -= 3
        kr_notes.append("원화약세")
    elif "강세" in krw or "상승" in krw:
        raw += 3
        kr_notes.append("원화강세")
    if "하락" in kospi or "-" in kospi:
        raw -= 4
        kr_notes.append("코스피하락")
    elif "상승" in kospi or "+" in kospi:
        raw += 4
        kr_notes.append("코스피상승")
    raw = max(-10, min(10, raw))
    components["한국시장"] = {
        "score":  round(raw * sw.get("한국시장", 0.8)),
        "reason": ", ".join(kr_notes) if kr_notes else "중립"
    }

    # 7. 숨겨진 시그널
    high_conf = sum(1 for h in hidden if h.get("confidence") == "높음")
    low_conf  = sum(1 for h in hidden if h.get("confidence") == "낮음")
    raw       = (high_conf * 3) - (low_conf * 2)
    raw       = max(-10, min(10, raw))
    components["숨은시그널"] = {
        "score":  round(raw * sw.get("숨은시그널", 0.7)),
        "reason": "고신뢰" + str(high_conf) + " / 저신뢰" + str(low_conf)
    }

    # 총점 계산
    total_delta = sum(c["score"] for c in components.values())
    score       = 50 + total_delta

    # VIX 극단 공포 시 최대 점수 캡
    if vix_val and vix_val >= 25:
        score = min(score, 60)
    if vkospi_val and vkospi_val >= 40:
        score = min(score, 55)

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
        "date":       now_kst().strftime("%Y-%m-%d"),
        "score":      score,
        "level":      level,
        "emoji":      emoji,
        "components": components,
        "regime":     regime,
        "trend":      trend,
        "vix_level":  vix_level,
        "vix_val":    vix_val,
        "vkospi_val": vkospi_val,
    }


def analyze_trend(history):
    if len(history) < 2:
        return {"direction": "neutral", "change": 0, "avg_7d": 50, "min_30d": 50, "max_30d": 50, "avg_30d": 50}

    scores_7d  = [h["score"] for h in history[-7:]]
    scores_30d = [h["score"] for h in history[-30:]]

    half       = len(scores_7d) // 2
    first_avg  = sum(scores_7d[:half]) / max(half, 1)
    second_avg = sum(scores_7d[half:]) / max(len(scores_7d) - half, 1)
    change     = round(second_avg - first_avg, 1)

    if change > 5:
        direction = "improving"
    elif change < -5:
        direction = "deteriorating"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "change":    change,
        "avg_7d":    round(sum(scores_7d) / len(scores_7d), 1),
        "min_30d":   min(scores_30d),
        "max_30d":   max(scores_30d),
        "avg_30d":   round(sum(scores_30d) / len(scores_30d), 1),
    }


def get_percentile(score, history):
    scores = [h["score"] for h in history[-30:]]
    if not scores:
        return 50
    below = sum(1 for s in scores if s <= score)
    return round(below / len(scores) * 100)


def make_component_bar(score, max_val=20):
    abs_s = abs(score)
    bar   = "█" * min(5, round(abs_s / max_val * 5))
    empty = "░" * (5 - len(bar))
    sign  = "+" if score > 0 else ""
    return "[" + bar + empty + "] " + sign + str(score)


def make_history_chart(history, days=10):
    recent = history[-days:]
    if not recent:
        return "No data"
    lines = []
    for h in recent:
        score      = h["score"]
        bar_len    = int(score / 10)
        bar        = "█" * bar_len
        empty      = "░" * (10 - bar_len)
        date_short = h["date"][5:]
        lines.append(date_short + " " + bar + empty + " " + str(score) + h.get("emoji", ""))
    return "\n".join(lines)


def load_sentiment():
    if SENTIMENT_FILE.exists():
        return json.loads(SENTIMENT_FILE.read_text(encoding="utf-8"))
    return {"history": [], "current": None}


def save_sentiment(data):
    SENTIMENT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def update_sentiment(report, market_data=None):
    data    = load_sentiment()
    new     = calculate_sentiment(report, market_data)
    history = data.get("history", [])

    # 같은 날 재실행 시 평균값 사용 (안정화)
    existing = next((h for h in history if h["date"] == new["date"]), None)
    if existing:
        blended_score  = round(existing["score"] * 0.4 + new["score"] * 0.6)
        new["score"]   = blended_score
        # 레벨 재판정
        if blended_score <= 20:   new["level"], new["emoji"] = "극단공포", "😱"
        elif blended_score <= 40: new["level"], new["emoji"] = "공포",     "😰"
        elif blended_score <= 60: new["level"], new["emoji"] = "중립",     "😐"
        elif blended_score <= 80: new["level"], new["emoji"] = "탐욕",     "😏"
        else:                     new["level"], new["emoji"] = "극단탐욕", "🤑"

    history = [h for h in history if h["date"] != new["date"]]
    history.append(new)
    history = history[-90:]

    trend = analyze_trend(history)
    data  = {"history": history, "current": new, "trend": trend}
    save_sentiment(data)
    return data


def send_sentiment_report(data):
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    current    = data.get("current", {})
    trend      = data.get("trend", {})
    history    = data.get("history", [])
    components = current.get("components", {})

    score = current.get("score", 50)
    level = current.get("level", "")
    emoji = current.get("emoji", "")

    if trend.get("direction") == "improving":
        arrow = "↑ 개선중"
    elif trend.get("direction") == "deteriorating":
        arrow = "↓ 악화중"
    else:
        arrow = "→ 안정"

    percentile = get_percentile(score, history)

    comp_lines = []
    for name, info in components.items():
        bar    = make_component_bar(info["score"])
        reason = info["reason"][:18]
        comp_lines.append(name[:5] + " " + bar)
        comp_lines.append("  " + reason)

    chart   = make_history_chart(history)
    min_30  = trend.get("min_30d", score)
    max_30  = trend.get("max_30d", score)
    avg_30  = trend.get("avg_30d", score)

    if score <= 20:   insight = "극단공포 - 분할매수 최적 타이밍"
    elif score <= 35: insight = "공포 - 분할매수 적극 검토"
    elif score <= 50: insight = "공포우위 - 신중한 분할매수"
    elif score <= 65: insight = "중립 - 추세 확인 후 대응"
    elif score <= 80: insight = "탐욕 - 리스크 관리 강화"
    else:             insight = "극단탐욕 - 비중 축소 고려"

    # VIX 캡 적용 여부 표시
    vix_cap_note = ""
    vix_val    = current.get("vix_val")
    vkospi_val = current.get("vkospi_val")
    if vix_val and vix_val >= 25:
        vix_cap_note = "\n<i>VIX " + str(vix_val) + " 감지 → 상한 60점 적용</i>"
    if vkospi_val and vkospi_val >= 40:
        vix_cap_note += "\n<i>VKOSPI " + str(vkospi_val) + " 감지 → 상한 55점 적용</i>"

    lines = [
        emoji + " <b>ARIA 시장 감정지수</b>",
        "<code>" + current.get("date", "") + "</code>",
        "",
        "오늘: <b>" + str(score) + "/100</b> (" + level + ")",
        "추세: " + arrow + " | 7일평균: " + str(trend.get("avg_7d", "-")),
        vix_cap_note,
        "",
        "━━ 구성요소 ━━",
        "<pre>" + "\n".join(comp_lines) + "</pre>",
        "",
        "━━ " + str(len(history[-10:])) + "일 추이 ━━",
        "<pre>" + chart + "</pre>",
        "",
        "최저:" + str(min_30) + " 최고:" + str(max_30) + " 평균:" + str(avg_30),
        "현재: 하위 " + str(percentile) + "% 구간",
        "",
        "💡 " + insight,
    ]

    send_message("\n".join(lines))
    print("Sentiment report sent. Score: " + str(score) + " / " + level)


def run_sentiment(report, market_data=None):
    data = update_sentiment(report, market_data)
    send_sentiment_report(data)
    return data


if __name__ == "__main__":
    test = {
        "market_regime": "취약한 위험선호",
        "trend_phase":   "상승추세",
        "volatility_index": {
            "level":   "공포",
            "vix":     "21.51",
            "vkospi":  "58.86",
            "fear_greed": "35"
        },
        "outflows": [{"zone": "에너지", "severity": "높음"}],
        "inflows":  [{"zone": "반도체", "momentum": "강함"},
                     {"zone": "빅테크", "momentum": "형성중"}],
        "counterarguments": [],
        "korea_focus": {"krw_usd": "원화강세", "kospi_flow": "+2.1%"},
        "hidden_signals": [{"confidence": "높음"}, {"confidence": "높음"}],
    }
    result = run_sentiment(test)
    print("Score: " + str(result["current"]["score"]) + " / " + result["current"]["level"])
    print("(VKOSPI 58 이므로 상한 55점 적용 기대)")
