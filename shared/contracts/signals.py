"""신호 라벨 canonical 계약 — ORCA·JACKAL 공유 (L2-1, 2026-06-12).

LLM이 만드는 자유 텍스트 수식어("bb_touch(-8%_밴드하단)",
"sector_inflow_감지(ARIA_미반영)")가 1건짜리 accuracy 버킷을 무한히
만들어 표본이 파편화된다. 모든 신호 라벨은 기록 전에
normalize_signal_label()을 통과해야 하며, 매핑 실패는 'other'다 —
새 버킷 무단 생성 금지.
"""
from __future__ import annotations

import re

# 표본이 실재하는 신호만 등재 (candidate_lessons signals_fired 실측 기준).
# 새 신호 추가는 이 튜플에 의식적으로 등재하는 것으로만 한다.
CANONICAL_SIGNALS = (
    "bb_touch",
    "rsi_oversold",
    "rsi_divergence",
    "momentum_dip",
    "ma_support",
    "volume_climax",
    "sector_inflow",
    "sector_rebound",
    "other",
)

# 접두 일치로 못 잡는 유의어 → canonical
_SYNONYMS = {
    "bb_oversold_zone": "bb_touch",
    "bullish_div": "rsi_divergence",
    "bearish_div": "rsi_divergence",
    "divergence": "rsi_divergence",
}

_PAREN_RE = re.compile(r"\([^)]*\)")


def normalize_signal_label(raw: object) -> str:
    """자유 텍스트 신호 라벨 → canonical. 실패는 'other'.

    절차: 괄호 수식어 제거 → 소문자/공백 정리 → 유의어 → 접두 일치.
    """
    text = _PAREN_RE.sub("", str(raw or "")).strip().strip("_- ").lower()
    if not text:
        return "other"
    if text in CANONICAL_SIGNALS:
        return text
    if text in _SYNONYMS:
        return _SYNONYMS[text]
    for synonym, canon in _SYNONYMS.items():
        if text.startswith(synonym):
            return canon
    for canon in CANONICAL_SIGNALS:
        if canon != "other" and text.startswith(canon):
            return canon
    return "other"


def normalize_regime_label(raw: object) -> str:
    """레짐 라벨 정규화 — 괄호 수식어 제거 ("위험선호 (급반전 취약)" → "위험선호").

    레짐은 신호와 달리 canonical enum을 강제하지 않는다(기본 라벨이 이미
    소수). 수식어로 인한 1건짜리 accuracy 버킷만 막는다.
    """
    text = _PAREN_RE.sub("", str(raw or "")).strip()
    return " ".join(text.split())


__all__ = ("CANONICAL_SIGNALS", "normalize_signal_label", "normalize_regime_label")
