"""Helpers for JACKAL backtest report selection and candidate materialization."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from orca.state import (
    record_backtest_candidate,
    record_backtest_lesson,
    record_backtest_outcome,
)


BACKTEST_SOURCE_EVENT_TYPE = "backtest"


def merge_reports_by_analysis_date(*report_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge report collections while preserving the first payload for a given date.

    ORCA research-session rows should win over memory.json fallback rows for the
    same trading day. Later groups only fill missing dates.
    """

    merged: dict[str, dict[str, Any]] = {}
    for reports in report_groups:
        for report in reports:
            analysis_date = str(report.get("analysis_date") or "").strip()
            if not analysis_date or analysis_date in merged:
                continue
            merged[analysis_date] = deepcopy(report)
    return [merged[key] for key in sorted(merged)]


def select_backtest_reports(
    reports: list[dict[str, Any]],
    *,
    backtest_days: int,
    tracking_days: int,
    after_analysis_date: str | None = None,
) -> list[dict[str, Any]]:
    """Select completed trading-day reports for full or incremental replay."""

    dated = [
        deepcopy(report)
        for report in reports
        if str(report.get("analysis_date") or "").strip()
    ]
    dated.sort(key=lambda report: str(report.get("analysis_date") or ""))
    if tracking_days > 0 and len(dated) > tracking_days:
        eligible = dated[:-tracking_days]
    elif tracking_days <= 0:
        eligible = dated
    else:
        eligible = []

    if after_analysis_date:
        eligible = [
            report
            for report in eligible
            if str(report.get("analysis_date") or "") > str(after_analysis_date)
        ]
        return eligible

    if backtest_days > 0:
        return eligible[-backtest_days:]
    return eligible


def infer_market(ticker: str) -> str:
    value = str(ticker or "").upper()
    if value.endswith(".KS"):
        return "KRX-KS"
    if value.endswith(".KQ"):
        return "KRX-KQ"
    return "US"


def build_backtest_signals(
    *,
    ticker: str,
    tech: dict[str, Any],
    inflows_text: str,
    sector_inflow_match: bool,
) -> list[str]:
    signals: list[str] = []
    rsi = float(tech.get("rsi", 50) or 50)
    bb_pos = float(tech.get("bb_pos", 50) or 50)
    change_5d = float(tech.get("change_5d", 0) or 0)
    vol_ratio = float(tech.get("vol_ratio", 1.0) or 1.0)
    price = float(tech.get("price", 0) or 0)
    ma50 = tech.get("ma50")

    if rsi <= 35:
        signals.append("rsi_oversold")
    if bb_pos <= 20:
        signals.append("bb_touch")
    if vol_ratio >= 1.5:
        signals.append("volume_climax")
    if change_5d <= -3:
        signals.append("momentum_dip")
    if tech.get("bullish_div"):
        signals.append("rsi_divergence")
    if ma50 and price > 0:
        try:
            ma50_val = float(ma50)
        except (TypeError, ValueError):
            ma50_val = 0.0
        if ma50_val > 0 and abs(price - ma50_val) / ma50_val < 0.03 and (rsi <= 40 or bb_pos <= 30):
            signals.append("ma_support")
    if sector_inflow_match or str(ticker or "").lower().split(".")[0] in str(inflows_text or ""):
        signals.append("sector_rebound")

    deduped: list[str] = []
    seen: set[str] = set()
    for signal in signals:
        if signal not in seen:
            seen.add(signal)
            deduped.append(signal)
    return deduped


def build_backtest_quality_label(score: float | int | None) -> str:
    try:
        numeric = float(score or 0.0)
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric >= 80:
        return "최강"
    if numeric >= 65:
        return "강"
    if numeric >= 50:
        return "보통"
    return "약"


def _analysis_timestamp(analysis_date: str, *, hour: int = 9, minute: int = 0) -> str:
    return f"{analysis_date}T{hour:02d}:{minute:02d}:00+09:00"


def build_backtest_candidate_entry(
    *,
    session_id: str,
    source_session_id: str | None,
    analysis_date: str,
    ticker: str,
    rank_index: int,
    regime: str,
    inflows: list[str],
    outflows: list[str],
    market_note: str,
    tech: dict[str, Any],
    quality_score: float | None,
    signals_fired: list[str],
) -> dict[str, Any]:
    detected_at = _analysis_timestamp(analysis_date)
    return {
        "ticker": ticker,
        "market": infer_market(ticker),
        "analysis_date": analysis_date,
        "timestamp": detected_at,
        "detected_at": detected_at,
        "alerted": True,
        "is_entry": True,
        "origin": "backtest",
        "mode": "backtest_replay",
        "signal_family": "general",
        "signal_family_raw": "general",
        "signals_fired": signals_fired,
        "quality_score": quality_score,
        "final_score": quality_score,
        "quality_label": build_backtest_quality_label(quality_score),
        "price_at_scan": tech.get("price"),
        "rsi": tech.get("rsi"),
        "bb_pos": tech.get("bb_pos"),
        "change_5d": tech.get("change_5d"),
        "vol_ratio": tech.get("vol_ratio"),
        "bullish_div": tech.get("bullish_div"),
        "market_regime": regime,
        "orca_inflows": list(inflows),
        "orca_outflows": list(outflows),
        "one_line_summary": market_note,
        "backtest_session_id": session_id,
        "source_session_id": source_session_id,
        "backtest_rank_index": rank_index,
        "probability_origin": "backtest",
    }


def build_backtest_outcome_entry(
    *,
    analysis_date: str,
    tech: dict[str, Any],
    outcome: dict[str, Any],
    tracking_days: int,
) -> dict[str, Any]:
    payload = {
        "analysis_date": analysis_date,
        "origin": "backtest",
        "outcome_tracked_at": _analysis_timestamp(analysis_date, hour=16),
        "outcome_checked": True,
        "tracking_days": tracking_days,
        "price_at_scan": tech.get("price"),
        "price_1d_later": outcome.get("price_1d_later"),
        "outcome_1d_pct": outcome.get("d1_pct"),
        "outcome_1d_hit": outcome.get("d1_hit"),
        "price_peak": outcome.get("price_peak"),
        "peak_day": outcome.get("peak_day"),
        "peak_pct": outcome.get("peak_pct"),
        "outcome_swing_hit": outcome.get("swing_hit"),
        "tracked_bars": outcome.get("tracked_bars"),
    }
    return payload


def materialize_backtest_day(
    *,
    session_id: str,
    source_session_id: str | None,
    analysis_date: str,
    regime: str,
    inflows: list[str],
    outflows: list[str],
    inflows_text: str,
    market_note: str,
    daily_picks: list[dict[str, Any]],
    tracking_days: int,
) -> dict[str, Any]:
    results = {
        "candidates": 0,
        "outcomes": 0,
        "lessons": 0,
        "candidate_ids": [],
    }
    for pick in daily_picks:
        ticker = str(pick.get("ticker") or "")
        rank_index = int(pick.get("rank_index") or 0)
        tech = dict(pick.get("indicators") or {})
        outcome = dict(pick.get("outcome") or {})
        if not ticker:
            continue
        signals_fired = build_backtest_signals(
            ticker=ticker,
            tech=tech,
            inflows_text=inflows_text,
            sector_inflow_match=bool(pick.get("sector_inflow_match")),
        )
        quality_score = pick.get("scores", {}).get("s2_score") or pick.get("scores", {}).get("s1_score")
        entry = build_backtest_candidate_entry(
            session_id=session_id,
            source_session_id=source_session_id,
            analysis_date=analysis_date,
            ticker=ticker,
            rank_index=rank_index,
            regime=regime,
            inflows=inflows,
            outflows=outflows,
            market_note=market_note,
            tech=tech,
            quality_score=quality_score,
            signals_fired=signals_fired,
        )
        external_key = f"jackal-backtest:{analysis_date}:{ticker}"
        source_event_id = f"{session_id}:{analysis_date}:{ticker}:{rank_index}"
        candidate_id = record_backtest_candidate(
            entry,
            source_event_id=source_event_id,
            source_external_key=external_key,
            source_session_id=session_id,
        )
        results["candidates"] += 1
        results["candidate_ids"].append(candidate_id)

        outcome_entry = build_backtest_outcome_entry(
            analysis_date=analysis_date,
            tech=tech,
            outcome=outcome,
            tracking_days=tracking_days,
        )
        latest_outcome = record_backtest_outcome(candidate_id, outcome_entry)
        if latest_outcome:
            results["outcomes"] += 1
            lesson_type = "backtest_win" if latest_outcome.get("hit") else "backtest_loss"
            lesson_label = "backtest win" if latest_outcome.get("hit") else "backtest loss"
            lesson_id = record_backtest_lesson(
                candidate_id,
                outcome_id=latest_outcome.get("outcome_id"),
                lesson_type=lesson_type,
                label=lesson_label,
                lesson_value=float(latest_outcome.get("return_pct") or 0.0),
                lesson_timestamp=_analysis_timestamp(analysis_date, hour=16),
                lesson={
                    "origin": "backtest",
                    "analysis_date": analysis_date,
                    "ticker": ticker,
                    "signal_family": entry.get("signal_family"),
                    "signals_fired": signals_fired,
                    "regime": regime,
                    "rank_index": rank_index,
                    "peak_day": outcome.get("peak_day"),
                    "peak_pct": outcome.get("peak_pct"),
                },
            )
            if lesson_id:
                results["lessons"] += 1
    return results
