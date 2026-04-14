"""
jackal_shield.py
Jackal Shield - 보안 + 비용 자동 체크 시스템

검사 항목:
  1. API 키 노출 (.env, *.py, *.json, *.yml 에서 패턴 탐색)
  2. 일일 토큰 예산 초과 여부 (compact_log 기반)
  3. 비정상 토큰 급증 감지 (전일 대비 300% 이상)
  4. skills/ 디렉토리 비정상 파일 탐지
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("jackal_shield")

_BASE = Path(__file__).parent

# ─── 설정 ─────────────────────────────────────────────────────────
# 일일 토큰 예산 (환경변수로 조정 가능)
_DAILY_TOKEN_BUDGET = int(os.getenv("JACKAL_DAILY_BUDGET", "500000"))
# 전일 대비 급증 임계 배율
_SPIKE_MULTIPLIER = float(os.getenv("JACKAL_SPIKE_MULTIPLIER", "3.0"))
# API 키 패턴 (Anthropic, OpenAI 등)
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}", re.I),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.I),
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*['\"]?[A-Za-z0-9\-_]+", re.I),
    re.compile(r"api[_\-]?key\s*[:=]\s*['\"]?[A-Za-z0-9\-_]{20,}", re.I),
]
# 스캔 제외 디렉토리
_EXCLUDE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
# 스캔 대상 확장자
_SCAN_EXTENSIONS = {".py", ".json", ".yml", ".yaml", ".env", ".txt", ".md"}


class JackalShield:
    """보안 + 비용 스캐너"""

    def __init__(self, scan_root: Path = _BASE):
        self.scan_root = Path(scan_root)
        self.compact_log = _BASE / "compact_log.json"

    # ── 공개 메서드 ────────────────────────────────────────────────
    def scan(self) -> dict:
        """
        전체 스캔 실행.

        Returns:
            {issues: List[str], abort: bool, stats: dict}
        """
        issues = []
        stats = {}

        # 1. API 키 노출 스캔
        leaked = self._scan_secrets()
        if leaked:
            for item in leaked:
                issues.append(f"🔑 API키 노출 의심: {item}")

        # 2. 일일 토큰 예산 체크
        budget_result = self._check_budget()
        stats["today_tokens"] = budget_result["today_tokens"]
        stats["daily_budget"] = _DAILY_TOKEN_BUDGET
        if budget_result["exceeded"]:
            issues.append(
                f"💸 일일 토큰 예산 초과: "
                f"{budget_result['today_tokens']:,} / {_DAILY_TOKEN_BUDGET:,}"
            )

        # 3. 토큰 급증 감지
        spike = self._detect_spike()
        stats["spike_ratio"] = spike["ratio"]
        if spike["detected"]:
            issues.append(
                f"📈 토큰 급증 감지: 전일 대비 {spike['ratio']:.1f}배 증가"
            )

        # 4. skills/ 이상 파일 탐지
        bad_skills = self._check_skills()
        for s in bad_skills:
            issues.append(f"⚠️  skills/ 이상 파일: {s}")

        # abort 조건: API 키 노출 OR 예산 2배 초과
        abort = bool(leaked) or budget_result["today_tokens"] > _DAILY_TOKEN_BUDGET * 2

        return {
            "issues": issues,
            "abort": abort,
            "stats": stats,
            "scanned_at": datetime.now().isoformat(),
        }

    # ── API 키 노출 스캔 ───────────────────────────────────────────
    def _scan_secrets(self) -> list[str]:
        """소스 파일에서 API 키 패턴 탐색"""
        found = []
        for path in self._iter_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(content):
                    # 실제 키 값은 로그에 남기지 않음 (파일명만)
                    rel = path.relative_to(self.scan_root)
                    if str(rel) not in found:
                        found.append(str(rel))
                    break
        return found

    def _iter_files(self):
        """스캔 대상 파일 이터레이터"""
        for p in self.scan_root.rglob("*"):
            if any(excl in p.parts for excl in _EXCLUDE_DIRS):
                continue
            if p.suffix in _SCAN_EXTENSIONS and p.is_file():
                yield p

    # ── 토큰 예산 체크 ─────────────────────────────────────────────
    def _check_budget(self) -> dict:
        logs = self._load_compact_log()
        today = datetime.now().date().isoformat()
        today_tokens = sum(
            entry.get("tokens_before", 0)
            for entry in logs
            if entry.get("timestamp", "")[:10] == today
        )
        return {
            "today_tokens": today_tokens,
            "exceeded": today_tokens > _DAILY_TOKEN_BUDGET,
        }

    # ── 급증 감지 ──────────────────────────────────────────────────
    def _detect_spike(self) -> dict:
        logs = self._load_compact_log()
        today = datetime.now().date()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_str = today.isoformat()

        today_t = sum(
            e.get("tokens_before", 0)
            for e in logs
            if e.get("timestamp", "")[:10] == today_str
        )
        yest_t = sum(
            e.get("tokens_before", 0)
            for e in logs
            if e.get("timestamp", "")[:10] == yesterday
        )

        if yest_t == 0:
            return {"detected": False, "ratio": 0.0}

        ratio = today_t / yest_t
        return {
            "detected": ratio >= _SPIKE_MULTIPLIER,
            "ratio": round(ratio, 2),
        }

    # ── skills/ 이상 탐지 ─────────────────────────────────────────
    def _check_skills(self) -> list[str]:
        skills_dir = _BASE / "skills"
        if not skills_dir.exists():
            return []
        issues = []
        for p in skills_dir.iterdir():
            # JSON이 아닌 파일
            if p.suffix != ".json":
                issues.append(f"{p.name} (비JSON 파일)")
                continue
            # JSON 파싱 불가
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                issues.append(f"{p.name} (파싱 오류)")
                continue
            # 필수 필드 누락
            required = {"name", "description", "trigger", "action"}
            missing = required - set(data.keys())
            if missing:
                issues.append(f"{p.name} (필드 누락: {missing})")
        return issues

    # ── 유틸 ───────────────────────────────────────────────────────
    def _load_compact_log(self) -> list[dict]:
        if not self.compact_log.exists():
            return []
        try:
            return json.loads(self.compact_log.read_text(encoding="utf-8"))
        except Exception:
            return []


# ─── 단독 실행 ────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    shield = JackalShield()
    result = shield.scan()

    print(f"\n{'='*50}")
    print("🛡️  Jackal Shield 스캔 결과")
    print(f"{'='*50}")
    if result["issues"]:
        print(f"⚠️  발견된 이슈 {len(result['issues'])}건:")
        for issue in result["issues"]:
            print(f"  {issue}")
    else:
        print("  ✅ 이상 없음")

    print(f"\n  통계:")
    for k, v in result["stats"].items():
        print(f"    {k}: {v}")
    print(f"  abort: {result['abort']}")
    print(f"{'='*50}\n")
