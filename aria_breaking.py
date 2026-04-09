import os
import sys
import json
import anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST          = timezone(timedelta(hours=9))
BREAKING_FILE = Path("breaking_sent.json")
API_KEY      = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL        = "claude-haiku-4-5-20251001"

client = anthropic.Anthropic(api_key=API_KEY)

# 긴급 속보 트리거 키워드
TRIGGER_KEYWORDS = [
    "긴급", "속보", "emergency", "breaking",
    "연준 긴급", "FOMC 긴급", "금리 인상", "금리 인하",
    "반도체 수출 규제", "관세 부과", "무역 전쟁",
    "원달러 1500", "원달러 1600",
    "엔비디아 급락", "엔비디아 폭락",
    "SK하이닉스 급락", "삼성전자 급락",
    "코스피 급락", "나스닥 급락", "S&P 급락",
    "지진", "전쟁 선포", "핵",
    "은행 파산", "금융위기",
]

BREAKING_SYSTEM = """You are a financial breaking news detector.
Search for urgent financial news from the last 2 hours.
Check if any major market-moving events have occurred.

Return ONLY valid JSON. No markdown.
{
  "has_breaking": true/false,
  "breaking_news": [
    {
      "headline": "",
      "severity": "critical/high/medium",
      "impact": "",
      "affected_assets": [],
      "source_hint": ""
    }
  ],
  "summary": ""
}"""


def load_sent():
    if BREAKING_FILE.exists():
        return json.loads(BREAKING_FILE.read_text(encoding="utf-8"))
    return {"sent_today": [], "last_check": ""}


def save_sent(data):
    BREAKING_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def check_breaking_news():
    now = datetime.now(KST)
    now_str = now.strftime("%Y-%m-%d %H:%M")
    today_str = now.strftime("%Y-%m-%d")

    sent = load_sent()

    # 하루 최대 5개 알림 제한
    today_sent = [s for s in sent.get("sent_today", []) if s.startswith(today_str)]
    if len(today_sent) >= 5:
        print("Daily breaking news limit reached (5)")
        return

    print("Checking breaking news at " + now_str)

    # 뉴스 검색
    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=1000,
        system=BREAKING_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": "Search for major financial breaking news in the last 2 hours: " + now_str + ". Check US markets, Korea markets, crypto, geopolitical events. Return JSON."
        }]
    ) as s:
        for ev in s:
            t = getattr(ev, "type", "")
            if t == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type", "") == "text_delta":
                    full += d.text

    if not full.strip():
        print("No response from API")
        return

    import re
    raw = re.sub(r"```json|```", "", full).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        print("No JSON found")
        return

    try:
        data = json.loads(m.group())
    except:
        print("JSON parse error")
        return

    if not data.get("has_breaking"):
        print("No breaking news detected")
        return

    # 중복 체크 후 전송
    breaking_list = data.get("breaking_news", [])
    new_alerts = []

    for news in breaking_list:
        headline = news.get("headline", "")
        severity = news.get("severity", "medium")

        # 이미 보낸 뉴스 스킵
        already_sent = any(headline[:30] in s for s in sent.get("sent_today", []))
        if already_sent:
            continue

        if severity in ["critical", "high"]:
            new_alerts.append(news)

    if not new_alerts:
        print("No new critical/high severity news")
        return

    # 텔레그램 전송
    send_breaking_alert(new_alerts, now_str)

    # 전송 기록 저장
    for news in new_alerts:
        sent.setdefault("sent_today", []).append(
            today_str + " " + news.get("headline", "")[:30]
        )
    sent["last_check"] = now_str
    save_sent(sent)


def send_breaking_alert(news_list, time_str):
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    for news in news_list:
        severity = news.get("severity", "medium")
        severity_emoji = "🚨" if severity == "critical" else "⚠️"

        affected = ", ".join(news.get("affected_assets", []))

        lines = [
            severity_emoji + " <b>ARIA 긴급 속보</b>",
            "<code>" + time_str + "</code>",
            "",
            "<b>" + news.get("headline", "") + "</b>",
            "",
            "영향: " + news.get("impact", ""),
        ]

        if affected:
            lines.append("관련 자산: " + affected)

        send_message("\n".join(lines))
        print("Breaking alert sent: " + news.get("headline", "")[:50])


if __name__ == "__main__":
    check_breaking_news()
