# orca/postprocess.py
"""
PR 3 ref: orchestrator split from orca/main.py
Upstream: PR 2 @2861c17, hotfix @d870b27
Stage: Step 2-2 (body copy)

Report post-processing and secondary analysis hooks.
"""
# Allowed imports: .analysis, .state, .learning_policy, .paths, .agents (local import only), .present.console
# Forbidden imports: .notify, .persist
# postprocess.py: may import present.console (one-way).
#                 MUST NOT be imported by present.py.
# Signature expanded in Step 2-2: update_pattern_database accepts health_tracker
# (consistency with run_candidate_review / record_predictions pattern)
# where="orca/main.py::main" preserved for PR 1 health contract.
# Do not change to new module names. Rationale: report JSON field stability.
# Future PR may migrate where values after verifying no downstream consumer
# parses them by value. Tracked in Backlog.

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from . import state as state_module
from .analysis import review_recent_candidates, run_portfolio, run_rotation, run_sentiment, save_baseline
from .brand import JACKAL_NAME
from .learning_policy import MIN_SAMPLES
from .paths import DATA_DIR, atomic_write_json
from .present import console
from .state import summarize_candidate_probabilities

KST = timezone(timedelta(hours=9))


def sanitize_korea_claims(report: dict, market_data: dict) -> dict:
    """KIS 미연결 시 한국 수급 단정 표현 완화"""
    import re
    kis_connected = os.environ.get("KIS_CONNECTED", "").lower() == "true"
    if kis_connected:
        return report

    SOFTEN_MAP = {
        r"외국인\s*\d+[개월주일]+\s*연속\s*순매도": "외국인 순매도 흐름 지속 추정(수급 미확인)",
        r"외국인\s*\d+[개월주일]+\s*연속\s*순매수": "외국인 순매수 흐름 추정(수급 미확인)",
        r"외국인\s*누적\s*[+-]?\d+": "외국인 누적 흐름 추정(직접 데이터 미확인)",
        r"기관\s*\d+[조억만]+\s*원\s*순[매도수]": "기관 수급 추정(직접 데이터 미확인)",
        r"수급\s*(악화|개선)\s*확정": "수급 추정",
        r"외국인\s*이탈\s*가속": "외국인 이탈 압력 추정",
        r"(확정|확인됨)(?=.*수급)": "가능성",
    }

    def soften_text(text: str) -> str:
        if not isinstance(text, str):
            return text
        for pattern, replacement in SOFTEN_MAP.items():
            text = re.sub(pattern, replacement, text)
        return text

    def soften_recursive(obj):
        if isinstance(obj, str):  return soften_text(obj)
        if isinstance(obj, list): return [soften_recursive(i) for i in obj]
        if isinstance(obj, dict): return {k: soften_recursive(v) for k, v in obj.items()}
        return obj

    return soften_recursive(report)


def compact_probability_summary(*, days: int = 90, min_samples: int = MIN_SAMPLES) -> dict:
    summary = summarize_candidate_probabilities(days=days, min_samples=MIN_SAMPLES)
    trusted = [
        item for item in summary.get("best_signal_families", [])
        if item.get("qualified")
    ][:5]
    cautious = [
        item for item in summary.get("weak_signal_families", [])
        if item.get("qualified")
    ][:5]
    return {
        "window_days": days,
        "min_samples": MIN_SAMPLES,
        "raw_rows": summary.get("raw_rows", 0),
        "deduped_rows": summary.get("deduped_rows", 0),
        "duplicates_skipped": summary.get("duplicates_skipped", 0),
        "overall": summary.get("overall", {}),
        "trusted_families": trusted,
        "cautious_families": cautious,
        "alignment_summary": summary.get("by_alignment", {}),
        "best_aligned_families": summary.get("best_aligned_families", [])[:3],
        "best_opposed_families": summary.get("best_opposed_families", [])[:3],
    }


def run_candidate_review(
    *,
    report: dict,
    run_id: str | None,
    analysis_date: str,
    health_tracker: Any,
) -> dict:
    print("\n=== JACKAL Candidate Review ===")
    candidate_review = {}
    try:
        candidate_review = review_recent_candidates(
            report,
            run_id=run_id,
            analysis_date=analysis_date,
        )
    except Exception as candidate_err:
        health_tracker.record_exception(
            "candidate_review_unavailable",
            "orca/main.py::main",
            candidate_err,
            message="JACKAL candidate review \uc2e4\ud328",
        )
        candidate_review = {
            "reviewed_count": 0,
            "aligned_count": 0,
            "neutral_count": 0,
            "opposed_count": 0,
            "review_verdict_breakdown": {},
            "average_review_confidence": "low",
            "reason_code_frequency": {},
            "error": str(candidate_err),
        }
    finally:
        health_tracker.ingest_state_events(state_module.drain_health_events())
    if candidate_review.get("reviewed_count", 0) > 0:
        report["jackal_candidate_review"] = candidate_review
        console.print(
            "[dim]{count} candidates reviewed | aligned {aligned} / neutral {neutral} / opposed {opposed}[/dim]".format(
                count=candidate_review.get("reviewed_count", 0),
                aligned=candidate_review.get("aligned_count", 0),
                neutral=candidate_review.get("neutral_count", 0),
                opposed=candidate_review.get("opposed_count", 0),
            )
        )
        breakdown = candidate_review.get("review_verdict_breakdown") or {}
        if sum(int(breakdown.get(key, 0) or 0) for key in ("strong_aligned", "aligned", "neutral", "opposed", "strong_opposed")) > 0:
            console.print(
                "[dim]   avg_conf: {conf} | strong_aligned {sa} / aligned {a} / neutral {n} / opposed {o} / strong_opposed {so}[/dim]".format(
                    conf=candidate_review.get("average_review_confidence", "low"),
                    sa=breakdown.get("strong_aligned", 0),
                    a=breakdown.get("aligned", 0),
                    n=breakdown.get("neutral", 0),
                    o=breakdown.get("opposed", 0),
                    so=breakdown.get("strong_opposed", 0),
                )
            )
    else:
        report["jackal_candidate_review"] = candidate_review
        console.print("[dim]No recent unresolved JACKAL candidates to review[/dim]")
    return candidate_review


def maybe_save_baseline(*, mode: str, report: dict, market_data: dict) -> bool:
    if mode == "MORNING":
        save_baseline(report, market_data)
        console.print("[dim]Morning baseline saved[/dim]")
        return True
    return False


def run_secondary_analyses(report: dict, market_data: dict) -> None:
    print("\n=== Sentiment Tracking ===")
    run_sentiment(report, market_data)

    print("\n=== Sector Rotation ===")
    run_rotation(report)

    print("\n=== Portfolio Analysis ===")
    run_portfolio(report, market_data)


def update_pattern_database(memory: list, health_tracker: Any) -> None:
    from .analysis import update_pattern_db
    from .present import console

    try:
        update_pattern_db(memory)
        console.print("[dim]Pattern DB updated[/dim]")
    except Exception as e:
        health_tracker.record_exception(
            "pattern_db_update_failed",
            "orca/postprocess.py::update_pattern_database",
            e,
            message="Pattern DB \uc5c5\ub370\uc774\ud2b8 \uc2e4\ud328",
        )
        console.print("[yellow]Pattern DB \uc2a4\ud0b5: " + str(e) + "[/yellow]")


def collect_jackal_news(hunter_data: dict) -> None:
    """
    data/jackal_watchlist.json 읽기 → 해당 종목 뉴스 수집 → data/jackal_news.json 저장.
    ORCA Hunter의 웹서치 결과에서 JACKAL 추천 종목 관련 헤드라인 추출.
    비용: Claude Haiku 1회 (약 $0.002)
    """
    from .paths import DATA_DIR
    watchlist_file = DATA_DIR / "jackal_watchlist.json"
    news_file      = DATA_DIR / "jackal_news.json"

    if not watchlist_file.exists():
        return

    try:
        wl = json.loads(watchlist_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    tickers = wl.get("tickers", [])
    details = wl.get("details", {})
    if not tickers:
        return

    console.print(f"[dim]{JACKAL_NAME} watchlist 뉴스 수집: {tickers}[/dim]")

    # Hunter가 수집한 신호에서 관련 헤드라인 추출
    signals = hunter_data.get("raw_signals", [])
    ticker_names = [details.get(t, {}).get("name", t) for t in tickers]
    search_terms = tickers + ticker_names

    relevant = []
    for sig in signals:
        headline = sig.get("headline", "")
        if any(term.lower() in headline.lower() for term in search_terms):
            relevant.append({
                "ticker":   next((t for t in tickers if t.lower() in headline.lower() or
                                  details.get(t,{}).get("name","").lower() in headline.lower()), tickers[0]),
                "headline": headline,
                "source":   sig.get("source_hint", ""),
                "data_pt":  sig.get("data_point", ""),
            })

    # Hunter 결과가 부족하면 Haiku로 보완 검색
    if len(relevant) < 3:
        try:
            from .agents import call_api, MODEL_HUNTER
            ticker_str = ", ".join([
                f"{t}({details.get(t, {}).get('name', t)})" for t in tickers
            ])
            regime_str = wl.get("regime", "")
            news_prompt = (
                f"Search recent news for these stocks: {ticker_str}. "
                f"Market regime: {regime_str}. "
                "Return ONLY valid JSON: "
                '{"news_items": [{"ticker": "X", "headline": "...", "impact": "bullish/bearish/neutral"}]}'
            )
            raw = call_api(
                "You are a financial news collector. Return ONLY valid JSON, no markdown.",
                news_prompt,
                use_search=True,
                model=MODEL_HUNTER,
                max_tokens=800,
            )
            import re as _re, json as _json
            cleaned = _re.sub(r"```(?:json)?|```", "", raw).strip()
            m = _re.search(r"\{[\s\S]*\}", cleaned)
            if m:
                data = _json.loads(m.group())
                for item in data.get("news_items", []):
                    relevant.append({
                        "ticker":   item.get("ticker", ""),
                        "headline": item.get("headline", ""),
                        "impact":   item.get("impact", "neutral"),
                        "source":   "web_search",
                    })
        except (json.JSONDecodeError, TypeError, ValueError, OSError, RuntimeError) as e:
            console.print(f"[yellow]{JACKAL_NAME} 뉴스 보완 검색 실패: {e}[/yellow]")

    # 저장
    try:
        result = {
            "collected_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
            "tickers":      tickers,
            "regime":       wl.get("regime", ""),
            "news_items":   relevant[:10],
            "total":        len(relevant),
        }
        atomic_write_json(news_file, result)
        console.print(f"[dim]{JACKAL_NAME} 뉴스 {len(relevant)}건 저장 → jackal_news.json[/dim]")
    except OSError as e:
        console.print(f"[yellow]jackal_news.json 저장 실패: {e}[/yellow]")
