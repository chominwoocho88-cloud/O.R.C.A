"""
sync_legacy_paths.py — 경로 shim 스크립트

문제: aria_backtest.yml은 data/ 기준 저장, 메인 aria.yml은 루트 파일 직접 참조
→ 백테스트와 데일리 워크플로가 다른 파일을 보는 구조적 불일치

해결: 이 스크립트를 aria.yml 마지막 단계에서 실행하면
      루트 ↔ data/ 간 동기화 유지 (임시 shim, 경로 통일 전까지)

사용:
  python sync_legacy_paths.py --direction data_to_root   # data/ → 루트 복사
  python sync_legacy_paths.py --direction root_to_data   # 루트 → data/ 복사
  python sync_legacy_paths.py --direction both           # 최신 기준 양방향

aria.yml 추가 예시:
  - name: Sync paths
    run: python sync_legacy_paths.py --direction data_to_root
"""

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent

# 동기화 대상 파일 목록
SYNC_MAP = {
    # (루트 경로, data/ 경로)
    "memory.json":    (ROOT / "data" / "memory.json",    ROOT / "memory.json"),
    "accuracy.json":  (ROOT / "data" / "accuracy.json",  ROOT / "accuracy.json"),
    "aria_lessons":   (ROOT / "data" / "aria_lessons.json", ROOT / "aria_lessons.json"),
    "aria_weights":   (ROOT / "data" / "aria_weights.json", ROOT / "aria_weights.json"),
}


def sync_file(src: Path, dst: Path, label: str):
    if not src.exists():
        print(f"  ⏭ {label}: src 없음 ({src.name})")
        return
    if dst.exists():
        src_mtime = src.stat().st_mtime
        dst_mtime = dst.stat().st_mtime
        if abs(src_mtime - dst_mtime) < 2:   # 2초 이내면 동일로 간주
            print(f"  ✅ {label}: 동일 (스킵)")
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"  📋 {label}: {src.name} → {dst.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--direction",
        choices=["data_to_root", "root_to_data", "both"],
        default="data_to_root",
    )
    args = parser.parse_args()

    print(f"\n🔄 sync_legacy_paths.py ({args.direction}) — {datetime.now():%Y-%m-%d %H:%M}")

    for label, (data_path, root_path) in SYNC_MAP.items():
        if args.direction == "data_to_root":
            sync_file(data_path, root_path, label)
        elif args.direction == "root_to_data":
            sync_file(root_path, data_path, label)
        else:   # both: 최신 파일 기준
            if data_path.exists() and root_path.exists():
                if data_path.stat().st_mtime >= root_path.stat().st_mtime:
                    sync_file(data_path, root_path, f"{label}(data→root)")
                else:
                    sync_file(root_path, data_path, f"{label}(root→data)")
            elif data_path.exists():
                sync_file(data_path, root_path, label)
            elif root_path.exists():
                sync_file(root_path, data_path, label)

    print("완료\n")


if __name__ == "__main__":
    main()
