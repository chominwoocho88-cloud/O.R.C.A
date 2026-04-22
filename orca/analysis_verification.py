"""Verification helpers and DI-driven implementations for orca.analysis."""

from __future__ import annotations

import json
import re
from datetime import timedelta


_VERIFIER_SYSTEM = """You are a financial prediction verifier.
Search for actual market outcomes and verify if predictions came true.
Return ONLY valid JSON. No markdown.
{"results":[{"event":"","verdict":"confirmed/invalidated/unclear","evidence":"","category":"금리/지정학/기업/기타"}]}"""


def _metric_float(value) -> float | None:
    try:
        return float(str(value).replace("%", "").replace("+", "").replace(",", "").strip())
    except Exception:
        return None


def _extract_numeric_thresholds(text: str) -> list[float]:
    matches = re.findall(r"[-+]?\d[\d,]*\.?\d*", str(text or ""))
    values: list[float] = []
    for match in matches:
        value = _metric_float(match)
        if value is not None:
            values.append(value)
    return values


def _direction_flags(text: str) -> tuple[bool, bool]:
    lower = str(text or "").lower()
    up_words = ("상승", "반등", "올라", "증가", "+")
    down_words = ("하락", "급락", "내려", "감소", "-")
    return any(word in lower for word in up_words), any(word in lower for word in down_words)


def _compare_level(level: float | None, confirms: str, invalids: str, label: str) -> tuple[str, str]:
    if level is None:
        return "unclear", ""

    def _level_hit(text: str, value: float) -> bool:
        if "이상" in text or "above" in text.lower() or "over" in text.lower():
            return level >= value
        if "이하" in text or "below" in text.lower() or "under" in text.lower():
            return level <= value
        return False

    nums_c = _extract_numeric_thresholds(confirms)
    nums_i = _extract_numeric_thresholds(invalids)
    if nums_c and _level_hit(confirms, nums_c[0]):
        return "confirmed", f"{label} {level:,.2f} (레벨 충족)"
    if nums_i and _level_hit(invalids, nums_i[0]):
        return "invalidated", f"{label} {level:,.2f} (무효화 레벨 도달)"
    return "unclear", ""


def _compare_change(change: float | None, confirms: str, invalids: str, label: str) -> tuple[str, str]:
    if change is None:
        return "unclear", ""

    nums_c = _extract_numeric_thresholds(confirms)
    nums_i = _extract_numeric_thresholds(invalids)
    conf_up, conf_down = _direction_flags(confirms)
    inv_up, inv_down = _direction_flags(invalids)

    conf_thr = abs(nums_c[0]) if nums_c else 1.0
    inv_thr = abs(nums_i[0]) if nums_i else 1.0

    if conf_up and change >= conf_thr:
        return "confirmed", f"{label} {change:+.2f}% (예측: +{conf_thr:.1f}% 이상)"
    if conf_down and change <= -conf_thr:
        return "confirmed", f"{label} {change:+.2f}% (예측: -{conf_thr:.1f}% 이하)"
    if conf_up and 0.3 <= change < conf_thr:
        return "confirmed", f"{label} {change:+.2f}% (예측 방향 일치, 수치 부분달성)"
    if conf_down and -conf_thr < change <= -0.3:
        return "confirmed", f"{label} {change:+.2f}% (예측 방향 일치, 수치 부분달성)"
    if inv_up and change >= inv_thr:
        return "invalidated", f"{label} {change:+.2f}% (예측 반대)"
    if inv_down and change <= -inv_thr:
        return "invalidated", f"{label} {change:+.2f}% (예측 반대)"
    if conf_up and change <= -0.3:
        return "invalidated", f"{label} {change:+.2f}% (예측 반대)"
    if conf_down and change >= 0.3:
        return "invalidated", f"{label} {change:+.2f}% (예측 반대)"
    if abs(change) < 0.3:
        return "unclear", f"변동 미미 ({change:+.2f}%)"
    return "unclear", f"방향 불명확 ({change:+.2f}%)"


def _verify_price(thesis_killers: list, market_data: dict) -> list:
    results = []
    metric_map = [
        ("나스닥", "nasdaq", "nasdaq_change", "나스닥"),
        ("s&p500", "sp500", "sp500_change", "S&P500"),
        ("s&p", "sp500", "sp500_change", "S&P500"),
        ("코스피", "kospi", "kospi_change", "코스피"),
        ("sk하이닉스", "sk_hynix", "sk_hynix_change", "SK하이닉스"),
        ("sk hynix", "sk_hynix", "sk_hynix_change", "SK하이닉스"),
        ("삼성전자", "samsung", "samsung_change", "삼성전자"),
        ("엔비디아", "nvda", "nvda_change", "엔비디아"),
        ("nvidia", "nvda", "nvda_change", "엔비디아"),
        ("nvda", "nvda", "nvda_change", "엔비디아"),
        ("avgo", "avgo", "avgo_change", "AVGO"),
    ]

    for tk in thesis_killers:
        event = tk.get("event", "")
        event_lower = event.lower()
        confirms = tk.get("confirms_if", "")
        invalids = tk.get("invalidates_if", "")
        verdict = "unclear"
        evidence = ""
        category = tk.get("category") or tk.get("quality") or "기타"

        for keyword, level_key, pct_key, label in metric_map:
            if keyword not in event_lower:
                continue

            level_value = _metric_float(market_data.get(level_key))
            pct_value = _metric_float(market_data.get(pct_key))
            level_text = f"{confirms} {invalids}"
            uses_level = (
                level_value is not None
                and ("pt" in level_text.lower() or "종가" in level_text or any(num >= 1000 for num in _extract_numeric_thresholds(level_text)))
            )

            if uses_level:
                verdict, evidence = _compare_level(level_value, confirms, invalids, label)
            if verdict == "unclear":
                verdict, evidence = _compare_change(pct_value, confirms, invalids, label)
            break

        results.append(
            {
                "event": event,
                "verdict": verdict,
                "evidence": evidence,
                "category": category,
            }
        )
    return results


def _ai_verify_impl(
    unclear: list,
    *,
    client,
    model: str,
    verifier_system: str,
) -> list:
    if not unclear:
        return []

    full = ""
    with client.messages.stream(
        model=model,
        max_tokens=1000,
        system=verifier_system,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[
            {
                "role": "user",
                "content": "Search and verify:\n" + json.dumps(unclear, ensure_ascii=False) + "\nReturn JSON.",
            }
        ],
    ) as s:
        for ev in s:
            t = getattr(ev, "type", "")
            if t == "content_block_start":
                blk = getattr(ev, "content_block", None)
                if blk and getattr(blk, "type", "") == "tool_use":
                    print("  Search: " + getattr(blk, "input", {}).get("query", ""))
            elif t == "content_block_delta":
                d = getattr(ev, "delta", None)
                if d and getattr(d, "type", "") == "text_delta":
                    full += d.text
    raw = re.sub(r"```json|```", "", full).strip()
    m = re.search(r"\{[\s\S]*\}", raw)
    try:
        return json.loads(m.group()).get("results", []) if m else []
    except Exception:
        return []


def _send_verification_report_impl(
    results,
    accuracy,
    today_acc,
    dir_acc=0,
    *,
    format_accuracy_fn,
    today_fn,
    send_message_fn,
):
    judged = [r for r in results if r["verdict"] != "unclear"]
    today_display = format_accuracy_fn(
        len([r for r in results if r["verdict"] == "confirmed"]),
        len(judged),
    )
    today_dir_text = f"{dir_acc}%" if judged else "N/A"
    total_display = format_accuracy_fn(
        accuracy.get("correct", 0),
        accuracy.get("total", 0),
    )
    dir_display = format_accuracy_fn(
        accuracy.get("dir_correct", 0),
        accuracy.get("dir_total", 0),
    )

    lines = ["<b>📋 어제 예측 채점</b>", "<code>" + today_fn() + "</code>", ""]
    for r in results:
        em = "✅" if r["verdict"] == "confirmed" else "❌" if r["verdict"] == "invalidated" else "❓"
        lines.append(em + " <b>" + r.get("event", "")[:40] + "</b>")
        if r.get("evidence"):
            lines.append("  <i>" + r["evidence"] + "</i>")
    lines += [
        "",
        "오늘: <b>" + str(today_display["pct_text"]) + "</b> (" + str(today_display["count_text"]) + ")",
        "  방향정확도: <b>" + today_dir_text + "</b>",
        "누적 방향: <b>"
        + str(dir_display["pct_text"])
        + "</b> | 종합: <b>"
        + str(total_display["pct_text"])
        + "</b> ("
        + str(total_display["count_text"])
        + ")",
    ]
    if accuracy.get("strong_areas"):
        lines.append("💪 강점: " + ", ".join(accuracy["strong_areas"][:3]))
    if accuracy.get("weak_areas"):
        lines.append("⚠️ 약점: " + ", ".join(accuracy["weak_areas"][:3]))
    send_message_fn("\n".join(lines))


def update_weights_from_accuracy_impl(
    accuracy_data: dict,
    *,
    load_weights_fn,
    now_fn,
    today_fn,
    save_fn,
    weights_file,
    min_samples: int,
    suggest_weight_delta_fn,
) -> list:
    """history_by_category(날짜별 스냅샷)에서 최근 30일 데이터만 집계해 가중치 업데이트."""
    weights = load_weights_fn()
    conf = weights.get("prediction_confidence", {})

    cutoff = (now_fn() - timedelta(days=30)).strftime("%Y-%m-%d")
    hist = [h for h in accuracy_data.get("history_by_category", []) if h.get("date", "") >= cutoff]
    if not hist:
        return []

    recent: dict = {}
    for snap in hist:
        for cat, v in snap.get("by_category", {}).items():
            if cat not in recent:
                recent[cat] = {"correct": 0, "total": 0}
            recent[cat]["correct"] += v.get("correct", 0)
            recent[cat]["total"] += v.get("total", 0)

    changes = []
    for cat, v in recent.items():
        if v["total"] < min_samples:
            continue
        acc = v["correct"] / v["total"]
        old_w = conf.get(cat, 1.0)
        adj = suggest_weight_delta_fn(v["correct"], v["total"])
        new_w = round(max(0.3, min(2.0, old_w + adj)), 3)
        if abs(new_w - old_w) >= 0.001:
            conf[cat] = new_w
            changes.append(f"{cat}: {old_w:.3f}→{new_w:.3f} (acc={acc:.1%})")

    if changes:
        weights["prediction_confidence"] = conf
        weights["last_updated"] = today_fn()
        weights["total_learning_cycles"] = weights.get("total_learning_cycles", 0) + 1
        save_fn(weights_file, weights)

    return changes


def run_verification_impl(
    *,
    load_fn,
    memory_file,
    accuracy_file,
    today_fn,
    flag_fn,
    load_market_data_fn,
    verify_price_fn,
    ai_verify_fn,
    update_weights_fn,
    resolve_outcomes_fn,
    save_fn,
    send_report_fn,
) -> dict:
    try:
        memory = load_fn(memory_file, [])
        if not isinstance(memory, list):
            print("⚠️ memory.json 형식 오류 — 빈 메모리로 재시작")
            memory = []
    except Exception:
        print("⚠️ memory.json 손상 감지 — 빈 메모리로 재시작")
        memory = []

    accuracy = load_fn(
        accuracy_file,
        {
            "total": 0,
            "correct": 0,
            "by_category": {},
            "history": [],
            "weak_areas": [],
            "strong_areas": [],
        },
    )

    if not memory:
        print("No previous analysis")
        return accuracy

    yesterday = memory[-1]
    today = today_fn()

    force_verify = flag_fn("ORCA_FORCE_VERIFY")
    already_done = any(h.get("date") == today for h in accuracy.get("history", []))
    if already_done and not force_verify:
        print(f"Already verified today ({today}) — set ORCA_FORCE_VERIFY=true to rerun")
        return accuracy

    tks = yesterday.get("thesis_killers", [])
    if not tks:
        print("No thesis killers to verify")
        return accuracy

    try:
        md = load_market_data_fn()
    except ImportError:
        md = {}

    print("Verifying " + str(len(tks)) + " predictions...")
    results = verify_price_fn(tks, md)

    unclear = [r for r in results if r["verdict"] == "unclear"]
    if unclear:
        print("[2단계] AI 보완 채점 (" + str(len(unclear)) + "개)")
        ai = ai_verify_fn(unclear)
        ai_map = {r["event"]: r for r in ai}
        for r in results:
            if r["verdict"] == "unclear" and r["event"] in ai_map:
                r.update({k: ai_map[r["event"]].get(k, r[k]) for k in ["verdict", "evidence", "category"]})
    else:
        print("[2단계] unclear 없음 — AI 호출 스킵")

    changes = update_weights_fn(accuracy)
    if changes:
        print("Weight updates: " + str(len(changes)))

    judged = [r for r in results if r["verdict"] != "unclear"]
    correct = [r for r in judged if r["verdict"] == "confirmed"]

    def _is_direction_correct(r):
        return r["verdict"] == "confirmed"

    def _is_full_correct(r):
        if r["verdict"] != "confirmed":
            return False
        ev = r.get("evidence", "")
        return "임계 미달" not in ev and "방향 일치" not in ev

    dir_correct = sum(1 for r in judged if _is_direction_correct(r))
    full_correct = sum(1 for r in judged if _is_full_correct(r))

    accuracy["total"] += len(judged)
    accuracy["correct"] += len(correct)
    accuracy.setdefault("dir_total", 0)
    accuracy.setdefault("dir_correct", 0)
    accuracy["dir_total"] += len(judged)
    accuracy["dir_correct"] += dir_correct

    def _strength(r):
        if r["verdict"] != "confirmed":
            return 0.0
        ev = r.get("evidence", "")
        return 0.5 if "임계 미달" in ev or "방향 일치" in ev else 1.0

    score_earned = sum(_strength(r) for r in judged)
    accuracy.setdefault("score_total", 0.0)
    accuracy.setdefault("score_earned", 0.0)
    accuracy["score_total"] += len(judged)
    accuracy["score_earned"] += score_earned
    accuracy["score_accuracy"] = (
        round(accuracy["score_earned"] / accuracy["score_total"] * 100, 1) if accuracy["score_total"] > 0 else 0.0
    )

    today_cat: dict = {}
    for r in judged:
        cat = r.get("category", "기타")
        if cat not in accuracy["by_category"]:
            accuracy["by_category"][cat] = {"total": 0, "correct": 0}
        accuracy["by_category"][cat]["total"] += 1
        if r["verdict"] == "confirmed":
            accuracy["by_category"][cat]["correct"] += 1
        if cat not in today_cat:
            today_cat[cat] = {"total": 0, "correct": 0}
        today_cat[cat]["total"] += 1
        if r["verdict"] == "confirmed":
            today_cat[cat]["correct"] += 1

    today_acc = round(len(correct) / len(judged) * 100, 1) if judged else 0
    dir_acc = round(dir_correct / len(judged) * 100, 1) if judged else 0

    accuracy["history"] = [h for h in accuracy["history"] if h.get("date") != today]
    accuracy["history"].append(
        {
            "date": today,
            "total": len(judged),
            "correct": len(correct),
            "accuracy": today_acc,
            "dir_correct": dir_correct,
            "dir_accuracy": dir_acc,
            "full_correct": full_correct,
        }
    )
    accuracy["history"] = sorted(accuracy["history"], key=lambda x: x.get("date", ""))[-90:]

    if "history_by_category" not in accuracy:
        accuracy["history_by_category"] = []
    accuracy["history_by_category"] = [h for h in accuracy["history_by_category"] if h.get("date") != today]
    accuracy["history_by_category"].append({"date": today, "by_category": today_cat})
    accuracy["history_by_category"] = accuracy["history_by_category"][-90:]

    strong, weak = [], []
    for cat, s in accuracy["by_category"].items():
        if s["total"] >= 3:
            a = s["correct"] / s["total"] * 100
            if a >= 70:
                strong.append(cat + " (" + str(round(a)) + "%)")
            elif a <= 40:
                weak.append(cat + " (" + str(round(a)) + "%)")
    accuracy["strong_areas"] = strong
    accuracy["weak_areas"] = weak

    d_total = accuracy.get("dir_total", 0)
    d_correct = accuracy.get("dir_correct", 0)
    accuracy["dir_accuracy_pct"] = round(d_correct / d_total * 100, 1) if d_total > 0 else 0

    try:
        resolution = resolve_outcomes_fn(
            str(yesterday.get("analysis_date", "")),
            results,
            resolved_analysis_date=today,
            metadata={
                "verification_date": today,
                "judged_count": len(judged),
                "confirmed_count": len(correct),
            },
        )
        if resolution.get("matched") or resolution.get("updated"):
            print(
                "State DB outcomes: "
                + str(resolution.get("matched", 0))
                + " inserted, "
                + str(resolution.get("updated", 0))
                + " updated"
            )
        if resolution.get("unmatched"):
            print("State DB unmatched predictions: " + str(len(resolution["unmatched"])))
    except Exception as e:
        print("State DB outcome sync skipped: " + str(e))

    save_fn(accuracy_file, accuracy)
    send_report_fn(results, accuracy, today_acc, dir_acc)
    today_acc_text = str(today_acc) + "%" if judged else "N/A"
    print("Done. Today accuracy: " + today_acc_text)
    return accuracy


__all__ = [
    "_VERIFIER_SYSTEM",
    "_metric_float",
    "_extract_numeric_thresholds",
    "_direction_flags",
    "_compare_level",
    "_compare_change",
    "_verify_price",
    "_ai_verify_impl",
    "_send_verification_report_impl",
    "update_weights_from_accuracy_impl",
    "run_verification_impl",
]
