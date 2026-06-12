"""보상 기반 학습 수학 (R0) — docs/REWARD_SYSTEM_ROADMAP.md, 설계 §3~4.

전부 순수 함수다. tracker가 확정 entry마다 호출하고, enabled=False인
동안은 shadow_weights/signal_reward 통계에만 쓰인다.

가드레일: vol_floor 제거 금지(보상 폭주), kappa 제거 금지(고착 재발).
"""
from __future__ import annotations

import math
from typing import Sequence

from jackal.thresholds import THRESHOLDS

REWARD_PARAMS = THRESHOLDS["tracker"]["reward"]


def realized_volatility(closes: Sequence[float], *, floor: float | None = None) -> float:
    """일간 수익률 표준편차(%) — 표본 2개 미만이면 floor.

    분모가 0에 가까우면 보상이 폭주하므로 floor는 항상 적용된다.
    """
    floor_value = REWARD_PARAMS["vol_floor"] if floor is None else floor
    values = [float(c) for c in closes if c]
    if len(values) < 3:
        return floor_value
    returns = [(b / a - 1) * 100 for a, b in zip(values, values[1:]) if a]
    if len(returns) < 2:
        return floor_value
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return max(round(math.sqrt(variance), 4), floor_value)


def compute_reward(
    *,
    swing_hit: bool,
    peak_pct: float,
    outcome_pct: float,
    vol_d: float,
    peak_day: int,
    trough_pct: float | None = None,
    params: dict | None = None,
) -> float:
    """확정 entry 1건의 보상 r ∈ [-1.5, 1) — 설계 §3 (+R4 드로다운 항).

    적중이면 peak_pct(질), 미적중이면 outcome_pct(얼마나 틀렸는지)가
    유효 수익률. 리스크 조정(vol·√day) 후 tanh 경계화, 손실은 λ배.
    drawdown_penalty>0이면 추적 중 깊은 트로프가 적중 보상도 깎는다
    ("이기긴 했지만 -8%를 견뎌야 했던" 신호 할인) — 기본 0.0 불활성.
    """
    p = params or REWARD_PARAMS
    eff = float(peak_pct if swing_hit else outcome_pct)
    vol = max(float(vol_d or 0.0), p["vol_floor"])
    day = max(int(peak_day or 1), 1)
    risk_adjusted = eff / (vol * math.sqrt(day))
    r = math.tanh(risk_adjusted / p["tanh_scale"])
    if r < 0:
        r *= p["loss_aversion"]
    penalty = p.get("drawdown_penalty", 0.0)
    if penalty > 0 and trough_pct is not None and trough_pct < 0:
        r += penalty * math.tanh(float(trough_pct) / (vol * p["tanh_scale"]))
    # tanh×λ 치역상 평시 불활성 — 페널티 합산·파라미터 변경 대비 안전망
    return round(max(r, -1.5), 4)


def next_weight(weight: float, reward: float, n_samples: int, params: dict | None = None) -> float:
    """가중치 갱신 — 설계 §4: w ← clip(w + η·r·warm + κ·(1−w)).

    κ(평균 회귀)가 ①상·하한 고착 방지 ②바닥 신호의 부활 경로("용서").
    """
    p = params or REWARD_PARAMS
    warm = min(1.0, n_samples / p["warmup_samples"])
    updated = weight + p["eta"] * reward * warm + p["kappa"] * (1.0 - weight)
    return round(min(max(updated, p["weight_min"]), p["weight_max"]), 4)


def update_ema(previous: float | None, reward: float, params: dict | None = None) -> float:
    """EMA 보상 — α=0.15: 유효 표본 ~13건, 반감 ~4.3건 ("망각")."""
    p = params or REWARD_PARAMS
    if previous is None:
        return round(reward, 4)
    alpha = p["alpha_ema"]
    return round((1 - alpha) * previous + alpha * reward, 4)


DEVIL_CONVICTION = {"반대": -1.0, "동의": 1.0, "부분동의": 0.5}


def devil_reward(signal_reward_value: float, verdict: str) -> float | None:
    """Devil의 보상 = 신호 보상의 관점 변환 (R4 — 에이전트 상벌 확장).

    반대(-1.0): 종목이 벌 받으면(하락) Devil이 상 받는다 — 부호 반전.
    동의(+1.0): 종목과 운명 공동체. 부분동의(+0.5): 확신 절반만 베팅.
    크기·리스크 조정·망각은 신호 보상에서 이미 처리됐으므로 그대로 계승.
    """
    conviction = DEVIL_CONVICTION.get(str(verdict or "").strip())
    if conviction is None:
        return None
    return round(conviction * float(signal_reward_value), 4)


def legacy_step(accuracy: float, params: dict | None = None) -> float:
    """기존 이진 규칙의 스텝 — 시뮬/비교용 (설계 §1)."""
    weights = THRESHOLDS["tracker"]["weights"]
    if accuracy >= weights["high_accuracy_cutoff"]:
        return weights["adjust_up"]
    if accuracy <= weights["low_accuracy_cutoff"]:
        return -weights["adjust_down"]
    return 0.0


__all__ = ("REWARD_PARAMS", "realized_volatility", "compute_reward",
           "next_weight", "update_ema", "legacy_step", "devil_reward")
