"""Lightweight transport helpers shared by ORCA modules.

This module deliberately avoids importing heavy analysis/reporting modules so
that data and analysis code can use Telegram send utilities without forming
an import cycle through orca.notify.
"""
from __future__ import annotations

import os

import httpx


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
BASE_URL = "https://api.telegram.org/bot" + TELEGRAM_TOKEN


def _format_accuracy_display(correct, total, *, empty_label: str = "N/A") -> dict:
    try:
        total_value = int(total or 0)
    except (TypeError, ValueError):
        total_value = 0

    try:
        correct_value = int(correct or 0)
    except (TypeError, ValueError):
        correct_value = 0

    if total_value <= 0:
        return {
            "has_data": False,
            "pct": None,
            "pct_text": empty_label,
            "count_text": "검증 데이터 없음",
        }

    pct = round(correct_value / total_value * 100, 1)
    return {
        "has_data": True,
        "pct": pct,
        "pct_text": f"{pct}%",
        "count_text": f"{correct_value}/{total_value}개",
    }


def _send_single(text: str, reply_markup=None, parse_mode: str = "HTML") -> bool:
    """Send a single Telegram message when the text fits within the limit."""
    try:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = httpx.post(BASE_URL + "/sendMessage", json=payload, timeout=10)
        return response.json().get("ok", False)
    except Exception as exc:
        print("Telegram send error: " + str(exc))
        return False


def send_message(text: str, reply_markup=None, parse_mode: str = "HTML") -> bool:
    """Split long Telegram payloads into safe chunks automatically."""
    limit = 4000
    if len(text) <= limit:
        return _send_single(text, reply_markup, parse_mode)

    lines = text.split("\n")
    chunks = []
    current = []
    length = 0

    for line in lines:
        if length + len(line) + 1 > limit:
            chunks.append("\n".join(current))
            current = [line]
            length = len(line)
        else:
            current.append(line)
            length += len(line) + 1

    if current:
        chunks.append("\n".join(current))

    ok = True
    for index, chunk in enumerate(chunks):
        suffix = (
            "\n<i>(" + str(index + 1) + "/" + str(len(chunks)) + ")</i>"
            if len(chunks) > 1 else ""
        )
        markup = reply_markup if index == len(chunks) - 1 else None
        ok = ok and _send_single(chunk + suffix, markup, parse_mode)

    return ok
