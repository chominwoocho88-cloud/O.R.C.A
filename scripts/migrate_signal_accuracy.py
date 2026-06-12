#!/usr/bin/env python
"""L2-1 일회성 마이그레이션 — signal_accuracy 파편 버킷을 canonical로 재집계.

사용:
  python scripts/migrate_signal_accuracy.py                 # dry-run (기본)
  python scripts/migrate_signal_accuracy.py --apply         # 실제 적용(백업 생성)
  python scripts/migrate_signal_accuracy.py --file <경로>   # 대상 파일 지정

count류(total/correct/swing_correct/d1_correct...)는 합산, 비율류
(*_accuracy)는 합산된 count에서 재계산한다. 적용은 JACKAL 로컬 전환
시점에 — GHA가 같은 파일을 커밋하므로 그 전 적용은 충돌 위험.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.contracts.signals import (normalize_regime_label,  # noqa: E402
    normalize_signal_label)

_COUNT_KEYS = ("total", "correct", "swing_correct", "d1_correct", "d1_total", "swing_total")


def merge_signal_accuracy(sig_acc: dict) -> tuple[dict, list[str]]:
    merged: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    mapping: list[str] = []
    for raw_label, rec in sorted(sig_acc.items()):
        canon = normalize_signal_label(raw_label)
        if canon != raw_label:
            mapping.append(f"{raw_label!r} -> {canon!r}")
        if not isinstance(rec, dict):
            continue
        for key in _COUNT_KEYS:
            if key in rec:
                merged[canon][key] += int(rec.get(key) or 0)
    out: dict[str, dict] = {}
    for canon, rec in merged.items():
        entry = dict(rec)
        total = entry.get("total") or 0
        if total:
            if "correct" in entry:
                entry["accuracy"] = round(entry["correct"] / total * 100, 1)
            if "swing_correct" in entry:
                entry["swing_accuracy"] = round(entry["swing_correct"] / total * 100, 1)
            if "d1_correct" in entry:
                d1_base = entry.get("d1_total") or total
                entry["d1_accuracy"] = round(entry["d1_correct"] / d1_base * 100, 1) if d1_base else 0.0
        out[canon] = entry
    return out, mapping


def merge_regime_accuracy(reg_acc: dict) -> tuple[dict, list[str]]:
    """regime_accuracy 파편 재집계 — count 합산, 비율 재계산.

    메타 필드(generated_at 등)는 표본 큰 쪽 것을 보존한다.
    """
    merged: dict[str, dict] = {}
    mapping: list[str] = []
    for raw_label, rec in sorted(reg_acc.items()):
        canon = normalize_regime_label(raw_label)[:25].strip() or raw_label
        if canon != raw_label:
            mapping.append(f"{raw_label!r} -> {canon!r}")
        if not isinstance(rec, dict):
            continue
        target = merged.setdefault(canon, {})
        if (rec.get("total") or 0) >= (target.get("total") or 0):
            for key, value in rec.items():
                if key not in _COUNT_KEYS and key not in ("accuracy", "swing_accuracy", "d1_accuracy"):
                    target.setdefault(key, value)
        for key in _COUNT_KEYS:
            if key in rec:
                target[key] = (target.get(key) or 0) + int(rec.get(key) or 0)
    for rec in merged.values():
        total = rec.get("total") or 0
        if total and "correct" in rec:
            rec["accuracy"] = round(rec["correct"] / total * 100, 1)
        if total and "swing_correct" in rec:
            rec["swing_accuracy"] = round(rec["swing_correct"] / total * 100, 1)
    return merged, mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="L2-1 signal_accuracy normalization")
    parser.add_argument("--file", default=str(ROOT / "jackal" / "jackal_weights.json"))
    parser.add_argument("--apply", action="store_true", help="백업 후 실제 적용 (기본 dry-run)")
    args = parser.parse_args(argv)

    path = Path(args.file)
    weights = json.loads(path.read_text(encoding="utf-8"))
    sig_acc = weights.get("signal_accuracy") or {}
    merged, mapping = merge_signal_accuracy(sig_acc)
    reg_acc = weights.get("regime_accuracy") or {}
    reg_merged, reg_mapping = merge_regime_accuracy(reg_acc)

    print(f"대상: {path}")
    print(f"버킷: {len(sig_acc)}개 -> {len(merged)}개")
    for line in mapping:
        print("  재매핑:", line)
    before_total = sum(int((r or {}).get("total") or 0) for r in sig_acc.values() if isinstance(r, dict))
    after_total = sum(int(r.get("total") or 0) for r in merged.values())
    print(f"표본 보존 검증: before={before_total} after={after_total} "
          f"{'OK' if before_total == after_total else 'MISMATCH!'}")
    if before_total != after_total:
        return 1
    print(f"regime 버킷: {len(reg_acc)}개 -> {len(reg_merged)}개")
    for line in reg_mapping:
        print("  재매핑:", line)
    if not args.apply:
        print("[dry-run] 변경 없음 — 적용하려면 --apply")
        return 0

    backup = path.with_name(f"{path.name}.bak-l2-{int(time.time())}")
    shutil.copy(path, backup)
    weights["signal_accuracy"] = merged
    weights["regime_accuracy"] = reg_merged
    path.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"적용 완료 (백업: {backup.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
