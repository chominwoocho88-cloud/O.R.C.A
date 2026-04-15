"""
aria_adapter.py — ARIA ↔ Jackal 인터페이스 레이어 (개선안 3)

배경:
  기존 jackal_hunter.py가 ARIA 파일 경로를 직접 하드코딩.
  ARIA 구조 변경 시 hunter.py를 직접 수정해야 하는 결합도 문제.

역할:
  - ARIA 데이터 로딩의 단일 진입점
  - 경로/구조 변경은 이 파일만 수정
  - Jackal 모듈은 이 adapter만 의존

사용법 (jackal_hunter.py):
  from aria_adapter import load_aria_context, aria_baseline_exists, get_aria_regime
  # 기존 _load_aria_context() 호출을 load_aria_context()로 교체
"""

import json
import logging
from pathlib import Path

log = logging.getLogger("aria_adapter")

# ── 경로 정의 (aria_paths.py와 동기화) ───────────────────────────
# jackal/ 폴더에서 실행 시: _BASE = jackal/, _ROOT = repo root
_BASE         = Path(__file__).parent
_ROOT         = _BASE.parent if (_BASE / "jackal_hunter.py").exists() else _BASE
DATA_DIR      = _ROOT / "data"

ARIA_BASELINE = DATA_DIR / "morning_baseline.json"   # 당일 ARIA 분석 요약
ARIA_MEMORY   = DATA_DIR / "memory.json"             # 누적 ARIA 리포트
JACKAL_NEWS   = DATA_DIR / "jackal_news.json"        # Jackal용 티커별 뉴스


# ══════════════════════════════════════════════════════════════════
# 공개 인터페이스
# ══════════════════════════════════════════════════════════════════

def load_aria_context() -> dict:
    """
    ARIA morning_baseline + memory.json + jackal_news.json 통합 로딩.

    Returns:
        dict with keys:
          one_line, regime, top_headlines, key_inflows, key_outflows,
          thesis_killers, actionable,
          inflows_detail, outflows_detail,  ← 상세 (reason + data_point)
          all_headlines,                    ← signal_tag + impact 포함
          jackal_news                       ← {ticker: [news_item, ...]}
    """
    ctx: dict = {
        "one_line":       "",
        "regime":         "",
        "top_headlines":  [],
        "key_inflows":    [],
        "key_outflows":   [],
        "thesis_killers": [],
        "actionable":     [],
        "inflows_detail":  [],
        "outflows_detail": [],
        "all_headlines":   [],
        "jackal_news":     {},
    }

    # ── 1. morning_baseline.json (당일 요약) ──────────────────────
    try:
        if ARIA_BASELINE.exists():
            b = json.loads(ARIA_BASELINE.read_text(encoding="utf-8"))
            ctx["one_line"]       = b.get("one_line_summary", "")
            ctx["regime"]         = b.get("market_regime", "")
            ctx["top_headlines"]  = [h.get("headline", "") for h in b.get("top_headlines", [])[:5]]
            ctx["key_inflows"]    = [i.get("zone", "") for i in b.get("inflows", [])[:3]]
            ctx["key_outflows"]   = [o.get("zone", "") for o in b.get("outflows", [])[:3]]
            ctx["thesis_killers"] = b.get("thesis_killers", [])
            ctx["actionable"]     = b.get("actionable_watch", [])[:5]
    except Exception as e:
        log.warning(f"ARIA baseline 로드 실패: {e}")

    # ── 2. memory.json (누적 리포트 — 상세 데이터) ───────────────
    try:
        if ARIA_MEMORY.exists():
            mem = json.loads(ARIA_MEMORY.read_text(encoding="utf-8"))
            if mem:
                last = sorted(mem, key=lambda x: x.get("analysis_date", ""))[-1]
                ctx["all_headlines"]   = last.get("top_headlines", [])[:8]
                ctx["inflows_detail"]  = last.get("inflows", [])[:4]
                ctx["outflows_detail"] = last.get("outflows", [])[:3]
                # baseline 없으면 memory로 보완
                if not ctx["regime"]:
                    ctx["regime"] = last.get("market_regime", "")
                if not ctx["top_headlines"]:
                    ctx["top_headlines"] = [h.get("headline", "") for h in ctx["all_headlines"]]
                if not ctx["key_inflows"]:
                    ctx["key_inflows"] = [i.get("zone", "") for i in ctx["inflows_detail"][:3]]
    except Exception as e:
        log.warning(f"ARIA memory 로드 실패: {e}")

    # ── 3. jackal_news.json (티커별 뉴스) ─────────────────────────
    try:
        if JACKAL_NEWS.exists():
            jn = json.loads(JACKAL_NEWS.read_text(encoding="utf-8"))
            for item in jn.get("news_items", []):
                t = item.get("ticker", "")
                if t:
                    ctx["jackal_news"].setdefault(t, []).append(item)
    except Exception:
        pass

    return ctx


def aria_baseline_exists() -> bool:
    """morning_baseline.json 존재 여부 (run_hunt 진입 조건)."""
    return ARIA_BASELINE.exists()


def get_aria_regime() -> str:
    """ARIA 레짐만 빠르게 조회 (Shield / 조건 체크용)."""
    try:
        if ARIA_BASELINE.exists():
            b = json.loads(ARIA_BASELINE.read_text(encoding="utf-8"))
            return b.get("market_regime", "")
    except Exception:
        pass
    return ""


def get_aria_inflows() -> list[str]:
    """ARIA 유입 섹터 목록만 반환."""
    try:
        if ARIA_BASELINE.exists():
            b = json.loads(ARIA_BASELINE.read_text(encoding="utf-8"))
            return [i.get("zone", "") for i in b.get("inflows", [])[:3]]
    except Exception:
        pass
    return []
