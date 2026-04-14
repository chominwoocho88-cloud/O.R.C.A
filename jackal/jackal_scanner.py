"""
jackal_scanner.py
Jackal Scanner — Claude Haiku 타점 분석 (FRED+KRX+FSC+yfinance 데이터 활용)

동작:
  1. 시장 데이터 수집 (yfinance 기술지표 + FRED 매크로 + KRX + FSC)
  2. Claude Haiku에게 종합 타점 판단 요청
  3. is_entry=True + score≥65 → 텔레그램 발송
  4. 결과를 scan_log.json 에 저장 (Evolution 자체 학습용)
"""

import os
import sys
import json
import re
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from anthropic import Anthropic

from jackal_market_data import fetch_all, fetch_technicals

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

log = logging.getLogger("jackal_scanner")

KST   = timezone(timedelta(hours=9))
_BASE = Path(__file__).parent

SCAN_LOG_FILE = _BASE / "scan_log.json"
COOLDOWN_FILE = _BASE / "scan_cooldown.json"
WEIGHTS_FILE  = _BASE / "jackal_weights.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MODEL            = os.environ.get("SUBAGENT_MODEL", "claude-haiku-4-5-20251001")

# 감시 종목
WATCHLIST = {
    "NVDA":      {"name": "엔비디아",   "avg_cost": 182.99, "market": "US", "currency": "$"},
    "AVGO":      {"name": "브로드컴",   "avg_cost": None,   "market": "US", "currency": "$"},
    "SCHD":      {"name": "SCHD",       "avg_cost": None,   "market": "US", "currency": "$"},
    "000660.KS": {"name": "SK하이닉스", "avg_cost": None,   "market": "KR", "currency": "₩"},
    "005930.KS": {"name": "삼성전자",   "avg_cost": None,   "market": "KR", "currency": "₩"},
    "035720.KS": {"name": "카카오",     "avg_cost": None,   "market": "KR", "currency": "₩"},
}

ALERT_THRESHOLD = 65
COOLDOWN_HOURS  = 4


# ══════════════════════════════════════════════════════════════════
# 시장 개장 여부
# ══════════════════════════════════════════════════════════════════

def _is_us_open() -> bool:
    from datetime import time as t
    now = datetime.now(timezone(timedelta(hours=-5)))
    return now.weekday() < 5 and t(9, 30) <= now.time() <= t(16, 0)

def _is_kr_open() -> bool:
    from datetime import time as t
    now = datetime.now(KST)
    return now.weekday() < 5 and t(9, 0) <= now.time() <= t(15, 30)


# ══════════════════════════════════════════════════════════════════
# 가중치 로드
# ══════════════════════════════════════════════════════════════════

def _load_weights() -> dict:
    try:
        if WEIGHTS_FILE.exists():
            return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


# ══════════════════════════════════════════════════════════════════
# Claude Haiku 타점 판단
# ══════════════════════════════════════════════════════════════════

def _analyze_with_claude(
    ticker: str,
    info:   dict,
    tech:   dict,
    macro:  dict,
) -> dict | None:
    """
    FRED + KRX + FSC + 기술지표를 모두 Claude에 전달해 타점 판단.
    """
    client  = Anthropic()
    weights = _load_weights()
    cur     = info["currency"]
    sent    = macro.get("sentiment", {})
    fred    = macro.get("fred", {})
    krx     = macro.get("krx", {})
    fsc     = macro.get("fsc", {})

    # 수익률 (평균단가 있을 때)
    pnl_str = ""
    if info.get("avg_cost") and info["market"] == "US":
        pnl     = (tech["price"] - info["avg_cost"]) / info["avg_cost"] * 100
        pnl_str = f"\n내 평균 매입가: {cur}{info['avg_cost']} (현재 {pnl:+.1f}%)"

    # MA50
    ma50_str = f"\nMA50: {cur}{tech['ma50']}" if tech.get("ma50") else ""

    # FRED 매크로 요약
    fred_str = ""
    if fred.get("source"):
        parts = []
        if fred.get("vix"):           parts.append(f"VIX {fred['vix']}")
        if fred.get("hy_spread"):     parts.append(f"HY스프레드 {fred['hy_spread']}%")
        if fred.get("yield_curve") is not None:
            yc = fred["yield_curve"]
            parts.append(f"장단기금리차 {yc:+.2f}% ({'침체경고' if yc < 0 else '정상'})")
        if fred.get("dxy"):           parts.append(f"달러지수 {fred['dxy']}")
        if fred.get("consumer_sent"): parts.append(f"소비자심리 {fred['consumer_sent']}")
        if parts:
            fred_str = "\n[FRED 매크로] " + " | ".join(parts)

    # KRX
    krx_str = ""
    if krx.get("source") and krx.get("kospi_close"):
        krx_str = f"\n[KRX] KOSPI {krx['kospi_close']}pt ({krx.get('kospi_change','?')}%)"

    # FSC (한국 종목일 때)
    fsc_str = ""
    if info["market"] == "KR" and fsc.get("source"):
        if ticker == "005930.KS" and fsc.get("samsung"):
            fsc_str = f"\n[FSC 공식] 삼성전자 {fsc['samsung']}원"
        elif ticker == "000660.KS" and fsc.get("sk_hynix"):
            fsc_str = f"\n[FSC 공식] SK하이닉스 {fsc['sk_hynix']}원"
        if fsc.get("gold"):
            fsc_str += f" | 금 {fsc['gold']}원/kg"

    # 가중치 힌트
    w_str = ""
    stw = weights.get("signal_type_weights", {})
    if stw:
        w_str = f"\n[Jackal 학습 가중치] 강한매수:{stw.get('강한매수',1.0):.2f} 매수검토:{stw.get('매수검토',1.0):.2f}"

    prompt = f"""당신은 주식 매수 타점 분석 전문가입니다.
아래 데이터를 종합해 지금이 매수 타점인지 판단하세요.

종목: {info['name']} ({ticker})
현재가: {cur}{tech['price']:,.2f if info['market'] == 'US' else tech['price']:,.0f} 
전일比: {tech['change_1d']:+.1f}% | 5일比: {tech['change_5d']:+.1f}%{pnl_str}

[기술 지표]
RSI(14): {tech['rsi']} | MA20: {cur}{tech['ma20']}{ma50_str}
볼린저 위치: {tech['bb_pos']}% (0%=하단, 100%=상단)
거래량: 평균 대비 {tech['vol_ratio']:.1f}x

[시장 환경]
센티먼트: {sent.get('score',50)}점 ({sent.get('level','중립')}) | 추세: {sent.get('trend','횡보')}
레짐: {sent.get('regime','')[:60] if sent.get('regime') else '정보없음'}{fred_str}{krx_str}{fsc_str}{w_str}

판단 기준:
- RSI ≤ 30: 강한 과매도 신호
- 볼린저 ≤ 10%: 하단 터치, 반등 가능
- 거래량 ≥ 2x + 가격 하락: 투매 구간 (역발상 매수)
- HY스프레드 급등: 위험회피 → 매수 자제
- 장단기금리차 음수: 침체 우려 → 보수적 접근
- VIX ≥ 30: 극단 공포 → 역발상 매수 고려

반드시 JSON만 반환. 설명 없이.
{{
  "is_entry": true 또는 false,
  "score": 0~100,
  "signal_type": "강한매수" 또는 "매수검토" 또는 "관망" 또는 "매도주의",
  "reason": "한 줄 핵심 이유 (30자 이내)",
  "entry_price": 숫자 또는 null,
  "stop_loss": 숫자 또는 null,
  "key_risk": "가장 큰 리스크 한 줄 (20자 이내)"
}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw     = resp.content[0].text
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        m       = re.search(r"\{[\s\S]*\}", cleaned)
        if not m:
            return None
        result = json.loads(m.group())
        result["is_entry"] = bool(result.get("is_entry", False))
        result["score"]    = int(result.get("score", 0))
        return result
    except Exception as e:
        log.error(f"  Claude 분석 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 쿨다운
# ══════════════════════════════════════════════════════════════════

def _is_on_cooldown(ticker: str) -> bool:
    if not COOLDOWN_FILE.exists():
        return False
    try:
        cd   = json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
        last = cd.get(ticker)
        if not last:
            return False
        return (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600 < COOLDOWN_HOURS
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
# 텔레그램
# ══════════════════════════════════════════════════════════════════

def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(text); return False
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                  "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=10,
        )
        return resp.json().get("ok", False)
    except Exception as e:
        log.error(f"  텔레그램 예외: {e}")
        return False


def _build_message(ticker: str, info: dict, tech: dict,
                   result: dict, macro: dict) -> str:
    now_str  = datetime.now(KST).strftime("%m/%d %H:%M")
    cur      = info["currency"]
    strong   = result.get("signal_type") == "강한매수"
    header   = "🔥 <b>강한 매수 타점</b>" if strong else "🔵 <b>매수 검토 타점</b>"
    price_str = f"{tech['price']:,.2f}" if info["market"] == "US" else f"{tech['price']:,.0f}"
    sent      = macro.get("sentiment", {})
    fred      = macro.get("fred", {})

    pnl_line = ""
    if info.get("avg_cost") and info["market"] == "US":
        pnl      = (tech["price"] - info["avg_cost"]) / info["avg_cost"] * 100
        pnl_line = f"\n{'📈' if pnl >= 0 else '📉'} 내 수익률: {pnl:+.1f}%"

    entry = result.get("entry_price")
    stop  = result.get("stop_loss")
    entry_line = f"\n🎯 진입가: {cur}{entry:,.0f}" if entry else ""
    stop_line  = f"\n🛑 손절가: {cur}{stop:,.0f}" if stop else ""
    risk_line  = f"\n⚡ 리스크: {result.get('key_risk','')}" if result.get("key_risk") else ""

    # FRED 핵심 지표
    fred_line = ""
    if fred.get("source"):
        parts = []
        if fred.get("vix"):       parts.append(f"VIX {fred['vix']}")
        if fred.get("hy_spread"): parts.append(f"HY {fred['hy_spread']}%")
        if fred.get("yield_curve") is not None:
            parts.append(f"금리차 {fred['yield_curve']:+.2f}%")
        if parts:
            fred_line = "\n📈 " + " | ".join(parts)

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{info['name']} ({ticker})</b>\n"
        f"💰 {cur}{price_str} ({tech['change_1d']:+.1f}%){pnl_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Jackal 점수: <b>{result['score']}/100</b>\n"
        f"📊 RSI {tech['rsi']} | BB {tech['bb_pos']}% | 거래량 {tech['vol_ratio']:.1f}x\n"
        f"💡 {result.get('reason','')}{entry_line}{stop_line}{risk_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"😐 센티먼트: {sent.get('score',50)}점 ({sent.get('level','중립')}){fred_line}\n"
        f"⏰ {now_str} KST | Jackal"
    )


# ══════════════════════════════════════════════════════════════════
# 스캔 로그
# ══════════════════════════════════════════════════════════════════

def _save_log(entry: dict):
    logs: list = []
    if SCAN_LOG_FILE.exists():
        try:
            logs = json.loads(SCAN_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    logs.append(entry)
    logs = logs[-500:]
    SCAN_LOG_FILE.write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 메인 스캔
# ══════════════════════════════════════════════════════════════════

def run_scan(force: bool = False) -> dict:
    now_kst = datetime.now(KST)
    us_open = _is_us_open()
    kr_open = _is_kr_open()

    log.info(f"📡 Jackal Scanner | {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    log.info(f"   미국장 {'✅' if us_open else '❌'} | 한국장 {'✅' if kr_open else '❌'}")

    # 공통 매크로 데이터 (1회 수집 → 모든 종목에 공유)
    macro = fetch_all()

    scanned = 0
    alerted = 0
    results: list = []

    for ticker, info in WATCHLIST.items():
        market = info["market"]

        if not force:
            if market == "US" and not us_open:
                continue
            if market == "KR" and not kr_open:
                continue

        if _is_on_cooldown(ticker):
            log.info(f"  {ticker}: 쿨다운 — 스킵")
            continue

        # 기술 지표
        tech = fetch_technicals(ticker)
        if not tech:
            continue

        log.info(
            f"  {ticker} ({info['name']}): "
            f"RSI={tech['rsi']} BB={tech['bb_pos']}% vol={tech['vol_ratio']:.1f}x"
        )

        # Claude 타점 판단 (FRED+KRX+FSC+기술지표 전달)
        result = _analyze_with_claude(ticker, info, tech, macro)
        if not result:
            continue

        scanned += 1
        results.append({"ticker": ticker, "name": info["name"],
                        "claude_score": result.get("score", 0),
                        "signal_type": result.get("signal_type", "관망"),
                        "rsi": tech["rsi"]})
        log.info(
            f"    → {result.get('signal_type','?')} | "
            f"점수 {result.get('score',0)} | {result.get('reason','')}"
        )

        # 알림 발송
        do_alert = result.get("is_entry", False) and result.get("score", 0) >= ALERT_THRESHOLD
        if do_alert:
            msg = _build_message(ticker, info, tech, result, macro)
            ok  = _send_telegram(msg)
            if ok:
                _set_cooldown(ticker)
                alerted += 1
                log.info(f"    ✅ 텔레그램 발송 완료")

        # 로그 저장 (Evolution 학습용)
        _save_log({
            "timestamp":       now_kst.isoformat(),
            "ticker":          ticker,
            "name":            info["name"],
            "market":          market,
            "price_at_scan":   tech["price"],
            "rsi":             tech["rsi"],
            "bb_pos":          tech["bb_pos"],
            "vol_ratio":       tech["vol_ratio"],
            "vix":             macro["fred"].get("vix"),
            "hy_spread":       macro["fred"].get("hy_spread"),
            "yield_curve":     macro["fred"].get("yield_curve"),
            "sent_score":      macro["sentiment"].get("score"),
            "claude_score":    result.get("score", 0),
            "signal_type":     result.get("signal_type", ""),
            "is_entry":        result.get("is_entry", False),
            "reason":          result.get("reason", ""),
            "key_risk":        result.get("key_risk", ""),
            "alerted":         do_alert,
            "outcome_checked": False,
            "outcome_price":   None,
            "outcome_pct":     None,
            "outcome_correct": None,
        })

    log.info(f"📡 완료 | 분석 {scanned}종목 | 알림 {alerted}건")

    # 장이 열려있는데 타점 없으면 결과 요약 발송
    any_market_open = (us_open or kr_open) or force
    if any_market_open and alerted == 0 and scanned > 0:
        now_str  = datetime.now(KST).strftime("%m/%d %H:%M")
        sent     = macro.get("sentiment", {})
        fred     = macro.get("fred", {})
        lines    = ["📊 <b>Jackal 스캔 완료 — 타점 없음</b>",
                    "━━━━━━━━━━━━━━━━━━━━"]
        for r in results:
            sig  = r.get("signal_type", "관망")
            icon = {"강한매수": "🔴", "매수검토": "🟡", "관망": "⚪", "매도주의": "🔵"}.get(sig, "⚪")
            lines.append(f"{icon} {r['name']} ({r['ticker']}): {r['claude_score']}점 | RSI {r['rsi']} | {sig}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        fred_parts = []
        if fred.get("vix"):         fred_parts.append(f"VIX {fred['vix']}")
        if fred.get("hy_spread"):   fred_parts.append(f"HY {fred['hy_spread']}%")
        if fred.get("yield_curve") is not None:
            fred_parts.append(f"금리차 {fred['yield_curve']:+.2f}%")
        if fred_parts:
            lines.append("📈 " + " | ".join(fred_parts))
        lines.append(f"😐 센티먼트: {sent.get('score', 50)}점 ({sent.get('level', '중립')})")
        lines.append(f"⏰ {now_str} KST | Jackal")
        _send_telegram("
".join(lines))

    return {"scanned": scanned, "alerted": alerted}
