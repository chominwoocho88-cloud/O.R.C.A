import httpx
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL         = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_message(text, reply_markup=None, parse_mode="HTML"):
    try:
        payload = {
            "chat_id":               TELEGRAM_CHAT_ID,
            "text":                  text,
            "parse_mode":            parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        r = httpx.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
        return r.json().get("ok", False)
    except Exception as e:
        print("Telegram send error: " + str(e))
        return False


def make_buttons():
    return {
        "inline_keyboard": [[
            {"text": "🔄 지금 분석",  "callback_data": "run_now"},
            {"text": "📋 히스토리",   "callback_data": "history"},
            {"text": "🧠 성장리뷰",   "callback_data": "review"},
            {"text": "📚 학습현황",   "callback_data": "lessons"},
        ]]
    }


def send_report(report, run_number):
    regime       = report.get("market_regime", "?")
    mode         = report.get("mode", "MORNING")
    mode_label   = report.get("mode_label", "")
    confidence   = report.get("confidence_overall", "?")
    date         = report.get("analysis_date", "")
    time_        = report.get("analysis_time", "")
    summary      = report.get("one_line_summary", "")

    regime_emoji = "🟢" if "선호" in regime else "🔴" if "회피" in regime else "🟡"

    mode_icons = {
        "MORNING":   "🌅",
        "AFTERNOON": "☀️",
        "EVENING":   "🌆",
        "DAWN":      "🌙",
    }
    mode_icon = mode_icons.get(mode, "📊")

    lines = [
        mode_icon + " <b>ARIA 리포트 #" + str(run_number) + "</b>",
        "<code>" + date + " " + time_ + "</code>",
        "",
        regime_emoji + " <b>" + regime + "</b>",
        "신뢰도: " + confidence + " | " + (mode_label or mode),
        "",
        "💡 <i>" + summary + "</i>",
        "",
    ]

    kr = report.get("korea_focus", {})
    if kr:
        lines += [
            "🇰🇷 <b>한국 시장</b>",
            "  원/달러: <code>" + kr.get("krw_usd", "-") + "</code>",
            "  코스피:  <code>" + kr.get("kospi_flow", "-") + "</code>",
            "  SK하이닉스: <code>" + kr.get("sk_hynix", "-") + "</code>",
            "  삼성전자:   <code>" + kr.get("samsung", "-") + "</code>",
            "  <i>" + kr.get("assessment", "") + "</i>",
            "",
        ]

    for o in report.get("outflows", [])[:3]:
        lines.append("▼ <b>" + o.get("zone", "") + "</b> [" + o.get("severity", "") + "]")
        lines.append("  <i>" + o.get("reason", "")[:70] + "</i>")
    if report.get("outflows"):
        lines.append("")

    for i in report.get("inflows", [])[:3]:
        lines.append("▲ <b>" + i.get("zone", "") + "</b> [" + i.get("momentum", "") + "]")
        lines.append("  <i>" + i.get("reason", "")[:70] + "</i>")
    if report.get("inflows"):
        lines.append("")

    for tk in report.get("thesis_killers", [])[:3]:
        lines.append("🎯 [" + tk.get("timeframe", "") + "] <b>" + tk.get("event", "") + "</b>")
        lines.append("  ✓ " + tk.get("confirms_if", "")[:50])
        lines.append("  ✗ " + tk.get("invalidates_if", "")[:50])
    if report.get("thesis_killers"):
        lines.append("")

    for idx, a in enumerate(report.get("actionable_watch", [])[:3], 1):
        lines.append("📌 " + str(idx) + ". " + a)

    # 저녁/새벽 모드: 내일 세팅 추가
    if mode in ["EVENING", "DAWN"] and report.get("tomorrow_setup"):
        lines += [
            "",
            "━━ 내일 준비 포인트 ━━",
            "<i>" + report.get("tomorrow_setup", "")[:100] + "</i>",
        ]

    # 아침 모드: 오늘 적용된 교훈 표시
    if mode == "MORNING":
        try:
            from aria_lessons import get_active_lessons
            lessons = get_active_lessons(max_lessons=5)
            if lessons:
                lines.append("")
                lines.append("━━ 🧠 오늘 반영된 교훈 ━━")
                for l in lessons[:3]:
                    sev = "🔴" if l["severity"] == "high" else "🟡" if l["severity"] == "medium" else "🟢"
                    reinf = " (" + str(l.get("reinforced", 0)) + "회 반복)" if l.get("reinforced", 0) > 0 else ""
                    lines.append(sev + " [" + l["category"] + "] " + l["lesson"][:50] + reinf)
        except ImportError:
            pass

    lines.append("")
    lines.append("<code>ARIA Multi-Agent | Anthropic</code>")

    return send_message("\n".join(lines), reply_markup=make_buttons())


def send_lessons_status():
    """학습현황 버튼 눌렸을 때"""
    try:
        from aria_lessons import load_lessons
        data    = load_lessons()
        lessons = data.get("lessons", [])
        total   = data.get("total_lessons", 0)
        updated = data.get("last_updated", "없음")

        if not lessons:
            return send_message(
                "📚 <b>학습 현황</b>\n\n아직 누적된 교훈이 없습니다.\n내일부터 새벽 리포트가 실수를 감지하기 시작합니다."
            )

        lines = [
            "📚 <b>ARIA 학습 현황</b>",
            "누적 교훈: <b>" + str(total) + "개</b>",
            "마지막 업데이트: " + updated,
            "",
            "━━ 현재 적용 중인 교훈 ━━",
        ]

        # 심각도 순으로 정렬
        sorted_lessons = sorted(
            lessons,
            key=lambda x: (
                3 if x["severity"] == "high" else
                2 if x["severity"] == "medium" else 1
            ),
            reverse=True
        )

        for l in sorted_lessons[:8]:
            sev_emoji = "🔴" if l["severity"] == "high" else "🟡" if l["severity"] == "medium" else "🟢"
            applied   = l.get("applied", 0)
            reinforced = l.get("reinforced", 0)
            stats     = "적용 " + str(applied) + "회"
            if reinforced > 0:
                stats += " | 반복 " + str(reinforced) + "회"

            lines.append(
                sev_emoji + " <b>[" + l["category"] + "]</b> " + l["source"] + " " + l["date"]
            )
            lines.append("  " + l["lesson"][:70])
            lines.append("  <i>" + stats + "</i>")
            lines.append("")

        # 카테고리별 요약
        categories = {}
        for l in lessons:
            cat = l["category"]
            categories[cat] = categories.get(cat, 0) + 1

        if categories:
            lines.append("━━ 카테고리별 교훈 수 ━━")
            for cat, cnt in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                bar = "█" * min(cnt, 5) + "░" * (5 - min(cnt, 5))
                lines.append("<code>" + cat.ljust(8) + " [" + bar + "] " + str(cnt) + "개</code>")

        lines += [
            "",
            "<i>교훈은 매일 새벽 자동 추출되어 아침 분석에 반영됩니다</i>",
        ]

        return send_message("\n".join(lines))

    except ImportError:
        return send_message("aria_lessons.py 파일을 찾을 수 없습니다.")
    except Exception as e:
        return send_message("오류: " + str(e))


def send_error(message):
    return send_message(
        "⚠️ <b>ARIA 오류</b>\n\n<code>" + message + "</code>\n\n"
        + "<i>" + datetime.now(KST).strftime("%Y-%m-%d %H:%M KST") + "</i>"
    )


def send_start_notification():
    mode = os.environ.get("ARIA_MODE", "MORNING")
    mode_labels = {
        "MORNING":   "🌅 아침 풀분석",
        "AFTERNOON": "☀️ 오후 업데이트",
        "EVENING":   "🌆 저녁 마감",
        "DAWN":      "🌙 새벽 글로벌",
    }
    label = mode_labels.get(mode, mode)
    return send_message(
        "⚙️ <b>ARIA 분석 시작</b> " + label + "\n"
        + "<i>" + datetime.now(KST).strftime("%Y-%m-%d %H:%M KST") + "</i>\n"
        + "Hunter → Analyst → Devil → Reporter..."
    )


if __name__ == "__main__":
    print("Telegram test...")
    ok = send_message("✅ ARIA 텔레그램 연결 성공!", reply_markup=make_buttons())
    print("OK" if ok else "FAIL")
