import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

KST = timezone(timedelta(hours=9))

# ── 포트폴리오 설정 ────────────────────────────────────────────────────────────
PORTFOLIO = {
    "holdings": [
        {"name": "엔비디아",      "ticker": "nvda",      "weight": 35.0, "type": "US_stock",  "sector": "반도체/AI"},
        {"name": "SK하이닉스",    "ticker": "sk_hynix",  "weight": 15.0, "type": "KR_stock",  "sector": "반도체"},
        {"name": "삼성전자",      "ticker": "samsung",   "weight": 10.0, "type": "KR_stock",  "sector": "반도체/전자"},
        {"name": "브로드컴",      "ticker": "avgo",      "weight": 10.0, "type": "US_stock",  "sector": "반도체/AI"},
        {"name": "카카오",        "ticker": "kakao",     "weight": 5.0,  "type": "KR_stock",  "sector": "플랫폼/IT"},
        {"name": "한국고배당ETF", "ticker": "kodex",     "weight": 10.0, "type": "KR_ETF",    "sector": "배당"},
        {"name": "SCHD",         "ticker": "schd",      "weight": 10.0, "type": "US_ETF",    "sector": "배당"},
        {"name": "현금",          "ticker": "cash",      "weight": 5.0,  "type": "cash",      "sector": "현금"},
    ]
}

# 위험 임계값 설정
RISK_THRESHOLD  = -2.0   # 이 % 이하면 위험
OPPO_THRESHOLD  = +1.5   # 이 % 이상이면 기회


def parse_change(change_str: str) -> float:
    """변동률 문자열 → float 변환"""
    if not change_str or change_str == "N/A":
        return 0.0
    try:
        return float(str(change_str).replace("%", "").replace("+", "").strip())
    except:
        return 0.0


def analyze_portfolio(report: dict, market_data: dict = None) -> dict:
    """실제 주가 변동 + 자금흐름 분석 결합"""

    # 실시간 데이터 로드
    if not market_data:
        try:
            from aria_data import load_market_data
            market_data = load_market_data()
        except ImportError:
            market_data = {}

    regime   = report.get("market_regime", "")
    trend    = report.get("trend_phase", "")
    outflows = report.get("outflows", [])
    inflows  = report.get("inflows", [])
    korea    = report.get("korea_focus", {})
    vix_level = report.get("volatility_index", {}).get("level", "")

    outflow_text = " ".join([o.get("zone", "") for o in outflows]).lower()
    inflow_text  = " ".join([i.get("zone", "") for i in inflows]).lower()

    results            = []
    total_risk         = 0.0
    total_opportunity  = 0.0
    portfolio_pnl      = 0.0  # 오늘 포트폴리오 가중 손익

    for h in PORTFOLIO["holdings"]:
        name    = h["name"]
        ticker  = h["ticker"]
        weight  = h["weight"]
        sector  = h["sector"].lower()

        # 실제 주가 변동률 가져오기
        change_key = ticker + "_change"
        actual_change = parse_change(market_data.get(change_key, "0"))

        # 포트폴리오 가중 손익 계산
        if ticker != "cash":
            portfolio_pnl += actual_change * (weight / 100)

        # 판단 로직 (실제 주가 우선 + 자금흐름 보조)
        status = "neutral"
        reason = ""
        data_basis = ""

        if ticker == "cash":
            status = "neutral"
            reason = "현금 보유"
            data_basis = "N/A"

        else:
            # 1차: 실제 주가 변동으로 판단
            if actual_change <= RISK_THRESHOLD:
                status = "risk"
                reason = "실제 하락 " + str(actual_change) + "% 감지"
                data_basis = str(actual_change) + "% (실제)"
            elif actual_change >= OPPO_THRESHOLD:
                status = "opportunity"
                reason = "실제 상승 " + str(actual_change) + "% 확인"
                data_basis = str(actual_change) + "% (실제)"

            # 2차: 자금흐름으로 보조 판단 (실제 데이터 없을 때)
            else:
                if "반도체" in sector or "ai" in sector:
                    if "반도체" in outflow_text or "nvidia" in outflow_text or "엔비디아" in outflow_text:
                        status = "risk"
                        reason = "반도체 섹터 자금 유출"
                        data_basis = str(actual_change) + "% (흐름 기반)"
                    elif "반도체" in inflow_text or "ai" in inflow_text:
                        status = "opportunity"
                        reason = "반도체/AI 자금 유입"
                        data_basis = str(actual_change) + "% (흐름 기반)"

                elif "플랫폼" in sector or "it" in sector:
                    if "회피" in regime:
                        status = "risk"
                        reason = "위험회피 환경"
                        data_basis = str(actual_change) + "%"
                    elif "선호" in regime:
                        status = "opportunity"
                        reason = "위험선호 환경 수혜"
                        data_basis = str(actual_change) + "%"

                elif "배당" in sector:
                    if "하락" in trend or "회피" in regime:
                        status = "opportunity"
                        reason = "하락장 방어주 수혜"
                        data_basis = str(actual_change) + "%"

            # 개별 종목 한국 데이터 보강
            if ticker == "sk_hynix" and korea.get("sk_hynix"):
                if actual_change == 0:
                    reason = "SK하이닉스: " + korea["sk_hynix"]

            if ticker == "samsung" and korea.get("samsung"):
                if actual_change == 0:
                    reason = "삼성전자: " + korea["samsung"]

        if status == "risk":
            total_risk += weight
        elif status == "opportunity":
            total_opportunity += weight

        results.append({
            "name":          name,
            "ticker":        ticker,
            "weight":        weight,
            "actual_change": actual_change,
            "status":        status,
            "reason":        reason,
            "data_basis":    data_basis,
        })

    # 전체 위험도 판단
    if total_risk >= 40:
        portfolio_risk = "높음"
    elif total_risk >= 20:
        portfolio_risk = "보통"
    else:
        portfolio_risk = "낮음"

    # 오늘 포트폴리오 손익
    pnl_str = ("+" if portfolio_pnl >= 0 else "") + str(round(portfolio_pnl, 2)) + "%"

    # 권장 액션
    actions = []
    if total_risk > 40:
        actions.append("위험 노출 " + str(round(total_risk)) + "% — 현금 비중 확대 검토")
    if "극단공포" in vix_level:
        actions.append("VIX 극단공포 — 분할매수 적극 검토")
    elif "공포" in vix_level:
        actions.append("VIX 공포 구간 — 분할매수 유지")
    if "회피" in regime and "하락" in trend:
        actions.append("위험회피 + 하락추세 — 배당/방어주 비중 유지")
    if portfolio_pnl <= -2.0:
        actions.append("오늘 포트 -2% 이하 — 손절 기준 재점검")

    return {
        "date":              datetime.now(KST).strftime("%Y-%m-%d"),
        "holdings":          results,
        "total_risk":        round(total_risk, 1),
        "total_opportunity": round(total_opportunity, 1),
        "portfolio_risk":    portfolio_risk,
        "portfolio_pnl":     pnl_str,
        "actions":           actions,
        "regime":            regime,
        "trend":             trend,
        "data_source":       "Yahoo Finance 실시간" if market_data else "자금흐름 기반",
    }


def send_portfolio_report(analysis: dict):
    try:
        from aria_telegram import send_message
    except ImportError:
        print("aria_telegram not found")
        return

    risk       = analysis["portfolio_risk"]
    risk_emoji = "🔴" if risk == "높음" else "🟡" if risk == "보통" else "🟢"
    pnl        = analysis.get("portfolio_pnl", "0%")
    pnl_emoji  = "📈" if "+" in str(pnl) else "📉"
    source     = analysis.get("data_source", "")

    lines = [
        "<b>💼 포트폴리오 분석</b>",
        "<code>" + analysis["date"] + " (" + source + ")</code>",
        "",
        risk_emoji + " 전체 위험도: <b>" + risk + "</b>",
        pnl_emoji + " 오늘 포트 손익: <b>" + pnl + "</b>",
        "위험 " + str(analysis["total_risk"]) + "% | 기회 " + str(analysis["total_opportunity"]) + "%",
        "",
    ]

    for h in analysis["holdings"]:
        if h["ticker"] == "cash":
            continue
        if h["status"] == "risk":
            emoji = "🔴"
        elif h["status"] == "opportunity":
            emoji = "🟢"
        else:
            emoji = "⚪"

        change = h.get("actual_change", 0)
        change_str = ("+" if change >= 0 else "") + str(change) + "%" if change != 0 else ""

        lines.append(
            emoji + " <b>" + h["name"] + "</b> (" + str(h["weight"]) + "%)"
            + (" <code>" + change_str + "</code>" if change_str else "")
        )
        if h["reason"]:
            lines.append("   <i>" + h["reason"] + "</i>")

    if analysis["actions"]:
        lines.append("")
        lines.append("📌 <b>권장 액션</b>")
        for a in analysis["actions"]:
            lines.append("  • " + a)

    send_message("\n".join(lines))
    print("Portfolio report sent")


def run_portfolio(report: dict, market_data: dict = None) -> dict:
    analysis = analyze_portfolio(report, market_data)
    send_portfolio_report(analysis)
    return analysis


if __name__ == "__main__":
    from aria_data import fetch_all_market_data
    md = fetch_all_market_data()
    test_report = {
        "market_regime": "위험회피",
        "trend_phase":   "하락추세",
        "outflows": [{"zone": "반도체/AI 섹터"}],
        "inflows":  [{"zone": "배당주/방어주"}],
        "volatility_index": {"level": "공포"},
        "korea_focus": {"sk_hynix": "-3.2%", "samsung": "+0.5%"},
    }
    result = run_portfolio(test_report, md)
    print("포트 손익: " + result["portfolio_pnl"])
    for h in result["holdings"]:
        if h["ticker"] != "cash":
            print(h["name"] + ": " + str(h["actual_change"]) + "% → " + h["status"])
