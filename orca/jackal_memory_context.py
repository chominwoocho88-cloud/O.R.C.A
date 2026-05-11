"""JACKAL memory-context builder for Phase 9-4a.

This module prepares the learning block that may be injected into
Analyst/Devil prompts in a later phase. In Phase 9-4a it is used for
shadow logging only, so Hunter prompts remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from orca import state
from orca import jackal_memory_shadow_store as _shadow_store
from shared.paths import JACKAL_LEGACY_DIR


MEMORY_MODE_OFF = "off"
MEMORY_MODE_SHADOW = "shadow"
MEMORY_MODE_ON = "on"
VALID_MEMORY_MODES = {MEMORY_MODE_OFF, MEMORY_MODE_SHADOW, MEMORY_MODE_ON}

MIN_GLOBAL_RESOLVED = 20
MIN_PATTERN_RESOLVED = 5
MAX_STATS_BLOCK_CHARS = 1000
SHADOW_LOG_FILE = JACKAL_LEGACY_DIR / "memory_context_shadow.log"
MEMORY_CONTEXT_SHADOW_SCHEMA = _shadow_store.SCHEMA_SQL


def get_memory_mode() -> str:
    """Return JACKAL memory prompt mode.

    Phase 9-4a supports only shadow logging at call sites. The ``on`` value
    is accepted now so Phase 9-4b can enable prompt injection without changing
    the flag contract.
    """
    mode = os.environ.get("JACKAL_MEMORY_PROMPT_MODE", MEMORY_MODE_SHADOW)
    mode = str(mode or "").strip().lower()
    return mode if mode in VALID_MEMORY_MODES else MEMORY_MODE_SHADOW


def build_memory_context(ticker: str, aria: dict[str, Any] | None, role: str) -> dict[str, Any] | None:
    """Build a compact learned-memory context for a JACKAL prompt.

    The preferred source is ``jackal_prediction_cards`` once enough resolved
    cards exist. Until then, this falls back to the older ``candidate_lessons``
    memory so shadow logs are useful before operating data accumulates.
    """
    aria = aria or {}
    role = _normalize_role(role)

    try:
        global_resolved = _count_resolved_predictions()
        if global_resolved >= MIN_GLOBAL_RESOLVED:
            similar = _query_similar_resolved(aria)
            if len(similar) >= MIN_PATTERN_RESOLVED:
                return _context_from_records(
                    similar,
                    ticker=ticker,
                    aria=aria,
                    role=role,
                    source="prediction_cards",
                    global_resolved=global_resolved,
                    match_scope="regime_fear_greed",
                )

        return _build_from_candidate_lessons(ticker, aria, role, global_resolved=global_resolved)
    except Exception:
        return None


def log_shadow_memory_context(
    ticker: str,
    aria: dict[str, Any] | None,
    role: str,
    memory_context: dict[str, Any] | None,
    *,
    mode: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Append a shadow-memory entry without changing any prompt."""
    aria = aria or {}
    target = log_path or _shadow_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ticker": ticker,
        "role": _normalize_role(role),
        "mode": mode or get_memory_mode(),
        "regime": aria.get("regime"),
        "fear_greed": aria.get("fear_greed"),
        "fear_greed_label": aria.get("fear_greed_label"),
        "memory_context": memory_context,
        "would_inject": bool(memory_context),
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        record_memory_context_shadow(
            ticker=ticker,
            role=entry["role"],
            aria=aria,
            memory_context=memory_context,
            memory_mode=entry["mode"],
            timestamp=entry["timestamp"],
        )
    except Exception:
        pass


def record_memory_context_shadow(
    ticker: str,
    role: str,
    aria: dict[str, Any] | None,
    memory_context: dict[str, Any] | None,
    memory_mode: str,
    *,
    build_hash: str | None = None,
    timestamp: str | None = None,
) -> str | None:
    """Persist one shadow memory-context entry to JACKAL DB."""
    state.init_state_db()
    timestamp = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    with state._connect_jackal() as conn:
        return _shadow_store.record_memory_context_shadow_conn(
            conn,
            timestamp=timestamp,
            ticker=ticker,
            role=_normalize_role(role),
            aria=aria,
            memory_context=memory_context,
            memory_mode=memory_mode,
            build_hash=build_hash,
        )


def shadow_memory_context(ticker: str, aria: dict[str, Any] | None, role: str) -> dict[str, Any] | None:
    """Build and log memory context when the feature flag is not off."""
    try:
        mode = get_memory_mode()
        if mode == MEMORY_MODE_OFF:
            return None
        memory_context = build_memory_context(ticker, aria, role)
        log_shadow_memory_context(ticker, aria, role, memory_context, mode=mode)
        return memory_context
    except Exception:
        return None


def _shadow_log_path() -> Path:
    override = os.environ.get("JACKAL_MEMORY_SHADOW_LOG")
    return Path(override) if override else SHADOW_LOG_FILE


def _normalize_role(role: str) -> str:
    role = str(role or "").strip().lower()
    return role if role in {"analyst", "devil"} else "analyst"


def _count_resolved_predictions() -> int:
    state.init_state_db()
    with state._connect_jackal() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM jackal_prediction_cards WHERE status = 'resolved'"
        ).fetchone()
    return int(row[0] if row else 0)


def _query_similar_resolved(aria: dict[str, Any]) -> list[dict[str, Any]]:
    regime = str(aria.get("regime") or "").strip()
    fg_value = _to_float(aria.get("fear_greed"))
    state.init_state_db()
    with state._connect_jackal() as conn:
        rows = conn.execute(
            """
            SELECT ticker, score, current_price, actual_close_d5, outcome_d5,
                   market_regime, fear_greed, pattern_label
              FROM jackal_prediction_cards
             WHERE status = 'resolved'
               AND outcome_d5 IS NOT NULL
             ORDER BY resolved_at DESC, created_at DESC
             LIMIT 300
            """
        ).fetchall()

    records = [dict(row) for row in rows]
    if regime:
        records = [row for row in records if str(row.get("market_regime") or "") == regime]
    if fg_value is not None:
        records = [
            row
            for row in records
            if row.get("fear_greed") is not None and abs(float(row["fear_greed"]) - fg_value) <= 15
        ]
    for row in records:
        row["outcome_pct"] = _outcome_pct(row)
    return records


def _build_from_candidate_lessons(
    ticker: str,
    aria: dict[str, Any],
    role: str,
    *,
    global_resolved: int = 0,
) -> dict[str, Any] | None:
    lessons = _query_candidate_lessons(aria)
    if len(lessons) < MIN_PATTERN_RESOLVED:
        return None
    return _context_from_records(
        lessons,
        ticker=ticker,
        aria=aria,
        role=role,
        source="candidate_lessons",
        global_resolved=global_resolved,
        match_scope=lessons[0].get("match_scope", "lesson_fallback"),
    )


def _query_candidate_lessons(aria: dict[str, Any]) -> list[dict[str, Any]]:
    regime = str(aria.get("regime") or "").strip()
    state.init_state_db()
    with state._connect_orca() as conn:
        rows = conn.execute(
            """
            SELECT lesson_type, label, lesson_value, lesson_timestamp, lesson_json
              FROM candidate_lessons
             ORDER BY lesson_timestamp DESC
             LIMIT 1200
            """
        ).fetchall()

    parsed: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads(row["lesson_json"])
        outcome = _lesson_outcome(row["lesson_type"], row["label"], row["lesson_value"])
        record = {
            "ticker": payload.get("ticker"),
            "outcome_d5": outcome,
            "outcome_pct": _to_float(payload.get("peak_pct")) or _to_float(row["lesson_value"]),
            "market_regime": payload.get("regime"),
            "pattern_label": payload.get("signal_family"),
            "match_scope": "candidate_lessons_global",
        }
        parsed.append(record)

    if regime:
        matched = [row for row in parsed if str(row.get("market_regime") or "") == regime]
        if len(matched) >= MIN_PATTERN_RESOLVED:
            for row in matched:
                row["match_scope"] = "candidate_lessons_regime"
            return matched
    return parsed


def _context_from_records(
    records: list[dict[str, Any]],
    *,
    ticker: str,
    aria: dict[str, Any],
    role: str,
    source: str,
    global_resolved: int,
    match_scope: str,
) -> dict[str, Any]:
    sample_size = len(records)
    win_rate = _calc_win_rate(records)
    avg_outcome = _calc_avg_outcome(records)
    stats_block = _format_stats_block(
        win_rate=win_rate,
        avg_outcome=avg_outcome,
        sample_size=sample_size,
        regime=aria.get("regime"),
        fear_greed=aria.get("fear_greed"),
        role=role,
        source=source,
    )
    return {
        "stats_block": stats_block,
        "sample_size": sample_size,
        "win_rate": win_rate,
        "avg_outcome": avg_outcome,
        "source": source,
        "match_scope": match_scope,
        "ticker": ticker,
        "role": role,
        "global_resolved": global_resolved,
    }


def _format_stats_block(
    *,
    win_rate: float,
    avg_outcome: float,
    sample_size: int,
    regime: Any,
    fear_greed: Any,
    role: str,
    source: str,
) -> str:
    action = "평가" if role == "analyst" else "반론"
    source_label = "정규 예측카드" if source == "prediction_cards" else "후보 lesson"
    block = (
        f"[과거 학습] 비슷한 환경({regime or '정보없음'}, F&G {fear_greed if fear_greed is not None else 'N/A'}) "
        f"{source_label} {sample_size}건 기준 성공률 {win_rate:.0%}, 평균 결과 {avg_outcome:+.1f}%.\n"
        f"이번 {action}에서는 이 통계를 참고하되, 현재 가격/뉴스/레짐 증거를 우선하세요."
    )
    if len(block) > MAX_STATS_BLOCK_CHARS:
        block = block[: MAX_STATS_BLOCK_CHARS - 3].rstrip() + "..."
    return block


def _calc_win_rate(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    wins = sum(1 for row in records if str(row.get("outcome_d5") or "").lower() == "win")
    return wins / len(records)


def _calc_avg_outcome(records: list[dict[str, Any]]) -> float:
    values = []
    for row in records:
        pct = row.get("outcome_pct")
        if pct is None:
            pct = _outcome_pct(row)
        if pct is not None:
            values.append(float(pct))
    if values:
        return float(mean(values))
    proxy = {"win": 1.0, "neutral": 0.0, "loss": -1.0}
    scores = [proxy.get(str(row.get("outcome_d5") or "").lower()) for row in records]
    scores = [value for value in scores if value is not None]
    return float(mean(scores)) if scores else 0.0


def _outcome_pct(row: dict[str, Any]) -> float | None:
    entry = _to_float(row.get("current_price"))
    close = _to_float(row.get("actual_close_d5"))
    if entry is None or close is None or entry <= 0:
        return None
    return (close - entry) / entry * 100.0


def _lesson_outcome(lesson_type: Any, label: Any, lesson_value: Any) -> str:
    text = f"{lesson_type or ''} {label or ''}".lower()
    if "win" in text:
        return "win"
    if "loss" in text:
        return "loss"
    value = _to_float(lesson_value)
    if value is None:
        return "neutral"
    return "win" if value > 0 else "loss" if value < 0 else "neutral"


def _loads(value: Any) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def cli_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview JACKAL memory context.")
    parser.add_argument("--ticker", default="UNKNOWN")
    parser.add_argument("--role", choices=["analyst", "devil"], default="analyst")
    parser.add_argument("--regime", default="")
    parser.add_argument("--fear-greed", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    aria = {"regime": args.regime, "fear_greed": args.fear_greed}
    context = build_memory_context(args.ticker, aria, args.role)
    if args.json:
        print(json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True))
    elif context:
        print(context["stats_block"])
    else:
        print("No memory context available.")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
