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

KST           = timezone(timedelta(hours=9))
MEMORY_FILE   = Path("memory.json")
ACCURACY_FILE = Path("accuracy.json")
API_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL         = "claude-sonnet-4-6"

client = anthropic.Anthropic(api_key=API_KEY)


def now_kst():
    return datetime.now(KST)


def parse_json(text):
    raw = re.sub(r"```json|```", "", text).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        raise ValueError("JSON not found")
    s = m.group()
    s = re.sub(r",\s*([}\]])", r"\1", s)
    s += "]" * (s.count("[") - s.count("]"))
    s += "}" * (s.count("{") - s.count("}"))
    return json.loads(s)


def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return []


def load_accuracy():
    if ACCURACY_FILE.exists():
        return json.loads(ACCURACY_FILE.read_text(encoding="utf-8"))
    return {
        "total": 0,
        "correct": 0,
        "by_category": {},
        "history": [],
        "weak_areas": [],
        "strong_areas": [],
    }


def save_accuracy(data):
    ACCURACY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


VERIFIER_SYSTEM = """You are ARIA-Verifier. Check if yesterday's predictions came true.

You will receive yesterday's thesis_killers and today's news.

For each thesis_killer determine:
- confirmed: the confirms_if scenario happened
- invalidated: the invalidates_if scenario happened
- unclear: not enough information

Return ONLY valid JSON. No markdown.
{
  "verification_date": "YYYY-MM-DD",
  "results": [
    {
      "event": "",
      "predicted_confirms": "",
      "predicted_invalidates": "",
      "actual_outcome": "",
      "verdict": "confirmed/invalidated/unclear",
      "evidence": "",
      "category": "금리/환율/주식/지정학/원자재/기업"
    }
  ],
  "summary": {
    "total": 0,
    "confirmed": 0,
    "invalidated": 0,
    "unclear": 0,
    "accuracy_today": 0.0
  },
  "pattern_insight": ""
}"""


def verify_predictions(yesterday_analysis):
    thesis_killers = yesterday_analysis.get("thesis_killers", [])
    if not thesis_killers:
        print("No thesis killers to verify")
        return {}

    print("Verifying " + str(len(thesis_killers)) + " predictions from " + str(yesterday_analysis.get("analysis_date")))

    search_results = []
    search_count = 0

    for tk in thesis_killers:
        event = tk.get("event", "")
        query = event + " result today"

        with client.messages.stream(
            model=MODEL,
            max_tokens=500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": "Search: " + query + ". Return brief summary."}]
        ) as s:
            text = ""
            for ev in s:
                t = getattr(ev, "type", "")
                if t == "content_block_start":
                    blk = getattr(ev, "content_block", None)
                    if blk and getattr(blk, "type", "") == "tool_use":
                        search_count += 1
                        print("  Search [" + str(search_count) + "]: " + query)
                elif t == "content_block_delta":
                    d = getattr(ev, "delta", None)
                    if d and getattr(d, "type", "") == "text_delta":
                        text += d.text
            search_results.append({"event": event, "news": text})

    payload = {
        "thesis_killers": thesis_killers,
        "news_results": search_results,
        "analysis_date": yesterday_analysis.get("analysis_date"),
    }

    with client.messages.stream(
        model=MODEL,
        max_tokens=2000,
        system=VERIFIER_SYSTEM,
        messages=[{"role": "user", "content": "Verify:\n" + json.dumps(payload, ensure_ascii=False) + "\n\nReturn JSON only."}]
    ) as s:
        full = ""
        for ev in s:
            t = getattr(ev, "type", "")
            if t == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type", "") == "text_delta":
                    full += d.text

    return parse_json(full)


def update_accuracy(verification, accuracy):
    summary = verification.get("summary", {})
    results = verification.get("results", [])

    total_judged = summary.get("confirmed", 0) + summary.get("invalidated", 0)
    correct = summary.get("confirmed", 0)

    accuracy["total"] += total_judged
    accuracy["correct"] += correct

    for r in results:
        if r.get("verdict") == "unclear":
            continue
        cat = r.get("category", "기타")
        if cat not in accuracy["by_category"]:
            accuracy["by_category"][cat] = {"total": 0, "correct": 0}
        accuracy["by_category"][cat]["total"] += 1
        if r.get("verdict") == "confirmed":
            accuracy["by_category"][cat]["correct"] += 1

    accuracy["history"].append({
        "date": verification.get("verification_date"),
        "total": total_judged,
        "correct": correct,
        "accuracy": round(correct / total_judged * 100, 1) if total_judged > 0 else 0,
        "pattern_insight": verification.get("pattern_insight", ""),
    })
    accuracy["history"] = accuracy["history"][-90:]

    strong = []
    weak = []
    for cat, stats in accuracy["by_category"].items():
        if stats["total"] >= 3:
            acc = stats["correct"] / stats["total"] * 100
            if acc >= 70:
                strong.append(cat + " (" + str(round(acc)) + "%)")
            elif acc <= 40:
                weak.append(cat + " (" + str(round(acc)) + "%)")
    accuracy["strong_areas"] = strong
    accuracy["weak_areas"] = weak

    return accuracy


def send_verification_report(verification, accuracy):
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    summary = verification.get("summary", {})
    results = verification.get("results", [])
    total_acc = round(accuracy["correct"] / accuracy["total"] * 100, 1) if accuracy["total"] > 0 else 0
    today_acc = summary.get("accuracy_today", 0)

    lines = [
        "<b>ARIA 어제 예측 채점</b>",
        "<code>" + str(verification.get("verification_date", "")) + "</code>",
        "",
    ]

    for r in results:
        verdict = r.get("verdict", "")
        if verdict == "confirmed":
            emoji = "confirmed"
        elif verdict == "invalidated":
            emoji = "wrong"
        else:
            emoji = "unclear"
        lines.append(emoji + " <b>" + r.get("event", "") + "</b>")
        lines.append("  <i>" + r.get("actual_outcome", "")[:60] + "</i>")

    lines += [
        "",
        "Today: <b>" + str(round(today_acc)) + "%</b> (" + str(summary.get("confirmed", 0)) + "/" + str(summary.get("confirmed", 0) + summary.get("invalidated", 0)) + ")",
        "Total: <b>" + str(total_acc) + "%</b> (" + str(accuracy["correct"]) + "/" + str(accuracy["total"]) + ")",
    ]

    if accuracy.get("strong_areas"):
        lines.append("Strong: " + ", ".join(accuracy["strong_areas"][:3]))
    if accuracy.get("weak_areas"):
        lines.append("Weak: " + ", ".join(accuracy["weak_areas"][:3]))

    if verification.get("pattern_insight"):
        lines += ["", "<i>" + verification.get("pattern_insight", "") + "</i>"]

    send_message("\n".join(lines))
    print("Verification report sent")


def run_verification():
    memory = load_memory()
    accuracy = load_accuracy()

    if len(memory) < 1:
        print("No previous analysis to verify")
        return accuracy

    yesterday = memory[-1]
    yesterday_date = yesterday.get("analysis_date", "")
    today = now_kst().strftime("%Y-%m-%d")

    if accuracy.get("history") and accuracy["history"][-1].get("date") == today:
        print("Already verified today, skipping")
        return accuracy

    print("Verifying predictions from " + yesterday_date)

    verification = verify_predictions(yesterday)
    if not verification:
        return accuracy

    accuracy = update_accuracy(verification, accuracy)
    save_accuracy(accuracy)

    # 가중치 자동 업데이트 (자기학습)
    try:
        from aria_weights import update_weights_from_accuracy
        changes = update_weights_from_accuracy(accuracy)
        if changes:
            print("Weight updates: " + str(len(changes)) + " changes applied")
    except ImportError:
        pass

    send_verification_report(verification, accuracy)

    today_acc = verification.get("summary", {}).get("accuracy_today", 0)
    print("Verification complete. Accuracy: " + str(round(today_acc)) + "%")
    return accuracy


if __name__ == "__main__":
    run_verification()
