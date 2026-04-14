"""
jackal_core.py
Jackal - ARIA 자동 성장 엔진 (메인 오케스트레이터)

실행 흐름:
  1. Shield Scan (보안/비용 사전 체크)
  2. Compact Check (Context Rot 방지)
  3. Evolution (패턴 학습 + Skill 승격)
  4. 결과 요약 출력
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from jackal_shield import JackalShield
from jackal_compact import JackalCompact
from jackal_evolution import JackalEvolution

# ─── 디렉토리 초기화 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / "skills"
LESSONS_DIR = BASE_DIR / "lessons"
WEIGHTS_FILE = BASE_DIR / "jackal_weights.json"

for d in [SKILLS_DIR, LESSONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ─── 로거 ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Jackal] %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("jackal_core")


class JackalCore:
    """Jackal 메인 엔진 - Shield → Compact → Evolution 순서로 실행"""

    def __init__(self):
        self.shield = JackalShield()
        self.compact = JackalCompact()
        self.evolution = JackalEvolution(
            skills_dir=SKILLS_DIR,
            lessons_dir=LESSONS_DIR,
            weights_file=WEIGHTS_FILE,
        )
        self.report: dict = {}

    # ── 공개 진입점 ────────────────────────────────────────────────
    def run(self, context_tokens: int = 0, force_evolve: bool = False) -> dict:
        """
        Jackal 전체 파이프라인 실행.

        Args:
            context_tokens: 현재 세션에서 사용된 토큰 수 (compact 판단에 사용)
            force_evolve:   Evolution을 강제 실행 (기본: 주 1회 자동 실행)

        Returns:
            실행 결과 딕셔너리
        """
        log.info("🦊 Jackal Core 시작")
        start = datetime.now()

        # 1. Shield Scan
        shield_result = self._run_shield()
        if shield_result.get("abort"):
            log.warning("⛔ Shield가 실행 중단을 요청했습니다.")
            return {"status": "aborted", "reason": shield_result}

        # 2. Compact Check
        compact_result = self._run_compact(context_tokens)

        # 3. Evolution (매일 00:00 이후 첫 실행 or force)
        evolve_result = {}
        if force_evolve or self._should_evolve():
            evolve_result = self._run_evolution()

        # 4. 가중치 저장
        self.evolution.save_weights()

        elapsed = (datetime.now() - start).total_seconds()
        self.report = {
            "status": "ok",
            "elapsed_sec": round(elapsed, 2),
            "shield": shield_result,
            "compact": compact_result,
            "evolution": evolve_result,
            "timestamp": datetime.now().isoformat(),
        }

        self._print_summary()
        return self.report

    # ── 내부 단계 ──────────────────────────────────────────────────
    def _run_shield(self) -> dict:
        log.info("🛡️  Shield Scan 실행 중...")
        result = self.shield.scan()
        if result["issues"]:
            for issue in result["issues"]:
                log.warning(f"  Shield 경고: {issue}")
        else:
            log.info("  Shield: 이상 없음 ✅")
        return result

    def _run_compact(self, context_tokens: int) -> dict:
        log.info(f"📦 Compact Check (현재 토큰: {context_tokens:,})")
        result = self.compact.check_and_compact(context_tokens)
        if result["compacted"]:
            log.info(f"  압축 완료: {result['saved_tokens']:,} 토큰 절약")
        else:
            log.info("  압축 불필요")
        return result

    def _run_evolution(self) -> dict:
        log.info("🧬 Evolution Engine 실행 중...")
        result = self.evolution.evolve()
        skills = result.get("new_skills", [])
        log.info(f"  새 Skill: {len(skills)}개 생성")
        return result

    def _should_evolve(self) -> bool:
        """마지막 Evolution 이후 24시간 경과 여부"""
        marker = LESSONS_DIR / ".last_evolve"
        if not marker.exists():
            return True
        last = datetime.fromisoformat(marker.read_text().strip())
        elapsed_hours = (datetime.now() - last).total_seconds() / 3600
        return elapsed_hours >= 24

    def _print_summary(self):
        r = self.report
        print("\n" + "=" * 52)
        print(f"  🦊 Jackal Report  ({r['timestamp'][:19]})")
        print("=" * 52)
        print(f"  상태      : {r['status'].upper()}")
        print(f"  소요 시간 : {r['elapsed_sec']}s")

        shield = r["shield"]
        print(f"  Shield    : {'⚠️  경고 ' + str(len(shield['issues'])) + '건' if shield['issues'] else '✅ 이상 없음'}")

        compact = r["compact"]
        if compact.get("compacted"):
            print(f"  Compact   : ✅ {compact['saved_tokens']:,} 토큰 절약")
        else:
            print("  Compact   : ⏭️  skip")

        ev = r["evolution"]
        if ev:
            print(f"  Evolution : ✅ Skill {len(ev.get('new_skills', []))}개 생성")
        else:
            print("  Evolution : ⏭️  skip (24h 미경과)")
        print("=" * 52 + "\n")


# ─── 단독 실행 ────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Jackal Core Runner")
    parser.add_argument("--tokens", type=int, default=0, help="현재 세션 토큰 수")
    parser.add_argument("--force-evolve", action="store_true", help="Evolution 강제 실행")
    args = parser.parse_args()

    core = JackalCore()
    core.run(context_tokens=args.tokens, force_evolve=args.force_evolve)
