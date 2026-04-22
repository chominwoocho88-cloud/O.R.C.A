"""Pure deterministic JACKAL signal-quality helpers extracted from scanner.py."""
from __future__ import annotations

ALERT_THRESHOLD = 65
STRONG_THRESHOLD = 78

_CRASH_REBOUND_SIGNALS = frozenset({"sector_rebound", "volume_climax", "52w_low_zone", "vol_accumulation"})
_MA_SUPPORT_SOLO = frozenset({"ma_support"})
_MA_SUPPORT_WEAK = frozenset({"ma_support", "momentum_dip"})
_STRONG_SIGNALS = frozenset({"rsi_oversold", "bb_touch", "volume_climax", "sector_rebound", "vol_accumulation", "52w_low_zone"})

def detect_pre_rule_signals(tech: dict) -> list[str]:
    """Detect deterministic pre-LLM signals using the existing scanner rules."""
    rules_pre = {
        "rsi_oversold": lambda t: t["rsi"] < 32,
        "bb_touch": lambda t: t["bb_pos"] < 15,
        "volume_climax": lambda t: t["vol_ratio"] > 1.8 and t["change_1d"] < -1.0,
        "momentum_dip": lambda t: t["change_5d"] < -4.0,
        "sector_rebound": lambda t: t["rsi"] < 40 and t.get("change_3d", t.get("change_5d", 0)) < -2.0,
        "rsi_divergence": lambda t: t.get("rsi_divergence", False) and t["rsi"] < 35,
        "52w_low_zone": lambda t: t.get("52w_pos", 50) < 15,
        "vol_accumulation": lambda t: t.get("vol_accumulation", False),
        "ma_support": lambda t: (
            t["ma50"] is not None and abs(t["price"] - t["ma50"]) / t["ma50"] < 0.025
        ),
    }
    signals_fired = [sig for sig, rule in rules_pre.items() if rule(tech)]
    if signals_fired == ["ma_support"]:
        return []
    if "ma_support" in signals_fired and not (_STRONG_SIGNALS & set(signals_fired)):
        return [signal for signal in signals_fired if signal != "ma_support"]
    return signals_fired
def _get_signal_family(signals: list) -> str:
    """Return the deterministic signal family for the current signal list."""
    sig = set(signals)
    if sig & _CRASH_REBOUND_SIGNALS:  # rebound 계열 1개라도 → crash_rebound
        return "crash_rebound"
    if sig == _MA_SUPPORT_SOLO:  # ma_support 단독
        return "ma_support_solo"
    if sig == _MA_SUPPORT_WEAK:  # ma_support + momentum_dip만
        return "ma_support_weak"
    return "general"

def _calc_signal_quality_core(
    signals: list,
    tech: dict,
    aria: dict,
    *,
    ticker: str = "",
    weights: dict | None = None,
    pcr_avg: float = 0.0,
    cached_vix: float = 0.0,
    hy_spread: float = 0.0,
) -> dict:
    """Evaluate deterministic signal quality from already-loaded inputs only."""
    if weights is None:
        weights = {}

    sig = set(signals)
    score = 50
    reasons: list = []

    if "sector_rebound" in sig:
        score += 20
        reasons.append("sector_rebound(93%)+20")
    if "volume_climax" in sig:
        score += 15
        reasons.append("volume_climax(80%)+15")
    if "bb_touch" in sig and "rsi_oversold" in sig:
        score += 16
        reasons.append("BB+RSI조합(97%+88%)+16")
    elif "bb_touch" in sig:
        score += 12
        reasons.append("BB하단(97%)+12")
    if "rsi_oversold" in sig and "sector_rebound" not in sig:
        score += 9
        reasons.append("RSI과매도(88%)+9")
    if "momentum_dip" in sig and len(sig) > 1:
        score += 5
        reasons.append("급락+복수신호+5")

    if "rsi_divergence" in sig:
        if sig == {"rsi_divergence"} or sig == {"rsi_divergence", "ma_support"}:
            score -= 20  # 단독 31.6% → skip 강제
            reasons.append("RSI다이버전스단독(31.6%)-20")
        elif "momentum_dip" in sig and "vol_accumulation" not in sig:
            score -= 12  # momentum_dip+rsi_div = 40% 최악 조합
            reasons.append("다이버전스+momentum_dip(40%)-12")
        elif "vol_accumulation" in sig:
            score += 3  # vol_acc와 함께면 60% → 소폭 플러스
            reasons.append("RSI다이버전스+매집+3")
        else:
            score += 0
    if "52w_low_zone" in sig:
        score += 12  # 52주 저점 15% 이내 — 심리적 지지
        reasons.append("52주저점구간+12")
    if "vol_accumulation" in sig:
        score += 12
        reasons.append("하락중거래량증가(매집,84%)+12")

    if "vol_accumulation" in sig and "sector_rebound" in sig:
        score += 8
        reasons.append("매집+반등조합시너지+8")
    if "52w_low_zone" in sig and "rsi_oversold" in sig:
        score += 6
        reasons.append("52주저점+RSI과매도조합+6")
    if "vol_accumulation" in sig and "momentum_dip" in sig:
        score += 5
        reasons.append("매집+급락조합+5")

    if {"bb_touch", "sector_rebound", "rsi_oversold"}.issubset(sig):
        score += 15
        reasons.append("3중combo(BB+반등+RSI,90%+)+15")

    if sig == _MA_SUPPORT_SOLO:
        score -= 12
        reasons.append("ma_support단독(61.8%)-12")
    elif sig == _MA_SUPPORT_WEAK:
        score -= 5
        reasons.append("ma+momentum약조합-5")

    if pcr_avg > 0:
        if pcr_avg > 1.3 and _CRASH_REBOUND_SIGNALS & sig:
            score += 10  # 극단공포(PCR>1.3) + 반등 신호 = 최강 조합
            reasons.append(f"PCR극단({pcr_avg:.2f})+반등=최강+10")
        elif pcr_avg > 1.1 and ("bb_touch" in sig or "rsi_oversold" in sig):
            score += 5
            reasons.append(f"PCR고조({pcr_avg:.2f})+과매도+5")
        elif pcr_avg < 0.8 and "volume_climax" in sig:
            score -= 8  # 과도한 낙관(PCR<0.8)에서 volume_climax는 고점 경고
            reasons.append(f"PCR낙관({pcr_avg:.2f})+volume=고점경고-8")

    vix = (
        float(tech.get("vix_level") or 0)
        or float(aria.get("fred_vix") or 0)
        or cached_vix
    )

    vix_extreme = vix > 35
    vix_high = vix > 25
    real_panic = vix > 30 and hy_spread > 4.0  # 진짜 공황: VIX+HY 교차 확인
    credit_stress = hy_spread > 3.5  # 크레딧 스트레스만

    rebound_raw = 0
    chg5d = float(tech.get("change_5d") or 0)

    if "sector_rebound" in sig:
        if real_panic:  # VIX>30 + HY>4.0 교차 = 진짜 패닉 반등
            rebound_raw += 10
            reasons.append(f"진짜패닉(VIX{vix:.0f}+HY{hy_spread:.1f})+반등+10")
        elif vix_extreme:  # VIX만 극단
            rebound_raw += 6
            reasons.append(f"VIX극단({vix:.0f})게이팅+반등+6")
        elif credit_stress and vix_high:  # HY 스트레스 + VIX 고조
            rebound_raw += 4
            reasons.append(f"크레딧스트레스(HY{hy_spread:.1f})+반등+4")

    if chg5d < -8 and "sector_rebound" in sig:
        rebound_raw += 10
        reasons.append(f"5일{chg5d:.0f}%급락+반등+10")
    elif chg5d < -5 and len(sig) >= 2:
        rebound_raw += 5
        reasons.append(f"5일{chg5d:.0f}%+복수신호+5")

    rebound_cap = 12
    rebound_capped = min(rebound_raw, rebound_cap)
    score += rebound_capped
    if rebound_raw > rebound_cap:
        reasons.append(f"반등상한cap({rebound_cap}←{rebound_raw})")

    thesis_killers = aria.get("thesis_killers", [])
    regime = aria.get("regime", "")

    has_negative_veto = False
    negative_reasons: list = []

    if thesis_killers:
        has_negative_veto = True
        negative_reasons.append(f"Thesis Killer({len(thesis_killers)}개)")

    if "전환중" in regime or regime.startswith("혼조"):
        score -= 15
        reasons.append("전환중/혼조레짐-15")
        has_negative_veto = True
        negative_reasons.append("레짐불확실")
    elif "위험회피" in regime:
        if "sector_rebound" in sig:
            score += 5
            reasons.append("위험회피+반등+5")

    if chg5d > 15 and "bb_touch" not in sig:
        score -= 8
        reasons.append(f"5일{chg5d:.0f}% 과열-8")
        has_negative_veto = True
        negative_reasons.append("단기과열")

    if has_negative_veto and rebound_capped > 0:
        rebound_cap_after_veto = rebound_capped // 2
        veto_penalty = rebound_capped - rebound_cap_after_veto
        score -= veto_penalty
        reasons.append(f"NegVeto({','.join(negative_reasons)}): rebound -{veto_penalty}")

    high_uncertainty_keywords = [
        "FOMC",
        "CPI",
        "관세",
        "tariff",
        "실적발표",
        "어닝",
        "earning",
        "금리결정",
        "고용지표",
        "기준금리",
        "연준",
        "Fed decision",
    ]
    orca_note = aria.get("note", "") + " " + aria.get("trend", "") + " " + regime
    has_event_kw = any(kw.lower() in orca_note.lower() for kw in high_uncertainty_keywords)

    fg_raw = aria.get("fear_greed", "50")
    try:
        fg_score = int(str(fg_raw).split()[0])
    except Exception:
        fg_score = 50

    fg_available = fg_raw not in (None, "", "50", 50)
    fg_fear_gate = fg_score <= 15 if fg_available else None

    gate_reason = None

    if vix >= 40:
        gate_reason = "vix_only_hard"
        gate_strength = "hard"
    elif vix >= 32 and fg_fear_gate is True:
        gate_reason = "vix_fg_hard"
        gate_strength = "hard"
    elif vix >= 32 and fg_fear_gate is None:
        gate_reason = "vix_only_soft"  # FG 누락 보정
        gate_strength = "soft"
    elif has_event_kw and vix >= 28:
        gate_reason = "keyword_vix_soft"
        gate_strength = "soft"
    else:
        gate_reason = None
        gate_strength = None

    is_high_uncertainty = gate_reason is not None

    micro_gate_active = False
    if not is_high_uncertainty:
        is_risk_off_regime = any(kw in regime for kw in ["위험회피", "하락추세", "bearish"])
        if is_risk_off_regime and vix >= 22 and family not in ("crash_rebound",):
            micro_gate_active = True
            gate_reason = "regime_micro"
            gate_strength = "micro"

    fg_str = f"FG{fg_score}" if fg_available else "FG없음"
    if is_high_uncertainty and family != "crash_rebound":
        penalty_map = {
            "vix_only_hard": 15,
            "vix_fg_hard": 15,
            "vix_only_soft": 8,
            "keyword_vix_soft": 8,
            "regime_micro": 5,
        }
        penalty = penalty_map.get(gate_reason, 8)
        score -= penalty
        reasons.append(f"불확실게이트[{gate_reason}](VIX{vix:.0f}/{fg_str})-{penalty}")

        if gate_strength == "hard" and vix >= 40:
            score = 0  # skip_threshold 하회 강제
            reasons.append(f"🚫 ABSTAIN(VIX극단{vix:.0f}≥40+hard gate)")

    elif micro_gate_active and family != "crash_rebound":
        score -= 5
        reasons.append(f"레짐microgate({regime[:6]}/VIX{vix:.0f})-5")
    elif is_high_uncertainty and family == "crash_rebound":
        reasons.append(f"고불확실→crash_rebound예외(VIX{vix:.0f},패널티없음)")

    if ticker and weights:
        tk_data = weights.get("ticker_accuracy", {}).get(ticker, {})
        acc_pct = tk_data.get("accuracy", 50)
        total = tk_data.get("total", 0)

        if total >= 8:
            acc_adj = (acc_pct - 50) * 0.20
            acc_adj = max(-10, min(0, acc_adj))  # 상방 완전 0 (Doc3 수용)
            score += acc_adj
            if abs(acc_adj) >= 1:
                reasons.append(f"종목정확도({acc_pct:.0f}%,n={total}){acc_adj:+.1f}")
        elif total >= 3:
            acc_adj = (acc_pct - 50) * 0.10
            acc_adj = max(-5, min(0, acc_adj))  # 약한 하방만
            score += acc_adj
            if abs(acc_adj) >= 0.5:
                reasons.append(f"종목정확도약(n={total}){acc_adj:+.1f}")

    score = max(0, min(100, score))

    family = _get_signal_family(signals)

    thresholds = {
        "crash_rebound": 35,  # 3중 combo 가능 family → 임계값 추가 완화
        "general": 45,  # 기본
        "ma_support_weak": 47,
        "ma_support_solo": 46,
    }
    skip_threshold = thresholds.get(family, 45)

    if family == "crash_rebound":
        if vix >= 30:
            skip_threshold = max(33, skip_threshold - 5)  # 완화
        elif vix < 18:
            skip_threshold = min(46, skip_threshold + 3)  # 약간 엄격
    elif family == "general":
        if vix < 18:
            skip_threshold = min(50, skip_threshold + 5)  # 저변동성: 엄격

    skip = score < skip_threshold
    label = "최강" if score >= 80 else "강" if score >= 65 else "보통" if score >= 50 else "약"

    analyst_adj = +5 if score >= 75 else 0
    final_adj = +5 if score >= 75 else 0

    return {
        "quality_score": score,
        "quality_label": label,
        "reasons": reasons,
        "skip": skip,
        "skip_threshold": skip_threshold,
        "signal_family": family,
        "analyst_adj": analyst_adj,
        "final_adj": final_adj,
        "vix_used": vix,
        "vix_extreme": vix_extreme,
        "rebound_bonus": rebound_capped,
        "rebound_raw": rebound_raw,
        "negative_veto": has_negative_veto,
        "negative_reasons": negative_reasons,
    }

def _final_judgment(analyst: dict, devil: dict) -> dict:
    """Combine analyst and devil outputs into the final deterministic judgment."""
    a_score = analyst.get("analyst_score", 50)
    d_score = devil.get("devil_score", 30)
    verdict = devil.get("verdict", "부분동의")
    tk_hit = devil.get("thesis_killer_hit", False)

    if tk_hit:
        return {
            "final_score": 20,
            "is_entry": False,
            "signal_type": "매도주의",
            "reason": f"⛔ Thesis Killer: {devil.get('killer_detail', '무효화 조건 충족')}",
        }

    weight_map = {"동의": 1.0, "부분동의": 0.75, "반대": 0.5}
    weight = weight_map.get(verdict, 0.75)

    devil_penalty = (d_score - 30) * 0.2  # devil_score 30 기준, 초과분의 20%
    final = max(0, min(100, round(a_score * weight - devil_penalty, 1)))

    if final >= STRONG_THRESHOLD and verdict != "반대":
        sig_type = "강한매수"
    elif final >= ALERT_THRESHOLD and verdict != "반대":
        sig_type = "매수검토"
    elif verdict == "반대" or final < 40:
        sig_type = "매도주의" if final < 30 else "관망"
    else:
        sig_type = "관망"

    is_entry = final >= ALERT_THRESHOLD and verdict != "반대" and not tk_hit

    reason_parts = []
    if analyst.get("bull_case"):
        reason_parts.append(analyst["bull_case"][:40])
    if devil.get("objections"):
        reason_parts.append("⚠️ " + devil["objections"][0][:30])

    return {
        "final_score": final,
        "is_entry": is_entry,
        "signal_type": sig_type,
        "reason": " | ".join(reason_parts)[:80],
        "entry_price": analyst.get("entry_price"),
        "stop_loss": analyst.get("stop_loss"),
        "verdict": verdict,
    }

def _get_signal_family_key(signals: list) -> str:
    """신호 목록에서 family 키 생성 (쿨다운 구분용)."""
    sig = set(signals)
    if sig & {"sector_rebound", "volume_climax", "vol_accumulation", "52w_low_zone"}:
        return "crash_rebound"
    if "bb_touch" in sig or "rsi_oversold" in sig:
        return "oversold"
    if "momentum_dip" in sig:
        return "momentum"
    return "general"
