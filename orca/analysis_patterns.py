"""Pattern database helpers extracted from orca.analysis."""

from __future__ import annotations

from ._analysis_common import _load, _save, _today
from .paths import PATTERN_DB_FILE


def update_pattern_db(memory: list) -> None:
    if len(memory) < 5:
        return
    db = _load(PATTERN_DB_FILE, {"patterns": {}, "last_updated": ""})
    pats = db.get("patterns", {})

    for i in range(len(memory) - 1):
        curr = memory[i]
        nxt = memory[i + 1]
        if curr.get("mode") != "MORNING" or nxt.get("mode") != "MORNING":
            continue
        key = curr.get("market_regime", "") + "|" + curr.get("trend_phase", "")
        if not key or key == "|":
            continue
        outcome = nxt.get("market_regime", "")
        if key not in pats:
            pats[key] = {}
        pats[key][outcome] = pats[key].get(outcome, 0) + 1

    db["patterns"] = pats
    db["last_updated"] = _today()
    _save(PATTERN_DB_FILE, db)


def get_pattern_context(memory: list, current_regime: str, current_trend: str) -> str:
    db = _load(PATTERN_DB_FILE, {"patterns": {}})
    key = current_regime + "|" + current_trend
    pats = db.get("patterns", {}).get(key, {})
    if not pats:
        return ""
    total = sum(pats.values())
    if total < 3:
        return ""
    top = sorted(pats.items(), key=lambda x: x[1], reverse=True)[:2]
    lines = [f"[패턴DB] {key} 이후 ({total}회):"]
    for regime, cnt in top:
        lines.append(f"  → {regime}: {cnt}회 ({cnt/total:.0%})")
    return "\n".join(lines)


def build_compact_history(memory: list, n: int = 7) -> str:
    recent = [m for m in memory if m.get("mode") == "MORNING"][-n:]
    if not recent:
        return ""
    lines = ["[최근 분석 요약]"]
    for m in recent:
        lines.append(
            f"  {m.get('analysis_date','')} {m.get('market_regime','')} "
            f"| {m.get('one_line_summary','')[:40]}"
        )
    return "\n".join(lines)
