"""
aria_scanner.py — ARIA Entry Point Scanner (타점 알리미)

매시간 실행 → 보유 종목 기술적 신호 계산 → 임계치 초과 시 텔레그램 발송
Claude API 호출 없음 (yfinance + 로컬 계산) → 비용 제로

신호 계산:
  1. RSI 14일 (과매도 / 과매수)
  2. MA20 × MA50 골든/데드 크로스
  3. 볼린저밴드 (20일, 2σ) 하단/상단 터치
  4. 거래량 급증 (5일 평균 대비)
  5. MA20 지지선 근접 (±1.2%)

점수 보정:
  - data/sentiment.json 로드 → 극단 공포(<30) 또는 탐욕(>65) 구간 시 +10~15%

알림 조건:
  - 최종 점수 ≥ 65  →  🔵 진입 검토 타점
  - 최종 점수 ≥ 78  →  🔥 강한 매수 타점
  - 같은 종목 4시간 내 재알림 없음 (쿨다운)

저장:
  - data/scanner_log.json      (최근 300건 스캔 기록)
  - data/scanner_cooldown.json (종목별 마지막 알림 시각)
"""

import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yfinance as yf

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─── 경로 (aria_paths.py 와 동일 규칙) ───────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SENTIMENT_FILE = DATA_DIR / "sentiment.json"
COOLDOWN_FILE  = DATA_DIR / "scanner_cooldown.json"
LOG_FILE       = DATA_DIR / "scanner_log.json"

# ─── 로거 ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Scanner] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("aria_scanner")

# ─── 텔레그램 ──────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KST = timezone(timedelta(hours=9))

# ─── 감시 종목 ─────────────────────────────────────────────────────
#   ticker  : yfinance 심볼
#   name    : 표시명
#   avg_cost: 평균 매입 단가 (None = 미보유 / 단순 감시)
#   market  : "US" | "KR"
#   currency: 가격 단위
WATCHLIST: dict = {
    "NVDA":      {"name": "엔비디아",   "avg_cost": 182.99, "market": "US", "currency": "$"},
    "AVGO":      {"name": "브로드컴",   "avg_cost": None,   "market": "US", "currency": "$"},
    "SCHD":      {"name": "SCHD",       "avg_cost": None,   "market": "US", "currency": "$"},
    "000660.KS": {"name": "SK하이닉스", "avg_cost": None,   "market": "KR", "currency": "₩"},
    "005930.KS": {"name": "삼성전자",   "avg_cost": None,   "market": "KR", "currency": "₩"},
    "035720.KS": {"name": "카카오",     "avg_cost": None,   "market": "KR", "currency": "₩"},
}

# ─── 임계치 ────────────────────────────────────────────────────────
SIGNAL_THRESHOLD = 65    # 이 점수 이상이면 텔레그램 발송
STRONG_THRESHOLD = 78    # 이 점수 이상이면 "강한 매수" 헤더
COOLDOWN_HOURS   = 4     # 같은 종목 재알림 최소 간격(시간)


# ══════════════════════════════════════════════════════════════════
# 시장 개장 여부
# ══════════════════════════════════════════════════════════════════

def _is_us_open() -> bool:
    """미국 정규장: EST 09:30 ~ 16:00, 월~금"""
    from datetime import time as _t
    now = datetime.now(timezone(timedelta(hours=-5)))
    return now.weekday() < 5 and _t(9, 30) <= now.time() <= _t(16, 0)


def _is_kr_open() -> bool:
    """한국 정규장: KST 09:00 ~ 15:30, 월~금"""
    from datetime import time as _t
    now = datetime.now(KST)
    return now.weekday() < 5 and _t(9, 0) <= now.time() <= _t(15, 30)


# ══════════════════════════════════════════════════════════════════
# 기술적 분석 (Claude API 없음, 순수 계산)
# ══════════════════════════════════════════════════════════════════

def analyze(ticker: str) -> dict | None:
    """
    65일 일봉 기준 기술적 신호 분석.
    Returns: {price, rsi, bb_pos, ma_cross, vol_ratio, score, signals}
             또는 None
    """
    try:
        hist = yf.Ticker(ticker).history(period="65d", interval="1d")
        if len(hist) < 22:
            log.warning(f"  {ticker}: 데이터 부족 ({len(hist)}일)")
            return None

        close  = hist["Close"]
        volume = hist["Volume"]
        price  = float(close.iloc[-1])

        score: float = 50.0
        signals: list = []

        # ── 1. RSI 14일 ──────────────────────────────────────────
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rsi   = float((100 - 100 / (1 + gain / loss)).iloc[-1])

        if rsi <= 28:
            score += 22; signals.append(f"🔴 RSI {rsi:.1f} 극단 과매도")
        elif rsi <= 38:
            score += 12; signals.append(f"🟠 RSI {rsi:.1f} 과매도권 진입")
        elif rsi >= 72:
            score -= 18; signals.append(f"⚠️ RSI {rsi:.1f} 과매수 — 진입 자제")
        elif rsi >= 62:
            score -= 8;  signals.append(f"RSI {rsi:.1f} 고점권")

        # ── 2. MA20 × MA50 크로스 ────────────────────────────────
        ma20     = close.rolling(20).mean()
        ma_cross = None

        if len(close) >= 52:
            ma50      = close.rolling(50).mean()
            was_above = bool(ma20.iloc[-2] > ma50.iloc[-2])
            now_above = bool(ma20.iloc[-1] > ma50.iloc[-1])

            if now_above and not was_above:
                score += 16; ma_cross = "golden"
                signals.append("✅ MA20 골든크로스 (MA50 상향돌파)")
            elif not now_above and was_above:
                score -= 18; ma_cross = "dead"
                signals.append("❌ MA20 데드크로스 (MA50 하향돌파)")
            else:
                gap = (float(ma20.iloc[-1]) - float(ma50.iloc[-1])) / float(ma50.iloc[-1]) * 100
                if abs(gap) < 0.5:
                    signals.append(f"MA20/MA50 크로스 임박 ({gap:+.1f}%)")

        # ── 3. 볼린저밴드 (20일, 2σ) ─────────────────────────────
        ma20_v = float(ma20.iloc[-1])
        std20  = float(close.rolling(20).std().iloc[-1])
        bb_up  = ma20_v + 2 * std20
        bb_dn  = ma20_v - 2 * std20
        rng    = bb_up - bb_dn
        bb_pos = (price - bb_dn) / rng if rng > 0 else 0.5

        if bb_pos <= 0.08:
            score += 18; signals.append(f"📉 볼린저 하단 터치 ({bb_pos:.0%}) — 반등 기대")
        elif bb_pos <= 0.20:
            score += 9;  signals.append(f"볼린저 하단 근접 ({bb_pos:.0%})")
        elif bb_pos >= 0.92:
            score -= 12; signals.append(f"📈 볼린저 상단 과확장 ({bb_pos:.0%})")

        # ── 4. 거래량 급증 ───────────────────────────────────────
        vol_ratio = 1.0
        if len(volume) >= 6:
            avg_vol   = float(volume.iloc[-6:-1].mean())
            vol_ratio = float(volume.iloc[-1]) / avg_vol if avg_vol > 0 else 1.0

            if vol_ratio >= 2.5:
                score += 12; signals.append(f"🔥 거래량 급증 {vol_ratio:.1f}x — 수급 유입")
            elif vol_ratio >= 1.8:
                score += 6;  signals.append(f"거래량 증가 {vol_ratio:.1f}x")

        # ── 5. MA20 지지선 근접 ──────────────────────────────────
        if ma20_v > 0:
            prox = abs(price - ma20_v) / ma20_v
            if prox <= 0.012:
                score += 6; signals.append(f"MA20 지지선 근접 ({prox:.1%} 이내)")

        score = max(0.0, min(100.0, score))

        return {
            "price":     price,
            "rsi":       round(rsi, 1),
            "bb_pos":    round(bb_pos, 3),
            "ma_cross":  ma_cross,
            "vol_ratio": round(vol_ratio, 2),
            "score":     score,
            "signals":   signals,
        }

    except Exception as e:
        log.error(f"  {ticker} 분석 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 센티먼트 가중치 보정
# ══════════════════════════════════════════════════════════════════

def _load_sentiment() -> float:
    try:
        if SENTIMENT_FILE.exists():
            data = json.loads(SENTIMENT_FILE.read_text(encoding="utf-8"))
            return float(data.get("current", {}).get("score", 50))
    except Exception:
        pass
    return 50.0


def _apply_sentiment(base: float, sent: float) -> float:
    """
    극단 공포 (<30): 역발상 매수 → +15%
    탐욕      (>65): 추세 추종   → +10%
    중립      그대로
    """
    if sent < 30:
        return min(100.0, base * 1.15)
    if sent > 65:
        return min(100.0, base * 1.10)
    return base


# ══════════════════════════════════════════════════════════════════
# 쿨다운
# ══════════════════════════════════════════════════════════════════

def _is_on_cooldown(ticker: str) -> bool:
    if not COOLDOWN_FILE.exists():
        return False
    try:
        cd = json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
        last = cd.get(ticker)
        if not last:
            return False
        elapsed_h = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
        return elapsed_h < COOLDOWN_HOURS
    except Exception:
        return False


def _set_cooldown(ticker: str):
    cd: dict = {}
    if COOLDOWN_FILE.exists():
        try:
            cd = json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    cd[ticker] = datetime.now().isoformat()
    COOLDOWN_FILE.write_text(json.dumps(cd, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 텔레그램 메시지 (aria_notify.py 와 동일한 httpx 방식)
# ══════════════════════════════════════════════════════════════════

def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("  텔레그램 설정 없음 — 콘솔 출력")
        print(text)
        return False
    try:
        url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = httpx.post(url, json={
            "chat_id":                  TELEGRAM_CHAT_ID,
            "text":                     text,
            "parse_mode":               "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        ok = resp.json().get("ok", False)
        if not ok:
            log.error(f"  텔레그램 오류: {resp.text[:150]}")
        return ok
    except Exception as e:
        log.error(f"  텔레그램 예외: {e}")
        return False


def _build_message(ticker: str, info: dict, sig: dict,
                   final: float, sent: float) -> str:
    now_str   = datetime.now(KST).strftime("%m/%d %H:%M")
    cur       = info["currency"]
    strong    = final >= STRONG_THRESHOLD
    header    = "🔥 <b>강한 매수 타점</b>" if strong else "🔵 <b>진입 검토 타점</b>"
    price_str = (f"{sig['price']:,.2f}" if info["market"] == "US"
                 else f"{sig['price']:,.0f}")

    pnl_line = ""
    if info.get("avg_cost") and info["market"] == "US":
        pnl      = (sig["price"] - info["avg_cost"]) / info["avg_cost"] * 100
        pnl_line = f"\n{'📈' if pnl >= 0 else '📉'} 내 수익률: {pnl:+.1f}% (평균단가 {cur}{info['avg_cost']})"

    sig_block = (
        "\n".join(f"  • {s}" for s in sig["signals"])
        if sig["signals"] else "  • 복합 기술적 조건 충족"
    )

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{info['name']} ({ticker})</b>\n"
        f"💰 현재가: {cur}{price_str}{pnl_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 타점 점수: <b>{final:.0f}/100</b>"
        f"  (기술 {sig['score']:.0f} × 센티먼트 {sent:.0f})\n"
        f"📊 RSI: {sig['rsi']} | 볼린저: {sig['bb_pos']:.0%}"
        f" | 거래량: {sig['vol_ratio']:.1f}x\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 감지된 신호:\n{sig_block}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ {now_str} KST | ARIA Scanner"
    )


# ══════════════════════════════════════════════════════════════════
# 로그 저장
# ══════════════════════════════════════════════════════════════════

def _save_log(results: list, alerts_sent: int):
    try:
        logs: list = []
        if LOG_FILE.exists():
            logs = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        logs.append({
            "timestamp":   datetime.now(KST).isoformat(),
            "alerts_sent": alerts_sent,
            "count":       len(results),
            "results":     results,
        })
        logs = logs[-300:]  # 최근 300건 유지 (약 20일치)
        LOG_FILE.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log.error(f"  로그 저장 실패: {e}")


# ══════════════════════════════════════════════════════════════════
# 메인 스캐너
# ══════════════════════════════════════════════════════════════════

def run_scanner() -> list:
    now_kst  = datetime.now(KST)
    us_open  = _is_us_open()
    kr_open  = _is_kr_open()
    sent_val = _load_sentiment()
    force    = os.environ.get("FORCE_SCAN", "").lower() == "true"

    log.info(f"🔍 ARIA Scanner | {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    log.info(
        f"   미국장 {'✅개장' if us_open else '❌마감'} | "
        f"한국장 {'✅개장' if kr_open else '❌마감'} | "
        f"센티먼트 {sent_val:.0f}"
    )

    results: list = []
    alerts_sent = 0

    for ticker, info in WATCHLIST.items():
        market = info["market"]

        # 장 마감 체크
        if not force:
            if market == "US" and not us_open:
                log.info(f"  {ticker}: 미국장 마감 — 스킵")
                continue
            if market == "KR" and not kr_open:
                log.info(f"  {ticker}: 한국장 마감 — 스킵")
                continue

        # 쿨다운 체크
        if _is_on_cooldown(ticker):
            log.info(f"  {ticker}: 쿨다운 중 ({COOLDOWN_HOURS}h) — 스킵")
            continue

        # 분석
        sig = analyze(ticker)
        if not sig:
            continue

        final_score = round(_apply_sentiment(sig["score"], sent_val), 1)

        row = {**sig,
               "ticker":      ticker,
               "name":        info["name"],
               "avg_cost":    info.get("avg_cost"),
               "market":      market,
               "sent_score":  sent_val,
               "final_score": final_score,
               "alerted":     False,
               "scanned_at":  now_kst.isoformat()}

        log.info(
            f"  {ticker} ({info['name']}): "
            f"점수 {final_score:.0f}  RSI {sig['rsi']}  "
            f"BB {sig['bb_pos']:.0%}  vol {sig['vol_ratio']:.1f}x  "
            f"신호 {len(sig['signals'])}개"
        )
        for s in sig["signals"]:
            log.info(f"    → {s}")

        # 알림 발송
        if final_score >= SIGNAL_THRESHOLD:
            msg = _build_message(ticker, info, sig, final_score, sent_val)
            ok  = _send_telegram(msg)
            if ok:
                _set_cooldown(ticker)
                row["alerted"] = True
                alerts_sent += 1
                log.info(f"  ✅ {ticker} 텔레그램 발송 완료 (점수 {final_score:.0f})")
        else:
            log.info(f"  — {ticker}: 임계치 미달 ({final_score:.0f} < {SIGNAL_THRESHOLD})")

        results.append(row)

    _save_log(results, alerts_sent)
    log.info(f"🔍 완료 | 분석 {len(results)}종목 | 알림 {alerts_sent}건")
    return results


if __name__ == "__main__":
    run_scanner()
