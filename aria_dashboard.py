"""
aria_dashboard.py — ARIA 대시보드 v3
정보 우선순위: 결론 → KPI → 자금흐름 → 정확도 → 리스크 → 패턴 → 포트폴리오 → 하단
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))

from aria_paths import (
    SENTIMENT_FILE, ACCURACY_FILE, ROTATION_FILE,
    MEMORY_FILE, COST_FILE, DASHBOARD_FILE as OUTPUT_FILE,
    PATTERN_DB_FILE, DATA_FILE,
)
try:
    from aria_paths import PORTFOLIO_FILE
except ImportError:
    PORTFOLIO_FILE = Path("portfolio.json")


def _load(path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default or {}

def _j(v): return json.dumps(v, ensure_ascii=False)
def _e(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def _trim(s, n): return _e(str(s)[:n] + ("…" if len(str(s)) > n else ""))


def build_dashboard():
    now     = datetime.now(KST)
    sent    = _load(SENTIMENT_FILE, {"history": [], "current": {}})
    acc     = _load(ACCURACY_FILE,  {"total":0,"correct":0,"by_category":{},"history":[]})
    rot     = _load(ROTATION_FILE,  {"ranking":[]})
    memory  = _load(MEMORY_FILE,    [])
    cost    = _load(COST_FILE,      {})
    pattern = _load(PATTERN_DB_FILE,{})
    market  = _load(DATA_FILE,      {})

    cur     = sent.get("current", {})
    hist30  = sent.get("history", [])[-30:]
    latest  = (memory[-1] if isinstance(memory,list) and memory else {})

    # 감정지수
    s_dates  = [h["date"][5:] for h in hist30]
    s_scores = [h["score"]    for h in hist30]
    s_score  = cur.get("score", 50)
    s_level  = cur.get("level", "중립")
    s_emoji  = cur.get("emoji", "😐")

    # 정확도
    a_total   = acc.get("total",0)
    a_correct = acc.get("correct",0)
    a_pct     = round(a_correct/a_total*100,1) if a_total>0 else 0
    a_dir     = acc.get("dir_accuracy_pct",0)
    by_cat    = acc.get("by_category",{})

    # 섹터 로테이션
    ranking    = rot.get("ranking",[])
    rot_labels = [r[0] for r in ranking][:8]
    rot_values = [r[1] for r in ranking][:8]
    top_in     = ranking[0][0]  if ranking and ranking[0][1]>0  else "—"
    top_out    = next((r[0] for r in reversed(ranking) if r[1]<0), "—")

    # 레짐 / 요약
    regime      = latest.get("market_regime","")
    confidence  = latest.get("confidence_overall","")
    summary     = latest.get("one_line_summary","")
    trend       = latest.get("trend_phase","")
    strategy    = latest.get("trend_strategy",{})
    recommended = (strategy.get("recommended","") if isinstance(strategy,dict) else "")
    caution_txt = (strategy.get("caution","")     if isinstance(strategy,dict) else "")
    analysis_dt = latest.get("analysis_date","")
    counterargs = latest.get("counterarguments",[])
    devil_cnt   = len(counterargs)
    main_risk   = counterargs[0].get("against","—") if counterargs else "—"
    tail_risks  = latest.get("tail_risks",[])

    # 패턴
    pat_sum   = pattern.get("summary",[])[:4]
    blackswan = pattern.get("blackswan",{})

    # 포트폴리오
    holdings = []
    if PORTFOLIO_FILE.exists():
        try: holdings = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8")).get("holdings",[])
        except: pass
    port_rows = []
    for h in holdings:
        if h.get("ticker")=="cash": continue
        chg_str = market.get(str(h.get("ticker",""))+"_change","0%")
        try:    chg = float(str(chg_str).replace("%","").replace("+",""))
        except: chg = 0.0
        port_rows.append((h.get("name",""), chg))

    # 비용
    mk  = now.strftime("%Y-%m")
    mc  = cost.get("monthly_runs",{}).get(mk,{})
    c_usd  = mc.get("estimated_usd",0.0)
    c_krw  = round(c_usd*1480)
    c_runs = mc.get("runs",0)

    # 시장 데이터
    vix    = market.get("vix","")
    krw    = market.get("krw_usd","")
    pcr    = market.get("pcr_avg")
    pcr_s  = market.get("pcr_signal","")
    hy     = market.get("fred_hy_spread")
    rrp    = market.get("fred_rrp")
    dxy    = market.get("fred_dxy")

    # ── 색상 헬퍼
    def rc(r):
        if "선호" in r: return "#0FC47D"
        if "회피" in r: return "#F04949"
        return "#F5A623"
    def rl(r):
        if "선호" in r: return "위험선호"
        if "회피" in r: return "위험회피"
        return "혼조"
    def sc_col(s):
        if s<=25: return "#F04949"
        if s<=45: return "#F5A623"
        if s<=60: return "#888780"
        if s<=75: return "#0FC47D"
        return "#0DAE6B"
    def conf_style(c):
        m = {"높음":("rgba(15,196,125,.12)","#0DAE6B"),
             "보통":("rgba(245,166,35,.12)","#CC8800"),
             "낮음":("rgba(240,73,73,.12)","#C0392B")}
        return m.get(c,("rgba(136,135,128,.1)","#888780"))

    _rc  = rc(regime)
    _rl  = rl(regime)
    _sc  = sc_col(s_score)
    cbg, cfg = conf_style(confidence)
    kpi_s_cls = "green" if s_score>60 else "amber" if s_score>40 else "red"
    kpi_a_cls = "green" if a_pct>=55  else "amber" if a_pct>=45  else "red"

    # ── 자금 흐름 아이템 HTML (유입/유출 구분)
    def flow_rows(direction):
        if direction=="in":
            items = [(r[0],r[1]) for r in ranking if r[1]>0][:3]
        else:
            items = [(r[0],r[1]) for r in reversed(ranking) if r[1]<0][:3]
        if not items:
            return f'<div class="flow-empty">데이터 없음</div>'
        out=""
        for lbl,val in items:
            sign = "+" if val>=0 else ""
            col  = "#0FC47D" if val>=0 else "#F04949"
            bar  = min(abs(val)*18, 90)
            out += f'''<div class="flow-row">
  <span class="flow-name">{_e(lbl)}</span>
  <div class="flow-bar-wrap"><div class="flow-bar" style="width:{bar}%;background:{col};"></div></div>
  <span class="flow-val" style="color:{col};">{sign}{val}</span>
</div>'''
        return out

    # ── 정확도 카테고리 카드
    def acc_cats():
        if not by_cat: return '<div class="no-data">카테고리 데이터 없음</div>'
        out=""
        for label,v in by_cat.items():
            t = v.get("total",0); c = v.get("correct",0)
            pct = round(c/t*100) if t>0 else 0
            col = "#0FC47D" if pct>=60 else "#F04949" if pct<40 else "#F5A623"
            bar = pct
            out += f'''<div class="acc-row">
  <div class="acc-meta"><span class="acc-label">{_e(label)}</span><span class="acc-sample">{c}/{t}건</span></div>
  <div class="acc-bar-bg"><div class="acc-bar-fill" style="width:{bar}%;background:{col};"></div></div>
  <span class="acc-pct" style="color:{col};">{pct}%</span>
</div>'''
        return out

    # ── 리스크 박스 아이템
    def risk_items():
        risks = []
        # VIX
        try:
            v = float(str(vix).replace("%",""))
            if v>=25: risks.append(("VIX 경고", f"VIX {v} — 변동성 급등 구간", "#F04949"))
            elif v>=20: risks.append(("VIX 주의", f"VIX {v} — 경계선 진입", "#F5A623"))
        except: pass
        # PCR
        if pcr and float(pcr)>=1.2: risks.append(("PCR 극단공포", f"PCR {pcr} — 헤지 수요 급증, 하락 대비 옵션 과다", "#F04949"))
        elif pcr and float(pcr)>=1.0: risks.append(("PCR 공포", f"PCR {pcr} — 풋옵션 우세", "#F5A623"))
        # 하이일드 스프레드
        if hy:
            try:
                h = float(hy)
                if h>=4.0: risks.append(("신용 위험", f"하이일드 스프레드 {h}% — 리스크오프 신호", "#F04949"))
            except: pass
        # 역레포 (유동성)
        if rrp:
            try:
                r = float(rrp)
                if r<0.3: risks.append(("유동성 주의", f"역레포 잔고 {r}조$ — 시중 유동성 축소 가능", "#F5A623"))
            except: pass
        # caution 텍스트에서 핵심 추출
        if caution_txt and not risks:
            risks.append(("오늘 경계", caution_txt[:80], "#F5A623"))
        if not risks:
            risks.append(("특이 리스크 없음", "현재 주요 시장 위험 지표 정상 범위", "#0FC47D"))
        out=""
        for title, desc, col in risks[:2]:
            out += f'''<div class="risk-item" style="border-left:3px solid {col};">
  <div class="risk-title" style="color:{col};">{_e(title)}</div>
  <div class="risk-desc">{_e(desc[:90])}</div>
</div>'''
        return out

    # ── 패턴 칩
    def pat_chips():
        if not pat_sum: return '<div class="no-data">패턴 데이터 없음</div>'
        out='<div class="pat-grid">'
        for p in pat_sum:
            parts = p.split("→")
            lbl  = parts[0].strip()
            prob = parts[1].strip() if len(parts)>1 else ""
            out += f'<div class="pat-chip"><div class="pat-lbl">{_e(lbl)}</div>'
            if prob: out += f'<div class="pat-prob">{_e(prob)}</div>'
            out += '</div>'
        if blackswan.get("reversal_count",0)>0:
            cnt=blackswan["reversal_count"]; avg=blackswan.get("avg_streak_before_reversal",0)
            out += f'<div class="pat-chip pat-swan"><div class="pat-lbl">🦢 블랙스완</div><div class="pat-prob">{cnt}회 · 평균 {avg}일 후 반전</div></div>'
        out += '</div>'
        return out

    # ── 포트폴리오
    def port_html():
        if not port_rows:
            return '''<div class="port-empty">
  <div class="port-empty-icon">📊</div>
  <div class="port-empty-text">포트폴리오 미연동</div>
  <div class="port-empty-sub">연동 시 오늘 손익·비중 표시</div>
</div>'''
        out=""
        for nm,chg in port_rows:
            cls = "pos" if chg>0 else "neg" if chg<0 else "neu"
            sign= "+" if chg>0 else ""
            out += f'<div class="port-row"><span class="port-name">{_e(nm)}</span><span class="port-chg {cls}">{sign}{chg}%</span></div>'
        return out

    # ── 거시지표 칩
    macro_chips = []
    if pcr:     macro_chips.append(("PCR", f"{pcr} ({_e(pcr_s)})", "#F04949" if float(pcr)>=1.0 else "#0FC47D"))
    if rrp:     macro_chips.append(("역레포", f"{rrp}조$", "#888780"))
    if dxy:     macro_chips.append(("DXY", str(dxy), "#888780"))
    if hy:      macro_chips.append(("HY스프레드", f"{hy}%", "#F5A623" if float(str(hy))>=3.5 else "#888780"))

    macro_html = ""
    for lbl,val,col in macro_chips:
        macro_html += f'<div class="macro-chip"><span class="macro-lbl">{_e(lbl)}</span><span class="macro-val" style="color:{col};">{_e(val)}</span></div>'

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>ARIA</title>
<style>
:root{{
  --bg:#F0EFEA;--card:#FFFFFF;--card2:#F5F4F0;--text:#17171A;--sub:#68686B;
  --border:rgba(0,0,0,.07);--green:#0FC47D;--red:#F04949;--amber:#F5A623;--r:16px;
}}
@media(prefers-color-scheme:dark){{:root{{
  --bg:#121211;--card:#1C1C1A;--card2:#232321;--text:#EEEDE6;--sub:#888780;--border:rgba(255,255,255,.07);
}}}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{font-family:-apple-system,'Helvetica Neue',sans-serif;background:var(--bg);color:var(--text);
  max-width:430px;margin:0 auto;padding-bottom:calc(env(safe-area-inset-bottom)+40px);-webkit-font-smoothing:antialiased;}}

/* ── 헤더 */
.hdr{{padding:18px 18px 0;display:flex;align-items:center;justify-content:space-between;}}
.hdr-left{{display:flex;flex-direction:column;gap:2px;}}
.hdr-brand{{font-size:11px;font-weight:700;letter-spacing:3px;color:var(--sub);text-transform:uppercase;}}
.hdr-time{{font-size:11px;color:var(--sub);}}
.regime-pill{{font-size:12px;font-weight:700;padding:6px 14px;border-radius:100px;color:#fff;letter-spacing:.2px;}}

/* ── 결론 박스 */
.conclusion{{margin:14px 16px 0;background:var(--card);border-radius:var(--r);border:.5px solid var(--border);overflow:hidden;}}
.conclusion-top{{padding:14px 16px 10px;}}
.conclusion-meta{{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;}}
.conf-tag{{font-size:11px;font-weight:600;padding:3px 9px;border-radius:100px;}}
.trend-tag{{font-size:11px;font-weight:500;color:var(--sub);background:var(--card2);padding:3px 8px;border-radius:6px;}}
.summary-txt{{font-size:14px;line-height:1.6;color:var(--text);letter-spacing:-.1px;}}
.action-strip{{background:var(--text);padding:12px 16px;display:flex;gap:8px;align-items:flex-start;}}
.action-icon{{font-size:14px;flex-shrink:0;margin-top:1px;}}
.action-txt{{font-size:13px;line-height:1.5;color:var(--bg);font-weight:400;}}

/* ── KPI */
.kpi-wrap{{padding:12px 16px 0;}}
.kpi-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.kpi{{background:var(--card);border-radius:var(--r);border:.5px solid var(--border);padding:15px 16px 13px;position:relative;overflow:hidden;}}
.kpi::after{{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:var(--r) var(--r) 0 0;}}
.kpi.green::after{{background:var(--green);}} .kpi.red::after{{background:var(--red);}} .kpi.amber::after{{background:var(--amber);}}
.kpi-lbl{{font-size:10px;font-weight:600;color:var(--sub);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px;}}
.kpi-num{{font-size:32px;font-weight:800;letter-spacing:-2px;line-height:1;margin-bottom:5px;}}
.kpi-sub{{font-size:11px;color:var(--sub);line-height:1.3;}}
.kpi-wide{{grid-column:span 2;}}

/* ── 섹션 */
.sec{{padding:20px 16px 0;}}
.sec-hdr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}}
.sec-title{{font-size:11px;font-weight:700;color:var(--sub);text-transform:uppercase;letter-spacing:.8px;}}
.sec-sub{{font-size:11px;color:var(--sub);}}
.card{{background:var(--card);border-radius:var(--r);border:.5px solid var(--border);padding:16px;margin-bottom:10px;}}

/* ── 자금 흐름 */
.flow-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.flow-card{{background:var(--card);border-radius:var(--r);border:.5px solid var(--border);padding:14px;}}
.flow-head{{display:flex;align-items:center;gap:6px;margin-bottom:12px;}}
.flow-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}
.flow-head-lbl{{font-size:12px;font-weight:700;}}
.flow-row{{display:flex;align-items:center;gap:6px;padding:4px 0;}}
.flow-name{{font-size:11px;color:var(--text);font-weight:500;width:52px;flex-shrink:0;line-height:1.2;}}
.flow-bar-wrap{{flex:1;height:5px;background:var(--card2);border-radius:3px;overflow:hidden;}}
.flow-bar{{height:100%;border-radius:3px;}}
.flow-val{{font-size:11px;font-weight:700;width:24px;text-align:right;flex-shrink:0;}}
.flow-empty{{font-size:12px;color:var(--sub);padding:8px 0;}}

/* ── 차트 */
.chart-card{{background:var(--card);border-radius:var(--r);border:.5px solid var(--border);padding:16px 16px 12px;margin-bottom:10px;}}
.chart-hdr{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:14px;}}
.chart-title{{font-size:14px;font-weight:600;}}
.chart-stat{{font-size:11px;color:var(--sub);}}
.chart-wrap{{position:relative;}}

/* ── 정확도 카테고리 */
.acc-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:.5px solid var(--border);}}
.acc-row:last-child{{border-bottom:none;}}
.acc-meta{{display:flex;flex-direction:column;width:60px;flex-shrink:0;}}
.acc-label{{font-size:12px;font-weight:600;}}
.acc-sample{{font-size:10px;color:var(--sub);margin-top:1px;}}
.acc-bar-bg{{flex:1;height:6px;background:var(--card2);border-radius:3px;overflow:hidden;}}
.acc-bar-fill{{height:100%;border-radius:3px;}}
.acc-pct{{font-size:13px;font-weight:700;width:36px;text-align:right;flex-shrink:0;}}

/* ── 시장 상태 해석 */
.state-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.state-item{{background:var(--card2);border-radius:10px;padding:12px;border:.5px solid var(--border);}}
.state-lbl{{font-size:10px;font-weight:600;color:var(--sub);text-transform:uppercase;letter-spacing:.6px;margin-bottom:5px;}}
.state-val{{font-size:14px;font-weight:700;line-height:1.2;}}

/* ── 거시지표 */
.macro-row{{display:flex;flex-wrap:wrap;gap:8px;}}
.macro-chip{{background:var(--card2);border-radius:8px;padding:8px 12px;border:.5px solid var(--border);display:flex;flex-direction:column;gap:3px;}}
.macro-lbl{{font-size:10px;color:var(--sub);font-weight:600;text-transform:uppercase;letter-spacing:.4px;}}
.macro-val{{font-size:14px;font-weight:700;}}

/* ── 리스크 */
.risk-item{{padding:12px 14px;border-radius:12px;background:var(--card2);margin-bottom:8px;border:.5px solid var(--border);}}
.risk-title{{font-size:12px;font-weight:700;margin-bottom:4px;}}
.risk-desc{{font-size:12px;color:var(--sub);line-height:1.4;}}

/* ── 패턴 */
.pat-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.pat-chip{{background:var(--card2);border-radius:10px;padding:11px 13px;border:.5px solid var(--border);}}
.pat-lbl{{font-size:12px;font-weight:500;margin-bottom:3px;line-height:1.3;}}
.pat-prob{{font-size:11px;color:var(--sub);}}
.pat-swan{{grid-column:span 2;background:rgba(244,73,73,.05);border-color:rgba(244,73,73,.15);}}

/* ── 포트폴리오 */
.port-row{{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:.5px solid var(--border);}}
.port-row:last-child{{border-bottom:none;}}
.port-name{{font-size:14px;font-weight:500;}}
.port-chg{{font-size:16px;font-weight:800;}}
.port-empty{{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;gap:6px;}}
.port-empty-icon{{font-size:28px;}}
.port-empty-text{{font-size:14px;font-weight:600;color:var(--sub);}}
.port-empty-sub{{font-size:12px;color:var(--sub);opacity:.7;}}

/* ── 비용 */
.cost-row{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:.5px solid var(--border);font-size:13px;}}
.cost-row:last-child{{border-bottom:none;}}
.cost-lbl{{color:var(--sub);}}
.cost-val{{font-weight:700;}}

/* ── 공통 */
.pos{{color:var(--green);}} .neg{{color:var(--red);}} .neu{{color:var(--sub);}}
.no-data{{font-size:12px;color:var(--sub);padding:6px 0;}}
.footer{{text-align:center;font-size:11px;color:var(--sub);padding:20px 16px 8px;line-height:1.7;}}
</style>
</head>
<body>

<!-- ① 헤더 -->
<div class="hdr">
  <div class="hdr-left">
    <span class="hdr-brand">ARIA</span>
    <span class="hdr-time">{now.strftime("%Y.%m.%d %H:%M KST")}</span>
  </div>
  <div class="regime-pill" style="background:{_rc};">{_rl}</div>
</div>

<!-- ② 결론 박스 -->
<div class="conclusion">
  <div class="conclusion-top">
    <div class="conclusion-meta">
      {"" if not confidence else f'<span class="conf-tag" style="background:{cbg};color:{cfg};">신뢰도 {_e(confidence)}</span>'}
      {"" if not trend else f'<span class="trend-tag">{_e(trend)}</span>'}
      {"" if devil_cnt==0 else f'<span class="trend-tag">반론 {devil_cnt}개</span>'}
    </div>
    <p class="summary-txt">{_e(summary) if summary else "분석 데이터 로딩 중"}</p>
  </div>
  {"" if not recommended else f'<div class="action-strip"><span class="action-icon">▶</span><span class="action-txt">{_e(recommended[:120])}</span></div>'}
</div>

<!-- ③ KPI 4개 -->
<div class="kpi-wrap">
  <div class="kpi-grid">
    <div class="kpi {kpi_s_cls}">
      <div class="kpi-lbl">감정지수</div>
      <div class="kpi-num" style="color:{_sc};">{s_score}</div>
      <div class="kpi-sub">{s_emoji} {_e(s_level)}</div>
    </div>
    <div class="kpi {kpi_a_cls}">
      <div class="kpi-lbl">예측 정확도</div>
      <div class="kpi-num">{a_pct}%</div>
      <div class="kpi-sub">방향 {a_dir}% · {a_correct}/{a_total}건</div>
    </div>
    <div class="kpi green">
      <div class="kpi-lbl">자금유입 1위</div>
      <div class="kpi-num" style="font-size:18px;letter-spacing:-.5px;color:var(--green);padding-top:6px;">{_e(top_in)}</div>
      <div class="kpi-sub">30일 누적 선두 섹터</div>
    </div>
    <div class="kpi amber">
      <div class="kpi-lbl">주요 리스크</div>
      <div class="kpi-num" style="font-size:13px;letter-spacing:-.2px;line-height:1.25;padding-top:4px;color:var(--amber);">{_trim(main_risk,30)}</div>
      <div class="kpi-sub">Devil 에이전트 분석</div>
    </div>
  </div>
</div>

<!-- ④ 자금 흐름 -->
<div class="sec">
  <div class="sec-hdr">
    <span class="sec-title">자금 흐름</span>
    <span class="sec-sub">30일 누적 기준</span>
  </div>
  <div class="flow-grid">
    <div class="flow-card">
      <div class="flow-head"><div class="flow-dot" style="background:var(--green);"></div><span class="flow-head-lbl">유입 섹터</span></div>
      {flow_rows("in")}
    </div>
    <div class="flow-card">
      <div class="flow-head"><div class="flow-dot" style="background:var(--red);"></div><span class="flow-head-lbl">유출 섹터</span></div>
      {flow_rows("out")}
    </div>
  </div>
</div>

<!-- ⑤ 감정지수 추이 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">감정지수 추이</span><span class="sec-sub">30일</span></div>
  <div class="chart-card">
    <div class="chart-hdr">
      <span class="chart-title">현재 {s_score} · {_e(s_level)}</span>
      <span class="chart-stat">{s_emoji}</span>
    </div>
    <div class="chart-wrap" style="height:130px;"><canvas id="sentChart"></canvas></div>
  </div>
</div>

<!-- ⑥ 정확도 상세 -->
<div class="sec">
  <div class="sec-hdr">
    <span class="sec-title">예측 정확도</span>
    <span class="sec-sub">종합 {a_pct}% · {a_total}건</span>
  </div>
  <div class="card" style="padding:8px 16px;">
    {acc_cats()}
  </div>
</div>

<!-- ⑦ 시장 상태 해석 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">시장 상태</span></div>
  <div class="card" style="padding:12px;">
    <div class="state-grid">
      <div class="state-item">
        <div class="state-lbl">레짐</div>
        <div class="state-val" style="color:{_rc};">{_e(_rl)}</div>
      </div>
      <div class="state-item">
        <div class="state-lbl">추세</div>
        <div class="state-val">{_e(trend) if trend else "—"}</div>
      </div>
      <div class="state-item">
        <div class="state-lbl">확신도</div>
        <div class="state-val" style="color:{cfg};">{_e(confidence) if confidence else "—"}</div>
      </div>
      <div class="state-item">
        <div class="state-lbl">반론 강도</div>
        <div class="state-val" style="color:{'var(--red)' if devil_cnt>=4 else 'var(--amber)' if devil_cnt>=2 else 'var(--green)'};">{"강" if devil_cnt>=4 else "보통" if devil_cnt>=2 else "약"} ({devil_cnt}개)</div>
      </div>
    </div>
  </div>
</div>

<!-- ⑧ 거시지표 -->
{"" if not macro_html else f'<div class="sec"><div class="sec-hdr"><span class="sec-title">거시지표</span></div><div class="card" style="padding:12px;"><div class="macro-row">{macro_html}</div></div></div>'}

<!-- ⑨ 경고/리스크 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">오늘의 경고</span></div>
  {risk_items()}
</div>

<!-- ⑩ 섹터 자금흐름 차트 -->
{"" if not rot_labels else f'''<div class="sec">
  <div class="sec-hdr"><span class="sec-title">섹터 자금흐름</span><span class="sec-sub">30일 누적</span></div>
  <div class="chart-card">
    <div class="chart-wrap" style="height:{max(130,len(rot_labels)*32)}px;"><canvas id="rotChart"></canvas></div>
  </div>
</div>'''}

<!-- ⑪ 레짐 전환 패턴 -->
{"" if not pat_sum else f'<div class="sec"><div class="sec-hdr"><span class="sec-title">레짐 전환 패턴</span></div><div class="card" style="padding:12px;">{pat_chips()}</div></div>'}

<!-- ⑫ 포트폴리오 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">포트폴리오</span><span class="sec-sub">오늘 손익</span></div>
  <div class="card" style="padding:{'8px 16px' if port_rows else '0'};">
    {port_html()}
  </div>
</div>

<!-- ⑬ 비용 + 푸터 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">이번 달 비용</span></div>
  <div class="card" style="padding:6px 16px;">
    <div class="cost-row"><span class="cost-lbl">추정 비용</span><span class="cost-val">${c_usd:.2f} · 약 {c_krw:,}원</span></div>
    <div class="cost-row"><span class="cost-lbl">실행 횟수</span><span class="cost-val">{c_runs}회</span></div>
  </div>
</div>

<div class="footer">
  분석일 {_e(analysis_dt)} · ARIA Multi-Agent v3<br>
  Yahoo Finance · FRED · FSC · FearGreedChart · PCR
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const dk=matchMedia('(prefers-color-scheme:dark)').matches;
const tc=dk?'rgba(255,255,255,.4)':'rgba(0,0,0,.35)';
const gc=dk?'rgba(255,255,255,.05)':'rgba(0,0,0,.05)';
const tip={{backgroundColor:dk?'rgba(28,28,26,.96)':'rgba(255,255,255,.96)',
  titleColor:dk?'#eee':'#111',bodyColor:dk?'#aaa':'#555',
  borderColor:dk?'rgba(255,255,255,.1)':'rgba(0,0,0,.08)',borderWidth:1,padding:10,cornerRadius:8}};

const sEl=document.getElementById('sentChart');
if(sEl)new Chart(sEl,{{type:'line',
  data:{{labels:{_j(s_dates)},datasets:[
    {{data:{_j(s_scores)},borderColor:'#0FC47D',backgroundColor:'rgba(15,196,125,.07)',
     fill:true,tension:.4,pointRadius:0,pointHoverRadius:4,borderWidth:2}},
    {{data:Array({len(s_scores)}).fill(50),borderColor:'rgba(136,135,128,.35)',
     borderDash:[4,3],borderWidth:1.5,pointRadius:0}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{mode:'index',intersect:false,...tip}}}},
    scales:{{
      x:{{ticks:{{color:tc,font:{{size:9}},maxRotation:0,autoSkip:true,maxTicksLimit:6}},grid:{{color:gc}}}},
      y:{{min:0,max:100,ticks:{{color:tc,font:{{size:9}},stepSize:25}},grid:{{color:gc}}}}
    }}
  }}
}});

const rEl=document.getElementById('rotChart');
if(rEl)new Chart(rEl,{{type:'bar',
  data:{{labels:{_j(rot_labels)},datasets:[{{
    data:{_j(rot_values)},
    backgroundColor:{_j(rot_values)}.map(v=>v>=0?'rgba(15,196,125,.75)':'rgba(240,73,73,.7)'),
    borderRadius:4,barPercentage:.6
  }}]}},
  options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}},tooltip:{{...tip}}}},
    scales:{{
      x:{{ticks:{{color:tc,font:{{size:9}}}},grid:{{color:gc}}}},
      y:{{ticks:{{color:tc,font:{{size:10}}}},grid:{{display:false}}}}
    }}
  }}
}});
</script>
</body>
</html>"""

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print("dashboard.html 생성 완료: " + str(OUTPUT_FILE))
    return html


if __name__ == "__main__":
    build_dashboard()
    print("완료")
