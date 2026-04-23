"""Shared explanation helpers for JACKAL alerts and persisted narratives."""
from __future__ import annotations

import re
from typing import Iterable


SWING_BIAS_THRESHOLD = 12

SIGNAL_NARRATIVE_MAP = {
    "rsi_oversold": "RSI 과매도",
    "bb_touch": "BB 하단 접근",
    "volume_climax": "거래량 급증",
    "momentum_dip": "단기 낙폭",
    "sector_rebound": "섹터 반등",
    "rsi_divergence": "RSI 다이버전스",
    "52w_low_zone": "52주 저점권",
    "vol_accumulation": "매집 거래량",
    "ma_support": "MA 지지",
}

FAMILY_NARRATIVE_MAP = {
    "rotation": ("섹터로테이션", "유입 섹터 안에서 아직 덜 반영된 눌림목 후보"),
    "panic_rebound": ("패닉반등", "투매성 급락 뒤 되돌림을 노리는 스냅백 구조"),
    "momentum_pullback": ("모멘텀눌림목", "강한 추세 안의 조정을 재진입 기회로 보는 패턴"),
    "ma_reclaim": ("MA지지반등", "주요 이동평균 부근 지지 확인 뒤 재상승을 보는 구조"),
    "divergence": ("강세다이버전스", "가격보다 모멘텀이 먼저 개선되는 전환 초기 신호"),
    "oversold_rebound": ("기술적과매도", "과매도 해소 반등을 노리는 회복형 패턴"),
    "general_rebound": ("일반반등", "단일 강신호는 약하지만 복수 완화 신호가 겹친 후보"),
}

HUNTER_LINE_BUDGETS = {
    "family": 60,
    "core": 112,
    "swing": 72,
    "regime": 82,
}

SCANNER_LINE_BUDGETS = {
    "family": 62,
    "core": 116,
    "swing": 88,
    "regime": 88,
}

SCANNER_SWING_DEFAULTS = {
    "sector_rebound": {"peak_day": "D4~5", "swing_acc": "93%", "mae_avg": "-2.1%"},
    "bb_touch": {"peak_day": "D4~5", "swing_acc": "97%", "mae_avg": "-3.8%"},
    "rsi_oversold": {"peak_day": "D4~5", "swing_acc": "88%", "mae_avg": "-2.9%"},
    "vol_accumulation": {"peak_day": "D5", "swing_acc": "84%", "mae_avg": "-3.2%"},
    "volume_climax": {"peak_day": "D4~5", "swing_acc": "80%", "mae_avg": "-4.5%"},
    "momentum_dip": {"peak_day": "D4~5", "swing_acc": "78%", "mae_avg": "-4.1%"},
    "ma_support": {"peak_day": "D3~4", "swing_acc": "67%", "mae_avg": "-1.8%"},
    "rsi_divergence": {"peak_day": "D4", "swing_acc": "52%", "mae_avg": "-2.3%"},
}

SCANNER_SWING_PRIORITY = [
    "sector_rebound",
    "bb_touch",
    "rsi_oversold",
    "vol_accumulation",
    "volume_climax",
    "momentum_dip",
    "ma_support",
    "rsi_divergence",
]

_QUALITY_REASON_HINTS = [
    (re.compile(r"bb\+rsi", re.IGNORECASE), "BB 하단 + RSI 과매도"),
    (re.compile(r"3.?combo", re.IGNORECASE), "복합 반등 조합"),
    (re.compile(r"sector_rebound", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["sector_rebound"]),
    (re.compile(r"volume_climax", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["volume_climax"]),
    (re.compile(r"momentum_dip", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["momentum_dip"]),
    (re.compile(r"rsi_divergence|divergence", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["rsi_divergence"]),
    (re.compile(r"52w|52", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["52w_low_zone"]),
    (re.compile(r"vol_acc|accumulation", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["vol_accumulation"]),
    (re.compile(r"ma_support|ma.?support", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["ma_support"]),
    (re.compile(r"\bbb\b", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["bb_touch"]),
    (re.compile(r"\brsi\b", re.IGNORECASE), SIGNAL_NARRATIVE_MAP["rsi_oversold"]),
    (re.compile(r"\bpcr\b", re.IGNORECASE), "투자심리 역풍 완화"),
    (re.compile(r"\bvix\b|\bhy\b", re.IGNORECASE), "변동성 과열 뒤 반등 여지"),
]


def truncate_text(text: str | None, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if limit <= 0:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    if limit <= 3:
        return cleaned[:limit]
    return cleaned[: limit - 3].rstrip() + "..."


def humanize_signal(signal: str | None) -> str:
    key = str(signal or "").strip()
    if not key:
        return ""
    if key in SIGNAL_NARRATIVE_MAP:
        return SIGNAL_NARRATIVE_MAP[key]
    return key.replace("_", " ")


def build_family_narrative_line(family_key: str | None, *, limit: int | None = None) -> str:
    key = str(family_key or "general_rebound").strip() or "general_rebound"
    label, narrative = FAMILY_NARRATIVE_MAP.get(key, FAMILY_NARRATIVE_MAP["general_rebound"])
    line = f"{label}: {narrative}"
    return truncate_text(line, limit) if limit else line


def _unique_nonempty(values: Iterable[str | None]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        items.append(cleaned)
    return items


def _extract_reason_weight(reason: str | None) -> int:
    matches = re.findall(r"([+-]\d+)(?!.*[+-]\d)", str(reason or ""))
    if not matches:
        return 0
    try:
        return int(matches[-1])
    except Exception:
        return 0


def _humanize_quality_reason(reason: str | None) -> str:
    raw = str(reason or "").strip()
    if not raw or _extract_reason_weight(raw) <= 0:
        return ""
    for pattern, phrase in _QUALITY_REASON_HINTS:
        if pattern.search(raw):
            return phrase
    return ""


def summarize_signal_breakdown(
    *,
    signals_fired: Iterable[str] | None,
    quality_reasons: Iterable[str] | None = None,
    max_items: int = 3,
    hint: str | None = None,
) -> str:
    items: list[str] = []
    for reason in quality_reasons or []:
        phrase = _humanize_quality_reason(reason)
        if phrase:
            items.append(phrase)
    for signal in signals_fired or []:
        items.append(humanize_signal(signal))
    items = _unique_nonempty(items)
    if hint and len(items) < max_items:
        items.append(truncate_text(hint, 28))
        items = _unique_nonempty(items)
    if not items:
        return "복수 신호가 동시에 확인됨"
    return ", ".join(items[:max_items])


def describe_hunter_swing_suitability(day1_score: int | float, swing_score: int | float) -> str:
    day1 = int(day1_score)
    swing = int(swing_score)
    if swing >= day1 + SWING_BIAS_THRESHOLD:
        return "3~7일 회복형 (swing 우세)"
    if day1 >= swing + SWING_BIAS_THRESHOLD:
        return "당일 반등형 (entry 우세)"
    return "혼합형 (당일/스윙 균형)"


def _peak_day_anchor(peak_day: str | None) -> int:
    match = re.search(r"D(\d+)", str(peak_day or ""))
    if not match:
        return 4
    return int(match.group(1))


def describe_scanner_swing_suitability(best_info: dict) -> str:
    peak_day = str(best_info.get("peak_day", "D4~5") or "D4~5")
    mae_avg = str(best_info.get("mae_avg", "-3.5%") or "-3.5%")
    anchor = _peak_day_anchor(peak_day)
    if anchor <= 2:
        style = "빠른 스냅백형"
    elif anchor <= 3:
        style = "초기 눌림 회복형"
    elif anchor <= 5:
        style = "3~5일 회복형"
    else:
        style = "눌림 소화형"
    return f"Peak {peak_day} / MAE avg {mae_avg} 기준 {style}"


def select_scanner_swing_info(signals_fired: Iterable[str] | None, weights: dict | None) -> dict:
    signal_details = (weights or {}).get("signal_details", {})

    def _get_info(signal: str) -> dict:
        default = SCANNER_SWING_DEFAULTS.get(signal, {"peak_day": "D4~5", "swing_acc": "74%", "mae_avg": "-3.5%"})
        current = signal_details.get(signal, {})
        peak_day = current.get("peak_day", default["peak_day"])
        swing_acc = current.get("swing_acc", default["swing_acc"])
        mae_avg = current.get("mae_avg", default["mae_avg"])
        if isinstance(mae_avg, (int, float)):
            mae_avg = f"{mae_avg:.1f}%"
        return {
            "peak_day": str(peak_day),
            "swing_acc": str(swing_acc),
            "mae_avg": str(mae_avg),
            "mae_source": "자동계산" if signal_details else "백테스트추정",
        }

    selected = _get_info("bb_touch")
    available = set(signals_fired or [])
    for signal in SCANNER_SWING_PRIORITY:
        if signal in available:
            selected = _get_info(signal)
            break
    return selected


def build_scanner_peak_line(best_info: dict) -> str:
    peak_day = str(best_info.get("peak_day", "D4~5") or "D4~5")
    mae_avg = str(best_info.get("mae_avg", "-3.5%") or "-3.5%")
    mae_source = str(best_info.get("mae_source", "백테스트추정") or "백테스트추정")
    return f"📈 스윙: Peak {peak_day} | MAE avg {mae_avg} [{mae_source}]"


def _join_market_labels(values: Iterable[str] | None, *, limit: int) -> str:
    labels = [truncate_text(value, 16) for value in values or [] if str(value or "").strip()]
    return ", ".join(labels[:limit])


def _format_hunter_regime_context(aria: dict) -> str:
    parts = [f"ORCA {str(aria.get('regime', '') or '').strip()}"]
    inflows = _join_market_labels(aria.get("key_inflows", []), limit=2)
    outflows = _join_market_labels(aria.get("key_outflows", []), limit=1)
    if inflows:
        parts.append(f"유입 {inflows}")
    if outflows:
        parts.append(f"역풍 {outflows}")
    return " | ".join(_unique_nonempty(parts))


def _format_scanner_regime_context(aria: dict) -> str:
    parts = [f"ORCA {str(aria.get('regime', '') or '').strip()}"]
    trend = str(aria.get("trend", "") or "").strip()
    if trend:
        parts.append(f"추세 {trend}")
    else:
        sentiment_score = aria.get("sentiment_score")
        if sentiment_score not in (None, ""):
            parts.append(f"심리 {sentiment_score}")
    inflows = _join_market_labels(aria.get("key_inflows", []), limit=2)
    outflows = _join_market_labels(aria.get("key_outflows", []), limit=1)
    if inflows:
        parts.append(f"유입 {inflows}")
    if outflows:
        parts.append(f"역풍 {outflows}")
    return " | ".join(_unique_nonempty(parts))


def _labeled_line(prefix: str, body: str, limit: int) -> str:
    return prefix + truncate_text(body, max(limit - len(prefix), 0))


def build_hunter_explanation_lines(
    *,
    signal_family: str | None,
    signals_fired: Iterable[str] | None,
    day1_score: int | float,
    swing_score: int | float,
    aria: dict,
    hint: str | None = None,
) -> list[str]:
    lines = [
        "🧭 추천 이유",
        build_family_narrative_line(signal_family, limit=HUNTER_LINE_BUDGETS["family"]),
        _labeled_line(
            "핵심 근거: ",
            summarize_signal_breakdown(signals_fired=signals_fired, hint=hint),
            HUNTER_LINE_BUDGETS["core"],
        ),
        _labeled_line(
            "스윙 적합성: ",
            describe_hunter_swing_suitability(day1_score, swing_score),
            HUNTER_LINE_BUDGETS["swing"],
        ),
    ]
    regime_context = _format_hunter_regime_context(aria)
    if regime_context:
        lines.append(_labeled_line("시장 맥락: ", regime_context, HUNTER_LINE_BUDGETS["regime"]))
    return lines


def build_scanner_explanation_lines(
    *,
    signal_family: str | None,
    signals_fired: Iterable[str] | None,
    quality_reasons: Iterable[str] | None,
    best_info: dict,
    aria: dict,
) -> list[str]:
    lines = [
        "🧭 추천 이유",
        build_family_narrative_line(signal_family, limit=SCANNER_LINE_BUDGETS["family"]),
        _labeled_line(
            "핵심 근거: ",
            summarize_signal_breakdown(signals_fired=signals_fired, quality_reasons=quality_reasons),
            SCANNER_LINE_BUDGETS["core"],
        ),
        _labeled_line(
            "스윙 적합성: ",
            describe_scanner_swing_suitability(best_info),
            SCANNER_LINE_BUDGETS["swing"],
        ),
    ]
    regime_context = _format_scanner_regime_context(aria)
    if regime_context:
        lines.append(_labeled_line("시장 맥락: ", regime_context, SCANNER_LINE_BUDGETS["regime"]))
    return lines


def build_devil_summary(devil: dict | None) -> str:
    devil = devil or {}
    status = str(devil.get("devil_status", "") or "").strip()
    objections = devil.get("objections", []) or []
    first_objection = str(objections[0] if objections else devil.get("main_risk", "") or "").strip()
    verdict = str(devil.get("verdict", "") or "").strip()
    if status == "ok_with_objection":
        if verdict and first_objection:
            return f"{verdict}: {first_objection}"
        return first_objection or "반박 제시"
    if status == "no_material_objection":
        return "반박 없음"
    if status == "api_error":
        return "응답 실패"
    if status == "parse_failed":
        return "응답 파싱 실패"
    if status == "skipped_quality_gate":
        return "미실행"
    return ""


def build_scanner_reason_payload(
    *,
    signal_family: str | None,
    signals_fired: Iterable[str] | None,
    quality_reasons: Iterable[str] | None,
    best_info: dict,
    aria: dict,
    devil: dict | None = None,
) -> tuple[str, dict]:
    lines = build_scanner_explanation_lines(
        signal_family=signal_family,
        signals_fired=signals_fired,
        quality_reasons=quality_reasons,
        best_info=best_info,
        aria=aria,
    )
    detail_lines = lines[1:]
    reason_detail = "\n".join(detail_lines)
    components = {
        "family_narrative": detail_lines[0] if len(detail_lines) > 0 else "",
        "signal_breakdown": detail_lines[1] if len(detail_lines) > 1 else "",
        "swing_suitability": detail_lines[2] if len(detail_lines) > 2 else "",
        "regime_context": detail_lines[3] if len(detail_lines) > 3 else "",
        "devil_summary": build_devil_summary(devil),
    }
    return reason_detail, components
