"""
jackal_compact.py
Jackal Compact - Context Rot 방지 자동 압축 시스템

역할:
  - 오늘 실제 API 사용량(usage_log)이 임계치 초과 시 자동 압축 실행
  - 핵심 정보(최근 신호, 학습 데이터)만 보존
  - 압축 결과를 compact_log.json에 기록

[Bug Fix 6] check_and_compact()가 usage_log에서 오늘 토큰 자체 계산
  기존: 외부에서 current_tokens를 받음 → Actions에서 0이 전달돼 항상 skip
  수정: current_tokens=0이면 jackal_usage_log.json에서 오늘 실사용량 합산
"""

import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from anthropic import Anthropic

log = logging.getLogger("jackal_compact")

_BASE          = Path(__file__).parent
_COMPACT_LOG   = _BASE / "compact_log.json"
_COMPACT_CACHE = _BASE / "compact_cache.json"
_USAGE_LOG     = _BASE / "jackal_usage_log.json"   # Bug Fix 2 연동

_COMPACT_THRESHOLD = int(os.getenv("JACKAL_COMPACT_THRESHOLD", "60000"))
_TARGET_RATIO      = 0.30

_MODEL = os.getenv("SUBAGENT_MODEL", "claude-haiku-4-5-20251001")


class JackalCompact:
    """Context Rot 방지 자동 압축기"""

    def __init__(self):
        self.client     = Anthropic()
        self.log_path   = _COMPACT_LOG
        self.cache_path = _COMPACT_CACHE

    # ── 공개 메서드 ────────────────────────────────────────────────
    def check_and_compact(self, current_tokens: int = 0) -> dict:
        """
        오늘 실제 API 토큰이 임계치 초과 시 자동 압축 실행.

        [Bug Fix 6] current_tokens=0이면 usage_log 자체 계산.
        GitHub Actions에서 --tokens 없이 실행돼도 정상 동작.

        Args:
            current_tokens: 명시적 토큰 수. 0이면 usage_log에서 계산.
        """
        # 0이면 usage_log에서 오늘 실사용량 계산
        if current_tokens == 0:
            current_tokens = self._get_today_tokens()
            if current_tokens > 0:
                log.info(f"  usage_log 기반 오늘 사용량: {current_tokens:,} 토큰")

        if current_tokens < _COMPACT_THRESHOLD:
            log.debug(f"Compact 스킵: {current_tokens:,} < {_COMPACT_THRESHOLD:,}")
            return {
                "compacted":      False,
                "current_tokens": current_tokens,
                "threshold":      _COMPACT_THRESHOLD,
                "saved_tokens":   0,
                "summary":        "",
            }

        log.info(f"⚡ 토큰 {current_tokens:,} >= {_COMPACT_THRESHOLD:,} → 압축 시작")
        return self._compact(current_tokens)

    def force_compact(self) -> dict:
        """강제 압축 실행 (토큰 수 무관)"""
        log.info("⚡ 강제 압축 실행")
        return self._compact(current_tokens=0, forced=True)

    # ── 오늘 토큰 자체 계산 ────────────────────────────────────────
    def _get_today_tokens(self) -> int:
        """
        jackal_usage_log.json에서 오늘 실제 소모 토큰 합산.
        파일 없으면 0 반환.
        """
        if not _USAGE_LOG.exists():
            return 0
        try:
            logs  = json.loads(_USAGE_LOG.read_text(encoding="utf-8"))
            today = date.today().isoformat()
            return sum(
                e.get("total_tokens", 0)
                for e in logs
                if e.get("timestamp", "")[:10] == today
            )
        except Exception as e:
            log.warning(f"usage_log 읽기 실패: {e}")
            return 0

    # ── 압축 로직 ──────────────────────────────────────────────────
    def _compact(self, current_tokens: int, forced: bool = False) -> dict:
        raw_data = self._collect_compressible_data()

        if not raw_data:
            log.warning("압축할 데이터가 없습니다.")
            return {"compacted": False, "saved_tokens": 0, "summary": "no data"}

        summary, token_usage = self._summarize(raw_data)
        self._save_cache(summary)

        estimated_saved = int(current_tokens * (1 - _TARGET_RATIO))
        self._append_log({
            "timestamp":        datetime.now().isoformat(),
            "forced":           forced,
            "tokens_before":    current_tokens,
            "estimated_saved":  estimated_saved,
            "summary_chars":    len(summary),
            "prompt_tokens":    token_usage["prompt_tokens"],
            "response_tokens":  token_usage["response_tokens"],
            "total_api_tokens": token_usage["total_api_tokens"],
            "cost_usd":         token_usage["estimated_cost_usd"],
        })

        log.info(f"  압축 완료 → 약 {estimated_saved:,} 토큰 절약 예상")
        return {
            "compacted":      True,
            "current_tokens": current_tokens,
            "threshold":      _COMPACT_THRESHOLD,
            "saved_tokens":   estimated_saved,
            "summary":        summary[:500] + ("..." if len(summary) > 500 else ""),
        }

    # ── 데이터 수집 ────────────────────────────────────────────────
    def _collect_compressible_data(self) -> dict:
        data = {}

        acc_path = _BASE / "accuracy.json"
        if acc_path.exists():
            try:
                data["accuracy"] = json.loads(acc_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        lessons_dir = _BASE / "lessons"
        if lessons_dir.exists():
            lessons = []
            for p in sorted(lessons_dir.glob("*.json"))[-10:]:
                try:
                    lessons.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
            if lessons:
                data["recent_lessons"] = lessons

        skills_dir = _BASE / "skills"
        if skills_dir.exists():
            data["skill_names"] = [p.stem for p in skills_dir.glob("*.json")]

        if self.cache_path.exists():
            try:
                prev = json.loads(self.cache_path.read_text(encoding="utf-8"))
                data["previous_summary"] = prev.get("summary", "")
            except Exception:
                pass

        return data

    # ── Claude 요약 ────────────────────────────────────────────────
    def _summarize(self, raw_data: dict) -> tuple:
        prompt = f"""
너는 ARIA 투자 분석 에이전트의 컨텍스트 압축기다.
아래 데이터를 분석하여 핵심 정보만 500 토큰 이내로 압축하라.

보존 우선순위:
1. 최근 정확도(accuracy) 수치
2. 최근 Instinct 경고 (실패 패턴)
3. 활성화된 Skill 목록
4. 이전 요약본의 핵심

제거 대상:
- 오래된 시장 상황 설명
- 중복 정보
- 성과 없는 패턴

입력 데이터:
{json.dumps(raw_data, ensure_ascii=False, indent=2)[:4000]}

출력: 한국어, 불릿 포인트 형식, 500자 이내
""".strip()

        resp = self.client.messages.create(
            model=_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        token_usage = {
            "prompt_tokens":      resp.usage.input_tokens,
            "response_tokens":    resp.usage.output_tokens,
            "total_api_tokens":   resp.usage.input_tokens + resp.usage.output_tokens,
            "estimated_cost_usd": round(
                resp.usage.input_tokens  * 0.00000080
                + resp.usage.output_tokens * 0.00000400,
                6,
            ),
        }
        return resp.content[0].text.strip(), token_usage

    def _save_cache(self, summary: str):
        self.cache_path.write_text(
            json.dumps({"summary": summary, "updated_at": datetime.now().isoformat()},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _append_log(self, entry: dict):
        logs = []
        if self.log_path.exists():
            try:
                logs = json.loads(self.log_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        logs.append(entry)
        self.log_path.write_text(
            json.dumps(logs[-100:], ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    parser = argparse.ArgumentParser(description="Jackal Compact Runner")
    parser.add_argument("--tokens", type=int, default=0)
    parser.add_argument("--force",  action="store_true")
    args = parser.parse_args()

    compact = JackalCompact()
    result  = compact.force_compact() if args.force else compact.check_and_compact(args.tokens)
    print(json.dumps(result, ensure_ascii=False, indent=2))
