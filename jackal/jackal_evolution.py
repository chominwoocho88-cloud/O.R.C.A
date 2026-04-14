"""
jackal_evolution.py
Jackal Evolution — 타점 스캔 결과 자체 학습

학습 흐름 (ARIA와 완전 독립):
  1. scan_log.json 에서 알림 발송 후 4시간 경과 항목 수집
  2. yfinance 로 현재가 조회 → 알림 시점 대비 수익률 계산
  3. 성공한 신호(맞음) → 해당 signal_type 가중치 ↑
     실패한 신호(틀림) → 해당 signal_type 가중치 ↓
  4. Claude Sonnet 으로 패턴 분석 → Skill/Instinct 자동 생성
  5. jackal_weights.json 저장
"""

import json
import re
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf
from anthropic import Anthropic

log = logging.getLogger("jackal_evolution")

_BASE         = Path(__file__).parent
WEIGHTS_FILE  = _BASE / "jackal_weights.json"
SCAN_LOG_FILE = _BASE / "scan_log.json"
SKILLS_DIR    = _BASE / "skills"
LESSONS_DIR   = _BASE / "lessons"

SKILLS_DIR.mkdir(exist_ok=True)
LESSONS_DIR.mkdir(exist_ok=True)

MODEL_S = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

OUTCOME_HOURS      = 4      # 알림 발송 후 결과 확인 시간
SUCCESS_PCT        = 0.5    # 이 % 이상 오르면 성공
WEIGHT_ADJUST_UP   = 0.05
WEIGHT_ADJUST_DOWN = 0.03
WEIGHT_MIN         = 0.1
WEIGHT_MAX         = 2.0

DEFAULT_WEIGHTS = {
    "강한매수":  1.0,
    "매수검토":  1.0,
    "관망":      1.0,
    "매도주의":  1.0,
}


class JackalEvolution:

    def __init__(self):
        self.client  = Anthropic()
        self.weights = self._load_weights()
        self._logs: list = []

    def evolve(self) -> dict:
        log.info("🧬 Evolution 시작")

        # 1. 스캔 결과 학습
        scan_result = self._learn_from_scans()

        # 2. 패턴 분석 → Skill/Instinct 생성
        context  = self._build_context()
        raw      = self._ask_claude(context)
        analysis = self._parse_response(raw)

        self._save_skills(analysis.get("new_skills", []))
        self._save_instincts(analysis.get("new_instincts", []))
        self._update_weights_from_claude(analysis)
        self._mark_last_evolve()

        log.info("🧬 Evolution 완료")
        return {
            "scan_learned":    scan_result["learned"],
            "weight_changes":  scan_result["changes"],
            "new_skills":      analysis.get("new_skills", []),
            "new_instincts":   analysis.get("new_instincts", []),
            "improvements":    analysis.get("prompt_improvements", ""),
        }

    def save_weights(self):
        self._save_weights()

    # ── 스캔 결과 자체 학습 ────────────────────────────────────────

    def _learn_from_scans(self) -> dict:
        """알림 발송 4시간 후 실제 가격 확인 → 가중치 조정"""
        if not SCAN_LOG_FILE.exists():
            return {"learned": 0, "changes": []}

        try:
            self._logs = json.loads(SCAN_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"learned": 0, "changes": []}

        cutoff  = datetime.now() - timedelta(hours=OUTCOME_HOURS)
        pending = [
            e for e in self._logs
            if e.get("alerted")
            and not e.get("outcome_checked")
            and datetime.fromisoformat(e["timestamp"]) < cutoff
        ]

        learned = 0
        changes = []

        for entry in pending:
            try:
                ticker      = entry["ticker"]
                price_alert = entry.get("price_at_scan", 0)
                if not price_alert:
                    continue

                hist = yf.Ticker(ticker).history(period="2d", interval="1h")
                if hist.empty:
                    continue

                current = float(hist["Close"].iloc[-1])
                pct     = (current - price_alert) / price_alert * 100
                correct = pct >= SUCCESS_PCT

                entry["outcome_checked"] = True
                entry["outcome_price"]   = round(current, 4)
                entry["outcome_pct"]     = round(pct, 2)
                entry["outcome_correct"] = correct

                # signal_type 기반 가중치 조정
                sig_type = entry.get("signal_type", "")
                adj      = WEIGHT_ADJUST_UP if correct else -WEIGHT_ADJUST_DOWN

                if sig_type in self.weights["signal_type_weights"]:
                    old = self.weights["signal_type_weights"][sig_type]
                    new = round(max(WEIGHT_MIN, min(WEIGHT_MAX, old + adj)), 4)
                    self.weights["signal_type_weights"][sig_type] = new
                    if old != new:
                        changes.append(
                            f"{sig_type}: {old:.3f}→{new:.3f} "
                            f"[{ticker} {pct:+.1f}%]"
                        )

                learned += 1
                log.info(f"  {ticker}: {pct:+.1f}% {'✅' if correct else '❌'} | {sig_type}")

            except Exception as e:
                log.error(f"  학습 실패: {e}")

        # 업데이트된 로그 저장
        if pending:
            SCAN_LOG_FILE.write_text(
                json.dumps(self._logs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return {"learned": learned, "changes": changes}

    # ── 컨텍스트 구성 ──────────────────────────────────────────────

    def _build_context(self) -> dict:
        recent_scans   = self._load_recent_scans(days=7)
        recent_lessons = self._load_recent_lessons(days=7)
        skill_names    = [p.stem for p in SKILLS_DIR.glob("*.json")]
        weight_summary = {
            k: round(v, 3) if isinstance(v, (int, float)) else v
            for k, v in self.weights.items()
        }

        # 최근 알림 성과 요약
        alerted = [e for e in recent_scans if e.get("alerted")]
        correct = [e for e in alerted if e.get("outcome_correct") is True]
        wrong   = [e for e in alerted if e.get("outcome_correct") is False]

        return {
            "scan_summary": {
                "total_scans":   len(recent_scans),
                "total_alerted": len(alerted),
                "correct":       len(correct),
                "wrong":         len(wrong),
                "accuracy_pct":  round(len(correct) / len(alerted) * 100, 1) if alerted else 0,
            },
            "recent_correct_signals": [
                {"ticker": e["ticker"], "signal_type": e.get("signal_type"), "pct": e.get("outcome_pct")}
                for e in correct[-5:]
            ],
            "recent_wrong_signals": [
                {"ticker": e["ticker"], "signal_type": e.get("signal_type"), "pct": e.get("outcome_pct")}
                for e in wrong[-5:]
            ],
            "existing_skills":  skill_names,
            "recent_lessons":   recent_lessons,
            "current_weights":  weight_summary,
        }

    def _load_recent_scans(self, days: int = 7) -> list:
        if not SCAN_LOG_FILE.exists():
            return []
        try:
            logs   = json.loads(SCAN_LOG_FILE.read_text(encoding="utf-8"))
            cutoff = datetime.now() - timedelta(days=days)
            return [e for e in logs
                    if datetime.fromisoformat(e["timestamp"]) >= cutoff]
        except Exception:
            return []

    def _load_recent_lessons(self, days: int = 7) -> list:
        cutoff  = datetime.now() - timedelta(days=days)
        lessons = []
        for p in sorted(LESSONS_DIR.glob("*.json")):
            if p.name.startswith("."):
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                ts   = datetime.fromisoformat(data.get("timestamp", "2000-01-01"))
                if ts >= cutoff:
                    lessons.append(data)
            except Exception:
                pass
        return lessons[-10:]

    # ── Claude 패턴 분석 ───────────────────────────────────────────

    def _ask_claude(self, context: dict) -> str:
        prompt = f"""
너는 Jackal, 주식 타점 분석 AI의 자동 진화 엔진이다.
아래 최근 7일 타점 스캔 성과를 분석하고 JSON으로만 반환하라.
마크다운, 설명 없이 순수 JSON만 출력.

### 성과 데이터
{json.dumps(context, ensure_ascii=False, indent=2)[:3000]}

### 반환 형식
{{
  "new_skills": [
    {{
      "name": "skill_이름(snake_case)",
      "description": "어떤 타점 상황에서 쓰는 Skill",
      "trigger": "발동 조건 (RSI/볼린저/거래량 기준)",
      "action": "구체적 판단 방법"
    }}
  ],
  "new_instincts": [
    {{
      "name": "instinct_이름",
      "warning": "피해야 할 패턴",
      "reason": "왜 실패했는가"
    }}
  ],
  "prompt_improvements": "타점 판단 프롬프트 개선사항 (없으면 빈 문자열)",
  "weight_adjustments": {{
    "강한매수": 0.0,
    "매수검토": 0.0
  }}
}}

규칙:
- 기존 Skill과 중복 제외
- 데이터 부족 시 빈 배열
- weight_adjustments 는 -0.1 ~ +0.1 범위
""".strip()

        resp = self.client.messages.create(
            model=MODEL_S,
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text

    def _parse_response(self, raw: str) -> dict:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except Exception as e:
            log.error(f"Evolution 파싱 실패: {e}")
            return {"new_skills": [], "new_instincts": [],
                    "prompt_improvements": "", "weight_adjustments": {}}

    # ── Skill / Instinct 저장 ──────────────────────────────────────

    def _save_skills(self, skills: list):
        for skill in skills:
            name = skill.get("name", "").strip()
            if not name:
                continue
            path = SKILLS_DIR / f"{name}.json"
            skill["created_at"] = datetime.now().isoformat()
            path.write_text(json.dumps(skill, ensure_ascii=False, indent=2), encoding="utf-8")
            log.info(f"  ✅ Skill 생성: {name}")

    def _save_instincts(self, instincts: list):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        for i, inst in enumerate(instincts):
            name = inst.get("name", f"instinct_{i}").strip()
            path = LESSONS_DIR / f"{ts}_{name}.json"
            inst["timestamp"] = datetime.now().isoformat()
            path.write_text(json.dumps(inst, ensure_ascii=False, indent=2), encoding="utf-8")
            log.info(f"  ⚠️  Instinct 등록: {name}")

    # ── 가중치 ─────────────────────────────────────────────────────

    def _update_weights_from_claude(self, result: dict):
        for key, delta in result.get("weight_adjustments", {}).items():
            if key in self.weights["signal_type_weights"]:
                old = self.weights["signal_type_weights"][key]
                self.weights["signal_type_weights"][key] = round(
                    max(WEIGHT_MIN, min(WEIGHT_MAX, old + float(delta))), 4
                )
        self.weights["last_updated"] = datetime.now().isoformat()

    def _mark_last_evolve(self):
        (_BASE / ".last_evolve").write_text(datetime.now().isoformat(), encoding="utf-8")

    def _load_weights(self) -> dict:
        default = {
            "signal_type_weights": DEFAULT_WEIGHTS.copy(),
            "alert_threshold":     65,
            "cooldown_hours":      4,
            "last_updated":        "",
        }
        if WEIGHTS_FILE.exists():
            try:
                loaded = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
                # signal_type_weights 병합
                sw = default["signal_type_weights"].copy()
                sw.update(loaded.get("signal_type_weights", {}))
                loaded["signal_type_weights"] = sw
                default.update(loaded)
            except Exception:
                pass
        return default

    def _save_weights(self):
        WEIGHTS_FILE.write_text(
            json.dumps(self.weights, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    ev = JackalEvolution()
    print(json.dumps(ev.evolve(), ensure_ascii=False, indent=2))
    ev.save_weights()
