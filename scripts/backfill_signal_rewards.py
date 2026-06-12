#!/usr/bin/env python
"""R1 일회성 백필 — hunt_log 확정 entry로 signal_reward·shadow_weights 초기화.

사용:
  python scripts/backfill_signal_rewards.py                # dry-run (기본)
  python scripts/backfill_signal_rewards.py --apply        # 백업 후 적용
  python scripts/backfill_signal_rewards.py --hunt-log <경로> --weights <경로>

실행 시점: JACKAL 로컬 전환 + 최종 시드 후 1회 (docs/REWARD_SYSTEM_ROADMAP.md R1).
과거 entry에는 realized_vol_d가 없으므로 설계 §6대로 vol=1.5를 가정한다.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jackal import reward as reward_math  # noqa: E402
from shared.contracts.signals import normalize_signal_label  # noqa: E402

DEFAULT_VOL = 1.5  # 과거분 vol 결측 가정 (설계 §6)


def replay(entries: list[dict], signal_weights: dict) -> tuple[dict, dict, dict]:
    """확정 entry를 시간순 재생 — (signal_reward, shadow_weights, devil_reward)."""
    stats: dict[str, dict] = {}
    shadow: dict[str, float] = {}
    devil_stats: dict[str, dict] = {}
    confirmed = sorted(
        (e for e in entries if e.get("outcome_checked")),
        key=lambda e: str(e.get("timestamp", "")),
    )
    for entry in confirmed:
        reward_value = entry.get("reward")
        if reward_value is None:
            reward_value = reward_math.compute_reward(
                swing_hit=bool(entry.get("outcome_swing_hit")),
                peak_pct=float(entry.get("peak_pct") or 0.0),
                outcome_pct=float(entry.get("outcome_pct") or 0.0),
                vol_d=float(entry.get("realized_vol_d") or DEFAULT_VOL),
                peak_day=int(entry.get("peak_day") or 1),
                trough_pct=entry.get("trough_pct"),
            )
        reward_value = float(reward_value)
        for raw_sig in entry.get("signals_fired") or []:
            sig = normalize_signal_label(raw_sig)
            rec = stats.setdefault(sig, {"ema_r": None, "n": 0, "last_r": 0.0, "sum_r": 0.0})
            rec["n"] += 1
            rec["last_r"] = round(reward_value, 4)
            rec["sum_r"] = round(rec["sum_r"] + reward_value, 4)
            rec["ema_r"] = reward_math.update_ema(rec["ema_r"], reward_value)
            if entry.get("alerted") and sig in signal_weights:
                base = shadow.get(sig, float(signal_weights.get(sig, 1.0)))
                shadow[sig] = reward_math.next_weight(base, reward_value, rec["n"])
        devil_r = reward_math.devil_reward(reward_value, entry.get("devil_verdict", ""))
        if devil_r is not None:
            rec = devil_stats.setdefault(
                str(entry.get("devil_verdict")).strip(),
                {"ema_r": None, "n": 0, "last_r": 0.0, "sum_r": 0.0})
            rec["n"] += 1
            rec["last_r"] = round(devil_r, 4)
            rec["sum_r"] = round(rec["sum_r"] + devil_r, 4)
            rec["ema_r"] = reward_math.update_ema(rec["ema_r"], devil_r)
    return stats, shadow, devil_stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="R1 signal reward backfill")
    parser.add_argument("--hunt-log", default=str(ROOT / "jackal" / "hunt_log.json"))
    parser.add_argument("--weights", default=str(ROOT / "jackal" / "jackal_weights.json"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    hunt_path, weights_path = Path(args.hunt_log), Path(args.weights)
    entries = json.loads(hunt_path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        entries = entries.get("entries") or []
    weights = json.loads(weights_path.read_text(encoding="utf-8"))
    live = weights.get("signal_weights") or {}

    stats, shadow, devil_stats = replay(entries, live)

    print(f"hunt_log: {hunt_path} (확정 {sum(1 for e in entries if e.get('outcome_checked'))}건)")
    print(f"{'신호':24s} {'n':>3s} {'ema_r':>7s} {'shadow_w':>8s} {'live_w':>7s}")
    for sig in sorted(stats, key=lambda s: -stats[s]["n"]):
        rec = stats[sig]
        sh = shadow.get(sig)
        print(f"{sig:24s} {rec['n']:3d} {rec['ema_r']:7.3f} "
              f"{(f'{sh:8.3f}' if sh is not None else '       -')} "
              f"{live.get(sig, float('nan')):7.3f}")
    if devil_stats:
        print("Devil 상벌 (관점 변환):")
        for verdict, rec in devil_stats.items():
            print(f"  {verdict:6s} n={rec['n']:3d} ema_r={rec['ema_r']:+.3f}")
    if not args.apply:
        print("[dry-run] 변경 없음 — 적용하려면 --apply")
        return 0

    backup = weights_path.with_name(f"{weights_path.name}.bak-reward-{int(time.time())}")
    shutil.copy(weights_path, backup)
    weights["signal_reward"] = stats
    weights["shadow_weights"] = shadow
    weights["devil_reward"] = devil_stats
    weights_path.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"적용 완료 (백업: {backup.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
