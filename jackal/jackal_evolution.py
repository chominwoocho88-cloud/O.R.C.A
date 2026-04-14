"""
jackal_evolution.py
Jackal Evolution — 강화된 자체 학습

학습 데이터:
  - 신호별 정확도:  rsi_oversold가 맞은 횟수/전체
  - 레짐별 정확도:  위험선호 레짐에서 매수 신호가 맞은 횟수
  - Devil 정확도:  Devil이 반대했을 때 실제로 실패한 횟수
  - 티커별 정확도: 종목별 타점 적중률
  - 주간 패턴 리뷰: Claude Sonnet이 전체 데이터 분석 → Skill/Instinct 생성
"""

import json
import re
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

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

OUTCOME_HOURS      = 4
SUCCESS_PCT        = 0.5    # 이 % 이상 올라야 성공
WEIGHT_ADJUST_UP   = 0.04
WEIGHT_ADJUST_DOWN = 0.03
WEIGHT_MIN         = 0.3
WEIGHT_MAX         = 2.5

DEFAULT_WEIGHTS = {
    # 신호별 가중치 (Analyst가 fires할 때 적용)
    "signal_weights": {
        "rsi_oversold":   1.0,
        "bb_touch":       1.0,
        "volume_surge":   1.0,
        "ma_support":     1.0,
        "golden_cross":   1.0,
        "fear_regime":    1.0,
        "sector_inflow":  1.0,
    },
    # 레짐별 신뢰도 보정
    "regime_weights": {
        "위험선호": 1.1,
        "혼조":     1.0,
        "위험회피": 0.8,
        "전환중":   0.9,
    },
    # Devil 판정별 신뢰도
    "devil_weights": {
        "동의":     1.1,
        "부분동의": 0.9,
        "반대":     0.6,
    },
    # 신호별 정확도 (학습으로 채워짐)
    "signal_accuracy": {},
    # 레짐별 정확도
    "regime_accuracy": {},
    # 티커별 정확도
    "ticker_accuracy": {},
    # Devil 판정 정확도
    "devil_accuracy": {
        "동의":     {"correct": 0, "total": 0},
        "부분동의": {"correct": 0, "total": 0},
        "반대":     {"correct": 0, "total": 0},
    },
    "last_updated": "",
}


class JackalEvolution:

    def __init__(self):
        self.client  = Anthropic()
        self.weights = self._load_weights()
        self._logs: list = []

    def evolve(self) -> dict:
        log.info("🧬 Evolution 시작")

        # 1. 4시간 경과 알림 결과 확인 + 학습
        learn_result = self._learn_from_outcomes()

        # 2. Claude Sonnet 주간 패턴 리뷰 (7일치 데이터)
        context  = self._build_context()
        raw      = self._ask_claude(context)
        analysis = self._parse_response(raw)

        self._save_skills(analysis.get("new_skills", []))
        self._save_instincts(analysis.get("new_instincts", []))
        self._apply_claude_adjustments(analysis)
        self._mark_last_evolve()

        self.weights["last_updated"] = datetime.now().isoformat()
        self._save_weights()

        log.info(f"🧬 완료 | 학습 {learn_result['learned']}건 | "
                 f"Skill {len(analysis.get('new_skills',[]))}개")

        return {
            "learned":       learn_result["learned"],
            "weight_changes": learn_result["changes"],
            "new_skills":    analysis.get("new_skills", []),
            "new_instincts": analysis.get("new_instincts", []),
            "improvements":  analysis.get("prompt_improvements", ""),
            "accuracy_summary": learn_result.get("accuracy_summary", {}),
        }

    def save_weights(self):
        self._save_weights()

    # ══════════════════════════════════════════════════════════════
    # 결과 학습 — 신호별 / 레짐별 / Devil / 티커별
    # ══════════════════════════════════════════════════════════════

    def _learn_from_outcomes(self) -> dict:
        if not SCAN_LOG_FILE.exists():
            return {"learned": 0, "changes": [], "accuracy_summary": {}}

        try:
            self._logs = json.loads(SCAN_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"learned": 0, "changes": [], "accuracy_summary": {}}

        cutoff  = datetime.now() - timedelta(hours=OUTCOME_HOURS)
        pending = [
            e for e in self._logs
            if e.get("alerted")
            and not e.get("outcome_checked")
            and datetime.fromisoformat(e["timestamp"]) < cutoff
        ]

        learned  = 0
        changes  = []
        sig_acc  = defaultdict(lambda: {"correct": 0, "total": 0})
        reg_acc  = defaultdict(lambda: {"correct": 0, "total": 0})
        tkr_acc  = defaultdict(lambda: {"correct": 0, "total": 0})
        dev_acc  = defaultdict(lambda: {"correct": 0, "total": 0})

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

                # ── 신호별 정확도 집계 ─────────────────────────
                for sig in entry.get("signals_fired", []):
                    sig_acc[sig]["total"]   += 1
                    sig_acc[sig]["correct"] += int(correct)

                # ── 레짐별 정확도 ──────────────────────────────
                regime = entry.get("aria_regime", "")
                if regime:
                    reg_acc[regime]["total"]   += 1
                    reg_acc[regime]["correct"] += int(correct)

                # ── 티커별 정확도 ──────────────────────────────
                tkr_acc[ticker]["total"]   += 1
                tkr_acc[ticker]["correct"] += int(correct)

                # ── Devil 판정 정확도 ──────────────────────────
                verdict = entry.get("devil_verdict", "")
                if verdict:
                    dev_acc[verdict]["total"]   += 1
                    # Devil "반대"가 맞으면 → 실제로 실패 = correct for Devil
                    if verdict == "반대":
                        dev_acc[verdict]["correct"] += int(not correct)
                    else:
                        dev_acc[verdict]["correct"] += int(correct)

                # ── 신호별 가중치 즉시 조정 ────────────────────
                adj = WEIGHT_ADJUST_UP if correct else -WEIGHT_ADJUST_DOWN
                sw  = self.weights["signal_weights"]
                for sig in entry.get("signals_fired", []):
                    if sig in sw:
                        old = sw[sig]
                        new = round(max(WEIGHT_MIN, min(WEIGHT_MAX, old + adj)), 4)
                        sw[sig] = new
                        if abs(old - new) > 0.001:
                            changes.append(f"{sig}: {old:.3f}→{new:.3f} [{ticker} {pct:+.1f}%]")

                learned += 1
                log.info(f"  {ticker}: {pct:+.1f}% {'✅' if correct else '❌'} | "
                         f"signals={entry.get('signals_fired',[])} devil={verdict}")

            except Exception as e:
                log.error(f"  학습 실패: {e}")

        # ── 누적 정확도 업데이트 ───────────────────────────────
        self._update_accuracy("signal_accuracy",  sig_acc)
        self._update_accuracy("regime_accuracy",  reg_acc)
        self._update_accuracy("ticker_accuracy",  tkr_acc)
        self._update_devil_accuracy(dev_acc)

        # 로그 저장
        if pending:
            SCAN_LOG_FILE.write_text(
                json.dumps(self._logs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # 정확도 요약
        acc_summary = {}
        for key in ["signal_accuracy", "regime_accuracy", "ticker_accuracy"]:
            acc = self.weights.get(key, {})
            acc_summary[key] = {
                k: {"accuracy": round(v["correct"]/v["total"]*100, 1),
                    "total": v["total"]}
                for k, v in acc.items() if v.get("total", 0) >= 3
            }

        return {"learned": learned, "changes": changes, "accuracy_summary": acc_summary}

    def _update_accuracy(self, key: str, new_data: dict):
        """누적 정확도 딕셔너리 업데이트"""
        acc = self.weights.setdefault(key, {})
        for k, v in new_data.items():
            if k not in acc:
                acc[k] = {"correct": 0, "total": 0}
            acc[k]["correct"] += v["correct"]
            acc[k]["total"]   += v["total"]
            acc[k]["accuracy"] = round(
                acc[k]["correct"] / acc[k]["total"] * 100, 1
            ) if acc[k]["total"] > 0 else 0

    def _update_devil_accuracy(self, new_data: dict):
        da = self.weights.setdefault("devil_accuracy", {})
        for verdict, v in new_data.items():
            if verdict not in da:
                da[verdict] = {"correct": 0, "total": 0}
            da[verdict]["correct"] += v["correct"]
            da[verdict]["total"]   += v["total"]
            da[verdict]["accuracy"] = round(
                da[verdict]["correct"] / da[verdict]["total"] * 100, 1
            ) if da[verdict]["total"] > 0 else 0

    # ══════════════════════════════════════════════════════════════
    # Claude Sonnet 주간 패턴 리뷰
    # ══════════════════════════════════════════════════════════════

    def _build_context(self) -> dict:
        """7일치 스캔 데이터 + 현재 정확도 요약"""
        recent = self._load_recent_logs(days=7)
        alerted = [e for e in recent if e.get("alerted")]
        correct = [e for e in alerted if e.get("outcome_correct") is True]
        wrong   = [e for e in alerted if e.get("outcome_correct") is False]

        # 신호 조합 분석
        sig_combos = defaultdict(lambda: {"correct": 0, "total": 0})
        for e in alerted:
            sigs = tuple(sorted(e.get("signals_fired", [])))
            sig_combos[str(sigs)]["total"] += 1
            if e.get("outcome_correct"):
                sig_combos[str(sigs)]["correct"] += 1

        # 레짐별 성과
        regime_perf = defaultdict(lambda: {"correct": 0, "total": 0})
        for e in alerted:
            r = e.get("aria_regime", "")
            if r:
                regime_perf[r]["total"] += 1
                if e.get("outcome_correct"):
                    regime_perf[r]["correct"] += 1

        return {
            "period": "7일",
            "scan_summary": {
                "total_scans":   len(recent),
                "total_alerted": len(alerted),
                "correct":       len(correct),
                "wrong":         len(wrong),
                "accuracy_pct":  round(len(correct)/len(alerted)*100, 1) if alerted else 0,
            },
            "signal_accuracy": {
                k: v for k, v in self.weights.get("signal_accuracy", {}).items()
                if v.get("total", 0) >= 2
            },
            "regime_accuracy": {
                k: v for k, v in self.weights.get("regime_accuracy", {}).items()
            },
            "ticker_accuracy": {
                k: v for k, v in self.weights.get("ticker_accuracy", {}).items()
            },
            "devil_accuracy": self.weights.get("devil_accuracy", {}),
            "top_signal_combos": dict(list(sig_combos.items())[:5]),
            "regime_performance": dict(regime_perf),
            "existing_skills":   [p.stem for p in SKILLS_DIR.glob("*.json")],
            "current_weights":   {
                k: round(v, 3) if isinstance(v, (int, float)) else v
                for k, v in self.weights.get("signal_weights", {}).items()
            },
            "recent_correct": [
                {"ticker": e["ticker"], "signals": e.get("signals_fired",[]),
                 "regime": e.get("aria_regime",""), "pct": e.get("outcome_pct")}
                for e in correct[-5:]
            ],
            "recent_wrong": [
                {"ticker": e["ticker"], "signals": e.get("signals_fired",[]),
                 "devil": e.get("devil_verdict",""), "pct": e.get("outcome_pct")}
                for e in wrong[-5:]
            ],
        }

    def _ask_claude(self, context: dict) -> str:
        prompt = f"""
너는 Jackal, 주식 타점 분석 AI의 자동 진화 엔진이다.
아래 7일간 타점 분석 성과를 보고 패턴을 파악해 JSON으로만 반환하라.

### 성과 데이터
{json.dumps(context, ensure_ascii=False, indent=2)[:4000]}

### 반환 형식
{{
  "new_skills": [
    {{
      "name": "snake_case 이름",
      "description": "어떤 상황에서 쓰는 Skill",
      "trigger": "발동 조건 (구체적 수치 포함)",
      "action": "판단 방법"
    }}
  ],
  "new_instincts": [
    {{
      "name": "instinct_이름",
      "warning": "피해야 할 패턴",
      "reason": "왜 실패했는가",
      "regime_context": "어떤 레짐에서 발생했는가"
    }}
  ],
  "prompt_improvements": {{
    "analyst": "Analyst 프롬프트 개선사항",
    "devil": "Devil 프롬프트 개선사항"
  }},
  "weight_adjustments": {{
    "rsi_oversold": 0.0,
    "bb_touch": 0.0,
    "volume_surge": 0.0,
    "golden_cross": 0.0,
    "sector_inflow": 0.0
  }},
  "regime_insights": "레짐별 성과에서 발견된 패턴",
  "devil_insights": "Devil 판정 정확도에서 발견된 패턴"
}}

규칙:
- 기존 Skill과 중복 제외
- 데이터 3건 미만이면 빈 배열
- weight_adjustments는 -0.15 ~ +0.15 범위
- 정확도가 60% 이상인 신호는 가중치 ↑, 40% 미만은 ↓ 권장
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
            log.error(f"파싱 실패: {e}")
            return {"new_skills": [], "new_instincts": [],
                    "prompt_improvements": {}, "weight_adjustments": {}}

    # ══════════════════════════════════════════════════════════════
    # Skill / Instinct 저장
    # ══════════════════════════════════════════════════════════════

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

    def _apply_claude_adjustments(self, result: dict):
        """Claude가 제안한 가중치 조정 적용"""
        sw = self.weights["signal_weights"]
        for key, delta in result.get("weight_adjustments", {}).items():
            if key in sw:
                old = sw[key]
                new = round(max(WEIGHT_MIN, min(WEIGHT_MAX, old + float(delta))), 4)
                sw[key] = new
                if abs(old - new) > 0.001:
                    log.info(f"  Claude 조정: {key} {old:.3f}→{new:.3f}")

    def _mark_last_evolve(self):
        (_BASE / ".last_evolve").write_text(datetime.now().isoformat(), encoding="utf-8")

    # ══════════════════════════════════════════════════════════════
    # 유틸
    # ══════════════════════════════════════════════════════════════

    def _load_recent_logs(self, days: int = 7) -> list:
        if not SCAN_LOG_FILE.exists():
            return []
        try:
            logs   = json.loads(SCAN_LOG_FILE.read_text(encoding="utf-8"))
            cutoff = datetime.now() - timedelta(days=days)
            return [e for e in logs
                    if datetime.fromisoformat(e["timestamp"]) >= cutoff]
        except Exception:
            return []

    def _load_weights(self) -> dict:
        if not WEIGHTS_FILE.exists():
            return DEFAULT_WEIGHTS.copy()
        try:
            loaded = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
            # 새 키 병합
            merged = DEFAULT_WEIGHTS.copy()
            for k, v in loaded.items():
                if k in merged and isinstance(v, dict) and isinstance(merged[k], dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
        except Exception:
            return DEFAULT_WEIGHTS.copy()

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
