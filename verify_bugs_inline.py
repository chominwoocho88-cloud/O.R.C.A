"""
verify_bugs_inline.py — 버그 수정 검증
repo root에서 실행: python verify_bugs_inline.py
"""
import re
import sys
from pathlib import Path

ROOT   = Path(__file__).parent
errors = []


def read(rel):
    f = ROOT / rel
    if not f.exists():
        errors.append(f"파일 없음: {rel}")
        return ""
    return f.read_text(encoding="utf-8")


src = read("jackal/jackal_evolution.py")
if src:
    m = re.search(r'"signal_weights"\s*:\s*\{([^}]+)\}', src, re.DOTALL)
    if m:
        keys = re.findall(r'"(\w+)"\s*:', m.group(1))
        dupes = {k for k in keys if keys.count(k) > 1}
        if dupes:
            errors.append(f"Bug1: signal_weights 중복 키 잔존: {dupes}")
    if "claude-sonnet-4-20250514" in src:
        errors.append("Bug1: 잘못된 모델명 잔존")
    if '".last_evolve").write_text' in src:
        errors.append("Bug8: .last_evolve 쓰기 잔존")
    if "last_evolved_at" not in src:
        errors.append("Bug3: last_evolved_at 없음")

src = read("jackal/jackal_core.py")
if src:
    if "import json" not in src:
        errors.append("Bug3: import json 없음")
    if ".last_evolve" in src and "last_evolved_at" not in src:
        errors.append("Bug3: .last_evolve 의존 잔존")

src = read("jackal/aria_adapter.py")
if src and "_BASE.parent if (_BASE" in src:
    errors.append("Bug4: 경로 분기 잔존")

src = read("jackal/jackal_hunter.py")
if src:
    if 'ARIA_BASELINE  = Path("data")' in src:
        errors.append("Bug5: ARIA_BASELINE 하드코딩 잔존")
    if "from aria_adapter import" not in src:
        errors.append("Bug5: aria_adapter import 없음")

src = read("aria_main.py")
if src and "kis_connected = False" in src:
    errors.append("Bug7: kis_connected = False 잔존")

src = read("aria_paths.py")
if src:
    if 'Path("data")' in src:
        errors.append('Bug9: 상대경로 Path("data") 잔존')
    if "ensure_dirs" not in src:
        errors.append("Bug9: ensure_dirs 없음")
    if "DATA_DIR.mkdir(exist_ok=True)" in src and "def ensure_dirs" not in src:
        errors.append("Bug9: 최상위 mkdir 사이드이펙트 잔존")

src = read("aria_analysis.py")
if src:
    if 'MODEL   = "claude-sonnet-4-6"' in src:
        errors.append("Bug10: aria_analysis MODEL 하드코딩 잔존")
    if "ARIA_MODEL" not in src:
        errors.append("Bug10: aria_analysis ARIA_MODEL 없음")
    if 'accuracy["history"][-1].get("date") == today' in src:
        errors.append("Bug11: [-1] 인덱스 잔존")
    if "ARIA_FORCE_VERIFY" not in src:
        errors.append("Bug11: ARIA_FORCE_VERIFY 없음")

src = read("aria_agents.py")
if src:
    if 'MODEL_ANALYST       = "claude-sonnet-4-6"' in src:
        errors.append("Bug10: aria_agents MODEL 하드코딩 잔존")
    if "ARIA_MODEL" not in src:
        errors.append("Bug10: aria_agents ARIA_MODEL 없음")
    if "return call_api(" in src:
        errors.append("Bug12: call_api 재귀 잔존")
    if "max_retries" not in src:
        errors.append("Bug12: 루프 없음")

src = read("aria_backtest.py")
if src and "import sys, os; sys.path.insert" in src:
    errors.append("Bug15: 중복 import 잔존")

print("\n" + "=" * 60)
print("  검증 결과")
print("=" * 60)
if errors:
    print(f"❌ 미수정 {len(errors)}건:")
    for e in errors:
        print(f"   • {e}")
else:
    print("✅ 모든 버그 수정 완료!")
print("=" * 60 + "\n")

sys.exit(1 if errors else 0)
