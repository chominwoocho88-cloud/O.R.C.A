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


def load_memory():
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    return []


def load_accuracy():
    if ACCURACY_FILE.exists():
        return json.loads(ACCURACY_FILE.read_text(encoding="utf-8"))
    return {
        "total": 0, "correct": 0,
        "by_category": {}, "history": [],
        "weak_areas": [], "strong_areas": [],
    }


def save_accuracy(data):
    ACCURACY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_change(change_str):
    try:
        return float(str(change_str).replace("%", "").replace("+", "").strip())
    except:
        return None


# ── 실제 주가 기반 자동 채점 ──────────────────────────────────────────────────
def verify_with_price_data(thesis_killers, market_data):
    """
    Yahoo Finance 실제 주가로 thesis_killers 자동 채점.
    텍스트 분석 없이 숫자로 판단.
    """
    results = []

    # 주가 변동 데이터 준비
    price_signals = {
        "sp500":    parse_change(market_data.get("sp500_change")),
        "nasdaq":   parse_change(market_data.get("nasdaq_change")),
        "vix":      parse_change(market_data.get("vix_change")),
        "kospi":    parse_change(market_data.get("kospi_change")),
        "sk_hynix": parse_change(market_data.get("sk_hynix_change")),
        "samsung":  parse_change(market_data.get("samsung_change")),
        "nvda":     parse_change(market_data.get("nvda_change")),
        "krw_usd":  parse_change(market_data.get("krw_usd")),
    }

    for tk in thesis_killers:
        event      = tk.get("event", "").lower()
        confirms   = tk.get("confirms_if", "").lower()
        invalidates = tk.get("invalidates_if", "").lower()

        verdict   = "unclear"
        evidence  = ""
        category  = "기타"

        # 나스닥/S&P 관련
        if any(k in event for k in ["나스닥", "nasdaq", "s&p", "미국증시", "기술주"]):
            category = "주식"
            chg = price_signals.get("nasdaq") or price_signals.get("sp500")
            if chg is not None:
                if chg > 0 and ("상승" in confirms or "반등" in confirms or "올라" in confirms):
                    verdict  = "confirmed"
                    evidence = "나스닥 실제 +" + str(chg) + "%"
                elif chg < 0 and ("하락" in confirms or "급락" in confirms or "내려" in confirms):
                    verdict  = "confirmed"
                    evidence = "나스닥 실제 " + str(chg) + "%"
                elif chg > 0 and ("하락" in confirms or "급락" in confirms):
                    verdict  = "invalidated"
                    evidence = "나스닥 실제 +" + str(chg) + "% (반등)"
                elif chg < 0 and ("상승" in confirms or "반등" in confirms):
                    verdict  = "invalidated"
                    evidence = "나스닥 실제 " + str(chg) + "% (하락)"

        # 반도체/SK하이닉스/엔비디아
        elif any(k in event for k in ["반도체", "sk하이닉스", "sk hynix", "엔비디아", "nvidia", "hbm"]):
            category = "주식"
            chg = price_signals.get("sk_hynix") or price_signals.get("nvda")
            if chg is not None:
                if chg >= 2 and ("상승" in confirms or "강세" in confirms or "유입" in confirms):
                    verdict  = "confirmed"
                    evidence = "반도체 실제 +" + str(chg) + "%"
                elif chg <= -2 and ("하락" in confirms or "약세" in confirms or "유출" in confirms):
                    verdict  = "confirmed"
                    evidence = "반도체 실제 " + str(chg) + "%"
                elif chg >= 2 and ("하락" in confirms or "유출" in confirms):
                    verdict  = "invalidated"
                    evidence = "반도체 실제 +" + str(chg) + "%"
                elif chg <= -2 and ("상승" in confirms or "유입" in confirms):
                    verdict  = "invalidated"
                    evidence = "반도체 실제 " + str(chg) + "%"

        # 코스피
        elif any(k in event for k in ["코스피", "kospi", "한국증시", "코스닥"]):
            category = "주식"
            chg = price_signals.get("kospi")
            if chg is not None:
                if chg > 0 and ("상승" in confirms or "반등" in confirms):
                    verdict  = "confirmed"
                    evidence = "코스피 실제 +" + str(chg) + "%"
                elif chg < 0 and ("하락" in confirms or "급락" in confirms):
                    verdict  = "confirmed"
                    evidence = "코스피 실제 " + str(chg) + "%"
                elif chg > 0 and ("하락" in confirms):
                    verdict  = "invalidated"
                    evidence = "코스피 실제 +" + str(chg) + "%"
                elif chg < 0 and ("상승" in confirms):
                    verdict  = "invalidated"
                    evidence = "코스피 실제 " + str(chg) + "%"

        # VIX / 변동성
        elif any(k in event for k in ["vix", "변동성", "공포"]):
            category = "VIX"
            chg = price_signals.get("vix")
            vix_val = parse_change(market_data.get("vix"))
            if vix_val is not None:
                if vix_val >= 30 and ("공포" in confirms or "급등" in confirms):
                    verdict  = "confirmed"
                    evidence = "VIX 실제 " + str(vix_val)
                elif vix_val < 25 and ("안정" in confirms or "하락" in confirms):
                    verdict  = "confirmed"
                    evidence = "VIX 실제 " + str(vix_val)
                elif vix_val >= 30 and ("안정" in confirms):
                    verdict  = "invalidated"
                    evidence = "VIX 실제 " + str(vix_val) + " (여전히 높음)"

        # 환율
        elif any(k in event for k in ["환율", "원달러", "krw", "달러"]):
            category = "환율"
            # 환율은 숫자 비교
            krw_str = str(market_data.get("krw_usd", ""))
            try:
                krw_val = float(re.search(r"[\d.]+", krw_str).group())
                if krw_val >= 1500 and ("약세" in confirms or "상승" in confirms or "1500" in confirms):
                    verdict  = "confirmed"
                    evidence = "원달러 실제 " + str(krw_val)
                elif krw_val < 1450 and ("강세" in confirms or "하락" in confirms):
                    verdict  = "confirmed"
                    evidence = "원달러 실제 " + str(krw_val)
            except:
                pass

        # 금리
        elif any(k in event for k in ["금리", "국채", "연준", "fomc", "fed"]):
            category = "금리"
            # 금리는 뉴스 검색으로 보완
            verdict = "unclear"
            evidence = "실시간 금리 데이터 미제공 — 뉴스 확인 필요"

        results.append({
            "event":     tk.get("event", ""),
            "verdict":   verdict,
            "evidence":  evidence,
            "category":  category,
            "confirms_if":   tk.get("confirms_if", ""),
            "invalidates_if": tk.get("invalidates_if", ""),
        })

    return results


# ── AI 보조 채점 (unclear 항목만) ─────────────────────────────────────────────
VERIFIER_SYSTEM = """You are ARIA-Verifier. 
Only check the UNCLEAR items that could not be verified with price data.
Search for specific news about these events.
Return ONLY valid JSON. No markdown.
{
  "results": [
    {
      "event": "",
      "verdict": "confirmed/invalidated/unclear",
      "evidence": "",
      "category": "금리/지정학/기업/기타"
    }
  ]
}"""


def verify_unclear_with_ai(unclear_items):
    """unclear 항목만 AI + 뉴스검색으로 보완"""
    if not unclear_items:
        return []

    full = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=1000,
        system=VERIFIER_SYSTEM,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{
            "role": "user",
            "content": "Search and verify these events:\n"
                + json.dumps(unclear_items, ensure_ascii=False)
                + "\nReturn JSON."
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
        return []
    try:
        return json.loads(m.group()).get("results", [])
    except:
        return []


# ── 정확도 업데이트 ────────────────────────────────────────────────────────────
def update_accuracy(results, accuracy):
    judged  = [r for r in results if r["verdict"] != "unclear"]
    correct = [r for r in judged if r["verdict"] == "confirmed"]

    accuracy["total"]   += len(judged)
    accuracy["correct"] += len(correct)

    for r in judged:
        cat = r.get("category", "기타")
        if cat not in accuracy["by_category"]:
            accuracy["by_category"][cat] = {"total": 0, "correct": 0}
        accuracy["by_category"][cat]["total"] += 1
        if r["verdict"] == "confirmed":
            accuracy["by_category"][cat]["correct"] += 1

    today      = datetime.now(KST).strftime("%Y-%m-%d")
    today_acc  = round(len(correct) / len(judged) * 100, 1) if judged else 0

    accuracy["history"].append({
        "date":     today,
        "total":    len(judged),
        "correct":  len(correct),
        "accuracy": today_acc,
    })
    accuracy["history"] = accuracy["history"][-90:]

    strong, weak = [], []
    for cat, stats in accuracy["by_category"].items():
        if stats["total"] >= 3:
            acc = stats["correct"] / stats["total"] * 100
            if acc >= 70:
                strong.append(cat + " (" + str(round(acc)) + "%)")
            elif acc <= 40:
                weak.append(cat + " (" + str(round(acc)) + "%)")
    accuracy["strong_areas"] = strong
    accuracy["weak_areas"]   = weak

    return accuracy, today_acc


def send_verification_report(results, accuracy, today_acc):
    try:
        from aria_telegram import send_message
    except ImportError:
        return

    total_acc = round(accuracy["correct"] / accuracy["total"] * 100, 1) if accuracy["total"] > 0 else 0
    judged    = [r for r in results if r["verdict"] != "unclear"]

    lines = [
        "<b>📋 어제 예측 채점</b>",
        "<code>" + datetime.now(KST).strftime("%Y-%m-%d") + "</code>",
        "",
    ]

    for r in results:
        if r["verdict"] == "confirmed":
            emoji = "✅"
        elif r["verdict"] == "invalidated":
            emoji = "❌"
        else:
            emoji = "❓"
        lines.append(emoji + " <b>" + r.get("event", "")[:40] + "</b>")
        if r.get("evidence"):
            lines.append("  <i>" + r["evidence"] + "</i>")

    lines += [
        "",
        "오늘: <b>" + str(today_acc) + "%</b> (" + str(len([r for r in results if r["verdict"]=="confirmed"])) + "/" + str(len(judged)) + ")",
        "누적: <b>" + str(total_acc) + "%</b> (" + str(accuracy["correct"]) + "/" + str(accuracy["total"]) + ")",
    ]

    if accuracy.get("strong_areas"):
        lines.append("💪 강점: " + ", ".join(accuracy["strong_areas"][:3]))
    if accuracy.get("weak_areas"):
        lines.append("⚠️ 약점: " + ", ".join(accuracy["weak_areas"][:3]))

    send_message("\n".join(lines))


# ── 메인 ──────────────────────────────────────────────────────────────────────
def run_verification():
    memory   = load_memory()
    accuracy = load_accuracy()

    if not memory:
        print("No previous analysis")
        return accuracy

    yesterday = memory[-1]
    today     = datetime.now(KST).strftime("%Y-%m-%d")

    # 오늘 이미 채점했으면 스킵
    if accuracy.get("history") and accuracy["history"][-1].get("date") == today:
        print("Already verified today")
        return accuracy

    thesis_killers = yesterday.get("thesis_killers", [])
    if not thesis_killers:
        print("No thesis killers to verify")
        return accuracy

    # 실시간 주가 데이터 로드
    try:
        from aria_data import load_market_data
        market_data = load_market_data()
    except ImportError:
        market_data = {}

    print("Verifying " + str(len(thesis_killers)) + " predictions...")
    print("[1단계] 실제 주가 기반 자동 채점")
    results = verify_with_price_data(thesis_killers, market_data)

    # unclear 항목만 AI로 보완
    unclear = [r for r in results if r["verdict"] == "unclear"]
    if unclear:
        print("[2단계] AI 보완 채점 (" + str(len(unclear)) + "개)")
        ai_results = verify_unclear_with_ai(unclear)
        # AI 결과로 unclear 업데이트
        ai_map = {r["event"]: r for r in ai_results}
        for r in results:
            if r["verdict"] == "unclear" and r["event"] in ai_map:
                ai = ai_map[r["event"]]
                r["verdict"]  = ai.get("verdict", "unclear")
                r["evidence"] = ai.get("evidence", "")
                r["category"] = ai.get("category", r["category"])

    # 가중치 업데이트
    try:
        from aria_weights import update_weights_from_accuracy
        changes = update_weights_from_accuracy(accuracy)
        if changes:
            print("Weight updates: " + str(len(changes)))
    except ImportError:
        pass

    accuracy, today_acc = update_accuracy(results, accuracy)
    save_accuracy(accuracy)
    send_verification_report(results, accuracy, today_acc)

    print("Done. Today accuracy: " + str(today_acc) + "%")
    return accuracy


if __name__ == "__main__":
    run_verification()
