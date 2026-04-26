"""
JACKAL scanner module.
Jackal Scanner — Analyst → Devil → Final 3단계 타점 분석

흐름:
  1. 데이터 수집 (yfinance + FRED + KRX + FSC + ARIA 파일)
  2. Analyst (Haiku): 매수 근거 구성
  3. Devil   (Haiku): Analyst 반박 + ARIA Thesis Killer 체크
  4. Final   판단:
       둘 다 매수  → 강한 신호 (가중 합산)
       엇갈림      → 점수 낮춤
       둘 다 반대  → 알림 없음
  5. 결과 저장 (Evolution 학습용 — 신호·레짐·Devil 정확도 포함)
"""

import os
import sys
import json
import re
import logging
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from anthropic import Anthropic

from orca.paths import DATA_FILE, atomic_write_json
from orca.state import (
    list_jackal_recommendations,
    list_candidates,
    load_jackal_cooldown_state,
    load_latest_jackal_weight_snapshot,
    record_jackal_shadow_signal,
    sync_jackal_cooldown_state,
    sync_jackal_live_events,
    sync_jackal_recommendations,
)
from .explanation import (
    build_scanner_explanation_lines,
    build_scanner_peak_line,
    build_scanner_reason_payload,
    select_scanner_swing_info,
)
from .families import canonical_family_key, family_label
from .market_data import fetch_all, fetch_technicals
from .probability import apply_probability_adjustment, load_probability_summary
from .quality_engine import (
    ALERT_THRESHOLD,
    STRONG_THRESHOLD,
    _calc_signal_quality_core,
    _final_judgment,
    _get_signal_family,
    _get_signal_family_key,
    detect_pre_rule_signals,
)
from .thresholds import THRESHOLDS

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

log = logging.getLogger("jackal_scanner")

KST   = timezone(timedelta(hours=9))
_BASE = Path(__file__).parent
_DATA_DIR = _BASE.parent / "data"

SCAN_LOG_FILE      = _BASE / "scan_log.json"
COOLDOWN_FILE      = _BASE / "scan_cooldown.json"
WEIGHTS_FILE       = _BASE / "jackal_weights.json"
RECOMMEND_LOG_FILE = _BASE / "recommendation_log.json"
JACKAL_WATCHLIST   = _DATA_DIR / "jackal_watchlist.json"   # ORCA가 읽음
JACKAL_NEWS_FILE   = _DATA_DIR / "jackal_news.json"        # ORCA가 씀, JACKAL이 읽음
# ARIA 데이터 파일 (읽기만, 의존성 없음)
ORCA_BASELINE  = _DATA_DIR / "morning_baseline.json"
ORCA_SENTIMENT = _DATA_DIR / "sentiment.json"
ORCA_ROTATION  = _DATA_DIR / "rotation.json"
PORTFOLIO_FILE = _DATA_DIR / "portfolio.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MODEL_H          = os.environ.get("SUBAGENT_MODEL", "claude-haiku-4-5-20251001")

_SCANNER = THRESHOLDS["scanner"]
_SCANNER_COOLDOWN = _SCANNER["cooldown"]
_SCANNER_SCHD = _SCANNER["schd_regime"]
_SCANNER_ANALYST_HINT = _SCANNER["analyst_hint"]
_SCANNER_SIGNAL_RELABEL = _SCANNER["signal_relabel"]


def _load_portfolio() -> dict:
    """
    data/portfolio.json 에서 포트폴리오 로드.
    ticker_yf (yfinance 형식) 키로 딕셔너리 구성.
    현금 등 ticker_yf 없는 항목은 스캔 제외.
    """
    # 기본값 — portfolio.json 없을 때 사용, asset_type 포함
    default = {
        "NVDA":      {"name": "엔비디아",   "avg_cost": 182.99, "market": "US", "currency": "$", "portfolio": True, "asset_type": "stock"},
        "AVGO":      {"name": "브로드컴",   "avg_cost": None,   "market": "US", "currency": "$", "portfolio": True, "asset_type": "stock"},
        # SCHD는 etf_broad_dividend → 기본값도 스캔 제외 반영
        "000660.KS": {"name": "SK하이닉스", "avg_cost": None,   "market": "KR", "currency": "₩", "portfolio": True, "asset_type": "stock"},
        "005930.KS": {"name": "삼성전자",   "avg_cost": None,   "market": "KR", "currency": "₩", "portfolio": True, "asset_type": "stock"},
        "035720.KS": {"name": "카카오",     "avg_cost": None,   "market": "KR", "currency": "₩", "portfolio": True, "asset_type": "stock"},
    }
    if not PORTFOLIO_FILE.exists():
        return default
    try:
        data   = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        result = {}
        for h in data.get("holdings", []):
            yf_ticker = h.get("ticker_yf")
            if not yf_ticker:          # 현금 등 yfinance 없는 항목 제외
                continue
            # jackal_scan: false → 스캔 제외 (배당형 ETF 등)
            if h.get("jackal_scan", True) is False:
                log.info(f"   {yf_ticker} 스캔 제외 (jackal_scan=false)")
                continue
            market     = h.get("market", "US")
            asset_type = h.get("asset_type", "stock")

            # asset_type 기반 jackal_scan 기본값 결정
            # etf_broad_dividend → 구조적으로 기술지표 미적합 → 기본 false
            # 명시된 jackal_scan 필드가 있으면 그것이 우선
            if "jackal_scan" not in h:
                default_scan = asset_type not in ("etf_broad_dividend", "cash")
            else:
                default_scan = h["jackal_scan"]

            if not default_scan:
                log.info(f"   {yf_ticker} 스캔 제외 (asset_type={asset_type})")
                continue

            result[yf_ticker] = {
                "name":       h.get("name", yf_ticker),
                "avg_cost":   h.get("avg_cost"),
                "market":     market,
                "currency":   h.get("currency", "$" if market == "US" else "₩"),
                "portfolio":  True,
                "asset_type": asset_type,
            }
        return result if result else default
    except Exception as e:
        log.warning(f"portfolio.json 로드 실패: {e} — 기본값 사용")
        return default


def _load_candidate_watchlist(*, max_age_days: int = 7, limit: int = 20) -> dict:
    """
    ORCA candidate registry의 최근 JACKAL 후보를 스캔 watchlist로 승격.
    portfolio가 비어 있어도 Scanner가 학습 후보를 다시 점검할 수 있게 한다.
    """
    now = datetime.now(KST)
    watchlist: dict[str, dict] = {}
    try:
        candidates = list_candidates(source_system="jackal", unresolved_only=True, limit=max(limit * 3, 30))
    except Exception as exc:
        log.warning(f"candidate watchlist 로드 실패: {exc}")
        return {}

    for candidate in candidates:
        ticker = str(candidate.get("ticker", "")).strip()
        if not ticker:
            continue
        source_type = str(candidate.get("source_event_type", "")).strip().lower()
        if source_type not in {"hunt", "shadow", "scan"}:
            continue
        detected_at = str(candidate.get("detected_at", "")).strip()
        try:
            dt = datetime.fromisoformat(detected_at) if detected_at else None
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            if dt and (now - dt.astimezone(KST)) > timedelta(days=max_age_days):
                continue
        except Exception:
            pass

        payload = candidate.get("payload", {}) or {}
        market = str(candidate.get("market") or payload.get("market") or ("KR" if ticker.endswith(".KS") else "US"))
        watchlist[ticker] = {
            "name": candidate.get("name") or payload.get("name") or ticker,
            "avg_cost": None,
            "market": market,
            "currency": payload.get("currency") or ("₩" if market == "KR" else "$"),
            "portfolio": False,
            "source": f"candidate:{source_type}",
            "reason": payload.get("reason") or payload.get("orca_reason") or candidate.get("signal_family", ""),
            "candidate_id": candidate.get("candidate_id"),
        }
        if len(watchlist) >= limit:
            break
    return watchlist


def _load_recommendation_watchlist(*, max_age_hours: int = 72, limit: int = 20) -> dict:
    """
    최근 recommendation log를 watchlist로 재사용.
    Scanner가 ORCA 추천 종목을 같은 세션/다음 세션에서 다시 검토할 수 있게 한다.
    """
    now = datetime.now(KST)
    watchlist: dict[str, dict] = {}
    for entry in reversed(_load_recommendation_log()):
        ticker = str(entry.get("ticker", "")).strip()
        if not ticker or ticker in watchlist:
            continue
        ts = str(entry.get("recommended_at", "")).strip()
        try:
            dt = datetime.fromisoformat(ts) if ts else None
            if dt and dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            if dt and (now - dt.astimezone(KST)) > timedelta(hours=max_age_hours):
                continue
        except Exception:
            pass

        market = str(entry.get("market") or ("KR" if ticker.endswith(".KS") else "US"))
        watchlist[ticker] = {
            "name": entry.get("name", ticker),
            "avg_cost": None,
            "market": market,
            "currency": entry.get("currency") or ("₩" if market == "KR" else "$"),
            "portfolio": False,
            "source": "recommendation_log",
            "reason": entry.get("reason", ""),
        }
        if len(watchlist) >= limit:
            break
    return watchlist


def _merge_watchlists(*sources: dict) -> dict:
    merged: dict[str, dict] = {}
    for source in sources:
        for ticker, info in (source or {}).items():
            if ticker not in merged:
                merged[ticker] = dict(info)
            else:
                merged[ticker].update({k: v for k, v in info.items() if v not in (None, "", [])})
                merged[ticker]["portfolio"] = bool(merged[ticker].get("portfolio")) or bool(info.get("portfolio"))
    return merged


def _save_watchlist_snapshot(watchlist: dict) -> None:
    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "tickers": list(watchlist.keys()),
        "details": watchlist,
        "counts": {
            "total": len(watchlist),
            "portfolio": sum(1 for info in watchlist.values() if info.get("portfolio")),
            "candidate": sum(1 for info in watchlist.values() if str(info.get("source", "")).startswith("candidate:")),
            "recommendation": sum(1 for info in watchlist.values() if info.get("source") == "recommendation_log"),
        },
    }
    atomic_write_json(JACKAL_WATCHLIST, payload)

COOLDOWN_HOURS  = _SCANNER_COOLDOWN["hours"]


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
# ARIA 컨텍스트 로딩 (파일 읽기만)
# ══════════════════════════════════════════════════════════════════

def _load_orca_context() -> dict:
    """
    ARIA가 생성한 파일들을 읽어 시장 맥락 구성.
    파일 없으면 빈 값 반환 — ARIA에 의존하지 않음.
    """
    ctx = {
        "regime":        "",
        "trend":         "",
        "confidence":    "",
        "one_line":      "",
        "thesis_killers": [],
        "key_inflows":   [],
        "key_outflows":  [],
        "sentiment_score": 50,
        "sentiment_level": "중립",
        "top_sector":    "",
        "bottom_sector": "",
    }

    # morning_baseline.json
    try:
        if ORCA_BASELINE.exists():
            b = json.loads(ORCA_BASELINE.read_text(encoding="utf-8"))
            ctx["regime"]     = b.get("market_regime", "")
            ctx["trend"]      = b.get("trend_phase", "")
            ctx["confidence"] = b.get("confidence", "")
            ctx["one_line"]   = b.get("one_line_summary", "")
            ctx["thesis_killers"] = b.get("thesis_killers", [])
            ctx["key_inflows"]    = [i.get("zone","") for i in b.get("key_inflows", [])[:3]]
            ctx["key_outflows"]   = [o.get("zone","") for o in b.get("key_outflows", [])[:3]]
    except Exception:
        pass

    # sentiment.json
    try:
        if ORCA_SENTIMENT.exists():
            s = json.loads(ORCA_SENTIMENT.read_text(encoding="utf-8"))
            cur = s.get("current", {})
            ctx["sentiment_score"] = cur.get("score", 50)
            ctx["sentiment_level"] = cur.get("level", "중립")
    except Exception:
        pass

    # rotation.json
    try:
        if ORCA_ROTATION.exists():
            r = json.loads(ORCA_ROTATION.read_text(encoding="utf-8"))
            ranking = r.get("ranking", [])
            if ranking:
                ctx["top_sector"]    = ranking[0][0] if ranking else ""
                ctx["bottom_sector"] = ranking[-1][0] if ranking else ""
            sig = r.get("rotation_signal", {})
            ctx["rotation_from"] = sig.get("from", "")
            ctx["rotation_to"]   = sig.get("to", "")
    except Exception:
        pass

    return ctx


def _load_weights() -> dict:
    snapshot = load_latest_jackal_weight_snapshot()
    if isinstance(snapshot, dict):
        return snapshot
    try:
        if WEIGHTS_FILE.exists():
            return json.loads(WEIGHTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _load_cooldown_state() -> dict:
    state = load_jackal_cooldown_state()
    if state:
        return state
    try:
        if COOLDOWN_FILE.exists():
            return json.loads(COOLDOWN_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cooldown_state(state: dict) -> None:
    atomic_write_json(COOLDOWN_FILE, state)
    sync_jackal_cooldown_state(state)


def _load_recommendation_log() -> list[dict]:
    logs = list_jackal_recommendations(limit=200)
    if logs:
        return logs
    try:
        if RECOMMEND_LOG_FILE.exists():
            return json.loads(RECOMMEND_LOG_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def _save_recommendation_log(logs: list[dict]) -> None:
    atomic_write_json(RECOMMEND_LOG_FILE, logs)
    sync_jackal_recommendations(logs)


# ══════════════════════════════════════════════════════════════════
# Agent 1: Analyst — 매수 근거 구성
# ══════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════
# 신호 품질 사전 평가 (백테스트 기반, Claude 호출 전 실행)
# ══════════════════════════════════════════════════════════════════

# 규칙 레지스트리 — 도입 근거/검토 기준 명시 (Doc3: 규칙 폐기 조건)
_RULE_REGISTRY = {
    # 각 규칙에 min_accuracy 추가 — 해당 건수 이상에서 정확도 미달 시 자동 비활성화
    # Evolution Engine이 이 메타데이터를 읽어 규칙 상태를 평가
    "sector_rebound_base":   {
        "introduced": "2026-04", "basis": "backtest 93.1%",
        "review_after_n": 50,  "min_accuracy": 0.75, "active": True,
    },
    "volume_climax_base":    {
        "introduced": "2026-04", "basis": "backtest 80.0%",
        "review_after_n": 20,  "min_accuracy": 0.65, "active": True,
    },
    "ma_support_solo_pen":   {
        "introduced": "2026-04", "basis": "backtest 55.6% → 단독 차단",
        "review_after_n": 30,  "min_accuracy": None, "active": True,  # 페널티라 정확도 기준 없음
    },
    "rebound_cap":           {
        "introduced": "2026-04", "basis": "anti-stacking",
        "review_after_n": 50,  "min_accuracy": None, "active": True,
    },
    "crash_rebound_pattern": {
        "introduced": "2026-04", "basis": "3/31~4/8 검증",
        "review_after_n": 30,  "min_accuracy": 0.70, "active": True,
    },
    "vix_gating":            {
        "introduced": "2026-04", "basis": "ARIA중복방지",
        "review_after_n": 20,  "min_accuracy": None, "active": True,
    },
    "heuristic_gate":        {
        "introduced": "2026-04", "basis": "이벤트-데이 품질 하락",
        "review_after_n": 30,  "min_accuracy": None, "active": True,
    },
}


def _check_rule_auto_disable(rule_name: str, recent_accuracy: float, sample_n: int) -> bool:
    """
    규칙 자동 폐기 검사.
    min_accuracy 미달 + review_after_n 이상 샘플 → active=False 권고 반환.
    실제 비활성화는 Evolution Engine이 담당.
    """
    rule = _RULE_REGISTRY.get(rule_name, {})
    if not rule.get("active", True):
        return False   # 이미 비활성
    min_acc = rule.get("min_accuracy")
    review_n = rule.get("review_after_n", 50)
    if min_acc is None or sample_n < review_n:
        return False   # 기준 없음 or 샘플 부족
    if recent_accuracy < min_acc:
        log.warning(
            f"  ⚠️ RULE AUTO-DISABLE 권고: {rule_name} "
            f"정확도 {recent_accuracy:.1%} < 기준 {min_acc:.1%} "
            f"(n={sample_n}/{review_n})"
        )
        return True    # Evolution이 처리하도록 True 반환
    return False

# ── signal_family 분류 테이블 ────────────────────────────────────
# Doc1 반박: 분류 기준이 코드에 없으면 새 신호 추가 시 일관성 깨짐
# 규칙: rebound 계열 신호가 1개라도 있으면 crash_rebound family
def _load_schd_regime_signal() -> float:
    """
    SCHD는 Jackal 스캔 제외(jackal_scan:false) 유지.
    방어 자산 레짐 지표로만 활용 — 5일 -3% 이하 시 전체 confidence -5.
    Doc7/9 부분 수용: 기각 유지 + 새 용도 추가, 충돌 없음.
    """
    try:
        from orca.market_fetch import fetch_daily_history

        end = (datetime.now(KST) + timedelta(days=1)).date().isoformat()
        start = (datetime.now(KST) - timedelta(days=int(_SCANNER_SCHD["period_days"]) * 2)).date().isoformat()
        df = fetch_daily_history("SCHD", start, end)
        if df is None:
            return 0.0
        if df.empty or len(df) < _SCANNER_SCHD["min_rows"]:
            return 0.0
        change_5d = (
            (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[-_SCANNER_SCHD["lookback_index"]]))
            / float(df["Close"].iloc[-_SCANNER_SCHD["lookback_index"]])
            * 100
        )
        if change_5d < _SCANNER_SCHD["drop_threshold"]:
            log.info(f"  ⚠️ SCHD 5일 {change_5d:.1f}% 하락 → 레짐 지표 -5")
            return _SCANNER_SCHD["confidence_penalty"]
        return 0.0
    except Exception:
        return 0.0


def _load_pcr_from_aria() -> float:
    """ARIA가 수집한 PCR(Put/Call Ratio) 로드 — Jackal 품질 평가에 활용."""
    try:
        from pathlib import Path
        import json
        cache = DATA_FILE
        if not cache.exists():
            return 0.0
        md = json.loads(cache.read_text(encoding="utf-8"))
        # ARIA 수집 구조: prices.pcr_avg 또는 put_call.avg
        pcr = (
            md.get("prices", {}).get("pcr_avg")
            or md.get("put_call", {}).get("avg")
            or md.get("pcr_avg")
        )
        return float(pcr) if pcr else 0.0
    except Exception:
        return 0.0


def _get_vix_from_cache() -> float:
    """ARIA가 수집한 시장 데이터에서 VIX 추출."""
    try:
        from pathlib import Path
        import json
        cache = DATA_FILE
        if cache.exists():
            md = json.loads(cache.read_text(encoding="utf-8"))
            return float(
                md.get("fred", {}).get("vixcls", 0)
                or md.get("prices", {}).get("^VIX", {}).get("price", 0)
                or 0
            )
    except Exception:
        pass
    return 0.0


def _calc_signal_quality(signals: list, tech: dict, aria: dict,
                          ticker: str = "", weights: dict = None) -> dict:
    """Existing scanner adapter that loads cached market context for the pure core."""
    if weights is None:
        weights = {}

    pcr_avg = _load_pcr_from_aria()
    cached_vix = _get_vix_from_cache()
    hy_spread = 0.0
    try:
        market_data = json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}
        hy_spread = float(
            market_data.get("fred", {}).get("bamlh0a0hym2", 0)
            or market_data.get("fred", {}).get("hy_spread", 0)
            or 0
        )
    except Exception:
        pass

    return _calc_signal_quality_core(
        signals,
        tech,
        aria,
        ticker=ticker,
        weights=weights,
        pcr_avg=pcr_avg,
        cached_vix=cached_vix,
        hy_spread=hy_spread,
    )



def agent_analyst(ticker: str, info: dict, tech: dict,
                  macro: dict, aria: dict) -> dict:
    """
    Haiku로 매수 근거를 구성.
    Returns: {score, signals_fired, reasoning, confidence}
    """
    cur     = info["currency"]
    fred    = macro.get("fred", {})
    weights = _load_weights()
    stw     = weights.get("signal_weights", {})

    price_str = f"{tech['price']:,.2f}" if info["market"] == "US" else f"{tech['price']:,.0f}"
    pnl_str = ""
    if info.get("avg_cost") and info["market"] == "US":
        pnl     = (tech["price"] - info["avg_cost"]) / info["avg_cost"] * 100
        pnl_str = f"\n내 평균단가: {cur}{info['avg_cost']} (현재 {pnl:+.1f}%)"

    # 학습된 신호별 정확도 힌트
    acc_hint = ""
    sig_acc = weights.get("signal_accuracy", {})
    if sig_acc:
        top = sorted(sig_acc.items(), key=lambda x: x[1].get("accuracy", 0), reverse=True)[:3]
        acc_hint = "\n[학습 정확도 높은 신호] " + " | ".join(
            f"{k}:{v['accuracy']:.0f}%" for k, v in top if v.get("total", 0) >= _SCANNER_ANALYST_HINT["min_accuracy_samples"]
        )

    # 신호 품질 컨텍스트 (백테스트 기반 사전 평가)
    quality = info.get("_quality", {})
    quality_hint = ""
    if quality:
        q_score = quality.get("quality_score", 50)
        q_label = quality.get("quality_label", "")
        q_reasons = ", ".join(quality.get("reasons", []))
        quality_hint = (
            f"\n[신호 품질 사전평가] {q_score}점 ({q_label})"
            f"\n  근거: {q_reasons}"
        )

    prompt = f"""당신은 주식 매수 타점 분석가(Analyst)입니다.
아래 데이터로 {info['name']} ({ticker})의 매수 근거를 분석하세요.
반드시 JSON만 반환하세요.

[종목]
현재가: {cur}{price_str}
전일比: {tech['change_1d']:+.1f}% | 5일比: {tech['change_5d']:+.1f}%{pnl_str}

[기술 지표]
RSI(14): {tech['rsi']} | MA20: {cur}{tech['ma20']} | MA50: {cur}{tech.get('ma50','N/A')}
볼린저: {tech['bb_pos']}% (0%=하단, 100%=상단) | BB폭: {tech.get('bb_width','N/A')}%
거래량: 평균 대비 {tech['vol_ratio']:.1f}x | 5일거래량추세: {tech.get('vol_trend_5d','N/A')}%
MA배열: {tech.get('ma_alignment','N/A')} | 52주위치: {tech.get('52w_pos','N/A')}%
RSI다이버전스: {'✅ 강세' if tech.get('rsi_divergence') else '없음'} | 매집신호: {'✅' if tech.get('vol_accumulation') else '없음'}

[매크로 (FRED)]
VIX: {fred.get('vix','N/A')} | HY스프레드: {fred.get('hy_spread','N/A')}%
장단기금리차: {fred.get('yield_curve','N/A')}% | 달러지수: {fred.get('dxy','N/A')}
소비자심리: {fred.get('consumer_sent','N/A')}

[ARIA 시장 맥락]
레짐: {aria['regime'] or '정보없음'} | 추세: {aria['trend'] or '정보없음'}
센티먼트: {aria['sentiment_score']}점 ({aria['sentiment_level']})
섹터유입: {', '.join(aria['key_inflows']) or '없음'}
섹터유출: {', '.join(aria['key_outflows']) or '없음'}
강세섹터: {aria.get('top_sector','N/A')} | 약세섹터: {aria.get('bottom_sector','N/A')}
{acc_hint}{quality_hint}

매수 근거가 있다면 높은 점수, 없다면 낮은 점수를 주세요.
신호 품질이 "최강/강"이면 낙관적으로, "약"이면 보수적으로 평가하세요.

{{
  "analyst_score": 0~100,
  "confidence": "낮음" 또는 "보통" 또는 "높음",
  "signals_fired": ["rsi_oversold", "bb_touch", "volume_surge", "ma_support", "golden_cross", "fear_regime", "sector_inflow"],
  "bull_case": "매수 근거 2~3줄",
  "entry_price": 숫자 또는 null,
  "stop_loss": 숫자 또는 null
}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw  = re.sub(r"```(?:json)?|```", "", resp.content[0].text).strip()
        m    = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"analyst_score": 50, "confidence": "낮음",
                    "signals_fired": [], "bull_case": "분석 실패"}
        result = json.loads(m.group())
        base = int(result.get("analyst_score", 50))
        # 신호 품질 보정 적용
        adj = info.get("_quality", {}).get("analyst_adj", 0) if info else 0
        result["analyst_score"] = max(0, min(100, base + adj))
        if adj != 0:
            result["_quality_adj_applied"] = adj
        return result
    except Exception as e:
        log.error(f"  Analyst 실패: {e}")
        return {"analyst_score": 50, "confidence": "낮음",
                "signals_fired": [], "bull_case": "분석 실패"}


# ══════════════════════════════════════════════════════════════════
# Agent 2: Devil — 반박 + Thesis Killer 체크
# ══════════════════════════════════════════════════════════════════

def agent_devil(ticker: str, info: dict, tech: dict,
                macro: dict, aria: dict, analyst: dict) -> dict:
    """
    Haiku로 Analyst 결론을 반박.
    ARIA의 Thesis Killer를 직접 체크.
    Returns: {devil_score, verdict, objections, thesis_killer_hit}
    """
    cur  = info["currency"]
    fred = macro.get("fred", {})

    price_str = f"{tech['price']:,.2f}" if info["market"] == "US" else f"{tech['price']:,.0f}"

    # Thesis Killer 텍스트 구성
    tk_text = ""
    tks = aria.get("thesis_killers", [])
    if tks:
        tk_lines = []
        for tk in tks[:3]:
            event = tk.get("event", "")
            inv   = tk.get("invalidates_if", "")
            if event and inv:
                tk_lines.append(f"  • {event}: {inv}")
        if tk_lines:
            tk_text = "\n[ARIA Thesis Killers — 이 조건이면 매수 무효]\n" + "\n".join(tk_lines)

    prompt = f"""당신은 투자 리스크 분석가(Devil)입니다.
Analyst가 {info['name']} ({ticker}) 매수를 주장합니다.
당신은 반드시 반박해야 합니다. JSON만 반환하세요.

[Analyst 결론]
점수: {analyst['analyst_score']} | 신뢰도: {analyst['confidence']}
근거: {analyst.get('bull_case','')}
발동 신호: {', '.join(analyst.get('signals_fired', []))}

[현재 상황]
현재가: {cur}{price_str}
RSI: {tech['rsi']} | 볼린저: {tech['bb_pos']}% | 거래량: {tech['vol_ratio']:.1f}x
VIX: {fred.get('vix','N/A')} | HY스프레드: {fred.get('hy_spread','N/A')}%
장단기금리차: {fred.get('yield_curve','N/A')}%

[ARIA 시장 맥락]
레짐: {aria['regime'] or '정보없음'} | 센티먼트: {aria['sentiment_score']}점
유출섹터: {', '.join(aria['key_outflows']) or '없음'}
{tk_text}

반박 기준:
- VIX > 25이면 변동성 과대
- HY스프레드 > 4%이면 위험회피 강화
- 레짐이 위험회피이면 매수 부적절
- Thesis Killer 조건 해당이면 즉시 무효
- 연속 3일+ 상승이면 과열 경고

{{
  "devil_score": 0~100 (높을수록 반박 강함, 매수 부적절),
  "verdict": "동의" 또는 "부분동의" 또는 "반대",
  "objections": ["반박 이유 1", "반박 이유 2"],
  "thesis_killer_hit": true 또는 false,
  "killer_detail": "해당 Thesis Killer 내용 (없으면 빈 문자열)",
  "bear_case": "매수 반대 근거 1~2줄"
}}"""

    raw = ""
    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        raw  = re.sub(r"```(?:json)?|```", "", resp.content[0].text).strip()
        m    = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return _with_scanner_devil_metadata(
                {
                    "devil_score": 30,
                    "verdict": "부분동의",
                    "objections": [],
                    "thesis_killer_hit": False,
                    "killer_detail": "",
                    "bear_case": "",
                },
                called=True,
                parse_ok=False,
                status="parse_failed",
                raw_excerpt=raw,
            )
        result = json.loads(m.group())
        return _with_scanner_devil_metadata(
            result,
            called=True,
            parse_ok=True,
            status="ok_with_objection" if _first_scanner_objection(result) else "no_material_objection",
        )
    except json.JSONDecodeError:
        return _with_scanner_devil_metadata(
            {
                "devil_score": 30,
                "verdict": "부분동의",
                "objections": [],
                "thesis_killer_hit": False,
                "killer_detail": "",
                "bear_case": "",
            },
            called=True,
            parse_ok=False,
            status="parse_failed",
            raw_excerpt=raw,
        )
    except Exception as e:
        log.error(f"  Devil 실패: {e}")
        return _with_scanner_devil_metadata(
            {
                "devil_score": 30,
                "verdict": "부분동의",
                "objections": [],
                "thesis_killer_hit": False,
                "killer_detail": "",
                "bear_case": "",
            },
            called=True,
            parse_ok=False,
            status="api_error",
            raw_excerpt=raw,
        )


def _trim_devil_raw_excerpt(text: str | None, limit: int = 200) -> str | None:
    if not text:
        return None
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if not cleaned:
        return None
    return cleaned[:limit]


def _first_scanner_objection(devil: dict) -> str:
    for objection in devil.get("objections", []) or []:
        text = str(objection or "").strip()
        if text:
            return text
    return ""


def _resolve_scanner_devil_status(devil: dict) -> str:
    status = str(devil.get("devil_status", "") or "").strip()
    if status:
        return status
    if devil.get("devil_called") is False:
        return "skipped_quality_gate"
    if _first_scanner_objection(devil):
        return "ok_with_objection"
    if devil:
        return "no_material_objection"
    return "unknown"


def _scanner_devil_render_mode(status: str) -> str:
    if status == "ok_with_objection":
        return "full"
    if status == "skipped_quality_gate":
        return "hidden"
    return "label_only"


def _with_scanner_devil_metadata(
    devil: dict,
    *,
    called: bool,
    parse_ok: bool,
    status: str,
    raw_excerpt: str | None = None,
) -> dict:
    result = dict(devil)
    result["devil_score"] = int(result.get("devil_score", 30))
    result.setdefault("verdict", "부분동의")
    result.setdefault("objections", [])
    result.setdefault("thesis_killer_hit", False)
    result.setdefault("killer_detail", "")
    result.setdefault("bear_case", "")
    result["devil_called"] = called
    result["devil_parse_ok"] = parse_ok
    result["devil_status"] = status
    result["devil_raw_excerpt"] = _trim_devil_raw_excerpt(raw_excerpt)
    result["devil_render_mode"] = _scanner_devil_render_mode(status)
    return result


# ══════════════════════════════════════════════════════════════════
# Final 판단
# ══════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════
# 쿨다운
# ══════════════════════════════════════════════════════════════════



def _is_on_cooldown(ticker: str, signals: list = None,
                    quality_score: float = 0,
                    vol_ratio: float = 0,
                    change_1d: float = 0) -> bool:
    """
    ticker + signal_family 기반 쿨다운 확인.
    쿨다운 override 조건 (Doc3 제안, 사이드이펙트 방어 포함):
      - quality_score가 이전 발동보다 +15 이상 급상승
      - AND vol_ratio > 2.5 (거래량 급등)
      - AND change_1d < 0 (상승 gap-up 상황 차단 — 하락 중 거래량 급등만 유효)
    세 조건 모두 만족해야 override → 하나라도 빠지면 쿨다운 유지
    """
    cd = _load_cooldown_state()
    if not cd:
        return False
    try:
        fam = _get_signal_family_key(signals) if signals else "any"

        key_fam = f"{ticker}:{fam}"
        if key_fam in cd:
            hrs = (datetime.now() - datetime.fromisoformat(cd[key_fam])).total_seconds() / 3600
            if hrs < _SCANNER_COOLDOWN["family_hours"]:
                # override 조건 확인: 세 조건 동시 만족 시 쿨다운 무시
                prev_quality = cd.get(f"{key_fam}:quality", 0)
                quality_surge = (quality_score - prev_quality) >= _SCANNER_COOLDOWN["quality_surge"]
                vol_spike     = vol_ratio > _SCANNER_COOLDOWN["volume_spike"]
                is_declining  = change_1d < _SCANNER_COOLDOWN["declining_change_max"]  # 상승 gap-up 차단

                if quality_surge and vol_spike and is_declining:
                    # override 5거래일 1회 제한 (Doc2: 연속 override 방지)
                    last_override = cd.get(f"{key_fam}:last_override")
                    if last_override:
                        override_hrs = (
                            datetime.now() - datetime.fromisoformat(last_override)
                        ).total_seconds() / 3600
                        if override_hrs < _SCANNER_COOLDOWN["override_limit_hours"]:   # 5거래일 = 120시간
                            log.info(
                                f"  ⛔ override 제한(5거래일 1회): {ticker} "
                                f"마지막override {override_hrs:.0f}h 전"
                            )
                            return True  # override 횟수 초과 → 쿨다운 유지
                    log.info(
                        f"  ⚡ 쿨다운 override: {ticker} quality+{quality_score-prev_quality:.0f}"
                        f" vol{vol_ratio:.1f}x change{change_1d:+.1f}%"
                    )
                    # override 상세 기록 (Doc3: reason, quality, count 추적)
                    override_count = cd.get(f"{key_fam}:override_count", 0) + 1
                    cd[f"{key_fam}:override_reason"]   = (
                        f"quality+{quality_score-prev_quality:.0f}_vol{vol_ratio:.1f}x"
                    )
                    cd[f"{key_fam}:override_quality"]  = quality_score
                    cd[f"{key_fam}:override_count"]    = override_count
                    cd[f"{key_fam}:last_override"]     = datetime.now().isoformat()
                    _save_cooldown_state(cd)
                    return False  # 쿨다운 무시 → 신호 통과
                return True   # 조건 미충족 → 쿨다운 유지

        # 레거시: ticker 전체 쿨다운
        last = cd.get(ticker)
        if last:
            hrs = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600
            if hrs < COOLDOWN_HOURS:
                return True
        return False
    except Exception:
        return False


def _set_cooldown(ticker: str, signals: list = None,
                  quality_score: float = 0, is_override: bool = False):
    """ticker + signal_family 기반 쿨다운 설정. quality_score 저장으로 override 판단."""
    cd = _load_cooldown_state()
    now_iso = datetime.now().isoformat()
    cd[ticker] = now_iso   # 레거시 호환
    if signals:
        fam = _get_signal_family_key(signals)
        key_fam = f"{ticker}:{fam}"
        cd[key_fam]               = now_iso
        cd[f"{key_fam}:quality"]  = quality_score   # override 판단용
        if is_override:
            cd[f"{key_fam}:last_override"] = now_iso  # override 시간 기록 (5거래일 제한)
    _save_cooldown_state(cd)


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


def _build_scanner_devil_line(devil: dict) -> str | None:
    status = _resolve_scanner_devil_status(devil)
    verdict = str(devil.get("verdict", "부분동의") or "부분동의").strip()
    objection = _first_scanner_objection(devil)
    if status == "ok_with_objection":
        return f"🔴 Devil ⚠️ {verdict}: {objection[:55]}"
    if status == "no_material_objection":
        return "🔴 Devil: 반박 없음"
    if status == "api_error":
        return "🔴 Devil: 응답 실패"
    if status == "parse_failed":
        return "🔴 Devil: 응답 파싱 실패"
    return None


def _build_alert_message(
    ticker: str,
    info: dict,
    tech: dict,
    analyst: dict,
    devil: dict,
    final: dict,
    quality: dict,
    canonical_signal_family: str,
    aria: dict,
) -> str:
    now_str = datetime.now(KST).strftime("%m/%d %H:%M")
    cur = info["currency"]
    strong = final["signal_type"] == "강한매수"
    score = final["final_score"]
    price_str = f"{tech['price']:,.2f}" if info["market"] == "US" else f"{tech['price']:,.0f}"

    icon = "🔥" if strong else "🎯"
    label = "강한 매수 타점" if strong else "스윙 타점"
    score_icon = "🟢" if score >= STRONG_THRESHOLD else "🟡"

    pnl_str = ""
    if info.get("avg_cost") and info["market"] == "US":
        pnl = (tech["price"] - info["avg_cost"]) / info["avg_cost"] * 100
        pnl_str = f"  ({'📈' if pnl >= 0 else '📉'}{pnl:+.1f}%)"

    devil_line = _build_scanner_devil_line(devil)
    entry = final.get("entry_price")
    stop = final.get("stop_loss")
    fired_sigs = final.get("signals_fired", []) or analyst.get("signals_fired", [])

    def _format_signals_display(sigs: list) -> str:
        if not sigs:
            return "없음"
        if len(sigs) == 1:
            return sigs[0]
        priority = [
            "sector_rebound",
            "volume_climax",
            "bb_touch",
            "rsi_oversold",
            "vol_accumulation",
            "momentum_dip",
            "ma_support",
            "rsi_divergence",
        ]
        sorted_sigs = sorted(sigs, key=lambda s: priority.index(s) if s in priority else 99)
        return " + ".join(sorted_sigs)

    signals_display = _format_signals_display(fired_sigs)
    best_info = select_scanner_swing_info(fired_sigs, weights)
    explanation_lines = build_scanner_explanation_lines(
        signal_family=canonical_signal_family,
        signals_fired=fired_sigs,
        quality_reasons=quality.get("reasons", []),
        best_info=best_info,
        aria=aria,
    )

    lines = [
        f"{icon} <b>Jackal Hunter — {label}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<b>{info['name']}</b>  <code>{ticker}</code>",
        f"💰 {cur}{price_str}  1일:{tech['change_1d']:+.1f}%  5일:{tech['change_5d']:+.1f}%{pnl_str}",
        "━━━━━━━━━━━━━━━━━━━━",
        f"{score_icon} <b>{score:.0f}/100</b>  {final['signal_type']}  [{analyst.get('confidence','')}]",
        build_scanner_peak_line(best_info),
        f"⚡ Analyst {analyst['analyst_score']}  →  Devil {devil['devil_score']}  →  Final {score:.0f}",
        f"📊 신호: {signals_display}",
        f"   RSI {tech['rsi']} | BB {tech['bb_pos']}% | 거래량 {tech['vol_ratio']:.1f}x",
    ]
    lines.extend(explanation_lines)

    bull = (analyst.get("bull_case") or "").strip()
    if bull:
        lines.append(f"🐂 {bull[:80]}")
    if devil_line:
        lines.append(devil_line)

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if entry:
        lines.append(f"🎯 진입: {cur}{entry}{'  🛑 손절: ' + cur + str(stop) if stop else ''}")
    elif stop:
        lines.append(f"🛑 손절: {cur}{stop}")

    lines.append(f"⏰ {now_str} KST | Jackal Hunter")
    return "\n".join(lines)


def _save_recommendation(extra: dict, aria: dict):
    """
    추천 종목을 두 곳에 저장:
    1. data/jackal_watchlist.json  → ARIA Hunter가 읽어 뉴스 검색
    2. jackal/recommendation_log.json → 24h 후 결과 확인용
    """
    now = datetime.now(KST)
    entries = []
    for ticker, info in extra.items():
        price_now = None
        try:
            from orca.market_fetch import fetch_latest_close

            latest = fetch_latest_close(ticker, lookback_days=3)
            if latest:
                price_now = float(latest[0])
        except Exception:
            pass
        entries.append({
            "ticker":          ticker,
            "name":            info.get("name", ticker),
            "market":          info.get("market", "US"),
            "reason":          info.get("reason", ""),
            "price_at_rec":    price_now,
            "recommended_at":  now.isoformat(),
            "orca_regime":     aria.get("regime", ""),
            "orca_inflows":    aria.get("key_inflows", []),
            "orca_trend":      aria.get("trend", ""),
            "outcome_checked": False,
            "price_next_day":  None,
            "outcome_pct":     None,
            "outcome_correct": None,
        })

    # 1. jackal_watchlist.json (ARIA Hunter가 읽음)
    watchlist = {
        "updated_at": now.isoformat(),
        "regime":     aria.get("regime", ""),
        "tickers":    [e["ticker"] for e in entries],
        "details":    {e["ticker"]: {"name": e["name"], "reason": e["reason"]} for e in entries},
    }
    try:
        JACKAL_WATCHLIST.parent.mkdir(exist_ok=True)
        JACKAL_WATCHLIST.write_text(
            json.dumps(watchlist, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info(f"   jackal_watchlist.json 저장: {watchlist['tickers']}")
    except Exception as e:
        log.error(f"   watchlist 저장 실패: {e}")

    # 2. recommendation_log.json (Evolution이 읽음)
    logs = _load_recommendation_log()
    logs.extend(entries)
    logs = logs[-200:]
    _save_recommendation_log(logs)


def _load_jackal_news() -> str:
    """ARIA가 수집한 Jackal 추천 종목 뉴스 → 프롬프트용 문자열."""
    if not JACKAL_NEWS_FILE.exists():
        return ""
    try:
        data  = json.loads(JACKAL_NEWS_FILE.read_text(encoding="utf-8"))
        items = data.get("news_items", [])
        if not items:
            return ""
        lines = ["\n[ARIA 수집 뉴스 — Jackal 추천 종목]"]
        for item in items[:5]:
            lines.append(f"  • {item.get('ticker','')}: {item.get('headline','')[:60]}")
        return "\n".join(lines)
    except Exception:
        return ""


def _send_orca_extra_message(extra: dict, aria: dict):
    """ARIA 분석 기반 추천 종목 전송 + 추적 저장."""
    if not extra:
        return

    _save_recommendation(extra, aria)

    now_str = datetime.now(KST).strftime("%m/%d %H:%M")
    regime  = aria.get("regime", "")
    inflows = aria.get("key_inflows", [])

    lines = [
        "💡 <b>ARIA 기반 관심 종목 추천</b>",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    if regime:
        lines.append(f"🌐 레짐: {regime[:30]}")
    if inflows:
        lines.append(f"📈 유입 섹터: {', '.join(inflows[:3])}")
    lines.append("")

    for ticker, info in extra.items():
        icon   = "🇺🇸" if info.get("market") == "US" else "🇰🇷"
        reason = info.get("reason", "")
        lines.append(f"{icon} <b>{info['name']}</b> ({ticker})")
        if reason:
            lines.append(f"   └ {reason}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "📰 ARIA가 관련 뉴스 수집 예정 (내일 아침 반영)",
        f"⏰ {now_str} KST | Jackal × ARIA",
    ]
    _send_telegram("\n".join(lines))
    log.info(f"   ARIA 추천 전송: {list(extra.keys())}")

def _build_summary_message(results: list, macro: dict, aria: dict) -> str:
    """타점 없을 때 스캔 결과 요약"""
    now_str = datetime.now(KST).strftime("%m/%d %H:%M")
    fred    = macro.get("fred", {})

    # 최고 점수 종목
    top_score = max((r["final_score"] for r in results), default=0)

    lines = [
        "📊 <b>JACKAL Scanner — 타점 없음</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"최고점수: {top_score:.0f}/100 (임계값 {ALERT_THRESHOLD})",
        "",
    ]

    # 신호 아이콘: 반등가능 > 중립 > 매도주의
    def _sig_icon(sig: str, score: float) -> str:
        if sig == "강한매수":  return "🟢"
        if sig == "매수검토":  return "🟡"
        if sig == "매도주의":  return "🔴"
        return "⚪"

    # 점수 내림차순 정렬
    sorted_r = sorted(results, key=lambda x: x["final_score"], reverse=True)

    for r in sorted_r:
        sig    = r.get("signal_type", "관망")
        icon   = _sig_icon(sig, r["final_score"])
        ticker = r["ticker"]
        name   = r["name"]
        # 한국 숫자 티커면 이름만
        label  = f"<b>{name}</b> ({ticker})" if not ticker[:6].isdigit() else f"<b>{name}</b>"
        dv     = r.get("devil_verdict", "")
        dv_str = f" | Devil {dv}" if dv else ""
        # 신호 한글 간략화
        sig_short = {"강한매수": "강한매수", "매수검토": "반등가능", "관망": "중립", "매도주의": "약세"}.get(sig, sig)
        lines.append(
            f"{icon} {label}  {r['final_score']:.0f}점"
            f" | RSI {r['rsi']} | 5일 {r.get('change_5d','N/A')}%"
            f" | {sig_short}{dv_str}"
        )

    lines.append("━━━━━━━━━━━━━━━━━━━━")

    # 매크로 요약
    fred_parts = []
    if fred.get("vix"):       fred_parts.append(f"VIX {fred['vix']}")
    if fred.get("hy_spread"): fred_parts.append(f"HY {fred['hy_spread']}%")
    if fred_parts:
        lines.append("📈 " + " | ".join(fred_parts))

    if aria.get("regime"):
        lines.append(f"🌐 {aria['regime'][:35]}")
    lines.append(f"⏰ {now_str} KST | JACKAL Scanner")
    return "\n".join(lines)


def _build_shadow_log_entry(
    *,
    now_kst: datetime,
    ticker: str,
    info: dict,
    tech: dict,
    macro: dict,
    aria: dict,
    signals_fired_pre: list,
    quality: dict,
) -> dict:
    return {
        "timestamp":        now_kst.isoformat(),
        "ticker":           ticker,
        "name":             info["name"],
        "market":           info["market"],
        "price_at_scan":    tech["price"],
        "rsi":              tech["rsi"],
        "bb_pos":           tech["bb_pos"],
        "vol_ratio":        tech["vol_ratio"],
        "vix":              macro["fred"].get("vix"),
        "hy_spread":        macro["fred"].get("hy_spread"),
        "yield_curve":      macro["fred"].get("yield_curve"),
        "orca_regime":      aria["regime"],
        "orca_sentiment":   aria["sentiment_score"],
        "orca_trend":       aria["trend"],
        "analyst_score":    None,
        "analyst_confidence": None,
        "signals_fired":    signals_fired_pre,
        "bull_case":        None,
        "devil_score":      None,
        "devil_verdict":    None,
        "devil_objections": [],
        "thesis_killer_hit": False,
        "killer_detail":    "",
        "devil_called":     False,
        "devil_parse_ok":   False,
        "devil_status":     "skipped_quality_gate",
        "devil_raw_excerpt": None,
        "devil_render_mode": "hidden",
        "final_score":      quality["quality_score"],
        "signal_type":      "관망",
        "signal_family":    canonical_family_key(
            signal_family=quality["signal_family"],
            signals_fired=signals_fired_pre,
        ),
        "signal_family_raw": quality["signal_family"],
        "signal_family_label": family_label(
            canonical_family_key(
                signal_family=quality["signal_family"],
                signals_fired=signals_fired_pre,
            )
        ),
        "is_entry":         False,
        "reason":           f"신호품질미달({quality['quality_score']}점)",
        "quality_score":    quality["quality_score"],
        "quality_label":    quality["quality_label"],
        "quality_reasons":  quality["reasons"],
        "skip_threshold":   quality["skip_threshold"],
        "rebound_bonus":    quality.get("rebound_bonus", 0),
        "vix_used":         quality.get("vix_used", 0),
        "shadow_record":    True,
        "shadow_storage":   "sqlite",
        "alerted":          False,
        "outcome_checked":  False,
        "outcome_price":    None,
        "outcome_pct":      None,
        "outcome_correct":  None,
    }


def _build_scan_log_entry(
    *,
    now_kst: datetime,
    ticker: str,
    market: str,
    info: dict,
    tech: dict,
    macro: dict,
    aria: dict,
    quality: dict,
    analyst: dict,
    devil: dict,
    final: dict,
    canonical_signal_family: str,
) -> dict:
    devil_status = _resolve_scanner_devil_status(devil)
    fired_sigs = analyst.get("signals_fired", []) or final.get("signals_fired", [])
    best_info = select_scanner_swing_info(fired_sigs, weights)
    reason_detail, reason_components = build_scanner_reason_payload(
        signal_family=canonical_signal_family,
        signals_fired=fired_sigs,
        quality_reasons=quality.get("reasons", []),
        best_info=best_info,
        aria=aria,
        devil=devil,
    )
    return {
        "timestamp":        now_kst.isoformat(),
        "ticker":           ticker,
        "name":             info["name"],
        "market":           market,
        "price_at_scan":    tech["price"],
        "rsi":              tech["rsi"],
        "bb_pos":           tech["bb_pos"],
        "vol_ratio":        tech["vol_ratio"],
        "vix":              macro["fred"].get("vix"),
        "hy_spread":        macro["fred"].get("hy_spread"),
        "yield_curve":      macro["fred"].get("yield_curve"),
        "orca_regime":      aria["regime"],
        "orca_sentiment":   aria["sentiment_score"],
        "orca_trend":       aria["trend"],
        "signal_family":    canonical_signal_family,
        "signal_family_raw": quality.get("signal_family", ""),
        "signal_family_label": family_label(canonical_signal_family),
        "quality_score":    quality.get("quality_score"),
        "quality_label":    quality.get("quality_label", ""),
        "quality_reasons":  quality.get("reasons", []),
        "analyst_score":    analyst["analyst_score"],
        "analyst_confidence": analyst.get("confidence",""),
        "signals_fired":    fired_sigs,
        "bull_case":        analyst.get("bull_case",""),
        "devil_score":      devil["devil_score"],
        "devil_verdict":    devil.get("verdict",""),
        "devil_objections": devil.get("objections", []),
        "thesis_killer_hit": devil.get("thesis_killer_hit", False),
        "killer_detail":    devil.get("killer_detail",""),
        "devil_called":     devil.get("devil_called", True),
        "devil_parse_ok":   devil.get("devil_parse_ok", False),
        "devil_status":     devil.get("devil_status", devil_status),
        "devil_raw_excerpt": devil.get("devil_raw_excerpt"),
        "devil_render_mode": devil.get("devil_render_mode", _scanner_devil_render_mode(devil_status)),
        "final_score":      final["final_score"],
        "signal_type":      final["signal_type"],
        "is_entry":         final["is_entry"],
        "reason":           final.get("reason",""),
        "reason_detail":    reason_detail,
        "reason_components": reason_components,
        "probability_adjustment": final.get("probability_adjustment", 0),
        "probability_samples": final.get("probability_samples", 0),
        "probability_win_rate": final.get("probability_win_rate"),
        "alerted":          final["is_entry"] and final["final_score"] >= ALERT_THRESHOLD,
        "outcome_checked":  False,
        "outcome_price":    None,
        "outcome_pct":      None,
        "outcome_correct":  None,
    }


# ══════════════════════════════════════════════════════════════════
# 스캔 로그 (Evolution 학습용 — 풍부한 메타데이터 포함)
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
    atomic_write_json(SCAN_LOG_FILE, logs)
    sync_jackal_live_events("scan", logs)

def _save_shadow_log(entry: dict):
    """
    Claude 호출 스킵된 신호 별도 저장 (Doc3: ARIA accuracy와 분리).
    scan_log.json과 혼용 금지 — SQLite state spine에 별도 적재한다.
    """
    record_jackal_shadow_signal(entry)


# ══════════════════════════════════════════════════════════════════
# 메인 스캔
# ══════════════════════════════════════════════════════════════════

def _suggest_extra_tickers(aria: dict, portfolio: dict) -> dict:
    """
    ARIA 분석에서 타점 가능성 높은 추가 5종목 추천.
    Claude Haiku가 섹터 유입/헤드라인 기반으로 추천.
    포트폴리오에 이미 있는 종목은 제외.
    """
    existing = set(portfolio.keys())
    inflows  = aria.get("key_inflows", [])
    outflows = aria.get("key_outflows", [])
    regime   = aria.get("regime", "")
    one_line = aria.get("one_line", "")
    top_sec  = aria.get("top_sector", "")

    if not inflows and not regime:
        return {}

    prompt = f"""당신은 주식 종목 추천 전문가입니다.
ARIA 시장 분석 결과를 보고 타점이 생길 가능성이 높은 종목 5개를 추천하세요.
이미 보유 중인 종목({', '.join(existing)})은 제외하세요.

[ARIA 분석]
레짐: {regime}
요약: {one_line[:80]}
주요 유입 섹터: {', '.join(inflows)}
주요 유출 섹터: {', '.join(outflows)}
강세 섹터: {top_sec}

조건:
- yfinance로 조회 가능한 실제 티커 심볼 사용
- 미국 주식: TICKER 형식 (예: TSM, AMD, QCOM)
- 한국 주식: 6자리+.KS 형식 (예: 012450.KS)
- 유입 섹터와 연관된 종목 우선
- 현재 레짐에서 수혜 가능한 종목

JSON만 반환하세요:
{{
  "recommendations": [
    {{"ticker": "TSM", "name": "TSMC", "market": "US", "currency": "$", "reason": "AI 반도체 수혜"}},
    {{"ticker": "AMD", "name": "AMD", "market": "US", "currency": "$", "reason": "GPU 경쟁"}},
    {{"ticker": "012450.KS", "name": "한화에어로스페이스", "market": "KR", "currency": "₩", "reason": "방산 섹터 유입"}}
  ]
}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw  = re.sub(r"", "", resp.content[0].text).strip()
        m    = re.search(r"\{{[\s\S]*\}}", raw)
        if not m:
            return {}
        data  = json.loads(m.group())
        extra = {}
        for r in data.get("recommendations", [])[:5]:
            t = r.get("ticker", "")
            if t and t not in existing:
                extra[t] = {
                    "name":      r.get("name", t),
                    "avg_cost":  None,
                    "market":    r.get("market", "US"),
                    "currency":  r.get("currency", "$"),
                    "portfolio": False,
                    "reason":    r.get("reason", ""),
                }
        log.info(f"   ARIA 추가 추천: {list(extra.keys())}")
        return extra
    except Exception as e:
        log.error(f"추가 종목 추천 실패: {e}")
        return {}


def run_scan(force: bool = False) -> dict:
    now_kst = datetime.now(KST)
    us_open = _is_us_open()
    kr_open = _is_kr_open()

    log.info(f"📡 Jackal Scanner | {now_kst.strftime('%Y-%m-%d %H:%M KST')}")
    log.info(f"   미국장 {'✅' if us_open else '❌'} | 한국장 {'✅' if kr_open else '❌'}")

    # 공통 데이터 수집 (1회)
    macro = fetch_all()
    aria  = _load_orca_context()

    log.info(f"   ARIA 레짐: {aria['regime'][:20] if aria['regime'] else '정보없음'} | "
             f"센티먼트: {aria['sentiment_score']}점")

    # watchlist 구성: portfolio + candidate registry + recent recommendations
    portfolio = _load_portfolio()
    candidate_watch = _load_candidate_watchlist()
    recommendation_watch = _load_recommendation_watchlist()
    base_watchlist = _merge_watchlists(portfolio, candidate_watch, recommendation_watch)
    log.info(f"   포트폴리오: {len(portfolio)}종목")
    log.info(f"   후보 watchlist: {len(candidate_watch)}종목")
    log.info(f"   추천 watchlist: {len(recommendation_watch)}종목")

    # ARIA 기반 추가 5종목 추천 → 별도 메시지 + watchlist snapshot 반영
    extra = _suggest_extra_tickers(aria, base_watchlist)
    if extra:
        _send_orca_extra_message(extra, aria)

    watchlist = _merge_watchlists(base_watchlist, extra)
    _save_watchlist_snapshot(watchlist)
    log.info(f"   최종 watchlist: {len(watchlist)}종목")

    scanned = 0
    alerted = 0
    results: list = []
    lesson_summary = load_probability_summary()

    for ticker, info in watchlist.items():
        market = info["market"]

        if not force:
            if market == "US" and not us_open:
                continue
            if market == "KR" and not kr_open:
                continue

        tech = fetch_technicals(ticker)
        if not tech:
            continue

        if _is_on_cooldown(ticker,
                           quality_score=0,
                           vol_ratio=tech.get("vol_ratio", 0),
                           change_1d=tech.get("change_1d", 0)):
            log.info(f"  {ticker}: 쿨다운 — 스킵")
            continue

        cache_note = ""
        if tech.get("from_cache"):
            cache_note = f" [cache {tech.get('cache_age_minutes', 0.0):.0f}m]"
        log.info(f"  {ticker} ({info['name']}): RSI={tech['rsi']} BB={tech['bb_pos']}% vol={tech['vol_ratio']:.1f}x{cache_note}")

        # ── 신호 품질 사전 평가 (Claude 호출 전) ─────────────────
        # 기술 신호 사전 감지 (백테스트와 동일한 기준)
        signals_fired_pre = detect_pre_rule_signals(tech)

        quality = _calc_signal_quality(
            signals  = signals_fired_pre,
            tech     = tech,
            aria     = aria,
            ticker   = ticker,
            weights  = _load_weights(),
        )
        info["_quality"] = quality  # agent_analyst에서 접근

        log.info(
            f"    신호품질: {quality['quality_score']}점({quality['quality_label']})"
            f" | family:{quality['signal_family']}"
            f" | 임계:{quality['skip_threshold']}"
            f" | vix:{quality['vix_used']:.0f}"
            f" | 신호:{signals_fired_pre}"
        )
        log.info(f"    근거: {', '.join(quality['reasons'][:3])}")
        if quality.get("negative_veto"):
            log.info(f"    ⚠️ NegVeto: {quality.get('negative_reasons', [])}")

        # 품질 45 미만 → Claude 호출 스킵 (Doc2/3 반박 수용)
        # shadow_record는 반드시 저장 → 나중에 "버린 신호의 실제 성과" 추적 가능
        if quality["skip"]:
            log.info(
                f"    ⛔ 신호품질미달 {quality['quality_score']}점"
                f" (임계:{quality['skip_threshold']}, family:{quality['signal_family']})"
                f" → 스킵+shadow저장"
            )
            scanned += 1
            results.append({
                "ticker":        ticker,
                "name":          info["name"],
                "final_score":   quality["quality_score"],
                "signal_type":   "관망",
                "devil_verdict":  "",
                "rsi":           tech["rsi"],
                "change_5d":     tech.get("change_5d", "N/A"),
                "is_portfolio":  info.get("portfolio", True),
                "orca_reason":   "신호품질미달",
                "quality_score": quality["quality_score"],
                "quality_label": quality["quality_label"],
            })
            # shadow_record: 별도 파일 저장 (Doc3: ARIA accuracy/scan_log와 완전 분리)
            _save_shadow_log(
                _build_shadow_log_entry(
                    now_kst=now_kst,
                    ticker=ticker,
                    info=info,
                    tech=tech,
                    macro=macro,
                    aria=aria,
                    signals_fired_pre=signals_fired_pre,
                    quality=quality,
                )
            )
            continue

        # ── Agent 1: Analyst ─────────────────────────────────────
        analyst = agent_analyst(ticker, info, tech, macro, aria)
        log.info(f"    Analyst: {analyst['analyst_score']}점 | {analyst['confidence']} | {analyst.get('signals_fired', [])}")

        # ── Agent 2: Devil ───────────────────────────────────────
        devil = agent_devil(ticker, info, tech, macro, aria, analyst)
        log.info(f"    Devil: {devil['verdict']} | {devil['devil_score']}점 | TK:{devil['thesis_killer_hit']}")

        # ── Final 판단 ───────────────────────────────────────────
        final = _final_judgment(analyst, devil)
        canonical_signal_family = canonical_family_key(
            signal_family=quality.get("signal_family", ""),
            signals_fired=analyst.get("signals_fired", []) or signals_fired_pre,
        )
        final = apply_probability_adjustment(
            final,
            canonical_signal_family,
            lesson_summary,
            entry_threshold=float(ALERT_THRESHOLD),
            blocked_verdict="반대",
        )
        if (
            final.get("verdict") == "반대"
            or final["final_score"] < _SCANNER_SIGNAL_RELABEL["watch_cutoff"]
        ):
            final["signal_type"] = (
                "매도주의"
                if final["final_score"] < _SCANNER_SIGNAL_RELABEL["sell_cutoff"]
                else "관망"
            )
        elif final["final_score"] >= STRONG_THRESHOLD:
            final["signal_type"] = "강한매수"
        elif final["final_score"] >= ALERT_THRESHOLD:
            final["signal_type"] = "매수검토"
        else:
            final["signal_type"] = "관망"
        scanned += 1

        log.info(
            f"    Final: {final['final_score']:.0f}점 | {final['signal_type']} | is_entry={final['is_entry']}"
            f" | 품질:{quality['quality_score']}({quality['quality_label']})"
            + (
                f" | learn {final['probability_adjustment']:+.0f}"
                f" ({final['probability_win_rate']:.1f}%/{final['probability_samples']}표본)"
                if final.get("probability_adjustment")
                else ""
            )
        )

        results.append({
            "ticker":       ticker,
            "name":         info["name"],
            "final_score":  final["final_score"],
            "signal_type":  final["signal_type"],
            "devil_verdict": devil.get("verdict", ""),
            "signal_family": canonical_signal_family,
            "signal_family_raw": quality.get("signal_family", ""),
            "signal_family_label": family_label(canonical_signal_family),
            "probability_adjustment": final.get("probability_adjustment", 0),
            "probability_samples": final.get("probability_samples", 0),
            "probability_win_rate": final.get("probability_win_rate"),
            "rsi":          tech["rsi"],
            "change_5d":    tech.get("change_5d", "N/A"),
            "is_portfolio": info.get("portfolio", True),
            "orca_reason":  info.get("reason", ""),
        })

        # ── 알림 발송 ─────────────────────────────────────────────
        if final["is_entry"] and final["final_score"] >= ALERT_THRESHOLD:
            msg = _build_alert_message(
                ticker,
                info,
                tech,
                analyst,
                devil,
                final,
                quality,
                canonical_signal_family,
                aria,
            )
            ok  = _send_telegram(msg)
            if ok:
                _set_cooldown(ticker,
                             final.get("signals_fired", signals_fired_pre),
                             quality_score=quality.get("quality_score", 0))
                alerted += 1
                log.info(f"    ✅ 텔레그램 발송 완료")

        # ── 로그 저장 (Evolution 학습용) ──────────────────────────
        _save_log(
            _build_scan_log_entry(
                now_kst=now_kst,
                ticker=ticker,
                market=market,
                info=info,
                tech=tech,
                macro=macro,
                aria=aria,
                quality=quality,
                analyst=analyst,
                devil=devil,
                final=final,
                canonical_signal_family=canonical_signal_family,
            )
        )

    log.info(f"📡 완료 | 분석 {scanned}종목 | 알림 {alerted}건")

    # 장이 열려있는데 타점 없으면 요약 발송
    any_open = (us_open or kr_open) or force
    if any_open and alerted == 0 and scanned > 0:
        _send_telegram(_build_summary_message(results, macro, aria))

    return {"scanned": scanned, "alerted": alerted}


def main() -> None:
    parser = argparse.ArgumentParser(description="JACKAL Scanner")
    parser.add_argument(
        "--force",
        action="store_true",
        help="시장 개장 여부와 무관하게 스캔 실행",
    )
    args = parser.parse_args()
    result = run_scan(force=args.force)
    print(
        f"JACKAL Scanner 완료 | scanned={result.get('scanned', 0)} | "
        f"alerted={result.get('alerted', 0)}"
    )


if __name__ == "__main__":
    main()



