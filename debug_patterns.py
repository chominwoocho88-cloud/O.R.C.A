"""
debug_patterns.py — 패턴 불일치 원인 진단
repo root에서 실행: python debug_patterns.py
"""
from pathlib import Path

ROOT = Path(__file__).parent


def show_context(rel_path, search, label, ctx=3):
    f = ROOT / rel_path
    if not f.exists():
        print(f"  파일 없음: {rel_path}")
        return
    lines = f.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if search in line:
            start = max(0, i - ctx)
            end   = min(len(lines), i + ctx + 1)
            print(f"\n[{label}] {rel_path}:{i+1}")
            for j in range(start, end):
                marker = ">>>" if j == i else "   "
                print(f"  {marker} {j+1:4d}: {repr(lines[j])}")
            return
    print(f"\n[{label}] 패턴 없음 ({search!r}) in {rel_path}")


print("=" * 60)
print("  패턴 진단")
print("=" * 60)

# Bug1-B: MODEL_S
show_context("jackal/jackal_evolution.py", "MODEL_S", "Bug1-B MODEL_S")

# Bug4: aria_adapter 경로
show_context("jackal/aria_adapter.py", "_BASE", "Bug4 _BASE")
show_context("jackal/aria_adapter.py", "_ROOT", "Bug4 _ROOT")

# Bug9: aria_paths DATA_DIR
show_context("aria_paths.py", "DATA_DIR", "Bug9 DATA_DIR")
show_context("aria_paths.py", "Path(", "Bug9 Path(")
