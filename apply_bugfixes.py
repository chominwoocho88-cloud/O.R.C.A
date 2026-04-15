"""
apply_bugfixes.py — 모든 버그를 실제 파일에 적용
repo root에서 실행: python apply_bugfixes.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
applied = 0
skipped = 0
failed  = 0


def patch(rel_path, old, new, label):
    global applied, skipped, failed
    f = ROOT / rel_path
    if not f.exists():
        print(f"  ⚠️  파일 없음: {rel_path}")
        failed += 1
        return
    src = f.read_text(encoding="utf-8")
    if old not in src:
        print(f"  ⏭  이미 적용됨: {label}")
        skipped += 1
        return
    f.write_text(src.replace(old, new, 1), encoding="utf-8")
    print(f"  ✅ {label}")
    applied += 1


print("\n" + "=" * 60)
print("  Bug Fix 적용 시작")
print("=" * 60 + "\n")

# ══════════════════════════════════════════════════════════════════
# Bug 1-A: jackal_evolution.py — signal_weights 중복 키
# ══════════════════════════════════════════════════════════════════
OLD_SW = (
    '    "signal_weights": {\n'
    '        "rsi_oversold":   1.0,\n'
    '        "bb_touch":       1.0,\n'
    '        "volume_surge":   1.0,\n'
    '        "volume_climax":  1.0,\n'
    '        "ma_support":     1.0,\n'
    '        "bullish_div":    1.0,\n'
    '        "sector_inflow":  1.0,\n'
    '        "golden_cross":   1.0,\n'
    '        "fear_regime":    1.0,\n'
    '        "sector_inflow":  1.0,\n'
    '    },'
)
NEW_SW = (
    '    "signal_weights": {\n'
    '        "bb_touch":         1.0,\n'
    '        "rsi_oversold":     1.0,\n'
    '        "volume_climax":    1.0,\n'
    '        "ma_support":       1.0,\n'
    '        "momentum_dip":     1.0,\n'
    '        "vol_accumulation": 1.0,\n'
    '        "sector_rebound":   1.0,\n'
    '        "rsi_divergence":   1.0,\n'
    '        "sector_inflow":    1.0,\n'
    '        "golden_cross":     1.0,\n'
    '        "fear_regime":      1.0,\n'
    '        "bullish_div":      1.0,\n'
    '        "volume_surge":     1.0,\n'
    '    },'
)
patch("jackal/jackal_evolution.py", OLD_SW, NEW_SW, "Bug1-A: signal_weights 중복 키 제거")

# ══════════════════════════════════════════════════════════════════
# Bug 1-B: jackal_evolution.py — 잘못된 모델명
# ══════════════════════════════════════════════════════════════════
patch(
    "jackal/jackal_evolution.py",
    'MODEL_S = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")',
    'MODEL_S = os.environ.get("ANTHROPIC_MODEL", os.environ.get("SUBAGENT_MODEL", "claude-sonnet-4-6"))',
    "Bug1-B: 잘못된 모델명 수정"
)

# ══════════════════════════════════════════════════════════════════
# Bug 3/8: jackal_evolution.py — _mark_last_evolve
# ══════════════════════════════════════════════════════════════════
patch(
    "jackal/jackal_evolution.py",
    '    def _mark_last_evolve(self):\n'
    '        (_BASE / ".last_evolve").write_text(datetime.now().isoformat(), encoding="utf-8")',
    '    def _mark_last_evolve(self):\n'
    '        """last_evolved_at을 weights에 기록 — .last_evolve 파일 의존 제거"""\n'
    '        self.weights["last_evolved_at"] = datetime.now().isoformat()',
    "Bug3/8: _mark_last_evolve → weights 기반"
)

# ══════════════════════════════════════════════════════════════════
# Bug 3: jackal_core.py — import json 추가
# ══════════════════════════════════════════════════════════════════
patch(
    "jackal/jackal_core.py",
    "import os\nimport sys\nimport logging\nimport argparse",
    "import os\nimport sys\nimport json\nimport logging\nimport argparse",
    "Bug3: import json 추가"
)

# ══════════════════════════════════════════════════════════════════
# Bug 3: jackal_core.py — _should_evolve
# ══════════════════════════════════════════════════════════════════
OLD_EVOLVE = (
    '    def _should_evolve(self) -> bool:\n'
    '        marker = _BASE / ".last_evolve"\n'
    '        if not marker.exists():\n'
    '            return True\n'
    '        try:\n'
    '            last    = datetime.fromisoformat(marker.read_text().strip())\n'
    '            elapsed = (datetime.now() - last).total_seconds() / 3600\n'
    '            return elapsed >= 24\n'
    '        except Exception:\n'
    '            return True'
)
NEW_EVOLVE = (
    '    def _should_evolve(self) -> bool:\n'
    '        """jackal_weights.json["last_evolved_at"] 기반 — .last_evolve 파일 제거"""\n'
    '        weights_file = _BASE / "jackal_weights.json"\n'
    '        if not weights_file.exists():\n'
    '            log.info("Evolution: weights 없음 → 실행")\n'
    '            return True\n'
    '        try:\n'
    '            weights  = json.loads(weights_file.read_text(encoding="utf-8"))\n'
    '            last_str = weights.get("last_evolved_at", "")\n'
    '            if not last_str:\n'
    '                return True\n'
    '            last    = datetime.fromisoformat(last_str)\n'
    '            elapsed = (datetime.now() - last).total_seconds() / 3600\n'
    '            should  = elapsed >= 24\n'
    '            log.info(f"Evolution: 마지막 {elapsed:.1f}h 전 → {\'실행\' if should else f\'스킵 ({24-elapsed:.1f}h 남음)\'}")\n'
    '            return should\n'
    '        except Exception as e:\n'
    '            log.warning(f"Evolution 체크 오류: {e} → 실행")\n'
    '            return True'
)
patch("jackal/jackal_core.py", OLD_EVOLVE, NEW_EVOLVE, "Bug3: _should_evolve → weights 기반")

# ══════════════════════════════════════════════════════════════════
# Bug 4: aria_adapter.py — 경로 분기 로직
# ══════════════════════════════════════════════════════════════════
patch(
    "jackal/aria_adapter.py",
    '_BASE         = Path(__file__).parent\n'
    '_ROOT         = _BASE.parent if (_BASE / "jackal_hunter.py").exists() else _BASE\n'
    'DATA_DIR      = _ROOT / "data"',
    '_JACKAL_DIR = Path(__file__).parent\n'
    '_REPO_ROOT  = _JACKAL_DIR.parent\n'
    'DATA_DIR    = _REPO_ROOT / "data"',
    "Bug4: aria_adapter 경로 분기 제거"
)

# ── aria_adapter.py 내부 ARIA_BASELINE 등도 변수명 맞춤 ──────────
patch(
    "jackal/aria_adapter.py",
    'ARIA_BASELINE = DATA_DIR / "morning_baseline.json"   # 당일 ARIA 분석 요약\n'
    'ARIA_MEMORY   = DATA_DIR / "memory.json"             # 누적 ARIA 리포트\n'
    'JACKAL_NEWS   = DATA_DIR / "jackal_news.json"        # Jackal용 티커별 뉴스',
    'ARIA_BASELINE = DATA_DIR / "morning_baseline.json"\n'
    'ARIA_MEMORY   = DATA_DIR / "memory.json"\n'
    'JACKAL_NEWS   = DATA_DIR / "jackal_news.json"',
    "Bug4: 주석 정리"
)

# ══════════════════════════════════════════════════════════════════
# Bug 5: jackal_hunter.py — aria_adapter 사용
# ══════════════════════════════════════════════════════════════════
patch(
    "jackal/jackal_hunter.py",
    'ARIA_BASELINE  = Path("data") / "morning_baseline.json"\n'
    'ARIA_MEMORY    = Path("data") / "memory.json"',
    '# [Bug Fix 5] ARIA 경로 직접 참조 제거 → aria_adapter 사용\n'
    'from aria_adapter import (\n'
    '    load_aria_context     as _load_aria_context,\n'
    '    aria_baseline_exists  as _aria_baseline_exists,\n'
    ')',
    "Bug5: ARIA 하드코딩 경로 → aria_adapter"
)

patch(
    "jackal/jackal_hunter.py",
    "    if not ARIA_BASELINE.exists():",
    "    if not _aria_baseline_exists():",
    "Bug5: ARIA_BASELINE.exists() → _aria_baseline_exists()"
)

# ══════════════════════════════════════════════════════════════════
# Bug 7: aria_main.py — kis_connected 하드코딩
# ══════════════════════════════════════════════════════════════════
patch(
    "aria_main.py",
    '    import re\n'
    '    kis_connected = False\n'
    '    if kis_connected:\n'
    '        return report',
    '    import re\n'
    '    kis_connected = os.environ.get("KIS_CONNECTED", "").lower() == "true"\n'
    '    if kis_connected:\n'
    '        return report',
    "Bug7: kis_connected 환경변수화"
)

# ══════════════════════════════════════════════════════════════════
# Bug 9: aria_paths.py — 절대경로 + ensure_dirs
# ══════════════════════════════════════════════════════════════════
patch(
    "aria_paths.py",
    'DATA_DIR    = Path("data")       # 상태 JSON 저장소\n'
    'REPORTS_DIR = Path("reports")   # 일별 리포트 (분석 아카이브)\n'
    '\n'
    'DATA_DIR.mkdir(exist_ok=True)\n'
    'REPORTS_DIR.mkdir(exist_ok=True)',
    '_REPO_ROOT  = Path(__file__).parent\n'
    'DATA_DIR    = _REPO_ROOT / "data"\n'
    'REPORTS_DIR = _REPO_ROOT / "reports"\n'
    '\n'
    '\n'
    'def ensure_dirs() -> None:\n'
    '    """data/, reports/ 보장 — import 사이드이펙트 제거"""\n'
    '    DATA_DIR.mkdir(exist_ok=True)\n'
    '    REPORTS_DIR.mkdir(exist_ok=True)\n'
    '\n'
    '\n'
    'ensure_dirs()',
    "Bug9: 상대경로 → 절대경로 + ensure_dirs"
)

patch(
    "aria_main.py",
    "from aria_paths import MEMORY_FILE, REPORTS_DIR",
    "from aria_paths import MEMORY_FILE, REPORTS_DIR, ensure_dirs\nensure_dirs()",
    "Bug9: aria_main.py ensure_dirs 호출"
)

# ══════════════════════════════════════════════════════════════════
# Bug 10: aria_analysis.py — MODEL 환경변수화
# ══════════════════════════════════════════════════════════════════
patch(
    "aria_analysis.py",
    'MODEL   = "claude-sonnet-4-6"',
    'MODEL   = os.environ.get("ARIA_MODEL", "claude-sonnet-4-6")',
    "Bug10: aria_analysis.py MODEL 환경변수화"
)

# Bug 10: aria_agents.py — 모델 5개 환경변수화
patch(
    "aria_agents.py",
    'MODEL_HUNTER        = "claude-haiku-4-5-20251001"\n'
    'MODEL_ANALYST       = "claude-sonnet-4-6"\n'
    'MODEL_DEVIL         = "claude-sonnet-4-6"\n'
    'MODEL_REPORTER_FULL = "claude-sonnet-4-6"\n'
    'MODEL_REPORTER_LITE = "claude-sonnet-4-6"',
    '_DEFAULT_HAIKU  = "claude-haiku-4-5-20251001"\n'
    '_DEFAULT_SONNET = "claude-sonnet-4-6"\n'
    'MODEL_HUNTER        = os.environ.get("ARIA_MODEL_HUNTER", _DEFAULT_HAIKU)\n'
    'MODEL_ANALYST       = os.environ.get("ARIA_MODEL",        _DEFAULT_SONNET)\n'
    'MODEL_DEVIL         = os.environ.get("ARIA_MODEL",        _DEFAULT_SONNET)\n'
    'MODEL_REPORTER_FULL = os.environ.get("ARIA_MODEL",        _DEFAULT_SONNET)\n'
    'MODEL_REPORTER_LITE = os.environ.get("ARIA_MODEL_LITE",   _DEFAULT_SONNET)',
    "Bug10: aria_agents.py 모델 환경변수화"
)

# ══════════════════════════════════════════════════════════════════
# Bug 11: aria_analysis.py — verification 중복 방어
# ══════════════════════════════════════════════════════════════════
patch(
    "aria_analysis.py",
    '    if accuracy.get("history") and accuracy["history"][-1].get("date") == today:\n'
    '        print("Already verified today"); return accuracy',
    '    force_verify = os.environ.get("ARIA_FORCE_VERIFY", "").lower() == "true"\n'
    '    already_done = any(h.get("date") == today for h in accuracy.get("history", []))\n'
    '    if already_done and not force_verify:\n'
    '        print(f"Already verified today ({today}) — set ARIA_FORCE_VERIFY=true to rerun")\n'
    '        return accuracy',
    "Bug11: verification 중복 방어 (any + FORCE_VERIFY)"
)

# ══════════════════════════════════════════════════════════════════
# Bug 12: aria_agents.py — call_api 재귀 → 루프
# ══════════════════════════════════════════════════════════════════
OLD_CALL = (
    'def call_api(system: str, user: str, use_search=False,\n'
    '             model=MODEL_ANALYST, max_tokens=2000, _retry: int = 0) -> str:\n'
    '    """Anthropic API 호출 — 500/529 서버 오류 시 1회 자동 재시도"""\n'
    '    import anthropic as _ac, time as _t\n'
    '    kwargs = dict(\n'
    '        model=model, max_tokens=max_tokens,\n'
    '        system=system,\n'
    '        messages=[{"role": "user", "content": user}],\n'
    '    )\n'
    '    if use_search:\n'
    '        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]\n'
    '\n'
    '    full = ""; sc = 0\n'
    '    try:\n'
    '        with client.messages.stream(**kwargs) as s:\n'
    '            for ev in s:\n'
    '                t = getattr(ev, "type", "")\n'
    '                if t == "content_block_start":\n'
    '                    blk = getattr(ev, "content_block", None)\n'
    '                    if blk and getattr(blk, "type", "") == "tool_use":\n'
    '                        sc += 1\n'
    '                        q = getattr(blk, "input", {}).get("query", "")\n'
    '                        console.print("    [dim]Search [" + str(sc) + "]: " + q + "[/dim]")\n'
    '                elif t == "content_block_delta":\n'
    '                    d = getattr(ev, "delta", None)\n'
    '                    if d and getattr(d, "type", "") == "text_delta":\n'
    '                        full += d.text\n'
    '    except _ac.InternalServerError:\n'
    '        if _retry < 1:\n'
    '            console.print("  [yellow]⚠️ Anthropic 500 — 20초 후 재시도[/yellow]")\n'
    '            _t.sleep(20)\n'
    '            return call_api(system, user, use_search, model, max_tokens, _retry=1)\n'
    '        raise\n'
    '    except _ac.RateLimitError:\n'
    '        if _retry < 1:\n'
    '            console.print("  [yellow]⚠️ Rate limit — 60초 후 재시도[/yellow]")\n'
    '            _t.sleep(60)\n'
    '            return call_api(system, user, use_search, model, max_tokens, _retry=1)\n'
    '        raise\n'
    '    return full'
)
NEW_CALL = (
    'def call_api(system: str, user: str, use_search: bool = False,\n'
    '             model: str = MODEL_ANALYST, max_tokens: int = 2000,\n'
    '             max_retries: int = 2) -> str:\n'
    '    """Anthropic API 호출 — 재귀 없는 루프 방식 재시도"""\n'
    '    import anthropic as _ac\n'
    '    import time as _t\n'
    '    kwargs = dict(\n'
    '        model=model, max_tokens=max_tokens,\n'
    '        system=system,\n'
    '        messages=[{"role": "user", "content": user}],\n'
    '    )\n'
    '    if use_search:\n'
    '        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]\n'
    '    _DELAYS = {_ac.InternalServerError: 20, _ac.RateLimitError: 60}\n'
    '    last_exc = None\n'
    '    for attempt in range(max_retries):\n'
    '        full = ""; sc = 0\n'
    '        try:\n'
    '            with client.messages.stream(**kwargs) as s:\n'
    '                for ev in s:\n'
    '                    t = getattr(ev, "type", "")\n'
    '                    if t == "content_block_start":\n'
    '                        blk = getattr(ev, "content_block", None)\n'
    '                        if blk and getattr(blk, "type", "") == "tool_use":\n'
    '                            sc += 1\n'
    '                            q = getattr(blk, "input", {}).get("query", "")\n'
    '                            console.print("    [dim]Search [" + str(sc) + "]: " + q + "[/dim]")\n'
    '                    elif t == "content_block_delta":\n'
    '                        d = getattr(ev, "delta", None)\n'
    '                        if d and getattr(d, "type", "") == "text_delta":\n'
    '                            full += d.text\n'
    '            return full\n'
    '        except tuple(_DELAYS.keys()) as e:\n'
    '            last_exc = e\n'
    '            delay = _DELAYS.get(type(e), 30)\n'
    '            if attempt < max_retries - 1:\n'
    '                console.print(f"  [yellow]⚠️ {type(e).__name__} — {delay}s 후 재시도[/yellow]")\n'
    '                _t.sleep(delay)\n'
    '    raise last_exc'
)
patch("aria_agents.py", OLD_CALL, NEW_CALL, "Bug12: call_api 재귀 → 루프")

# ══════════════════════════════════════════════════════════════════
# Bug 15: aria_backtest.py — 중복 import
# ══════════════════════════════════════════════════════════════════
patch(
    "aria_backtest.py",
    '        import sys, os\n'
    '        sys.path.insert(0, os.getcwd())\n'
    '        import sys, os; sys.path.insert(0, os.getcwd()); from aria_analysis import update_weights_from_accuracy',
    '        from aria_analysis import update_weights_from_accuracy',
    "Bug15: 중복 import 제거"
)

# ══════════════════════════════════════════════════════════════════
# 결과 요약
# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print(f"  완료: ✅ 적용 {applied}  ⏭  스킵 {skipped}  ⚠️  실패 {failed}")
print("=" * 60 + "\n")
sys.exit(1 if failed > 0 else 0)
