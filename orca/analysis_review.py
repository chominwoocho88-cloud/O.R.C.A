"""Candidate review scorecard helpers extracted from orca.analysis."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from ._analysis_common import KST, _now, _today
from .learning_policy import (
    CAUTIOUS_EFFECTIVE_WIN_RATE,
    MIN_SAMPLES,
    TRUSTED_EFFECTIVE_WIN_RATE,
)
from .state import (
    list_candidates,
    record_candidate_review,
    summarize_candidate_probabilities,
)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def _report_market_bias(report: dict) -> dict:
    regime = str(report.get("market_regime", ""))
    trend = str(report.get("trend_phase", ""))
    summary = str(report.get("one_line_summary", ""))
    confidence = str(report.get("confidence_overall", ""))
    text = " ".join([regime, trend, summary])

    bearish = ("위험회피" in regime) or ("하락" in trend)
    bullish = ("위험선호" in regime) and ("하락" not in trend)
    mixed = any(token in text for token in ["혼조", "전환", "반론", "불확실", "관망"])

    if bearish and not bullish:
        bias = "risk_off"
        label = "위험회피"
        reason = "현재 ORCA 레짐이 방어적이어서 장기 추세보다 리스크 관리가 우선입니다."
    elif bullish and not mixed and confidence != "낮음":
        bias = "risk_on"
        label = "위험선호"
        reason = "현재 ORCA 레짐이 우호적이라 JACKAL의 롱 후보를 함께 검토하기 좋은 구간입니다."
    else:
        bias = "mixed"
        label = "혼조/관망"
        reason = "현재 ORCA 레짐이 혼조라서 후보를 바로 추종하기보다 관찰 대상으로 보는 편이 안전합니다."

    return {"bias": bias, "label": label, "reason": reason}


def _match_candidate_themes(candidate_terms: list[str], flows: list[dict]) -> list[str]:
    matches: list[str] = []
    blobs = [
        " ".join(
            [
                str(flow.get("zone", "")),
                str(flow.get("reason", "")),
                str(flow.get("data_point", "")),
            ]
        ).lower()
        for flow in flows
    ]
    for term in candidate_terms:
        lowered = str(term or "").strip().lower()
        if len(lowered) < 2:
            continue
        tokens = [tok for tok in re.split(r"[/,·()\s]+", lowered) if len(tok) >= 2]
        for blob in blobs:
            if lowered in blob or any(tok in blob for tok in tokens):
                if term not in matches:
                    matches.append(term)
                break
    return matches


_REVIEW_SCORE_WEIGHTS = {
    "market_bias": 0.15,
    "signal_family_history": 0.30,
    "quality": 0.20,
    "theme_match": 0.15,
    "devil_penalty": 0.10,
    "thesis_killer_penalty": 0.10,
}
# Penalty weights are positive. Components return negative values
# when the penalty condition is met, resulting in negative contribution.

_REVIEW_VERDICTS = (
    "strong_aligned",
    "aligned",
    "neutral",
    "opposed",
    "strong_opposed",
)

_CONFIDENCE_SCORE = {"low": 1, "medium": 2, "high": 3}


def _clamp(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _alignment_from_review_verdict(review_verdict: str) -> str:
    if review_verdict in {"strong_aligned", "aligned"}:
        return "aligned"
    if review_verdict in {"strong_opposed", "opposed"}:
        return "opposed"
    return "neutral"


def normalize_candidate_review_payload(payload: dict | None, alignment: str) -> dict:
    review = dict(payload or {})
    try:
        alignment_score = float(review.get("alignment_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        alignment_score = 0.0
    alignment_score = round(_clamp(alignment_score), 3)

    review_verdict = str(review.get("review_verdict", "")).strip()
    if review_verdict not in _REVIEW_VERDICTS:
        review_verdict = "aligned" if alignment == "aligned" else "opposed" if alignment == "opposed" else "neutral"

    reason_codes_raw = review.get("alignment_reason_codes", [])
    if isinstance(reason_codes_raw, list):
        reason_codes = [str(code).strip() for code in reason_codes_raw if str(code).strip()]
    else:
        reason_codes = []

    review_confidence = str(review.get("review_confidence", "low") or "low").strip().lower()
    if review_confidence not in _CONFIDENCE_SCORE:
        review_confidence = "low"

    review["alignment"] = alignment or _alignment_from_review_verdict(review_verdict)
    review["alignment_score"] = alignment_score
    review["alignment_reason_codes"] = reason_codes
    review["review_confidence"] = review_confidence
    review["review_verdict"] = review_verdict
    return review


def _match_candidate_flow_items(candidate_terms: list[str], flows: list[dict]) -> list[dict]:
    matches = _match_candidate_themes(candidate_terms, flows)
    if not matches:
        return []

    matched_items: list[dict] = []
    for flow in flows:
        blob = " ".join(
            [
                str(flow.get("zone", "")),
                str(flow.get("reason", "")),
                str(flow.get("data_point", "")),
            ]
        ).lower()
        for term in matches:
            lowered = str(term or "").strip().lower()
            if len(lowered) < 2:
                continue
            tokens = [tok for tok in re.split(r"[/,·()\s]+", lowered) if len(tok) >= 2]
            if lowered in blob or any(tok in blob for tok in tokens):
                matched_items.append(flow)
                break
    return matched_items


def _flow_has_bullish_momentum(flow: dict) -> bool:
    text = str(flow.get("momentum", "")).lower()
    return any(token in text for token in ["강", "상승", "개선", "bull", "up", "positive"])


def _flow_has_bearish_momentum(flow: dict) -> bool:
    text = str(flow.get("momentum", "")).lower()
    return any(token in text for token in ["약", "하락", "악화", "bear", "down", "negative"])


def _market_bias_component(bias: dict) -> tuple[float, list[str]]:
    if bias["bias"] == "risk_on":
        return 1.0, ["market_bias_tailwind"]
    if bias["bias"] == "risk_off":
        return -1.0, ["market_bias_headwind"]
    return 0.0, ["regime_unclear"]


def _signal_family_history_component(
    signal_family: str,
    family_history: dict[str, dict],
) -> tuple[float, list[str], bool]:
    if not signal_family:
        return 0.0, ["insufficient_data"], False

    stats = family_history.get(signal_family, {})
    if not stats or not stats.get("qualified"):
        return 0.0, ["insufficient_data"], False

    effective = float(stats.get("effective_win_rate", 0.0) or 0.0)
    component = _clamp((effective - 50.0) / 20.0)
    codes: list[str] = []
    if effective >= TRUSTED_EFFECTIVE_WIN_RATE * 100:
        codes.append("signal_family_trusted")
    elif effective <= CAUTIOUS_EFFECTIVE_WIN_RATE * 100:
        codes.append("signal_family_cautious")
    return round(component, 3), codes, True


def _quality_component(signal_quality: float | int | None) -> tuple[float, list[str], bool]:
    try:
        quality = float(signal_quality)
    except (TypeError, ValueError):
        return 0.0, ["insufficient_data"], False

    component = _clamp((quality - 50.0) / 50.0)
    codes: list[str] = []
    if quality >= 75:
        codes.append("quality_high")
    elif quality <= 40:
        codes.append("quality_low")
    return round(component, 3), codes, True


def _theme_match_component(
    inflow_matches: list[str],
    outflow_matches: list[str],
    inflow_items: list[dict],
    outflow_items: list[dict],
) -> tuple[float, list[str]]:
    if inflow_matches and outflow_matches:
        return 0.0, ["mixed_signals"]

    if inflow_matches:
        codes = ["sector_inflow_match"]
        component = 1.0 if len(inflow_matches) >= 2 else 0.6
        if len(inflow_matches) >= 2:
            codes.append("theme_match_strong")
        if any(_flow_has_bullish_momentum(flow) for flow in inflow_items):
            codes.append("sector_momentum_bullish")
        return component, codes

    if outflow_matches:
        codes = ["sector_outflow_match", "theme_mismatch"]
        component = -1.0 if len(outflow_matches) >= 2 else -0.6
        if any(_flow_has_bearish_momentum(flow) for flow in outflow_items):
            codes.append("sector_momentum_bearish")
        return component, codes

    return 0.0, []


def _devil_penalty_component(devil_verdict: str) -> tuple[float, list[str], bool]:
    verdict = str(devil_verdict or "").strip()
    if verdict == "반대":
        return -1.0, ["devil_bearish_warn", "devil_contradicts_thesis"], False
    if verdict == "부분동의":
        return -0.5, ["devil_bearish_warn"], False
    if verdict == "동의":
        return 0.0, ["devil_bullish_agree"], True
    return 0.0, [], False


def _thesis_killer_penalty_component(payload: dict) -> tuple[float, list[str]]:
    if payload.get("thesis_killer_hit"):
        return -1.0, ["thesis_killer_triggered"]
    return 0.0, []


def _score_to_review_verdict(score: float) -> str:
    if score >= 0.60:
        return "strong_aligned"
    if score >= 0.30:
        return "aligned"
    if score > -0.30:
        return "neutral"
    if score >= -0.60:
        return "opposed"
    return "strong_opposed"


def _legacy_action_recommendation(
    alignment: str,
    signal_quality: float | int | None,
    devil_verdict: str,
    payload: dict,
) -> str:
    try:
        quality = float(signal_quality or 0.0)
    except (TypeError, ValueError):
        quality = 0.0

    if alignment == "aligned" and quality >= 75 and devil_verdict != "반대":
        return "follow"
    if alignment == "opposed" or devil_verdict == "반대" or payload.get("thesis_killer_hit"):
        return "avoid"
    return "watch"


def _review_confidence_label(
    *,
    evidence_count: int,
    bullish_agree: bool,
    reason_codes: list[str],
) -> str:
    if "insufficient_data" in reason_codes:
        return "low"
    if evidence_count >= 4 and ("mixed_signals" not in reason_codes) and ("regime_unclear" not in reason_codes):
        return "high"
    if evidence_count >= 2 or bullish_agree:
        return "medium"
    return "low"


def review_recent_candidates(
    report: dict,
    *,
    run_id: str | None = None,
    analysis_date: str | None = None,
    limit: int = 12,
    max_age_days: int = 7,
) -> dict:
    analysis_date = analysis_date or _today()
    bias = _report_market_bias(report)
    inflows = report.get("inflows", [])
    outflows = report.get("outflows", [])
    probability_summary = summarize_candidate_probabilities(days=90, min_samples=MIN_SAMPLES)
    family_history = probability_summary.get("by_signal_family", {})

    recent = list_candidates(source_system="jackal", unresolved_only=True, limit=max(limit * 4, 40))
    cutoff = _now() - timedelta(days=max_age_days)
    selected = []
    for candidate in recent:
        detected_at = _parse_iso(candidate.get("detected_at", ""))
        if detected_at and detected_at < cutoff:
            continue
        selected.append(candidate)
        if len(selected) >= limit:
            break

    summary = {
        "analysis_date": analysis_date,
        "market_bias": bias["bias"],
        "market_bias_label": bias["label"],
        "reviewed_count": 0,
        "aligned_count": 0,
        "neutral_count": 0,
        "opposed_count": 0,
        "follow_count": 0,
        "watch_count": 0,
        "avoid_count": 0,
        "review_verdict_breakdown": {
            "strong_aligned": 0,
            "aligned": 0,
            "neutral": 0,
            "opposed": 0,
            "strong_opposed": 0,
        },
        "average_review_confidence": "low",
        "reason_code_frequency": {},
        "highlights": [],
    }
    if not selected:
        return summary

    confidence_points = 0
    for candidate in selected:
        payload = candidate.get("payload", {})
        signal_quality = payload.get("quality_score", candidate.get("quality_score"))
        devil_verdict = str(payload.get("devil_verdict", ""))
        theme_terms = payload.get("orca_inflows", []) if isinstance(payload.get("orca_inflows"), list) else []
        inflow_matches = _match_candidate_themes(theme_terms, inflows)
        outflow_matches = _match_candidate_themes(theme_terms, outflows)
        inflow_items = _match_candidate_flow_items(theme_terms, inflows)
        outflow_items = _match_candidate_flow_items(theme_terms, outflows)

        market_bias_score, market_bias_codes = _market_bias_component(bias)
        history_score, history_codes, history_present = _signal_family_history_component(
            str(candidate.get("signal_family", "") or ""),
            family_history,
        )
        quality_score_component, quality_codes, quality_present = _quality_component(signal_quality)
        theme_match_score, theme_codes = _theme_match_component(
            inflow_matches,
            outflow_matches,
            inflow_items,
            outflow_items,
        )
        devil_penalty, devil_codes, devil_bullish_agree = _devil_penalty_component(devil_verdict)
        thesis_killer_penalty, thesis_killer_codes = _thesis_killer_penalty_component(payload)

        alignment_score = (
            market_bias_score * _REVIEW_SCORE_WEIGHTS["market_bias"]
            + history_score * _REVIEW_SCORE_WEIGHTS["signal_family_history"]
            + quality_score_component * _REVIEW_SCORE_WEIGHTS["quality"]
            + theme_match_score * _REVIEW_SCORE_WEIGHTS["theme_match"]
            + devil_penalty * _REVIEW_SCORE_WEIGHTS["devil_penalty"]
            + thesis_killer_penalty * _REVIEW_SCORE_WEIGHTS["thesis_killer_penalty"]
        )
        alignment_score = round(_clamp(alignment_score), 3)

        review_verdict = _score_to_review_verdict(alignment_score)
        alignment = _alignment_from_review_verdict(review_verdict)

        thesis_killer = ""
        if payload.get("thesis_killer_hit"):
            thesis_killer = str(payload.get("killer_detail") or "JACKAL Devil thesis killer hit")
        elif outflow_matches:
            thesis_killer = "현재 ORCA 역풍 테마와 겹침: " + ", ".join(outflow_matches[:2])
        elif report.get("thesis_killers"):
            thesis_killer = str(report["thesis_killers"][0].get("event", ""))

        action_recommendation = _legacy_action_recommendation(alignment, signal_quality, devil_verdict, payload)

        reason_codes = list(
            dict.fromkeys(
                market_bias_codes
                + history_codes
                + quality_codes
                + theme_codes
                + devil_codes
                + thesis_killer_codes
            )
        )
        evidence_count = sum(
            1
            for present in (
                bias["bias"] != "mixed",
                history_present,
                quality_present,
                bool(inflow_matches or outflow_matches),
                bool(devil_verdict),
                bool(payload.get("thesis_killer_hit")),
            )
            if present
        )
        review_confidence = _review_confidence_label(
            evidence_count=evidence_count,
            bullish_agree=devil_bullish_agree,
            reason_codes=reason_codes,
        )

        rationale_parts = [bias["reason"]]
        if history_codes:
            rationale_parts.append(
                "Signal family history: "
                + ", ".join(history_codes)
                + f" ({candidate.get('signal_family', '') or 'unknown'})"
            )
        if inflow_matches:
            rationale_parts.append("현재 ORCA 유입 테마와 겹침: " + ", ".join(inflow_matches[:2]))
        if outflow_matches:
            rationale_parts.append("현재 ORCA 역풍 테마와 겹침: " + ", ".join(outflow_matches[:2]))
        if devil_verdict:
            rationale_parts.append("Devil verdict: " + devil_verdict)
        if thesis_killer:
            rationale_parts.append("Thesis killer: " + thesis_killer)

        review = normalize_candidate_review_payload(
            {
                "alignment": alignment,
                "review_verdict": review_verdict,
                "alignment_score": alignment_score,
                "alignment_reason_codes": reason_codes,
                "review_confidence": review_confidence,
                "orca_regime": report.get("market_regime", ""),
                "orca_trend": report.get("trend_phase", ""),
                "candidate_signal_family": candidate.get("signal_family", ""),
                "quality_score": signal_quality,
                "inflow_matches": inflow_matches,
                "outflow_matches": outflow_matches,
                "rationale": rationale_parts,
            },
            alignment,
        )
        record_candidate_review(
            candidate["candidate_id"],
            analysis_date=analysis_date,
            run_id=run_id,
            alignment=alignment,
            review_verdict=review_verdict,
            orca_regime=report.get("market_regime", ""),
            orca_trend=report.get("trend_phase", ""),
            confidence=report.get("confidence_overall", ""),
            thesis_killer=thesis_killer or None,
            review=review,
        )

        summary["reviewed_count"] += 1
        summary[f"{alignment}_count"] += 1
        summary[f"{action_recommendation}_count"] += 1
        summary["review_verdict_breakdown"][review_verdict] += 1
        confidence_points += _CONFIDENCE_SCORE.get(review_confidence, 1)
        for code in reason_codes:
            summary["reason_code_frequency"][code] = summary["reason_code_frequency"].get(code, 0) + 1
        if len(summary["highlights"]) < 5:
            summary["highlights"].append(
                {
                    "ticker": candidate.get("ticker", ""),
                    "name": candidate.get("name", ""),
                    "source_event_type": candidate.get("source_event_type", ""),
                    "alignment": alignment,
                    "review_verdict": review_verdict,
                    "alignment_score": alignment_score,
                    "alignment_reason_codes": reason_codes,
                    "review_confidence": review_confidence,
                    "quality_score": signal_quality,
                    "signal_family": candidate.get("signal_family", ""),
                    "why": " | ".join(rationale_parts[:2]),
                }
            )

    if summary["reviewed_count"] > 0:
        avg_confidence = confidence_points / summary["reviewed_count"]
        if avg_confidence >= 2.5:
            summary["average_review_confidence"] = "high"
        elif avg_confidence >= 1.5:
            summary["average_review_confidence"] = "medium"
        else:
            summary["average_review_confidence"] = "low"

    return summary
