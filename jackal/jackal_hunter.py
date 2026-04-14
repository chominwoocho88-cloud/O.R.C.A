"""
jackal_hunter.py
Jackal Hunter — 100→50→25→10→5 단계별 스윙 타점 탐색

흐름:
  Universe 구성  (~100):  고정 섹터풀 80 + ARIA 뉴스 기반 Claude 추천 20
  Stage 1 100→50: yfinance 기술지표 점수 (비용 $0)
  Stage 2  50→25: ARIA 레짐/섹터 매칭 보정 (비용 $0)
  Stage 3  25→10: Claude Haiku 빠른 판단, 웹서치 없음 (~$0.04)
  Stage 4  10→5:  Analyst → Devil → Final, 웹서치 포함 (~$0.15)
  총 비용: ~$0.20/회

포트폴리오 종목 제외 — 항상 새 종목만 발굴
"""

import os
import sys
import json
import re
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yfinance as yf
import pandas as pd
from anthropic import Anthropic

os.environ["PYTHONIOENCODING"] = "utf-8"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

log = logging.getLogger("jackal_hunter")

KST   = timezone(timedelta(hours=9))
_BASE = Path(__file__).parent

HUNT_LOG_FILE  = _BASE / "hunt_log.json"
HUNT_COOL_FILE = _BASE / "hunt_cooldown.json"
ARIA_BASELINE  = Path("data") / "morning_baseline.json"
ARIA_MEMORY    = Path("data") / "memory.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MODEL_H          = os.environ.get("SUBAGENT_MODEL", "claude-haiku-4-5-20251001")

ANALYZE_FINAL   = 5     # 최종 Analyst+Devil 실행 수
HUNT_COOLDOWN_H = 6

# ── 내 포트폴리오 제외 ──────────────────────────────────────────
MY_PORTFOLIO = {
    "NVDA", "AVGO", "SCHD", "000660.KS",
    "005930.KS", "035720.KS", "466920.KS",
}

# ══════════════════════════════════════════════════════════════════
# 고정 섹터풀 (~80 종목)
# ARIA 유입 섹터에 따라 동적으로 선택됨
# ══════════════════════════════════════════════════════════════════
SECTOR_POOLS = {
    "반도체/AI": [
        "TSM", "AMD", "INTC", "QCOM", "MU", "MRVL", "ARM",
        "AMAT", "LRCX", "KLAC", "TXN", "MCHP", "ASML",
        "000990.KS", "042700.KS", "086520.KS",
    ],
    "빅테크": [
        "AAPL", "MSFT", "GOOGL", "META", "AMZN",
        "NFLX", "ORCL", "CRM", "NOW", "SNOW",
    ],
    "에너지": [
        "XOM", "CVX", "OXY", "COP", "SLB",
        "MPC", "VLO", "PSX", "HES", "DVN",
        "010950.KS", "096770.KS",
    ],
    "금융": [
        "JPM", "BAC", "WFC", "GS", "MS",
        "BLK", "AXP", "V", "MA", "C",
        "105560.KS", "055550.KS",
    ],
    "방산/우주": [
        "LMT", "RTX", "NOC", "GD", "BA",
        "RKLB", "LUNR",
        "012450.KS", "047810.KS", "329180.KS",
    ],
    "헬스케어": [
        "JNJ", "PFE", "MRK", "ABBV", "LLY",
        "UNH", "TMO", "AMGN",
    ],
    "한국": [
        "005380.KS", "000270.KS", "035420.KS",
        "051910.KS", "068270.KS", "207940.KS",
        "003550.KS", "009150.KS", "066570.KS",
    ],
    "전기차/배터리": [
        "TSLA", "RIVN", "NIO",
        "373220.KS", "247540.KS", "051600.KS",
    ],
}


# ── 섹터 ETF 매핑 (상대강도 계산용) ──────────────────────────────
SECTOR_ETF = {
    "반도체/AI":    "SOXX",   # iShares 반도체 ETF
    "빅테크":       "QQQ",    # 나스닥 100
    "에너지":       "XLE",    # 에너지 섹터
    "금융":         "XLF",    # 금융 섹터
    "방산/우주":    "ITA",    # 방산 ETF
    "헬스케어":     "XLV",    # 헬스케어 섹터
    "한국":         "EWY",    # MSCI 한국 ETF
    "전기차/배터리": "LIT",   # 배터리/리튬 ETF
}


def _extract_relevant_news(ticker: str, name: str, aria: dict) -> str:
    """
    ARIA 수집 뉴스에서 이 티커/섹터 관련 내용 추출.
    Analyst 프롬프트에 주입할 뉴스 컨텍스트 반환.
    비용 $0 — 파일 읽기만.
    """
    lines = []

    # 1. jackal_news.json에서 직접 티커 뉴스
    ticker_news = aria.get("jackal_news", {}).get(ticker, [])
    for n in ticker_news[:2]:
        h = n.get("headline", "")
        impact = n.get("impact", "")
        if h:
            icon = "📈" if impact == "bullish" else "📉" if impact == "bearish" else "📰"
            lines.append(f"{icon} {h[:70]}")

    # 2. ARIA 전체 헤드라인에서 종목/섹터 관련 필터링
    search_terms = [ticker.replace(".KS",""), name[:4]]
    # 티커가 속한 섹터 찾기
    ticker_sector = None
    for sec, tks in SECTOR_POOLS.items():
        if ticker in tks:
            ticker_sector = sec
            break
    if ticker_sector:
        keywords = ticker_sector.lower().replace("/", " ").split()
        search_terms.extend(keywords)

    for h_item in aria.get("all_headlines", []):
        h_text  = h_item.get("headline", "")
        sig_tag = h_item.get("signal_tag", "")
        impact  = h_item.get("impact", "")
        h_lower = h_text.lower()
        if any(t.lower() in h_lower for t in search_terms if len(t) >= 3):
            if h_text not in "".join(lines):  # 중복 제거
                icon = "📈" if sig_tag == "강세" else "📉" if sig_tag == "약세" else "📰"
                lines.append(f"{icon} [{impact}] {h_text[:70]}")
            if len(lines) >= 3:
                break

    # 3. 섹터 유입/유출 상세 이유 (가장 중요)
    sector_context = []
    for inflow in aria.get("inflows_detail", []):
        zone   = inflow.get("zone", "")
        reason = inflow.get("reason", "")
        dp     = inflow.get("data_point", "")
        mom    = inflow.get("momentum", "")
        if ticker_sector and any(
            k in zone.lower()
            for k in (ticker_sector.lower().replace("/", " ").split())
        ):
            if reason:
                sector_context.append(f"✅ 유입근거: {reason[:80]}")
            if dp:
                sector_context.append(f"   데이터: {dp[:60]}")

    for outflow in aria.get("outflows_detail", []):
        zone   = outflow.get("zone", "")
        reason = outflow.get("reason", "")
        sev    = outflow.get("severity", "")
        if ticker_sector and any(
            k in zone.lower()
            for k in (ticker_sector.lower().replace("/", " ").split())
        ):
            if reason:
                sector_context.append(f"⚠️  유출근거[{sev}]: {reason[:80]}")

    if not lines and not sector_context:
        return "관련 뉴스 없음"

    result = "\n".join(lines + sector_context)
    return result or "관련 뉴스 없음"


# ══════════════════════════════════════════════════════════════════
# ARIA 컨텍스트
# ══════════════════════════════════════════════════════════════════

def _load_aria_context() -> dict:
    ctx = {
        "one_line": "", "regime": "",
        "top_headlines": [], "key_inflows": [],
        "key_outflows": [], "thesis_killers": [],
        "actionable": [],
        # 뉴스 품질 향상용 상세 데이터
        "inflows_detail":  [],   # zone + reason + data_point
        "outflows_detail": [],
        "all_headlines":   [],   # signal_tag + impact 포함
        "jackal_news":     {},   # 티커별 수집 뉴스
    }
    try:
        if ARIA_BASELINE.exists():
            b = json.loads(ARIA_BASELINE.read_text(encoding="utf-8"))
            ctx["one_line"]       = b.get("one_line_summary", "")
            ctx["regime"]         = b.get("market_regime", "")
            ctx["top_headlines"]  = [h.get("headline","") for h in b.get("top_headlines",[])[:5]]
            ctx["key_inflows"]    = [i.get("zone","") for i in b.get("inflows",[])[:3]]
            ctx["key_outflows"]   = [o.get("zone","") for o in b.get("outflows",[])[:3]]
            ctx["thesis_killers"] = b.get("thesis_killers", [])
            ctx["actionable"]     = b.get("actionable_watch", [])[:5]
    except Exception as e:
        log.warning(f"ARIA baseline 로드 실패: {e}")

    # memory.json에서 최신 리포트 상세 데이터 로드
    try:
        if ARIA_MEMORY.exists():
            mem = json.loads(ARIA_MEMORY.read_text(encoding="utf-8"))
            if mem:
                last = sorted(mem, key=lambda x: x.get("analysis_date",""))[-1]
                # 헤드라인 전체 (signal_tag + impact 포함)
                ctx["all_headlines"] = last.get("top_headlines", [])[:8]
                # 섹터 유입 상세 (reason + data_point)
                ctx["inflows_detail"] = last.get("inflows", [])[:4]
                # 섹터 유출 상세
                ctx["outflows_detail"] = last.get("outflows", [])[:3]
                # baseline에 없으면 memory에서 보완
                if not ctx["regime"]:
                    ctx["regime"] = last.get("market_regime", "")
                if not ctx["top_headlines"]:
                    ctx["top_headlines"] = [h.get("headline","")
                                            for h in ctx["all_headlines"]]
                if not ctx["key_inflows"]:
                    ctx["key_inflows"] = [i.get("zone","")
                                          for i in ctx["inflows_detail"][:3]]
    except Exception as e:
        log.warning(f"ARIA memory 로드 실패: {e}")

    # jackal_news.json (ARIA가 수집한 티커별 뉴스)
    try:
        jn_file = Path("data") / "jackal_news.json"
        if jn_file.exists():
            jn = json.loads(jn_file.read_text(encoding="utf-8"))
            for item in jn.get("news_items", []):
                t = item.get("ticker","")
                if t:
                    ctx["jackal_news"].setdefault(t, []).append(item)
    except Exception:
        pass

    return ctx


# ══════════════════════════════════════════════════════════════════
# Universe 구성 (~100)
# ══════════════════════════════════════════════════════════════════

def _build_universe(aria: dict) -> list:
    """
    고정 섹터풀 + ARIA 뉴스 기반 Claude 추천으로 ~100개 구성.
    ARIA 유입 섹터를 우선 포함.
    """
    inflows = " ".join(aria["key_inflows"]).lower()
    universe_set = set()

    # ARIA 유입 섹터 풀 우선 추가
    sector_priority = []
    for sector, tickers in SECTOR_POOLS.items():
        sector_lower = sector.lower()
        keywords = sector_lower.replace("/", " ").split()
        if any(kw in inflows for kw in keywords):
            sector_priority.extend(tickers)
        else:
            # 비우선 섹터도 일부 포함
            sector_priority.extend(tickers[:5])

    for t in sector_priority:
        if t not in MY_PORTFOLIO:
            universe_set.add(t)

    # Claude 추천 20개 추가 (ARIA 뉴스 기반)
    claude_suggestions = _claude_suggest_20(aria, universe_set)
    for s in claude_suggestions:
        t = s.get("ticker", "")
        if t and t not in MY_PORTFOLIO:
            universe_set.add(t)

    universe = list(universe_set)
    log.info(f"  Universe: {len(universe)}개 (섹터풀+Claude 추천)")
    return universe


def _claude_suggest_20(aria: dict, existing: set) -> list:
    """ARIA 뉴스에서 20개 추가 추천. 웹서치 포함."""
    headlines = "\n".join(f"  - {h}" for h in aria["top_headlines"] if h)
    actionable = "\n".join(f"  - {a}" for a in aria["actionable"] if a)
    existing_str = ", ".join(list(existing)[:20])
    exclude_str  = ", ".join(MY_PORTFOLIO)

    prompt = f"""오늘 ARIA 시장 분석에서 스윙 가능 종목 20개를 추천하세요.
레짐: {aria['regime']} | 요약: {aria['one_line'][:60]}
헤드라인:\n{headlines}
ARIA 관심종목:\n{actionable}
이미 있는 종목들(추가 불필요): {existing_str[:200]}...
제외: {exclude_str}

JSON만 반환:
{{"suggestions": [{{"ticker": "TSM", "name": "TSMC", "market": "US", "currency": "$", "reason": "이유"}}]}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        full = "".join(getattr(b, "text", "") for b in resp.content)
        m    = re.search(r"\{[\s\S]*\}", re.sub(r"```(?:json)?|```", "", full).strip())
        if not m:
            return []
        data = json.loads(m.group())
        sugg = [s for s in data.get("suggestions", [])
                if s.get("ticker") and s["ticker"] not in MY_PORTFOLIO][:20]
        log.info(f"  Claude 추천: {[s['ticker'] for s in sugg]}")
        return sugg
    except Exception as e:
        log.error(f"  Claude 추천 실패: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# 기술지표 일괄 계산
# ══════════════════════════════════════════════════════════════════

def _fetch_etf_returns() -> dict:
    """섹터 ETF 5일 수익률 가져오기 (상대강도 계산용)."""
    etfs = list(set(SECTOR_ETF.values()))
    ret  = {}
    try:
        raw = yf.download(
            " ".join(etfs), period="10d", interval="1d",
            group_by="ticker", auto_adjust=True, progress=False,
        )
        for etf in etfs:
            try:
                df    = raw[etf] if len(etfs) > 1 else raw
                close = df["Close"].dropna()
                if len(close) >= 6:
                    ret[etf] = round(
                        (float(close.iloc[-1]) - float(close.iloc[-6]))
                        / float(close.iloc[-6]) * 100, 2
                    )
            except Exception:
                pass
    except Exception as e:
        log.warning(f"  ETF 수익률 조회 실패: {e}")
    return ret


def _batch_technicals(tickers: list) -> dict:
    """
    yfinance batch 다운로드로 전 종목 지표 한 번에 계산.
    개별 호출보다 빠름.
    """
    log.info(f"  yfinance 다운로드: {len(tickers)}종목...")
    result = {}

    # 미국/한국 분리 (한국은 개별이 더 안정적)
    us_tickers = [t for t in tickers if not t.endswith(".KS")]
    kr_tickers = [t for t in tickers if t.endswith(".KS")]

    # 미국 batch
    if us_tickers:
        try:
            raw = yf.download(
                " ".join(us_tickers), period="65d", interval="1d",
                group_by="ticker", auto_adjust=True, progress=False,
            )
            for t in us_tickers:
                try:
                    df = raw[t] if len(us_tickers) > 1 else raw
                    tech = _calc_tech(df)
                    if tech:
                        result[t] = tech
                except Exception:
                    pass
        except Exception as e:
            log.warning(f"  US batch 실패: {e}")

    # 한국 개별
    for t in kr_tickers:
        try:
            df   = yf.Ticker(t).history(period="65d", interval="1d")
            tech = _calc_tech(df)
            if tech:
                result[t] = tech
            time.sleep(0.1)
        except Exception:
            pass

    log.info(f"  기술지표 완료: {len(result)}/{len(tickers)}개")
    return result


def _calc_tech(df: pd.DataFrame) -> dict | None:
    if df is None or len(df) < 22:
        return None
    try:
        close  = df["Close"] if "Close" in df else df.iloc[:, 0]
        volume = df["Volume"] if "Volume" in df else None
        price  = float(close.iloc[-1])
        if price <= 0:
            return None

        delta  = close.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rsi    = float((100 - 100 / (1 + gain / loss)).iloc[-1])

        ma20   = float(close.rolling(20).mean().iloc[-1])
        ma50   = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
        std20  = float(close.rolling(20).std().iloc[-1])
        bb_pos = (price - (ma20 - 2*std20)) / (4*std20) * 100 if std20 > 0 else 50

        vol_ratio = 1.0
        if volume is not None and len(volume) >= 6:
            avg_vol   = float(volume.iloc[-6:-1].mean())
            vol_ratio = round(float(volume.iloc[-1]) / avg_vol, 2) if avg_vol > 0 else 1.0

        def chg(n):
            if len(close) > n:
                return round((price - float(close.iloc[-n-1])) / float(close.iloc[-n-1]) * 100, 2)
            return 0.0

        # RSI 다이버전스: 5일 전과 비교
        rsi_5d_ago = None
        price_5d_ago = float(close.iloc[-6]) if len(close) >= 6 else None
        if len(close) >= 20:
            try:
                sub5 = close.iloc[:-5]
                d5   = sub5.diff()
                g5   = d5.clip(lower=0).rolling(14).mean()
                l5   = (-d5.clip(upper=0)).rolling(14).mean()
                rsi_5d_ago = float((100 - 100 / (1 + g5 / l5)).iloc[-1])
            except Exception:
                pass

        # 강세 다이버전스: 가격 하락 + RSI 상승
        bullish_div = bool(
            rsi_5d_ago is not None and price_5d_ago is not None
            and price < price_5d_ago       # 가격 신저점
            and rsi > rsi_5d_ago + 2       # RSI는 개선
        )

        # 오늘 캔들이 양봉인지 (하락 후 반전 신호)
        try:
            today_open  = float(df["Open"].iloc[-1]) if "Open" in df else price
            bullish_candle = price > today_open
        except Exception:
            bullish_candle = False

        return {
            "price": round(price, 2), "change_1d": chg(1),
            "change_3d": chg(3), "change_5d": chg(5),
            "rsi": round(rsi, 1), "ma20": round(ma20, 2),
            "ma50": round(ma50, 2) if ma50 else None,
            "bb_pos": round(bb_pos, 1), "vol_ratio": vol_ratio,
            "bullish_div": bullish_div,
            "bullish_candle": bullish_candle,
        }
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# Stage 1: 100 → 50 (기술지표 점수)
# ══════════════════════════════════════════════════════════════════

def _stage1_technical(universe: list, tech_map: dict,
                       candidates_meta: dict,
                       etf_returns: dict = None,
                       aria: dict = None) -> list:
    """
    yfinance 기술지표 + 다이버전스 + 섹터상대강도로 100 → 50 선별.
    """
    etf_returns = etf_returns or {}
    aria        = aria or {}
    inflows     = " ".join(aria.get("key_inflows",[])).lower()
    scored      = []

    for ticker in universe:
        tech = tech_map.get(ticker)
        if not tech:
            continue

        s = 0
        rsi   = tech["rsi"]
        bb    = tech["bb_pos"]
        chg5  = tech["change_5d"]
        vol   = tech["vol_ratio"]
        chg1  = tech["change_1d"]

        # ── RSI (최대 35점) ──────────────────────────────────
        if rsi <= 25:    s += 35
        elif rsi <= 30:  s += 28
        elif rsi <= 35:  s += 18
        elif rsi <= 40:  s +=  9
        elif rsi <= 50:  s +=  3
        elif rsi >= 75:  s -= 18
        elif rsi >= 65:  s -=  8

        # ── 볼린저 하단 (최대 30점) ──────────────────────────
        if bb <= 5:      s += 30
        elif bb <= 10:   s += 24
        elif bb <= 20:   s += 15
        elif bb <= 30:   s +=  7
        elif bb >= 90:   s -= 13
        elif bb >= 80:   s -=  6

        # ── 콤보 보너스: RSI+BB 동시 충족 (최대 25점) ────────
        # 두 조건이 함께 충족될 때 실제 스윙 기회
        if rsi <= 30 and bb <= 15:   s += 25   # 강한 과매도
        elif rsi <= 35 and bb <= 25: s += 15   # 과매도 + 하단근접
        elif rsi <= 40 and bb <= 35: s +=  8   # 약한 신호

        # ── 5일 낙폭 (최대 20점) ─────────────────────────────
        if chg5 <= -10:  s += 20
        elif chg5 <= -7: s += 14
        elif chg5 <= -5: s +=  9
        elif chg5 <= -3: s +=  4
        elif chg5 >= 15: s -= 14
        elif chg5 >= 10: s -=  7

        # ── 거래량 투매 소진 (최대 15점) ─────────────────────
        # 낙폭 중 거래량 급증 = 투매 소진 신호
        if vol >= 3.0 and chg1 < 0:   s += 15   # 급락+투매
        elif vol >= 2.0 and chg1 < 0: s += 10
        elif vol >= 3.0:               s +=  7
        elif vol >= 2.0:               s +=  5
        elif vol >= 1.5:               s +=  2

        # ── MA 지지 확인 (최대 5점) ──────────────────────────
        ma50 = tech.get("ma50")
        if ma50 and abs(tech["price"] - ma50) / ma50 < 0.03:
            s += 5

        # ── 강세 RSI 다이버전스 (최대 15점) ──────────────────
        if tech.get("bullish_div"):
            s += 15
            log.debug(f"    {ticker}: 강세 다이버전스 감지 +15")

        # ── 오늘 양봉 (하락 후 반전 신호, 5점) ──────────────
        if tech.get("bullish_candle") and chg5 < -3:
            s += 5

        # ── 섹터 상대강도 (최대 12점) ────────────────────────
        # 섹터 ETF 대비 더 많이 빠진 종목 = 개별 과매도 = 반등 여지
        ticker_sector = None
        for sec, tks in SECTOR_POOLS.items():
            if ticker in tks:
                ticker_sector = sec
                break
        if ticker_sector and ticker_sector in SECTOR_ETF:
            etf  = SECTOR_ETF[ticker_sector]
            er   = etf_returns.get(etf)
            if er is not None:
                relative = chg5 - er   # 종목 - 섹터 (음수 = 섹터보다 더 빠짐)
                if relative <= -5:     s += 12
                elif relative <= -3:   s +=  8
                elif relative <= -1:   s +=  4

        # ── 이유 자동생성 (Stage 3 Claude 판단 품질 향상) ────
        reason_parts = candidates_meta.get(ticker, {}).get("reason", "")
        if not reason_parts or reason_parts in SECTOR_POOLS:
            parts = []
            if ticker_sector:
                is_inflow = any(
                    k in inflows
                    for k in ticker_sector.lower().replace("/", " ").split()
                )
                if is_inflow:
                    parts.append(f"{ticker_sector} 섹터 유입")
            if chg5 <= -7:
                parts.append(f"5일 {chg5:+.1f}% 급락")
            elif chg5 <= -4:
                parts.append(f"5일 {chg5:+.1f}% 하락")
            if rsi <= 30:
                parts.append(f"RSI {rsi:.0f} 극단 과매도")
            elif rsi <= 40:
                parts.append(f"RSI {rsi:.0f} 과매도")
            if tech.get("bullish_div"):
                parts.append("강세 다이버전스")
            reason_parts = " | ".join(parts) if parts else f"{ticker_sector or ''} 기술적 과매도"
        else:
            reason_parts = reason_parts  # Claude 추천 이유 유지

        scored.append({
            "ticker":     ticker,
            "name":       candidates_meta.get(ticker, {}).get("name", ticker),
            "market":     candidates_meta.get(ticker, {}).get("market",
                          "KR" if ticker.endswith(".KS") else "US"),
            "currency":   "₩" if ticker.endswith(".KS") else "$",
            "hunt_reason": reason_parts,
            "tech":       tech,
            "s1_score":   round(s, 1),
        })

    scored.sort(key=lambda x: x["s1_score"], reverse=True)
    top50 = scored[:50]
    top5_str = " ".join(f"{x['ticker']}({x['s1_score']}pts)" for x in top50[:5])
    log.info(f"  Stage1: {len(scored)} → 50 | 상위: {top5_str}")
    return top50


# ══════════════════════════════════════════════════════════════════
# Stage 2: 50 → 25 (ARIA 레짐/섹터 보정)
# ══════════════════════════════════════════════════════════════════

def _stage2_aria_context(top50: list, aria: dict) -> list:
    """
    ARIA 레짐과 섹터 유입/유출 정보로 점수 보정 → 25개 선별.
    비용 $0, 파일 읽기만.
    """
    regime   = aria["regime"].lower()
    inflows  = " ".join(aria["key_inflows"]).lower()
    outflows = " ".join(aria["key_outflows"]).lower()

    # 레짐별 과매도 신뢰도
    regime_boost = 0
    if "선호" in regime:   regime_boost =  8
    elif "회피" in regime: regime_boost = -5
    elif "혼조" in regime: regime_boost =  2

    result = []
    for item in top50:
        ticker = item["ticker"]
        boost  = 0

        # 섹터 유입 보정
        for sector, tickers in SECTOR_POOLS.items():
            if ticker in tickers:
                sector_lower = sector.lower()
                if any(k in inflows for k in sector_lower.replace("/", " ").split()):
                    boost += 10
                if any(k in outflows for k in sector_lower.replace("/", " ").split()):
                    boost -= 8

        # 레짐 보정
        boost += regime_boost

        # 한국 종목 + 위험회피 → 추가 패널티
        if ticker.endswith(".KS") and "회피" in regime:
            boost -= 5

        item["s2_score"] = round(item["s1_score"] + boost, 1)
        item["aria_boost"] = boost
        result.append(item)

    result.sort(key=lambda x: x["s2_score"], reverse=True)
    top25 = result[:25]
    top5_str = " ".join(f"{x['ticker']}({x['s2_score']}pts)" for x in top25[:5])
    log.info(f"  Stage2: 50 → 25 | 상위: {top5_str}")
    return top25


# ══════════════════════════════════════════════════════════════════
# Stage 3: 25 → 10 (Claude Haiku 빠른 판단, 웹서치 없음)
# ══════════════════════════════════════════════════════════════════

def _stage3_quick_scan(top25: list, aria: dict) -> list:
    """
    Claude Haiku에게 25개를 한 번에 보여주고 10개 선별.
    웹서치 없음 — 순수 수치 기반 판단.
    비용: ~$0.04 (1회 API 콜)
    """
    items_str = "\n".join(
        f"  {i+1:2}. {x['ticker']:12} RSI:{x['tech']['rsi']:5.1f} "
        f"BB:{x['tech']['bb_pos']:5.1f}% 5d:{x['tech']['change_5d']:+.1f}% "
        f"vol:{x['tech']['vol_ratio']:.1f}x score:{x['s2_score']}"
        f"{'  ★다이버전스' if x['tech'].get('bullish_div') else ''}"
        f"  [{x.get('hunt_reason','')[:30]}]"
        for i, x in enumerate(top25)
    )
    regime = aria["regime"]
    inflows = ", ".join(aria["key_inflows"][:2]) or "없음"

    prompt = f"""25개 종목 중 단기 스윙(1~5일) 반등 가능성 TOP 10을 고르세요.
레짐: {regime} | 유입섹터: {inflows}

기술 데이터:
{items_str}

선택 기준: RSI 낮음 + BB 하단 + 최근 급락 + 레짐 부합
JSON만: {{"top10": ["TICKER1", "TICKER2", ...]}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw  = re.sub(r"```(?:json)?|```", "", resp.content[0].text).strip()
        m    = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return top25[:10]
        data    = json.loads(m.group())
        top10t  = data.get("top10", [])[:10]
        ticker_map = {x["ticker"]: x for x in top25}
        result = [ticker_map[t] for t in top10t if t in ticker_map]
        if len(result) < 10:
            # 부족하면 점수 순으로 보충
            existing = {x["ticker"] for x in result}
            for x in top25:
                if x["ticker"] not in existing and len(result) < 10:
                    result.append(x)
        log.info(f"  Stage3: 25 → 10 | {[x['ticker'] for x in result]}")
        return result
    except Exception as e:
        log.error(f"  Stage3 실패: {e}")
        return top25[:10]


# ══════════════════════════════════════════════════════════════════
# Stage 4: 10 → 5 (Analyst → Devil → Final)
# ══════════════════════════════════════════════════════════════════

def _safe_parse_json(text: str) -> dict:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    s = m.group()
    for attempt in [
        lambda x: json.loads(x),
        lambda x: json.loads(re.sub(r",\s*([}\]])", r"\1", x)),
    ]:
        try:
            return attempt(s)
        except json.JSONDecodeError:
            pass
    s3 = re.sub(r",\s*([}\]])", r"\1", s)
    s3 += "]" * (s3.count("[") - s3.count("]"))
    s3 += "}" * (s3.count("{") - s3.count("}"))
    try:
        return json.loads(s3)
    except Exception:
        return {}


def _classify_swing_type(tech: dict, hunt_reason: str) -> str:
    """기술 데이터 기반 스윙 타입 분류."""
    rsi = tech["rsi"]; bb = tech["bb_pos"]
    chg5 = tech["change_5d"]; vol = tech["vol_ratio"]
    if tech.get("bullish_div"):
        return "강세다이버전스"
    if rsi <= 30 and vol >= 1.8 and chg5 <= -5:
        return "패닉셀반등"
    if "섹터 유입" in hunt_reason and rsi <= 45:
        return "섹터로테이션"
    if tech.get("ma50") and abs(tech["price"] - tech["ma50"]) / tech["ma50"] < 0.03:
        return "MA지지반등"
    return "기술적과매도"


def _analyst_swing(ticker: str, name: str, tech: dict,
                   hunt_reason: str, aria: dict, cur: str) -> dict:
    price_str  = f"{tech['price']:,.2f}" if cur == "$" else f"{tech['price']:,.0f}"
    swing_type = _classify_swing_type(tech, hunt_reason)
    tk_events  = [tk.get("event","") for tk in aria.get("thesis_killers",[])[:3]]

    type_guide = {
        "강세다이버전스": "가격은 하락했지만 RSI가 개선됨. 매도 모멘텀 약화 신호. 1~3일 내 반등 집중 분석.",
        "패닉셀반등":     "거래량 급증+급락 = 투매 소진 패턴. 다음날 스냅백 가능성과 지속 하락 위험 분석.",
        "섹터로테이션":   "ARIA 섹터 유입 감지. 이 종목은 아직 미반영. 5~7일 추세 합류 가능성 분석.",
        "MA지지반등":     "MA50 지지선 테스트 중. 지지 성공 반등 vs 이탈 추가 하락 분기점 분석.",
        "기술적과매도":   "RSI/볼린저 과매도. 기술적 반등 가능하나 펀더멘털 확인 필요.",
    }.get(swing_type, "")

    ma50 = tech.get("ma50")
    ma_str = f"MA50 대비 {(tech['price']-ma50)/ma50*100:+.1f}%" if ma50 else "MA50 데이터 없음"

    # 티커 관련 ARIA 뉴스 추출
    relevant_news = _extract_relevant_news(ticker, name, aria)

    prompt = f"""당신은 단기 스윙 트레이딩 전문 분석가입니다.
{name}({ticker})의 1~5일 스윙 반등 가능성을 분석하세요. JSON만 반환하세요.

━━ 스윙 타입: {swing_type} ━━
{type_guide}

━━ 기술 데이터 ━━
현재가: {cur}{price_str}
변화: 1일 {tech['change_1d']:+.1f}% / 3일 {tech['change_3d']:+.1f}% / 5일 {tech['change_5d']:+.1f}%
RSI(14): {tech['rsi']} | 볼린저 위치: {tech['bb_pos']:.0f}% | 거래량: {tech['vol_ratio']:.1f}x
{ma_str} | 다이버전스: {"★감지" if tech.get("bullish_div") else "없음"} | 양봉: {"있음" if tech.get("bullish_candle") else "없음"}

━━ ARIA 뉴스 컨텍스트 ━━
{relevant_news}

━━ 시장 레짐 ━━
레짐: {aria['regime']}
유입: {', '.join(aria.get('key_inflows', [])) or '없음'}
유출: {', '.join(aria.get('key_outflows', [])) or '없음'}
Thesis Killer: {', '.join(tk_events) or '없음'}

━━ 발굴 이유 ━━
{hunt_reason}

━━ 점수 기준 ━━
강세다이버전스 확인: 기본 +15점
RSI≤30 + BB≤15%: 80~95점
RSI≤35 + BB≤25%: 65~80점
조건 1개: 45~65점
레짐 위험회피: -10점 패널티
TK 직접 관련: -15점 패널티

{{"analyst_score": 0~100,
  "swing_setup": "강한반등 또는 반등가능 또는 중립 또는 추가하락",
  "swing_type": "{swing_type}",
  "signals_fired": ["rsi_oversold/bb_touch/volume_climax/bullish_div/ma_support/sector_inflow"],
  "bull_case": "반등 근거 구체적으로 2줄",
  "expected_days": 1~7,
  "entry_zone": "{cur}범위",
  "target_1d": "{cur}가격",
  "target_5d": "{cur}가격",
  "stop_loss": "{cur}가격",
  "risk_reward": "1:X"}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=450,
            messages=[{"role": "user", "content": prompt}],
        )
        r = _safe_parse_json(re.sub(r"```(?:json)?|```", "", resp.content[0].text).strip())
        r["analyst_score"] = int(r.get("analyst_score", 50))
        r.setdefault("swing_setup", "중립"); r.setdefault("signals_fired", [])
        r.setdefault("swing_type", swing_type); r.setdefault("bull_case", "")
        r.setdefault("entry_zone", ""); r.setdefault("target_1d", "")
        r.setdefault("target_5d", ""); r.setdefault("stop_loss", "")
        r.setdefault("expected_days", 3); r.setdefault("risk_reward", "1:2")
        return r
    except Exception as e:
        log.error(f"  Analyst 실패 {ticker}: {e}")
        return {"analyst_score": 50, "swing_setup": "중립", "signals_fired": [],
                "swing_type": swing_type, "bull_case": "", "entry_zone": "",
                "target_1d": "", "target_5d": "", "stop_loss": "", "expected_days": 3}

def _devil_swing(ticker: str, tech: dict, analyst: dict, aria: dict, cur: str) -> dict:
    price_str = f"{tech['price']:,.2f}" if cur == "$" else f"{tech['price']:,.0f}"
    tk_text = "".join(
        f"\n  • {tk.get('event','')}: {tk.get('invalidates_if','')}"
        for tk in aria.get("thesis_killers",[])[:2] if tk.get("invalidates_if")
    )
    prompt = f"""{ticker}({cur}{price_str}) 반등 반박. JSON만.
Analyst:{analyst['analyst_score']}점 {analyst.get('swing_setup','')} {analyst.get('bull_case','')[:50]}
RSI:{tech['rsi']} BB:{tech['bb_pos']:.0f}% 5일:{tech['change_5d']:+.1f}%
레짐:{aria['regime']} TK:{tk_text or '없음'}
{{"devil_score":0~100,"verdict":"동의/부분동의/반대",
  "main_risk":"1줄","is_dead_cat":true/false,"thesis_killer_hit":true/false}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        r = _safe_parse_json(re.sub(r"```(?:json)?|```", "", resp.content[0].text).strip())
        r["devil_score"] = int(r.get("devil_score", 30))
        r.setdefault("verdict","부분동의"); r.setdefault("main_risk","")
        r.setdefault("thesis_killer_hit",False); r.setdefault("is_dead_cat",False)
        return r
    except Exception as e:
        log.error(f"  Devil 실패 {ticker}: {e}")
        return {"devil_score":30,"verdict":"부분동의","main_risk":"",
                "thesis_killer_hit":False,"is_dead_cat":False}



def _devil_swing(ticker: str, tech: dict, analyst: dict, aria: dict, cur: str) -> dict:
    price_str  = f"{tech['price']:,.2f}" if cur == "$" else f"{tech['price']:,.0f}"
    swing_type = analyst.get("swing_type", "기술적과매도")

    # Thesis Killer 상세 (Devil에게 구체적 반박 근거 제공)
    tk_details = ""
    for tk in aria.get("thesis_killers", [])[:3]:
        event = tk.get("event", "")
        inv   = tk.get("invalidates_if", "")
        if event:
            tk_details += f"\n  • {event}"
            if inv:
                tk_details += f" → 무효조건: {inv}"

    # 거래량 패턴 해석
    vol   = tech["vol_ratio"]
    chg1  = tech["change_1d"]
    if vol >= 2.0 and chg1 < -1:
        vol_interp = f"하락일 거래량 {vol:.1f}x — 투매 가능성 (소진이면 반등, 지속이면 추가 하락)"
    elif vol >= 2.0 and chg1 > 0:
        vol_interp = f"상승일 거래량 {vol:.1f}x — 분산 매도 가능성 (반등 후 차익실현 우려)"
    elif vol < 0.7:
        vol_interp = f"거래량 {vol:.1f}x 저조 — 관심 부족, 반등 모멘텀 약할 수 있음"
    else:
        vol_interp = f"거래량 {vol:.1f}x 보통"

    # 스윙 타입별 반박 포인트
    type_counter = {
        "강세다이버전스": "다이버전스가 발생해도 거시 악재 지속 시 무력화될 수 있음. 실제 모멘텀 전환 확인 필요.",
        "패닉셀반등":     "투매 소진처럼 보여도 추가 악재 시 '이중 바닥' 없이 직행 하락 가능.",
        "섹터로테이션":   "섹터 유입이 ETF 중심이면 개별 종목 수혜가 선택적. 이 종목에 직접 수혜 여부 불명확.",
        "MA지지반등":     "MA50 이탈 시 다음 지지선까지 빠르게 하락. 이탈 가능성이 더 높은 환경인지 점검.",
        "기술적과매도":   "RSI 과매도는 충분조건이 아님. 하락 이유가 구조적이면 과매도에서 추가 하락 가능.",
    }.get(swing_type, "")

    relevant_news = _extract_relevant_news(ticker, ticker, aria)

    prompt = f"""당신은 비판적 리스크 분석가입니다.
Analyst가 {ticker}({cur}{price_str}) 스윙 매수를 추천합니다. 반드시 반박하세요. JSON만 반환.

━━ Analyst 주장 ━━
점수: {analyst['analyst_score']} | 셋업: {analyst.get('swing_setup','')} | 타입: {swing_type}
근거: {analyst.get('bull_case','')[:80]}
신호: {', '.join(analyst.get('signals_fired',[]))}
목표: {analyst.get('target_5d','')} | 손절: {analyst.get('stop_loss','')}

━━ 반박 포인트 ━━
[스윙 타입 약점] {type_counter}

[거래량 해석]
{vol_interp}

[시장 리스크]
레짐: {aria['regime']}
Thesis Killers:{tk_details or ' 없음'}
유출 섹터: {', '.join(aria.get('key_outflows', [])) or '없음'}

[ARIA 수집 뉴스]
{relevant_news}

[기술적 위험]
RSI: {tech['rsi']} (과매도라도 구조적 하락 중엔 더 낮아질 수 있음)
BB: {tech['bb_pos']:.0f}% (하단 터치가 반등 보장 아님)
5일: {tech['change_5d']:+.1f}% (이유가 구조적이면 반등 없음)

{{"devil_score": 0~100 (높을수록 회의적),
  "verdict": "동의 또는 부분동의 또는 반대",
  "main_risk": "가장 큰 반등 실패 이유 (구체적으로 1~2줄)",
  "structural_decline": true/false (구조적 하락인가?),
  "is_dead_cat": true/false,
  "thesis_killer_hit": true/false,
  "volume_concern": "투매소진 또는 분산매도 또는 무기력 또는 정상"}}"""

    try:
        resp = Anthropic().messages.create(
            model=MODEL_H, max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        r = _safe_parse_json(re.sub(r"```(?:json)?|```", "", resp.content[0].text).strip())
        r["devil_score"] = int(r.get("devil_score", 30))
        r.setdefault("verdict", "부분동의"); r.setdefault("main_risk", "")
        r.setdefault("thesis_killer_hit", False); r.setdefault("is_dead_cat", False)
        r.setdefault("structural_decline", False); r.setdefault("volume_concern", "정상")
        return r
    except Exception as e:
        log.error(f"  Devil 실패 {ticker}: {e}")
        return {"devil_score": 30, "verdict": "부분동의", "main_risk": "",
                "thesis_killer_hit": False, "is_dead_cat": False,
                "structural_decline": False, "volume_concern": "정상"}

ALERT_THRESHOLD = 55   # 재설계된 공식 기준 (이전 68은 사실상 통과 불가)


def _final(analyst: dict, devil: dict) -> dict:
    """
    재설계된 Final 점수 공식.

    이전 문제:
      analyst × weight 구조에서 부분동의(0.72)면
      analyst=90이어도 64.8점 → 임계값 68 통과 불가

    새 공식:
      final = analyst_score - devil_score × 0.3
      Devil이 높을수록(회의적) 점수 차감
      임계값 55: 실질적으로 의미있는 타점 기준

    예시:
      A:72 D:30 (부분동의) → 72 - 9  = 63 ✅
      A:72 D:65 (반대)     → 72 - 19 = 53 ❌
      A:55 D:30            → 55 - 9  = 46 ❌
      A:80 D:35 (동의)     → 80 - 10 = 70 ✅✅
    """
    # 즉시 차단 조건
    if devil.get("thesis_killer_hit") or devil.get("is_dead_cat"):
        return {"final_score": 20, "is_entry": False, "label": "🚫 데드캣/TK"}
    if devil.get("verdict") == "반대" and devil.get("devil_score", 30) >= 70:
        return {"final_score": 25, "is_entry": False, "label": "❌ Devil 강반대"}

    a_score = analyst.get("analyst_score", 50)
    d_score = devil.get("devil_score", 30)
    setup   = analyst.get("swing_setup", "중립")

    # final = analyst - devil × 0.3
    score = round(max(0, min(100, a_score - d_score * 0.3)), 1)

    # 추가하락 셋업이면 임계값 +10 (더 엄격)
    threshold = ALERT_THRESHOLD + (10 if setup == "추가하락" else 0)

    is_entry = score >= threshold and setup not in ("추가하락", "중립")
    label    = {
        "강한반등": "🔥 강한 반등",
        "반등가능": "🟢 반등 가능",
        "중립":     "⚪ 중립",
        "추가하락": "🔴 추가 하락",
    }.get(setup, "⚪ 중립")

    return {"final_score": score, "is_entry": is_entry, "label": label}


def _stage4_full_analysis(top10: list, aria: dict) -> list:
    """
    10개에 대해 Analyst → Devil → Final 적용.
    최종 점수 상위 5개 반환 (알림 발송 대상).
    """
    results = []
    for item in top10:
        ticker = item["ticker"]
        tech   = item["tech"]
        cur    = item["currency"]
        name   = item["name"]
        reason = item.get("hunt_reason", "")

        if _is_on_cooldown(ticker):
            continue

        analyst = _analyst_swing(ticker, name, tech, reason, aria, cur)
        devil   = _devil_swing(ticker, tech, analyst, aria, cur)
        final   = _final(analyst, devil)

        log.info(f"  {ticker:12} A:{analyst['analyst_score']} "
                 f"D:{devil['devil_score']}({devil.get('verdict','?')}) "
                 f"→ F:{final['final_score']:.0f} {final['label']}")

        results.append({**item, "analyst": analyst, "devil": devil, "final": final})

    results.sort(key=lambda x: x["final"]["final_score"], reverse=True)
    top5 = results[:ANALYZE_FINAL]
    log.info(f"  Stage4: 10 → 5 | {[x['ticker'] for x in top5]}")
    return top5


# ══════════════════════════════════════════════════════════════════
# 쿨다운 / 텔레그램 / 로그
# ══════════════════════════════════════════════════════════════════

def _is_on_cooldown(ticker: str) -> bool:
    if not HUNT_COOL_FILE.exists():
        return False
    try:
        cd = json.loads(HUNT_COOL_FILE.read_text(encoding="utf-8"))
        last = cd.get(ticker)
        return bool(last) and \
               (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 3600 < HUNT_COOLDOWN_H
    except Exception:
        return False

def _set_cooldown(ticker: str):
    cd: dict = {}
    if HUNT_COOL_FILE.exists():
        try:
            cd = json.loads(HUNT_COOL_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    cd[ticker] = datetime.now().isoformat()
    HUNT_COOL_FILE.write_text(json.dumps(cd, ensure_ascii=False), encoding="utf-8")

def _send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(text); return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":text,
                  "parse_mode":"HTML","disable_web_page_preview":True},
            timeout=10,
        )
        return r.json().get("ok", False)
    except Exception as e:
        log.error(f"텔레그램 오류: {e}"); return False

def _build_alert(item: dict, aria: dict) -> str:
    ticker  = item["ticker"]; name = item["name"]
    tech    = item["tech"];   cur  = item["currency"]
    analyst = item["analyst"]; devil = item["devil"]; final = item["final"]
    now_str = datetime.now(KST).strftime("%m/%d %H:%M")
    price_str = f"{tech['price']:,.2f}" if cur == "$" else f"{tech['price']:,.0f}"
    dv_icon = {"동의":"✅","부분동의":"⚠️","반대":"❌"}.get(devil.get("verdict",""), "")
    return (
        f"🎯 <b>Jackal Hunter — 스윙 타점</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>{name} ({ticker})</b>\n"
        f"💰 {cur}{price_str}  1일:{tech['change_1d']:+.1f}%  5일:{tech['change_5d']:+.1f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>{final['final_score']:.0f}/100</b>  {final['label']}\n"
        f"📊 RSI {tech['rsi']} | BB {tech['bb_pos']:.0f}% | 거래량 {tech['vol_ratio']:.1f}x\n"
        f"💡 {item.get('hunt_reason','')[:55]}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🐂 {analyst.get('bull_case','')[:55]}\n"
        f"🔴 Devil {dv_icon}: {devil.get('main_risk','')[:45]}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 진입:{analyst.get('entry_zone','')}  "
        f"📈 5일:{analyst.get('target_5d','')}  "
        f"🛑 손절:{analyst.get('stop_loss','')}\n"
        f"⏰ {now_str} KST | Jackal Hunter"
    )

def _build_summary(top5: list, aria: dict) -> str:
    now_str  = datetime.now(KST).strftime("%m/%d %H:%M")
    best     = top5[0] if top5 else None
    top_score = best["final"]["final_score"] if best else 0

    lines = [
        "📊 <b>Jackal Hunter — 타점 없음</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"최고점수: {top_score:.0f}/100 (임계값 {ALERT_THRESHOLD})",
        "",
    ]
    for x in top5:
        f    = x["final"]
        tech = x["tech"]
        setup = x["analyst"].get("swing_setup","중립")
        icon  = {"강한반등":"🔥","반등가능":"🟢","중립":"⚪","추가하락":"🔴"}.get(setup,"⚪")
        div_mark = "★" if tech.get("bullish_div") else ""
        lines.append(
            f"{icon} <b>{x['name']}</b>({x['ticker']}) {div_mark} "
            f"{f['final_score']:.0f}점 | RSI {tech['rsi']} | "
            f"5일 {tech['change_5d']:+.1f}% | {setup}"
        )
    lines += [
        "━━━━━━━━━━━━━━━━━━━━",
        f"🌐 {aria['regime'][:35]}",
        f"⏰ {now_str} KST | Jackal Hunter",
    ]
    return "\n".join(lines)

def _save_log(entry: dict):
    logs: list = []
    if HUNT_LOG_FILE.exists():
        try:
            logs = json.loads(HUNT_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    logs.append(entry)
    HUNT_LOG_FILE.write_text(json.dumps(logs[-500:], ensure_ascii=False, indent=2), encoding="utf-8")


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════

def _send_status(msg: str, aria: dict = None):
    """항상 발송되는 상태 메시지."""
    now_str = datetime.now(KST).strftime("%m/%d %H:%M")
    regime  = aria.get("regime","")[:30] if aria else ""
    sep = "━━━━━━━━━━━━━━━━━━━━"
    text = "\n".join([
        "🦊 <b>Jackal Hunter</b>",
        sep, msg, sep,
        f"🌐 {regime}",
        f"⏰ {now_str} KST",
    ])
    _send_telegram(text)


def run_hunt(force: bool = False) -> dict:
    now_kst = datetime.now(KST)
    log.info(f"🎯 Jackal Hunter | {now_kst.strftime('%Y-%m-%d %H:%M KST')}")

    if not ARIA_BASELINE.exists():
        log.info("  ARIA baseline 없음 — 스킵")
        _send_status("⚠️ ARIA morning 분석 대기 중\n(매일 오전 ARIA 실행 후 활성화)")
        return {"hunted": 0, "alerted": 0}

    aria = _load_aria_context()
    if not aria["regime"]:
        log.info("  ARIA 레짐 없음 — 스킵")
        _send_status("⚠️ ARIA 레짐 데이터 없음", aria)
        return {"hunted": 0, "alerted": 0}

    log.info(f"  ARIA: {aria['regime'][:40]} | 유입: {aria['key_inflows'][:2]}")

    # ── Universe 구성 ─────────────────────────────────────────────
    universe = _build_universe(aria)

    # candidates_meta: Claude 추천 종목의 이름/이유 보존
    candidates_meta = {}
    for sector, tickers in SECTOR_POOLS.items():
        for t in tickers:
            candidates_meta[t] = {"name": t, "market": "KR" if t.endswith(".KS") else "US", "reason": sector}

    # ── 기술지표 + ETF 수익률 일괄 계산 ────────────────────────────
    tech_map    = _batch_technicals(universe)
    etf_returns = _fetch_etf_returns()
    log.info(f"  섹터 ETF 수익률: {etf_returns}")

    # ── Stage 1: 100 → 50 ────────────────────────────────────────
    top50 = _stage1_technical(universe, tech_map, candidates_meta,
                               etf_returns=etf_returns, aria=aria)
    if not top50:
        log.info("  Stage1: 후보 없음")
        _send_status(f"📊 Stage1: 후보 없음\nUniverse {len(universe)}개 스캔\n기술지표 조건 충족 종목 없음", aria)
        return {"hunted": 0, "alerted": 0}

    # ── Stage 2: 50 → 25 ─────────────────────────────────────────
    top25 = _stage2_aria_context(top50, aria)

    # ── Stage 3: 25 → 10 ─────────────────────────────────────────
    top10 = _stage3_quick_scan(top25, aria)

    # ── Stage 4: 10 → 5 (Analyst + Devil) ───────────────────────
    log.info("  Stage4: Analyst + Devil 실행 (10종목)...")
    top5  = _stage4_full_analysis(top10, aria)

    # top5 없는 경우 처리
    if not top5:
        _send_status(f"📊 스캔 완료 — 타점 없음\nUniverse {len(universe)}개 → Stage4 후보 없음", aria)
        return {"hunted": 0, "alerted": 0}

    alerted = 0
    for item in top5:
        final = item["final"]

        if final["is_entry"]:
            ok = _send_telegram(_build_alert(item, aria))
            if ok:
                _set_cooldown(item["ticker"])
                alerted += 1
                log.info(f"  ✅ 알림: {item['ticker']}")

        _save_log({
            "timestamp":         now_kst.isoformat(),
            "ticker":            item["ticker"],
            "name":              item["name"],
            "price_at_hunt":     item["tech"]["price"],
            "rsi":               item["tech"]["rsi"],
            "bb_pos":            item["tech"]["bb_pos"],
            "change_5d":         item["tech"]["change_5d"],
            "vol_ratio":         item["tech"]["vol_ratio"],
            "s1_score":          item.get("s1_score", 0),
            "s2_score":          item.get("s2_score", 0),
            "aria_regime":       aria["regime"],
            "aria_inflows":      aria["key_inflows"],
            "analyst_score":     item["analyst"]["analyst_score"],
            "swing_setup":       item["analyst"].get("swing_setup",""),
            "signals_fired":     item["analyst"].get("signals_fired",[]),
            "devil_verdict":     item["devil"].get("verdict",""),
            "devil_score":       item["devil"]["devil_score"],
            "thesis_killer_hit": item["devil"].get("thesis_killer_hit",False),
            "final_score":       final["final_score"],
            "is_entry":          final["is_entry"],
            "alerted":           final["is_entry"],
            "outcome_checked":   False,
            "price_5d_later":    None,
            "outcome_pct":       None,
            "outcome_correct":   None,
        })

    # 요약 메시지: 타점 없어도 항상 발송
    if alerted == 0:
        _send_telegram(_build_summary(top5, aria))
    log.info(f"  발송 완료: 타점알림 {alerted}건 + 요약 {1 if alerted==0 else 0}건")

    log.info(f"🎯 완료 | 분석 {len(top5)}종목 | 알림 {alerted}건")
    return {"hunted": len(top5), "alerted": alerted}
