"""
aria_adapter.py — ARIA ↔ Jackal 인터페이스 레이어

[Bug Fix 4] _ROOT 경로 분기 로직 불안정 수정
  기존: _ROOT = _BASE.parent if (_BASE / "jackal_hunter.py").exists() else _BASE
  → jackal/에서 실행 시 정상이지만, jackal_hunter.py가 다른 위치로 이동하면 깨짐
  → 조건이 False일 때 _BASE(=jackal/)를 _ROOT로 써버려 DATA_DIR = jackal/data 가 됨

  수정: __file__이 jackal/ 안에 있으면 무조건 .parent.parent = repo root
        파일 존재 조건 없이 경로만으로 결정 → 견고함

역할:
  - ARIA 데이터 로딩의 단일 진입점
  - 경로/구조 변경은 이 파일만 수정
  - Jackal 모듈은 이 adapter만 의존
"""

import json
import logging
from pathlib import Path

log = logging.getLogger("aria_adapter")

# ── 경로 정의 (Bug Fix: 조건 없이 항상 repo root 계산) ──────────
_JACKAL_DIR = Path(__file__).parent          # jackal/
_REPO_ROOT  = _JACKAL_DIR.parent             # repo root — 항상 고정

DATA_DIR = _REPO_ROOT / "data"               # data/ — 항상 정확

ARIA_BASELINE = DATA_DIR / "morning_baseline.json"
ARIA_MEMORY   = DATA_DIR / "memory.json"
JACKAL_NEWS   = DATA_DIR / "jackal_news.json"


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
          inflows_detail, outflows_detail,
          all_headlines,
          jackal_news  ← {ticker: [news_item, ...]}
    """
    ctx: dict = {
        "one_line":        "",
        "regime":          "",
        "top_headlines":   [],
        "key_inflows":     [],
        "key_outflows":    [],
        "thesis_killers":  [],
        "actionable":      [],
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
                if not ctx["regime"]:
                    ctx["regime"] = last.get("market_regime", "")
                if not ctx["top_headlines"]:
                    ctx["top_headlines"] = [h.get("headline", "") for h in ctx["all_headlines"]]
                if not ctx["key_inflows"]:
                    ctx["key_inflows"] = [i.get("zone", "") for i in ctx["inflows_detail"][:3]]
    except Exception as e:
        log.warning(f"ARIA memory 로드 실패: {e}")

    # ── 3. jackal_news.json ────────────────────────────────────────
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
    return ARIA_BASELINE.exists()


def get_aria_regime() -> str:
    try:
        if ARIA_BASELINE.exists():
            b = json.loads(ARIA_BASELINE.read_text(encoding="utf-8"))
            return b.get("market_regime", "")
    except Exception:
        pass
    return ""


def get_aria_inflows() -> list:
    try:
        if ARIA_BASELINE.exists():
            b = json.loads(ARIA_BASELINE.read_text(encoding="utf-8"))
            return [i.get("zone", "") for i in b.get("inflows", [])[:3]]
    except Exception:
        pass
    return []
