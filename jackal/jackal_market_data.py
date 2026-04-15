"""
jackal_market_data.py
Jackal 전용 시장 데이터 수집 — ARIA와 완전 독립

수집 데이터:
  - yfinance:  종목 현재가 + 기술 지표용 일봉
  - FRED API:  VIX / HY스프레드 / 장단기금리차 / 달러지수 / 소비자심리
  - KRX API:   KOSPI 종가
  - FSC API:   삼성전자·SK하이닉스 공식 종가 / 금시세 / 유류가
  - sentiment: data/sentiment.json (ARIA가 생성, 있으면 참고)
"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yfinance as yf

log = logging.getLogger("jackal_market_data")

KST = timezone(timedelta(hours=9))


# ══════════════════════════════════════════════════════════════════
# FRED API
# ══════════════════════════════════════════════════════════════════

def fetch_fred() -> dict:
    """
    FRED API — 핵심 매크로 6개 지표
    결과: {vix, hy_spread, yield_curve, consumer_sent, dxy, source}
    """
    result = {
        "vix":           None,   # VIX 공포지수
        "hy_spread":     None,   # 하이일드 스프레드 (높을수록 위험회피)
        "yield_curve":   None,   # 장단기 금리차 T10Y2Y (음수=침체 신호)
        "consumer_sent": None,   # 미시간 소비자심리
        "dxy":           None,   # 달러인덱스 (높을수록 신흥국 부담)
        "source":        False,
    }
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key:
        log.warning("  FRED_API_KEY 미설정")
        return result

    SERIES = {
        "VIXCLS":       "vix",
        "BAMLH0A0HYM2": "hy_spread",
        "T10Y2Y":       "yield_curve",
        "UMCSENT":      "consumer_sent",
        "DTWEXBGS":     "dxy",
    }
    base    = "https://api.stlouisfed.org/fred/series/observations"
    success = 0

    for series_id, key in SERIES.items():
        try:
            r = httpx.get(base, params={
                "series_id":  series_id,
                "api_key":    api_key.strip(),
                "sort_order": "desc",
                "limit":      5,
                "file_type":  "json",
            }, timeout=8)
            if r.status_code != 200:
                continue
            obs = [o for o in r.json().get("observations", [])
                   if o.get("value", "") not in (".", "")]
            if obs:
                result[key] = round(float(obs[0]["value"]), 2)
                success += 1
                log.info(f"  FRED {series_id}: {result[key]}")
        except Exception as e:
            log.warning(f"  FRED {series_id} 실패: {e}")

    result["source"] = success >= 2
    return result


# ══════════════════════════════════════════════════════════════════
# KRX API
# ══════════════════════════════════════════════════════════════════

def fetch_krx() -> dict:
    """
    KRX OpenAPI — KOSPI 지수 종가
    (외국인 수급은 유료 미제공 — KOSPI 시세만 수집)
    """
    result = {"kospi_close": None, "kospi_change": None, "source": False}
    api_key = os.environ.get("KRX_API_KEY", "")
    if not api_key:
        log.warning("  KRX_API_KEY 미설정")
        return result

    now = datetime.now(KST)
    d   = now if now.hour >= 18 else now - timedelta(days=1)
    for _ in range(7):
        if d.weekday() < 5:
            break
        d -= timedelta(days=1)
    date_str = d.strftime("%Y%m%d")

    try:
        r = httpx.get(
            "https://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd",
            headers={"AUTH_KEY": api_key.strip(), "Accept": "application/json"},
            params={"basDd": date_str},
            timeout=12,
            follow_redirects=True,
        )
        if r.status_code == 200:
            rows = r.json().get("OutBlock_1", [])
            for row in rows:
                nm = str(row.get("IDX_NM", "") or row.get("idxNm", ""))
                if "종합" in nm or "KOSPI" in nm.upper():
                    close = str(row.get("CLSPRC", "") or row.get("clsPrc", ""))
                    fluc  = str(row.get("FLUC_RT", "") or row.get("flucRt", ""))
                    if close:
                        result["kospi_close"]  = close
                        result["kospi_change"] = fluc
                        result["source"]       = True
                        log.info(f"  KRX KOSPI: {close} ({fluc}%)")
                        break
        else:
            log.warning(f"  KRX API {r.status_code}")
    except Exception as e:
        log.warning(f"  KRX 실패: {e}")

    return result


# ══════════════════════════════════════════════════════════════════
# FSC API
# ══════════════════════════════════════════════════════════════════

def fetch_fsc() -> dict:
    """
    금융위원회 공공데이터 API
    - 삼성전자·SK하이닉스 공식 종가
    - 금시세 (안전자산)
    - 유류가 (에너지 비용)
    """
    result = {
        "samsung":       None,
        "sk_hynix":      None,
        "gold":          None,   # 금 시세 (원/kg)
        "oil_diesel":    None,   # 경유 (원/L)
        "source":        False,
    }
    api_key = os.environ.get("FSCAPI_KEY", "")
    if not api_key:
        log.warning("  FSCAPI_KEY 미설정")
        return result

    BASE = "https://apis.data.go.kr/1160100/service"
    now  = datetime.now(KST)
    d    = now - timedelta(days=1)
    for _ in range(7):
        if d.weekday() < 5:
            break
        d -= timedelta(days=1)
    date_str = d.strftime("%Y%m%d")

    def _get(endpoint, params):
        try:
            r = httpx.get(BASE + endpoint, params={
                "serviceKey": api_key.strip(),
                "numOfRows":  "5",
                "pageNo":     "1",
                "resultType": "json",
                **params,
            }, timeout=8)
            if r.status_code != 200:
                return []
            items = r.json().get("response", {}).get("body", {}).get("items", {})
            item  = items.get("item", []) if isinstance(items, dict) else []
            return item if isinstance(item, list) else [item]
        except Exception as e:
            log.warning(f"  FSC 실패: {e}")
            return []

    success = 0

    # 삼성전자·SK하이닉스
    for code, key in [("005930", "samsung"), ("000660", "sk_hynix")]:
        rows = _get("/GetStockSecuritiesInfoService/getStockPriceInfo",
                    {"likeSrtnCd": code, "basDd": date_str})
        if rows and rows[0].get("clpr"):
            result[key] = str(rows[0]["clpr"])
            success += 1
            log.info(f"  FSC {key}: {result[key]}원")

    # 금시세
    rows = _get("/GetGeneralProductInfoService/getGoldPriceInfo", {"basDd": date_str})
    if rows:
        for row in rows:
            if "99.99" in str(row.get("itmsNm", "")) and "1kg" in str(row.get("itmsNm", "")):
                result["gold"] = str(row.get("clpr", ""))
                success += 1
                break
        if not result["gold"] and rows:
            result["gold"] = str(rows[0].get("clpr", ""))
            success += 1

    # 유류가
    rows = _get("/GetGeneralProductInfoService/getOilPriceInfo", {"basDd": date_str})
    for row in rows:
        ctg = str(row.get("oilCtg", ""))
        prc = str(row.get("wtAvgPrcCptn", "") or row.get("clpr", ""))
        if "경유" in ctg and prc and prc != "0":
            result["oil_diesel"] = prc
            success += 1

    result["source"] = success >= 2
    return result


# ══════════════════════════════════════════════════════════════════
# Sentiment (ARIA 생성 파일 — 있으면 참고, 없으면 기본값)
# ══════════════════════════════════════════════════════════════════

def load_sentiment() -> dict:
    """data/sentiment.json 로드 (ARIA가 생성, 없으면 기본값)"""
    path = Path("data") / "sentiment.json"
    if not path.exists():
        return {"score": 50, "level": "중립", "trend": "횡보추세", "regime": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cur  = data.get("current", {})
        return {
            "score":  cur.get("score", 50),
            "level":  cur.get("level", "중립"),
            "trend":  cur.get("trend", "횡보추세"),
            "regime": cur.get("regime", ""),
        }
    except Exception:
        return {"score": 50, "level": "중립", "trend": "횡보추세", "regime": ""}


# ══════════════════════════════════════════════════════════════════
# 종목별 기술 지표 (yfinance)
# ══════════════════════════════════════════════════════════════════

def fetch_technicals(ticker: str) -> dict | None:
    """
    65일(+52주 고저점용 1년) 일봉으로 기술 지표 계산.

    기존: price, change_1d, change_5d, rsi, ma20, ma50, bb_pos, vol_ratio
    추가:
      change_3d       - 3일 수익률 (sector_rebound 신호에 필요)
      rsi_divergence  - 강세 다이버전스 (가격↓ + RSI↑) → 반등 선행 신호
      52w_pos         - 52주 고/저 대비 현재 위치 (0~100%)
      bb_width        - 볼린저 밴드 폭 (수축→확장 예고)
      bb_expanding    - 밴드 폭 최근 3일 확장 여부
      vol_trend_5d    - 5일 거래량 추세 (양수=증가, 음수=감소)
      vol_accumulation- 가격 하락 중 거래량 증가 (매집 신호)
      ma_alignment    - MA 배열 (bullish/bearish/neutral)
    """
    try:
        # 52주 위치를 위해 1년 데이터 사용
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        if len(hist) < 22:
            return None

        close  = hist["Close"]
        volume = hist["Volume"]
        price  = float(close.iloc[-1])
        prev   = float(close.iloc[-2])

        # ── 기본 수익률 ────────────────────────────────────────────
        def chg(n: int) -> float:
            return round((price - float(close.iloc[-n-1])) / float(close.iloc[-n-1]) * 100, 2)                    if len(close) > n else 0.0

        chg_1d = chg(1)
        chg_3d = chg(3)
        chg_5d = chg(5)

        # ── RSI 14 ─────────────────────────────────────────────────
        delta  = close.diff()
        gain   = delta.clip(lower=0).rolling(14).mean()
        loss   = (-delta.clip(upper=0)).rolling(14).mean()
        rsi_s  = 100 - 100 / (1 + gain / loss)
        rsi    = float(rsi_s.iloc[-1])

        # ── RSI 강세 다이버전스 감지 ──────────────────────────────
        # 조건: 최근 5일 가격 하락 + RSI는 상승 → 매도 소진 신호
        rsi_divergence = False
        if len(rsi_s) >= 6 and chg_5d < -1.5:
            rsi_now  = float(rsi_s.iloc[-1])
            rsi_5d   = float(rsi_s.iloc[-6])
            price_now = price
            price_5d  = float(close.iloc[-6])
            if price_now < price_5d and rsi_now > rsi_5d + 2:
                rsi_divergence = True   # 가격 낮아졌는데 RSI 올라감

        # ── MA ─────────────────────────────────────────────────────
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None

        # MA 배열: 현재가/MA20/MA50 상대 위치
        if ma50:
            if price > ma20 > ma50:
                ma_alignment = "bullish"
            elif price < ma20 < ma50:
                ma_alignment = "bearish"
            else:
                ma_alignment = "neutral"
        else:
            ma_alignment = "neutral"

        # ── 볼린저 밴드 ────────────────────────────────────────────
        std20   = float(close.rolling(20).std().iloc[-1])
        bb_upper = ma20 + 2 * std20
        bb_lower = ma20 - 2 * std20
        bb_pos  = (price - bb_lower) / (bb_upper - bb_lower) * 100 if std20 > 0 else 50.0
        bb_pos  = round(bb_pos, 1)

        # BB 폭 및 확장 여부
        bb_width = round((bb_upper - bb_lower) / ma20 * 100, 2) if ma20 > 0 else 0
        bb_width_3d_ago = None
        if len(close) >= 23:
            std_3d = float(close.rolling(20).std().iloc[-4])
            ma_3d  = float(close.rolling(20).mean().iloc[-4])
            bb_width_3d_ago = (ma_3d + 2*std_3d - (ma_3d - 2*std_3d)) / ma_3d * 100 if ma_3d > 0 else 0
        bb_expanding = (bb_width_3d_ago is not None and bb_width > bb_width_3d_ago * 1.05)

        # ── 거래량 ─────────────────────────────────────────────────
        avg_vol   = float(volume.iloc[-6:-1].mean()) if len(volume) >= 6 else float(volume.mean())
        vol_ratio = round(float(volume.iloc[-1]) / avg_vol, 2) if avg_vol > 0 else 1.0

        # 5일 거래량 추세 (선형 회귀 기울기 대신 단순 비교)
        if len(volume) >= 10:
            vol_recent = float(volume.iloc[-5:].mean())
            vol_prior  = float(volume.iloc[-10:-5].mean())
            vol_trend_5d = round((vol_recent - vol_prior) / vol_prior * 100, 1) if vol_prior > 0 else 0
        else:
            vol_trend_5d = 0

        # 매집 신호: 가격 하락 중 거래량 증가
        vol_accumulation = chg_5d < -2.0 and vol_trend_5d > 15

        # ── 52주 위치 ──────────────────────────────────────────────
        high_52w = float(close.rolling(252).max().iloc[-1]) if len(close) >= 50 else float(close.max())
        low_52w  = float(close.rolling(252).min().iloc[-1]) if len(close) >= 50 else float(close.min())
        if high_52w > low_52w:
            pos_52w = round((price - low_52w) / (high_52w - low_52w) * 100, 1)
        else:
            pos_52w = 50.0

        return {
            # 기존
            "price":          round(price, 2),
            "change_1d":      chg_1d,
            "change_3d":      chg_3d,
            "change_5d":      chg_5d,
            "rsi":            round(rsi, 1),
            "ma20":           round(ma20, 2),
            "ma50":           round(ma50, 2) if ma50 else None,
            "bb_pos":         bb_pos,
            "vol_ratio":      vol_ratio,
            # 신규
            "rsi_divergence": rsi_divergence,
            "52w_pos":        pos_52w,
            "bb_width":       bb_width,
            "bb_expanding":   bb_expanding,
            "vol_trend_5d":   vol_trend_5d,
            "vol_accumulation": vol_accumulation,
            "ma_alignment":   ma_alignment,
        }
    except Exception as e:
        log.error(f"  {ticker} 기술 지표 실패: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# 통합 수집
# ══════════════════════════════════════════════════════════════════

def fetch_all() -> dict:
    """
    모든 외부 데이터 한 번에 수집.
    Returns: {fred, krx, fsc, sentiment}
    """
    log.info("📊 시장 데이터 수집 시작")
    fred = fetch_fred()
    krx  = fetch_krx()
    fsc  = fetch_fsc()
    sent = load_sentiment()
    log.info(
        f"  FRED {'✅' if fred['source'] else '❌'} | "
        f"KRX {'✅' if krx['source'] else '❌'} | "
        f"FSC {'✅' if fsc['source'] else '❌'} | "
        f"Sentiment {sent['score']}점"
    )
    return {"fred": fred, "krx": krx, "fsc": fsc, "sentiment": sent}
