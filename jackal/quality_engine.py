"""Pure deterministic JACKAL signal-quality helpers extracted from scanner.py."""
from __future__ import annotations

from .thresholds import THRESHOLDS

_QUALITY = THRESHOLDS["quality"]
_QUALITY_PRE_RULE = _QUALITY["pre_rule"]
_QUALITY_CORE = _QUALITY["core_scores"]
_QUALITY_PCR = _QUALITY["pcr"]
_QUALITY_MACRO = _QUALITY["macro_rebound"]
_QUALITY_VETO = _QUALITY["regime_veto"]
_QUALITY_FG = _QUALITY["fear_greed"]
_QUALITY_TICKER = _QUALITY["ticker_accuracy"]
_QUALITY_FAMILY = _QUALITY["family_skip"]
_QUALITY_LABELS = _QUALITY["labels"]
_QUALITY_FINAL = _QUALITY["final_judgment"]

ALERT_THRESHOLD = _QUALITY["alert_threshold"]
STRONG_THRESHOLD = _QUALITY["strong_threshold"]

_CRASH_REBOUND_SIGNALS = frozenset({"sector_rebound", "volume_climax", "52w_low_zone", "vol_accumulation"})
_MA_SUPPORT_SOLO = frozenset({"ma_support"})
_MA_SUPPORT_WEAK = frozenset({"ma_support", "momentum_dip"})
_STRONG_SIGNALS = frozenset({"rsi_oversold", "bb_touch", "volume_climax", "sector_rebound", "vol_accumulation", "52w_low_zone"})

def detect_pre_rule_signals(tech: dict) -> list[str]:
    """Detect deterministic pre-LLM signals using the existing scanner rules."""
    rules_pre = {
        "rsi_oversold": lambda t: t["rsi"] < _QUALITY_PRE_RULE["rsi_oversold"],
        "bb_touch": lambda t: t["bb_pos"] < _QUALITY_PRE_RULE["bb_touch"],
        "volume_climax": lambda t: (
            t["vol_ratio"] > _QUALITY_PRE_RULE["volume_climax_ratio"]
            and t["change_1d"] < _QUALITY_PRE_RULE["volume_climax_change_1d"]
        ),
        "momentum_dip": lambda t: t["change_5d"] < _QUALITY_PRE_RULE["momentum_dip_change_5d"],
        "sector_rebound": lambda t: (
            t["rsi"] < _QUALITY_PRE_RULE["sector_rebound_rsi"]
            and t.get("change_3d", t.get("change_5d", 0)) < _QUALITY_PRE_RULE["sector_rebound_change"]
        ),
        "rsi_divergence": lambda t: t.get("rsi_divergence", False) and t["rsi"] < _QUALITY_PRE_RULE["rsi_divergence_rsi"],
        "52w_low_zone": lambda t: t.get("52w_pos", 50) < _QUALITY_PRE_RULE["52w_low_zone"],
        "vol_accumulation": lambda t: t.get("vol_accumulation", False),
        "ma_support": lambda t: (
            t["ma50"] is not None
            and abs(t["price"] - t["ma50"]) / t["ma50"] < _QUALITY_PRE_RULE["ma_support_distance"]
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
    family = _get_signal_family(signals)
    score = 50
    reasons: list = []

    if "sector_rebound" in sig:
        score += _QUALITY_CORE["sector_rebound"]
        reasons.append("sector_rebound(93%)+20")
    if "volume_climax" in sig:
        score += _QUALITY_CORE["volume_climax"]
        reasons.append("volume_climax(80%)+15")
    if "bb_touch" in sig and "rsi_oversold" in sig:
        score += _QUALITY_CORE["bb_touch_with_rsi_oversold"]
        reasons.append("BB+RSI조합(97%+88%)+16")
    elif "bb_touch" in sig:
        score += _QUALITY_CORE["bb_touch"]
        reasons.append("BB하단(97%)+12")
    if "rsi_oversold" in sig and "sector_rebound" not in sig:
        score += _QUALITY_CORE["rsi_oversold"]
        reasons.append("RSI과매도(88%)+9")
    if "momentum_dip" in sig and len(sig) > 1:
        score += _QUALITY_CORE["momentum_dip_multi_signal"]
        reasons.append("급락+복수신호+5")

    if "rsi_divergence" in sig:
        if sig == {"rsi_divergence"} or sig == {"rsi_divergence", "ma_support"}:
            score += _QUALITY_CORE["rsi_divergence_solo_penalty"]  # 단독 31.6% → skip 강제
            reasons.append("RSI다이버전스단독(31.6%)-20")
        elif "momentum_dip" in sig and "vol_accumulation" not in sig:
            score += _QUALITY_CORE["rsi_divergence_momentum_penalty"]  # momentum_dip+rsi_div = 40% 최악 조합
            reasons.append("다이버전스+momentum_dip(40%)-12")
        elif "vol_accumulation" in sig:
            score += _QUALITY_CORE["rsi_divergence_vol_accumulation"]  # vol_acc와 함께면 60% → 소폭 플러스
            reasons.append("RSI다이버전스+매집+3")
        else:
            score += 0
    if "52w_low_zone" in sig:
        score += _QUALITY_CORE["52w_low_zone"]  # 52주 저점 15% 이내 — 심리적 지지
        reasons.append("52주저점구간+12")
    if "vol_accumulation" in sig:
        score += _QUALITY_CORE["vol_accumulation"]
        reasons.append("하락중거래량증가(매집,84%)+12")

    if "vol_accumulation" in sig and "sector_rebound" in sig:
        score += _QUALITY_CORE["vol_accumulation_sector_rebound_combo"]
        reasons.append("매집+반등조합시너지+8")
    if "52w_low_zone" in sig and "rsi_oversold" in sig:
        score += _QUALITY_CORE["52w_low_zone_rsi_oversold_combo"]
        reasons.append("52주저점+RSI과매도조합+6")
    if "vol_accumulation" in sig and "momentum_dip" in sig:
        score += _QUALITY_CORE["vol_accumulation_momentum_combo"]
        reasons.append("매집+급락조합+5")

    if {"bb_touch", "sector_rebound", "rsi_oversold"}.issubset(sig):
        score += _QUALITY_CORE["bb_sector_rsi_combo"]
        reasons.append("3중combo(BB+반등+RSI,90%+)+15")

    if sig == _MA_SUPPORT_SOLO:
        score += _QUALITY_CORE["ma_support_solo_penalty"]
        reasons.append("ma_support단독(61.8%)-12")
    elif sig == _MA_SUPPORT_WEAK:
        score += _QUALITY_CORE["ma_support_weak_penalty"]
        reasons.append("ma+momentum약조합-5")

    if pcr_avg > 0:
        if pcr_avg > _QUALITY_PCR["extreme"] and _CRASH_REBOUND_SIGNALS & sig:
            score += _QUALITY_PCR["extreme_bonus"]  # 극단공포(PCR>1.3) + 반등 신호 = 최강 조합
            reasons.append(f"PCR극단({pcr_avg:.2f})+반등=최강+10")
        elif pcr_avg > _QUALITY_PCR["elevated"] and ("bb_touch" in sig or "rsi_oversold" in sig):
            score += _QUALITY_PCR["elevated_bonus"]
            reasons.append(f"PCR고조({pcr_avg:.2f})+과매도+5")
        elif pcr_avg < _QUALITY_PCR["crowded_long"] and "volume_climax" in sig:
            score += _QUALITY_PCR["crowded_long_penalty"]  # 과도한 낙관(PCR<0.8)에서 volume_climax는 고점 경고
            reasons.append(f"PCR낙관({pcr_avg:.2f})+volume=고점경고-8")

    vix = (
        float(tech.get("vix_level") or 0)
        or float(aria.get("fred_vix") or 0)
        or cached_vix
    )

    vix_extreme = vix > _QUALITY_MACRO["vix_extreme"]
    vix_high = vix > _QUALITY_MACRO["vix_high"]
    real_panic = (
        vix > _QUALITY_MACRO["real_panic_vix"]
        and hy_spread > _QUALITY_MACRO["real_panic_hy_spread"]
    )  # 진짜 공황: VIX+HY 교차 확인
    credit_stress = hy_spread > _QUALITY_MACRO["credit_stress_hy_spread"]  # 크레딧 스트레스만

    rebound_raw = 0
    chg5d = float(tech.get("change_5d") or 0)

    if "sector_rebound" in sig:
        if real_panic:  # VIX>30 + HY>4.0 교차 = 진짜 패닉 반등
            rebound_raw += _QUALITY_MACRO["real_panic_bonus"]
            reasons.append(f"진짜패닉(VIX{vix:.0f}+HY{hy_spread:.1f})+반등+10")
        elif vix_extreme:  # VIX만 극단
            rebound_raw += _QUALITY_MACRO["vix_extreme_bonus"]
            reasons.append(f"VIX극단({vix:.0f})게이팅+반등+6")
        elif credit_stress and vix_high:  # HY 스트레스 + VIX 고조
            rebound_raw += _QUALITY_MACRO["credit_stress_bonus"]
            reasons.append(f"크레딧스트레스(HY{hy_spread:.1f})+반등+4")

    if chg5d < _QUALITY_MACRO["chg5_extreme_drop"] and "sector_rebound" in sig:
        rebound_raw += _QUALITY_MACRO["chg5_extreme_bonus"]
        reasons.append(f"5일{chg5d:.0f}%급락+반등+10")
    elif (
        chg5d < _QUALITY_MACRO["chg5_drop"]
        and len(sig) >= _QUALITY_MACRO["multi_signal_count_min"]
    ):
        rebound_raw += _QUALITY_MACRO["chg5_multi_signal_bonus"]
        reasons.append(f"5일{chg5d:.0f}%+복수신호+5")

    rebound_cap = _QUALITY_CORE["rebound_cap"]
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
        score += _QUALITY_VETO["mixed_penalty"]
        reasons.append("전환중/혼조레짐-15")
        has_negative_veto = True
        negative_reasons.append("레짐불확실")
    elif "위험회피" in regime:
        if "sector_rebound" in sig:
            score += _QUALITY_VETO["risk_off_sector_rebound_bonus"]
            reasons.append("위험회피+반등+5")

    if chg5d > _QUALITY_VETO["overheat_change_5d"] and "bb_touch" not in sig:
        score += _QUALITY_VETO["overheat_penalty"]
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
        fg_score = _QUALITY_FG["default_score"]

    fg_available = fg_raw not in (None, "", "50", 50)
    fg_fear_gate = fg_score <= _QUALITY_FG["fear_gate"] if fg_available else None

    gate_reason = None

    if vix >= _QUALITY_FG["vix_only_hard"]:
        gate_reason = "vix_only_hard"
        gate_strength = "hard"
    elif vix >= _QUALITY_FG["vix_fg_hard"] and fg_fear_gate is True:
        gate_reason = "vix_fg_hard"
        gate_strength = "hard"
    elif vix >= _QUALITY_FG["vix_fg_hard"] and fg_fear_gate is None:
        gate_reason = "vix_only_soft"  # FG 누락 보정
        gate_strength = "soft"
    elif has_event_kw and vix >= _QUALITY_FG["keyword_vix_soft"]:
        gate_reason = "keyword_vix_soft"
        gate_strength = "soft"
    else:
        gate_reason = None
        gate_strength = None

    is_high_uncertainty = gate_reason is not None

    micro_gate_active = False
    if not is_high_uncertainty:
        is_risk_off_regime = any(kw in regime for kw in ["위험회피", "하락추세", "bearish"])
        if is_risk_off_regime and vix >= _QUALITY_FG["micro_gate_vix"] and family not in ("crash_rebound",):
            micro_gate_active = True
            gate_reason = "regime_micro"
            gate_strength = "micro"

    fg_str = f"FG{fg_score}" if fg_available else "FG없음"
    if is_high_uncertainty and family != "crash_rebound":
        penalty_map = {
            "vix_only_hard": _QUALITY_FG["hard_penalty"],
            "vix_fg_hard": _QUALITY_FG["hard_penalty"],
            "vix_only_soft": _QUALITY_FG["soft_penalty"],
            "keyword_vix_soft": _QUALITY_FG["soft_penalty"],
            "regime_micro": _QUALITY_FG["micro_penalty"],
        }
        penalty = penalty_map.get(gate_reason, _QUALITY_FG["soft_penalty"])
        score -= penalty
        reasons.append(f"불확실게이트[{gate_reason}](VIX{vix:.0f}/{fg_str})-{penalty}")

        if gate_strength == "hard" and vix >= _QUALITY_FG["vix_only_hard"]:
            score = 0  # skip_threshold 하회 강제
            reasons.append(f"🚫 ABSTAIN(VIX극단{vix:.0f}≥40+hard gate)")

    elif micro_gate_active and family != "crash_rebound":
        score -= _QUALITY_FG["micro_penalty"]
        reasons.append(f"레짐microgate({regime[:6]}/VIX{vix:.0f})-5")
    elif is_high_uncertainty and family == "crash_rebound":
        reasons.append(f"고불확실→crash_rebound예외(VIX{vix:.0f},패널티없음)")

    if ticker and weights:
        tk_data = weights.get("ticker_accuracy", {}).get(ticker, {})
        acc_pct = tk_data.get("accuracy", 50)
        total = tk_data.get("total", 0)

        if total >= _QUALITY_TICKER["strong_sample_min"]:
            acc_adj = (acc_pct - 50) * _QUALITY_TICKER["strong_slope"]
            acc_adj = max(
                _QUALITY_TICKER["strong_floor"],
                min(_QUALITY_TICKER["strong_cap"], acc_adj),
            )  # 상방 완전 0 (Doc3 수용)
            score += acc_adj
            if abs(acc_adj) >= _QUALITY_TICKER["strong_reason_min_abs"]:
                reasons.append(f"종목정확도({acc_pct:.0f}%,n={total}){acc_adj:+.1f}")
        elif total >= _QUALITY_TICKER["light_sample_min"]:
            acc_adj = (acc_pct - 50) * _QUALITY_TICKER["light_slope"]
            acc_adj = max(
                _QUALITY_TICKER["light_floor"],
                min(_QUALITY_TICKER["light_cap"], acc_adj),
            )  # 약한 하방만
            score += acc_adj
            if abs(acc_adj) >= _QUALITY_TICKER["light_reason_min_abs"]:
                reasons.append(f"종목정확도약(n={total}){acc_adj:+.1f}")

    score = max(0, min(100, score))

    thresholds = {
        "crash_rebound": _QUALITY_FAMILY["crash_rebound"],  # 3중 combo 가능 family → 임계값 추가 완화
        "general": _QUALITY_FAMILY["general"],  # 기본
        "ma_support_weak": _QUALITY_FAMILY["ma_support_weak"],
        "ma_support_solo": _QUALITY_FAMILY["ma_support_solo"],
    }
    skip_threshold = thresholds.get(family, _QUALITY_FAMILY["general"])

    if family == "crash_rebound":
        if vix >= _QUALITY_FAMILY["crash_rebound_high_vix"]:
            skip_threshold = max(
                _QUALITY_FAMILY["crash_rebound_high_vix_floor"],
                skip_threshold + _QUALITY_FAMILY["crash_rebound_high_vix_delta"],
            )  # 완화
        elif vix < _QUALITY_FAMILY["crash_rebound_low_vix"]:
            skip_threshold = min(
                _QUALITY_FAMILY["crash_rebound_low_vix_cap"],
                skip_threshold + _QUALITY_FAMILY["crash_rebound_low_vix_delta"],
            )  # 약간 엄격
    elif family == "general":
        if vix < _QUALITY_FAMILY["general_low_vix"]:
            skip_threshold = min(
                _QUALITY_FAMILY["general_low_vix_cap"],
                skip_threshold + _QUALITY_FAMILY["general_low_vix_delta"],
            )  # 저변동성: 엄격

    skip = score < skip_threshold
    label = (
        "최강" if score >= _QUALITY_LABELS["strong"]
        else "강" if score >= _QUALITY_LABELS["good"]
        else "보통" if score >= _QUALITY_LABELS["fair"]
        else "약"
    )

    analyst_adj = +5 if score >= _QUALITY_LABELS["analyst_bonus_cutoff"] else 0
    final_adj = +5 if score >= _QUALITY_LABELS["final_bonus_cutoff"] else 0

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
            "final_score": _QUALITY_FINAL["thesis_killer_score"],
            "is_entry": False,
            "signal_type": "매도주의",
            "reason": f"⛔ Thesis Killer: {devil.get('killer_detail', '무효화 조건 충족')}",
        }

    weight_map = {
        "동의": _QUALITY_FINAL["verdict_weights"]["agree"],
        "부분동의": _QUALITY_FINAL["verdict_weights"]["partial"],
        "반대": _QUALITY_FINAL["verdict_weights"]["oppose"],
    }
    weight = weight_map.get(verdict, _QUALITY_FINAL["verdict_weights"]["partial"])

    devil_penalty = (
        d_score - _QUALITY_FINAL["devil_penalty_baseline"]
    ) * _QUALITY_FINAL["devil_penalty_multiplier"]  # devil_score 30 기준, 초과분의 20%
    final = max(0, min(100, round(a_score * weight - devil_penalty, 1)))

    if final >= STRONG_THRESHOLD and verdict != "반대":
        sig_type = "강한매수"
    elif final >= ALERT_THRESHOLD and verdict != "반대":
        sig_type = "매수검토"
    elif verdict == "반대" or final < _QUALITY_FINAL["watch_cutoff"]:
        sig_type = "매도주의" if final < _QUALITY_FINAL["sell_cutoff"] else "관망"
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
