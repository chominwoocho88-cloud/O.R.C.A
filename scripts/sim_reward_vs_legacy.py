#!/usr/bin/env python
"""설계 §7 시뮬 재현 — 기존(이진·누적) vs 신규(보상·망각·용서) 가중치 비교.

사용: python scripts/sim_reward_vs_legacy.py [--events 200] [--seed 42]
테스트가 질적 성질(고착/감쇠/차등/부활)을 고정하는 회귀 자산이다.
"""
from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jackal.reward import compute_reward, legacy_step, next_weight, update_ema  # noqa: E402

W_MIN, W_MAX, MIN_SAMPLES = 0.3, 2.5, 5


@dataclass
class Profile:
    name: str
    hit_rate: float
    mu: float          # 적중 시 평균 peak(%)
    vol: float         # 일변동성(%)
    flip_at: int | None = None   # 이 시점 이후 hit_rate 붕괴
    flip_rate: float = 0.25


PROFILES = (
    Profile("strong_calm", 0.70, 2.5, 0.8),
    Profile("lottery",     0.45, 2.5, 3.5),
    Profile("weak",        0.35, 0.5, 1.2),
    Profile("regime_flip", 0.65, 2.0, 1.0, flip_at=100),
)


def simulate(profile: Profile, *, events: int = 200, seed: int = 42) -> dict:
    rng = random.Random(seed)
    w_old = w_new = 1.0
    correct = 0
    ema = None
    for i in range(1, events + 1):
        rate = profile.flip_rate if (profile.flip_at and i > profile.flip_at) else profile.hit_rate
        hit = rng.random() < rate
        peak = max(1.0, rng.gauss(profile.mu, profile.vol)) if hit else 0.0
        outcome = rng.gauss(0.5, profile.vol) if hit else -abs(rng.gauss(1.0, profile.vol))
        peak_day = rng.randint(1, 7)

        # 기존: 누적 정확도 + 고정 스텝
        correct += int(hit)
        if i >= MIN_SAMPLES:
            w_old = min(max(w_old + legacy_step(correct / i), W_MIN), W_MAX)

        # 신규: 보상 비례 + 평균 회귀
        r = compute_reward(swing_hit=hit, peak_pct=peak, outcome_pct=outcome,
                           vol_d=profile.vol, peak_day=peak_day)
        w_new = next_weight(w_new, r, i)
        ema = update_ema(ema, r)
    return {"legacy": round(w_old, 3), "reward": round(w_new, 3), "ema_r": ema}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"{'프로필':14s} {'기존 w':>7s} {'신규 w':>7s} {'EMA r':>7s}")
    for profile in PROFILES:
        out = simulate(profile, events=args.events, seed=args.seed)
        print(f"{profile.name:14s} {out['legacy']:7.3f} {out['reward']:7.3f} {out['ema_r']:7.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
