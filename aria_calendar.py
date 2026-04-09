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

KST     = timezone(timedelta(hours=9))
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = "claude-haiku-4-5-20251001"

client = anthropic.Anthropic(api_key=API_KEY)

CALENDAR_SYSTEM = """You are a financial calendar agent.
Search for this week's major economic events and data releases.

Focus on:
- US: FOMC, CPI, PPI, NFP, GDP, retail sales, fed speakers
- Korea: BOK rate decision, trade balance, CPI
- Major earnings: especially semiconductor/AI companies
- Geopolitical events scheduled this week

Return ONLY valid JSON. No markdown.
{
  "week_start": "YYYY-MM-DD",
  "week_end": "YYYY-MM-DD",
  "events": [
    {
      "date": "YYYY-MM-DD",
      "day": "월/화/수/목/금",
      "time": "HH:MM KST or TBD",
      "event": "",
      "importance": "high/medium/low",
      "expected": "",
      "previous": "",
      "market_impact": "",
      "affected_assets": []
    }
  ],
  "week_summary": "",
  "key_watch": ""
}"""


def get_week_calendar():
    now = datetime.now(KST)
    week_str = now.strftime("%Y-%m-%d")

    print("Fetching economic calendar for week of " + week_str)

    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=2000,
        system=CALENDAR_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": "Search for this week economic calendar events starting " + week_str + ". Include US and Korea major events. Return JSON."
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
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("No JSON found")

    s = m.group()
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s += "]" * (s.count("[") - s.count("]"))
    s += "}" * (s.count("{") - s.count("}"))
    return json.loads(s)


def send_calendar_report(calendar):
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    events = calendar.get("events", [])
    high_events = [e for e in events if e.get("importance") == "high"]
    other_events = [e for e in events if e.get("importance") != "high"]

    lines = [
        "<b>📅 이번 주 경제 캘린더</b>",
        "<code>" + calendar.get("week_start", "") + " ~ " + calendar.get("week_end", "") + "</code>",
        "",
        "<b>" + calendar.get("week_summary", "") + "</b>",
        "",
        "━━ 핵심 이벤트 ━━",
    ]

    for e in high_events[:6]:
        imp = e.get("importance", "")
        imp_emoji = "🔴" if imp == "high" else "🟡" if imp == "medium" else "⚪"
        lines.append(
            imp_emoji + " <b>[" + e.get("day", "") + "] " + e.get("event", "") + "</b>"
        )
        lines.append("   " + e.get("time", "") + " | " + e.get("market_impact", "")[:50])
        if e.get("expected"):
            lines.append("   예상: " + e.get("expected", ""))

    if other_events:
        lines.append("")
        lines.append("━━ 기타 일정 ━━")
        for e in other_events[:4]:
            lines.append(
                "⚪ [" + e.get("day", "") + "] " + e.get("event", "")
            )

    if calendar.get("key_watch"):
        lines += [
            "",
            "👀 <b>이번 주 핵심 관전 포인트</b>",
            "<i>" + calendar.get("key_watch", "") + "</i>",
        ]

    send_message("\n".join(lines))
    print("Calendar report sent")


def run_calendar():
    calendar = get_week_calendar()
    send_calendar_report(calendar)
    return calendar


if __name__ == "__main__":
    run_calendar()
