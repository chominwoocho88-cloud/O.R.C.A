"""
aria_paths.py — ARIA 경로 중앙 관리
모든 파일 경로를 한 곳에서 정의. 경로 변경 시 이 파일만 수정하면 됩니다.

[Bug Fix 9] mkdir을 import 시점 사이드이펙트에서 함수로 분리
  기존: DATA_DIR.mkdir() / REPORTS_DIR.mkdir()이 모듈 최상위에서 즉시 실행
        → import 한 번에 디렉토리 생성, 테스트/경로 오류 시 엉뚱한 위치에 폴더 생성
        → 상대경로 Path("data")이므로 실행 위치에 따라 경로가 달라짐
  수정: 절대경로로 고정 + ensure_dirs()를 명시적으로 호출하는 방식으로 변경
        → 실행 위치 무관하게 항상 repo root / data 에 저장
"""
from pathlib import Path

# ── repo root 계산 (이 파일이 repo root에 있으므로 항상 정확) ────────────────
_REPO_ROOT = Path(__file__).parent

# ── 디렉토리 (절대경로) ───────────────────────────────────────────────────────
DATA_DIR    = _REPO_ROOT / "data"
REPORTS_DIR = _REPO_ROOT / "reports"

# ── 누적 데이터 (Git 추적) ─────────────────────────────────────────────────────
MEMORY_FILE     = DATA_DIR / "memory.json"
ACCURACY_FILE   = DATA_DIR / "accuracy.json"
SENTIMENT_FILE  = DATA_DIR / "sentiment.json"
ROTATION_FILE   = DATA_DIR / "rotation.json"
WEIGHTS_FILE    = DATA_DIR / "aria_weights.json"
LESSONS_FILE    = DATA_DIR / "aria_lessons.json"
COST_FILE       = DATA_DIR / "aria_cost.json"
PORTFOLIO_FILE  = DATA_DIR / "portfolio.json"
PATTERN_DB_FILE = DATA_DIR / "pattern_db.json"

# ── 런타임 임시 파일 (Git 무시 권장) ───────────────────────────────────────────
BASELINE_FILE = DATA_DIR / "morning_baseline.json"
DATA_FILE     = DATA_DIR / "aria_market_data.json"
BREAKING_FILE = DATA_DIR / "breaking_sent.json"

# ── 출력 파일 ─────────────────────────────────────────────────────────────────
DASHBOARD_FILE = _REPO_ROOT / "dashboard.html"


def ensure_dirs() -> None:
    """
    data/, reports/ 디렉토리를 명시적으로 생성.
    import 시점 사이드이펙트 제거 — 실제 사용 전에만 호출.
    aria_main.py, aria_backtest.py 등 진입점에서 호출하면 됨.
    """
    DATA_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)
