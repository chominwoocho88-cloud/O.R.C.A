"""Market-facing analysis helpers extracted from orca.analysis."""

from __future__ import annotations

from ._analysis_common import _load, _now, _save, _today
from .data import load_market_data
from .paths import (
    BASELINE_FILE,
    PORTFOLIO_FILE,
    ROTATION_FILE,
    SENTIMENT_FILE,
    WEIGHTS_FILE,
)


_DEFAULT_WEIGHTS = {
    "version": 1,
    "last_updated": "",
    "total_learning_cycles": 0,
    "sentiment": {
        "시장레짐": 1.0,
        "추세방향": 1.0,
        "변동성지수": 1.2,
        "자금흐름": 1.0,
        "반론강도": 0.8,
        "한국시장": 0.8,
        "숨은시그널": 0.7,
    },
    "prediction_confidence": {
        "금리": 1.0,
        "환율": 1.0,
        "주식": 1.0,
        "지정학": 0.7,
        "원자재": 1.0,
        "기업": 1.0,
        "기타": 0.8,
    },
    "learning_log": [],
    "component_accuracy": {
        "시장레짐": {"correct": 0, "total": 0},
        "추세방향": {"correct": 0, "total": 0},
        "변동성지수": {"correct": 0, "total": 0},
        "자금흐름": {"correct": 0, "total": 0},
    },
}


def load_weights() -> dict:
    saved = _load(WEIGHTS_FILE)
    if not saved:
        return _DEFAULT_WEIGHTS.copy()
    for key, val in _DEFAULT_WEIGHTS.items():
        if key not in saved:
            saved[key] = val
        elif isinstance(val, dict):
            for k2, v2 in val.items():
                if k2 not in saved[key]:
                    saved[key][k2] = v2
    return saved


def get_sentiment_weights() -> dict:
    return load_weights().get("sentiment", _DEFAULT_WEIGHTS["sentiment"])


def calculate_sentiment(report: dict, market_data: dict = None) -> dict:
    weights = get_sentiment_weights()
    regime = report.get("market_regime", "")
    trend = report.get("trend_phase", "")
    devil = report.get("counterarguments", [])
    hidden = report.get("hidden_signals", [])
    korea = report.get("korea_focus", {})
    vi = report.get("volatility_index", {})

    vix_val = None
    vkospi_val = None
    if market_data:
        try:
            vix_val = float(str(market_data.get("vix", "")).replace(",", ""))
        except Exception:
            pass
        try:
            vkospi_val = float(str(market_data.get("vkospi", "")).replace(",", ""))
        except Exception:
            pass
    if vix_val is None:
        try:
            vix_val = float(str(vi.get("vix", "20")).replace(",", ""))
        except Exception:
            vix_val = 20.0
    if vkospi_val is None:
        try:
            vkospi_val = float(str(vi.get("vkospi", "15")).replace(",", ""))
        except Exception:
            vkospi_val = 15.0

    comps = {}

    reg_s = 70 if "선호" in regime else 30 if "회피" in regime else 50 if "전환" in regime else 50
    comps["시장레짐"] = round(reg_s * weights.get("시장레짐", 1.0))

    tr_s = 70 if "상승" in trend else 30 if "하락" in trend else 50
    comps["추세방향"] = round(tr_s * weights.get("추세방향", 1.0))

    if vix_val < 15:
        vi_s = 70
    elif vix_val < 20:
        vi_s = 60
    elif vix_val < 25:
        vi_s = 45
    elif vix_val < 30:
        vi_s = 35
    else:
        vi_s = 20
    comps["변동성지수"] = round(vi_s * weights.get("변동성지수", 1.2))

    inflows = len(report.get("inflows", []))
    outflows = len(report.get("outflows", []))
    fl_s = 60 if inflows > outflows else 40 if outflows > inflows else 50
    comps["자금흐름"] = round(fl_s * weights.get("자금흐름", 1.0))

    high_risk = sum(1 for d in devil if d.get("risk_level") == "높음")
    ca_s = 40 if high_risk >= 2 else 55 if high_risk == 1 else 65
    comps["반론강도"] = round(ca_s * weights.get("반론강도", 0.8))

    kor_assess = korea.get("assessment", "")
    ko_s = (
        60
        if "긍정" in kor_assess or "강세" in kor_assess
        else 40 if "부정" in kor_assess or "약세" in kor_assess
        else 50
    )
    comps["한국시장"] = round(ko_s * weights.get("한국시장", 0.8))

    hi_conf = sum(1 for h in hidden if h.get("confidence") == "높음")
    hs_s = 65 if hi_conf >= 2 else 58 if hi_conf == 1 else 50
    comps["숨은시그널"] = round(hs_s * weights.get("숨은시그널", 0.7))

    fred_score = 50
    fred_indicators = {}
    if market_data:
        hy = market_data.get("hy_spread")
        yc = market_data.get("yield_curve")
        cs = market_data.get("consumer_sent")
        if hy is not None:
            try:
                hy_f = float(hy)
                fred_indicators["hy_spread"] = hy_f
                if hy_f < 3:
                    fred_score += 5
                elif hy_f > 5:
                    fred_score -= 10
            except Exception:
                pass
        if yc is not None:
            try:
                yc_f = float(yc)
                fred_indicators["yield_curve"] = yc_f
                if yc_f < 0:
                    fred_score -= 8
                elif yc_f > 1:
                    fred_score += 5
            except Exception:
                pass
        if cs is not None:
            try:
                cs_f = float(cs)
                fred_indicators["consumer_sent"] = cs_f
                if cs_f > 80:
                    fred_score += 5
                elif cs_f < 60:
                    fred_score -= 5
            except Exception:
                pass
        fred_score = max(20, min(80, fred_score))

    total_w = sum(weights.get(k, 1.0) for k in comps)
    raw = sum(comps.values()) / max(total_w, 1)
    raw = max(0, min(100, raw))

    fg_raw = None
    if market_data:
        try:
            fg_raw = float(str(market_data.get("fear_greed_value", "")).replace(",", ""))
        except Exception:
            pass
    if fg_raw is None:
        try:
            fg_raw = float(str(vi.get("fear_greed", "50")).replace(",", ""))
        except Exception:
            fg_raw = 50.0

    internal_raw = raw
    score = round(raw * 0.7 + fg_raw * 0.3 + (fred_score - 50) * 0.1)
    score = max(0, min(100, score))

    divergence = abs(internal_raw - (fg_raw or 50))
    divergence_flag = divergence >= 25

    if score <= 20:
        level, emoji = "극단공포", "😱"
    elif score <= 40:
        level, emoji = "공포", "😰"
    elif score <= 60:
        level, emoji = "중립", "😐"
    elif score <= 80:
        level, emoji = "탐욕", "😏"
    else:
        level, emoji = "극단탐욕", "🤑"

    return {
        "date": _today(),
        "score": score,
        "level": level,
        "emoji": emoji,
        "components": comps,
        "regime": regime,
        "trend": trend,
        "vix_level": vi.get("level", ""),
        "vix_val": vix_val,
        "vkospi_val": vkospi_val,
        "fear_greed": fg_raw,
        "internal_raw": internal_raw,
        "divergence": divergence_flag,
        "fred_score": fred_score,
        "fred_indicators": fred_indicators,
    }


def _analyze_trend(history: list) -> dict:
    if len(history) < 2:
        return {
            "direction": "neutral",
            "change": 0,
            "avg_7d": 50,
            "min_30d": 50,
            "max_30d": 50,
            "avg_30d": 50,
        }
    sc7 = [h["score"] for h in history[-7:]]
    sc30 = [h["score"] for h in history[-30:]]
    half = len(sc7) // 2
    chg = round(sum(sc7[half:]) / max(len(sc7) - half, 1) - sum(sc7[:half]) / max(half, 1), 1)
    return {
        "direction": "improving" if chg > 5 else "deteriorating" if chg < -5 else "stable",
        "change": chg,
        "avg_7d": round(sum(sc7) / len(sc7), 1),
        "min_30d": min(sc30),
        "max_30d": max(sc30),
        "avg_30d": round(sum(sc30) / len(sc30), 1),
    }


def run_sentiment(report: dict, market_data: dict = None) -> dict:
    data = _load(SENTIMENT_FILE, {"history": [], "current": None})
    new = calculate_sentiment(report, market_data)
    history = data.get("history", [])

    _BLEND_WEIGHT = {"MORNING": 1.0, "AFTERNOON": 0.7, "EVENING": 0.8, "DAWN": 0.5}
    mode = report.get("mode", "MORNING")
    new_weight = _BLEND_WEIGHT.get(mode, 0.6)

    try:
        md = load_market_data()
        sp_chg = float(str(md.get("sp500_change", "0")).replace("%", "").replace("+", ""))
        if sp_chg <= -3:
            new["score"] = min(new["score"] + 8, 100)
            new["rebound_bias"] = True
    except Exception:
        pass

    if history:
        prev = history[-1]
        prev_score = prev.get("score", new["score"])
        blended = round(prev_score * (1 - new_weight) + new["score"] * new_weight)
        new["score"] = max(0, min(100, blended))

    history = [h for h in history if h.get("date") != _today()]
    history.append(new)
    history = history[-90:]

    trend = _analyze_trend(history)
    data = {"history": history, "current": new, "trend": trend, "last_updated": _now().isoformat()}
    _save(SENTIMENT_FILE, data)
    return new


def run_portfolio(report: dict, market_data: dict = None) -> dict:
    portfolio = _load(PORTFOLIO_FILE, {"holdings": []})
    if not portfolio.get("holdings"):
        print("  포트폴리오 없음 — 스킵")
        return {}

    regime = report.get("market_regime", "")
    inflows = [i.get("zone", "") for i in report.get("inflows", [])[:3]]
    outflows = [o.get("zone", "") for o in report.get("outflows", [])[:3]]

    assessments = []
    for h in portfolio["holdings"]:
        ticker = h.get("ticker_yf") or h.get("ticker", "")
        name = h.get("name", ticker)
        sector = h.get("sector", "")
        signal = "neutral"
        if any(sector.lower() in i.lower() for i in inflows if sector):
            signal = "bullish"
        elif any(sector.lower() in o.lower() for o in outflows if sector):
            signal = "bearish"
        assessments.append({"ticker": ticker, "name": name, "signal": signal, "regime": regime})

    print(f"  포트폴리오 {len(assessments)}종목 평가 완료")
    return {"assessments": assessments}


def run_rotation(report: dict) -> dict:
    data = _load(ROTATION_FILE, {"ranking": [], "history": []})
    inflows = report.get("inflows", [])
    outflows = report.get("outflows", [])

    scores: dict = {}
    for item in inflows:
        zone = item.get("zone", "")
        mom = item.get("momentum", "")
        if zone:
            s = 3 if mom == "강함" else 2 if mom == "형성중" else 1
            scores[zone] = scores.get(zone, 0) + s
    for item in outflows:
        zone = item.get("zone", "")
        sev = item.get("severity", "")
        if zone:
            s = -3 if sev == "높음" else -2 if sev == "보통" else -1
            scores[zone] = scores.get(zone, 0) + s

    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    rotation_signal = {}
    if len(ranking) >= 2:
        top = ranking[0]
        bottom = ranking[-1]
        if top[1] > 0 and bottom[1] < 0:
            rotation_signal = {
                "from": bottom[0],
                "to": top[0],
                "strength": "강함" if top[1] >= 3 else "보통",
            }

    history = data.get("history", [])
    history.append({"date": _today(), "ranking": ranking[:8], "rotation_signal": rotation_signal})
    history = history[-30:]

    result = {
        "ranking": ranking,
        "rotation_signal": rotation_signal,
        "history": history,
        "last_updated": _today(),
    }
    _save(ROTATION_FILE, result)
    return result


def save_baseline(report: dict, market_data: dict = None) -> None:
    baseline = {
        "date": _today(),
        "one_line_summary": report.get("one_line_summary", ""),
        "market_regime": report.get("market_regime", ""),
        "trend_phase": report.get("trend_phase", ""),
        "confidence": report.get("confidence_overall", ""),
        "top_headlines": report.get("top_headlines", [])[:5],
        "inflows": report.get("inflows", [])[:4],
        "outflows": report.get("outflows", [])[:3],
        "thesis_killers": report.get("thesis_killers", [])[:3],
        "actionable_watch": report.get("actionable_watch", [])[:5],
        "korea_focus": report.get("korea_focus", {}),
        "hidden_signals": report.get("hidden_signals", [])[:3],
    }
    if market_data:
        baseline["market_snapshot"] = {
            k: market_data.get(k)
            for k in [
                "sp500",
                "nasdaq",
                "vix",
                "kospi",
                "krw_usd",
                "fear_greed_value",
                "fear_greed_rating",
            ]
        }
    _save(BASELINE_FILE, baseline)


def build_baseline_context(memory: list) -> str:
    if not isinstance(memory, list) or not memory:
        return ""
    prev = memory[-1]
    if not isinstance(prev, dict):
        return ""
    return (
        f"\n[어제 분석] {prev.get('analysis_date','')} "
        f"레짐={prev.get('market_regime','')} "
        f"요약={prev.get('one_line_summary','')[:50]}"
    )


def get_regime_drift(current_regime: str) -> str:
    data = _load(SENTIMENT_FILE, {})
    history = data.get("history", [])
    if len(history) < 3:
        return "STABLE"
    recent_regimes = [h.get("regime", "") for h in history[-3:]]
    if all(r == current_regime for r in recent_regimes):
        return "STABLE"
    if recent_regimes.count(current_regime) == 0:
        return "SHIFT"
    return "DRIFT"
