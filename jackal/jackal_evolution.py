"""
jackal_evolution.py
Jackal Evolution — 스캔 알림 결과 학습 + 신호 가중치 자동 조정

학습 흐름:
  1. scan_log.json 에서 알림 발송 후 4시간 이상 지난 미채점 항목 수집
  2. yfinance 로 현재가 조회 → 알림 시점 대비 수익률 계산
  3. 수익 시 → 해당 알림의 fired 신호들 가중치 ↑
     손실 시 → 해당 알림의 fired 신호들 가중치 ↓
  4. jackal_weights.json 에 저장
"""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

log = logging.getLogger("jackal_evolution")

_BASE         = Path(__file__).parent
WEIGHTS_FILE  = _BASE / "jackal_weights.json"
SCAN_LOG_FILE = _BASE / "scan_log.json"

OUTCOME_CHECK_HOURS = 4    # 알림 후 몇 시간 뒤 결과 확인
SUCCESS_PCT         = 0.5  # 이 % 이상 오르면 성공
WEIGHT_ADJUST_UP    = 0.05
WEIGHT_ADJUST_DOWN  = 0.03
WEIGHT_MIN          = 0.3
WEIGHT_MAX          = 2.5

DEFAULT_SIGNAL_WEIGHTS = {
    "rsi_extreme":    1.0,
    "rsi_oversold":   1.0,
    "golden_cross":   1.0,
    "dead_cross":     1.0,
    "bb_touch":       1.0,
    "bb_near":        1.0,
    "bb_upper":       1.0,
    "volume_surge":   1.0,
    "volume_rise":    1.0,
    "ma20_support":   1.0,
    "cross_imminent": 1.0,
}


class JackalEvolution:

    def __init__(self):
        self.weights  = self._load_weights()
        self._all_logs: list = []

    def evolve(self) -> dict:
        log.info("🧬 Evolution 시작")
        pending = self._get_pending_alerts()

        if not pending:
            log.info("  학습할 알림 없음")
            return {"learned": 0, "weight_changes": []}

        changes = []
        learned = 0

        for entry in pending:
            outcome = self._check_outcome(entry)
            if outcome is None:
                continue

            entry["outcome_checked"] = True
            entry["outcome_price"]   = outcome["current_price"]
            entry["outcome_pct"]     = outcome["pct_change"]
            entry["outcome_correct"] = outcome["correct"]

            fired   = entry.get("fired", [])
            correct = outcome["correct"]
            adj     = WEIGHT_ADJUST_UP if correct else -WEIGHT_ADJUST_DOWN

            for key in fired:
                if key in self.weights["signal_weights"]:
                    old = self.weights["signal_weights"][key]
                    new = round(max(WEIGHT_MIN, min(WEIGHT_MAX, old + adj)), 4)
                    self.weights["signal_weights"][key] = new
                    if old != new:
                        changes.append(
                            f"{key}: {old:.3f}→{new:.3f} "
                            f"[{entry['ticker']} {outcome['pct_change']:+.1f}%]"
                        )
            learned += 1
            log.info(
                f"  {entry['ticker']}: {outcome['pct_change']:+.1f}% "
                f"{'✅' if correct else '❌'} | fired={fired}"
            )

        # 로그 + 가중치 저장
        if self._all_logs:
            SCAN_LOG_FILE.write_text(
                json.dumps(self._all_logs, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        self.weights["last_updated"] = datetime.now().isoformat()
        self._save_weights()

        for c in changes:
            log.info(f"  ⚖️  {c}")
        log.info(f"🧬 완료 | 학습 {learned}건 | 가중치 변경 {len(changes)}개")
        return {"learned": learned, "weight_changes": changes}

    def save_weights(self):
        self._save_weights()

    def _get_pending_alerts(self) -> list:
        if not SCAN_LOG_FILE.exists():
            return []
        try:
            self._all_logs = json.loads(SCAN_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []

        cutoff  = datetime.now() - timedelta(hours=OUTCOME_CHECK_HOURS)
        pending = []
        for entry in self._all_logs:
            if not entry.get("alerted"):
                continue
            if entry.get("outcome_checked"):
                continue
            try:
                if datetime.fromisoformat(entry["timestamp"]) < cutoff:
                    pending.append(entry)
            except Exception:
                continue
        return pending

    def _check_outcome(self, entry: dict) -> dict | None:
        try:
            price_alert = entry.get("price_at_scan")
            if not price_alert:
                return None
            hist = yf.Ticker(entry["ticker"]).history(period="2d", interval="1h")
            if hist.empty:
                return None
            current = float(hist["Close"].iloc[-1])
            pct     = (current - price_alert) / price_alert * 100
            return {
                "current_price": round(current, 4),
                "pct_change":    round(pct, 2),
                "correct":       pct >= SUCCESS_PCT,
            }
        except Exception as e:
            log.error(f"  outcome 조회 실패: {e}")
            return None

    def _load_weights(self) -> dict:
        default = {
            "signal_weights":      DEFAULT_SIGNAL_WEIGHTS.copy(),
            "fear_greed_weight":   0.35,
            "technical_weight":    0.40,
            "fundamental_weight":  0.25,
            "last_updated":        "",
        }
        if WEIGHTS_FILE.exists():
            try:
                loaded = json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
                sw = default["signal_weights"].copy()
                sw.update(loaded.get("signal_weights", {}))
                loaded["signal_weights"] = sw
                # 문자열 필드는 round 제외하고 업데이트
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
