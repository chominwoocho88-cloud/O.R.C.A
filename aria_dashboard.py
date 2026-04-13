"""aria_dashboard.py — ARIA Dashboard v4 (Dark Espresso)"""
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
        try: return json.loads(path.read_text(encoding="utf-8"))
        except: pass
    return default or {}

def _j(v): return json.dumps(v, ensure_ascii=False)
def _e(s): return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def _trim(s,n): t=str(s); return _e(t[:n]+("…" if len(t)>n else ""))

def build_dashboard():
    now    = datetime.now(KST)
    sent   = _load(SENTIMENT_FILE, {"history":[],"current":{}})
    acc    = _load(ACCURACY_FILE,  {"total":0,"correct":0,"by_category":{}})
    rot    = _load(ROTATION_FILE,  {"ranking":[]})
    memory = _load(MEMORY_FILE,    [])
    cost   = _load(COST_FILE,      {})
    pat    = _load(PATTERN_DB_FILE,{})
    mkt    = _load(DATA_FILE,      {})

    cur    = sent.get("current",{})
    h30    = sent.get("history",[])[-30:]
    latest = memory[-1] if isinstance(memory,list) and memory else {}

    sd = [h["date"][5:] for h in h30]; ss = [h["score"] for h in h30]
    sc = cur.get("score",50); sl = cur.get("level","중립"); se = cur.get("emoji","😐")

    at = acc.get("total",0); ac = acc.get("correct",0)
    ap = round(ac/at*100,1) if at>0 else 0; adp = acc.get("dir_accuracy_pct",0)
    bcat = acc.get("by_category",{})

    rnk = rot.get("ranking",[])
    rl8 = [r[0] for r in rnk][:8]; rv8 = [r[1] for r in rnk][:8]
    ti  = rnk[0][0] if rnk and rnk[0][1]>0 else "—"

    regime   = latest.get("market_regime","")
    conf     = latest.get("confidence_overall","")
    summ     = latest.get("one_line_summary","")
    trend    = latest.get("trend_phase","")
    strat    = latest.get("trend_strategy",{})
    rec      = strat.get("recommended","") if isinstance(strat,dict) else ""
    caut     = strat.get("caution","")     if isinstance(strat,dict) else ""
    adt      = latest.get("analysis_date","")
    cargs    = latest.get("counterarguments",[])
    dc       = len(cargs)
    mrisk    = cargs[0].get("against","—") if cargs else "—"
    psm      = pat.get("summary",[])[:4]; bsw = pat.get("blackswan",{})

    port_rows = []
    if PORTFOLIO_FILE.exists():
        try:
            hs = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8")).get("holdings",[])
            for h in hs:
                if h.get("ticker")=="cash": continue
                cs = mkt.get(str(h.get("ticker",""))+"_change","0%")
                try: cv=float(str(cs).replace("%","").replace("+",""))
                except: cv=0.0
                port_rows.append((h.get("name",""),cv))
        except: pass

    mk2=now.strftime("%Y-%m"); mc=cost.get("monthly_runs",{}).get(mk2,{})
    cu=mc.get("estimated_usd",0.0); ck=round(cu*1480); cr=mc.get("runs",0)

    vix=mkt.get("vix",""); krw=mkt.get("krw_usd","")
    pcr=mkt.get("pcr_avg"); pcrs=mkt.get("pcr_signal","")
    hy=mkt.get("fred_hy_spread"); rrp=mkt.get("fred_rrp"); dxy=mkt.get("fred_dxy")
    fg=mkt.get("fear_greed_value","")

    def _rc(r):
        if "선호" in r: return "#14E87A"
        if "회피" in r: return "#FF5252"
        return "#FFB547"
    def _rl(r):
        if "선호" in r: return "위험선호"
        if "회피" in r: return "위험회피"
        return "혼조"
    def _sc(s):
        if s<=25: return "#FF5252"
        if s<=45: return "#FFB547"
        if s<=60: return "#909090"
        return "#14E87A"
    def _cbg(c):
        return {"높음":"rgba(20,232,122,.15)","보통":"rgba(255,181,71,.15)","낮음":"rgba(255,82,82,.15)"}.get(c,"rgba(144,144,144,.12)")
    def _cfg(c):
        return {"높음":"#14E87A","보통":"#FFB547","낮음":"#FF5252"}.get(c,"#909090")

    rco=_rc(regime); rla=_rl(regime); sco=_sc(sc)
    cbg=_cbg(conf); cfg2=_cfg(conf)

    # 자금흐름 아이템
    def flow_block(direction):
        items = [(r[0],r[1]) for r in rnk if r[1]>0][:3] if direction=="in" else [(r[0],r[1]) for r in reversed(rnk) if r[1]<0][:3]
        if not items: return '<div class="fe">데이터 없음</div>'
        o=""
        for lbl,val in items:
            col="#14E87A" if val>=0 else "#FF5252"
            bw=min(abs(val)*14,85)
            sign="+" if val>=0 else ""
            o+=f'<div class="frow"><div class="fn">{_e(lbl[:6])}</div><div class="fbg"><div class="fb" style="width:{bw}%;background:{col};opacity:.85;"></div></div><span class="fv" style="color:{col};">{sign}{val}</span></div>'
        return o

    # 정확도 카테고리
    def acc_block():
        if not bcat: return '<div class="fe">카테고리 없음</div>'
        o=""
        for lbl,v in bcat.items():
            t=v.get("total",0); c=v.get("correct",0)
            p=round(c/t*100) if t>0 else 0
            col="#14E87A" if p>=60 else "#FF5252" if p<40 else "#FFB547"
            o+=f'''<div class="arow">
  <div class="am"><div class="albl">{_e(lbl)}</div><div class="asub">{c}/{t}건</div></div>
  <div class="abg"><div class="afill" style="width:{p}%;background:{col};"></div></div>
  <span class="apct" style="color:{col};">{p}%</span>
</div>'''
        return o

    # 리스크 판단
    def risk_block():
        items=[]
        if pcr:
            try:
                p=float(pcr)
                if p>=1.2: items.append(("PCR 극단공포",f"PCR {p} · 헤지 수요 폭발","#FF5252"))
                elif p>=1.0: items.append(("PCR 공포",f"PCR {p} · 풋옵션 우세","#FFB547"))
            except: pass
        try:
            v=float(str(vix))
            if v>=25: items.append(("VIX 경고",f"VIX {v} · 변동성 급등","#FF5252"))
            elif v>=20: items.append(("VIX 주의",f"VIX {v} · 경계선","#FFB547"))
        except: pass
        if hy:
            try:
                h=float(hy)
                if h>=4.0: items.append(("신용위험",f"HY스프레드 {h}% · 리스크오프","#FF5252"))
            except: pass
        if not items: items=[("특이 리스크 없음","주요 지표 정상 범위","#14E87A")]
        o=""
        for title,desc,col in items[:2]:
            o+=f'<div class="ritem"><div class="rtitle" style="color:{col};">⬤ {_e(title)}</div><div class="rdesc">{_e(desc[:70])}</div></div>'
        return o

    # 패턴 칩
    def pat_block():
        if not psm: return '<div class="fe">데이터 없음</div>'
        o='<div class="patg">'
        for p in psm:
            pts=p.split("→"); lbl=pts[0].strip(); pr=pts[1].strip() if len(pts)>1 else ""
            o+=f'<div class="pchip"><div class="plbl">{_e(lbl)}</div>'
            if pr: o+=f'<div class="ppr">{_e(pr)}</div>'
            o+='</div>'
        if bsw.get("reversal_count",0)>0:
            cnt=bsw["reversal_count"]; avg=bsw.get("avg_streak_before_reversal",0)
            o+=f'<div class="pchip pswan"><div class="plbl">🦢 블랙스완</div><div class="ppr">{cnt}회 · 평균 {avg}일</div></div>'
        o+='</div>'
        return o

    # 거시지표 칩
    mch=""
    if pcr:   mch+=f'<div class="mchip"><div class="mlbl">PCR</div><div class="mval" style="color:{"#FF5252" if float(pcr)>=1.0 else "#14E87A"};">{pcr}<br><small>{_e(pcrs)}</small></div></div>'
    if rrp:   mch+=f'<div class="mchip"><div class="mlbl">역레포</div><div class="mval">{rrp}조$</div></div>'
    if dxy:   mch+=f'<div class="mchip"><div class="mlbl">달러지수</div><div class="mval">{dxy}</div></div>'
    if hy:    mch+=f'<div class="mchip"><div class="mlbl">HY스프레드</div><div class="mval" style="color:{"#FFB547" if float(str(hy))>=3.5 else "#909090"};">{hy}%</div></div>'
    if fg:    mch+=f'<div class="mchip"><div class="mlbl">공포탐욕</div><div class="mval">{_e(str(fg))}</div></div>'

    port_html = ""
    if port_rows:
        for nm,cv in port_rows:
            cls="pos" if cv>0 else "neg" if cv<0 else "neu"; sign="+" if cv>0 else ""
            port_html+=f'<div class="prow"><span class="pname">{_e(nm)}</span><span class="pval {cls}">{sign}{cv}%</span></div>'
    else:
        port_html='<div class="pempty"><span>📊</span><span>포트폴리오 미연동</span></div>'

    html=f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>ARIA</title>
<style>
:root{{
  --bg:#18160F;       /* 다크 에스프레소 */
  --s1:#211E16;       /* 카드 1레벨 */
  --s2:#2A271E;       /* 카드 2레벨 */
  --s3:#332F24;       /* 인풋/배지 */
  --tx:#EDE9DF;       /* 메인 텍스트 */
  --mu:#7A7669;       /* 뮤트 텍스트 */
  --gr:#14E87A;       /* 그린 */
  --rd:#FF5252;       /* 레드 */
  --am:#FFB547;       /* 앰버 */
  --bd:rgba(255,255,255,.06); /* 보더 */
  --r:16px;
}}
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{
  font-family:-apple-system,'Helvetica Neue',sans-serif;
  background:var(--bg);color:var(--tx);
  max-width:430px;margin:0 auto;
  padding-bottom:calc(env(safe-area-inset-bottom)+40px);
  -webkit-font-smoothing:antialiased;
}}

/* ── 헤더 */
.hdr{{
  padding:20px 18px 0;
  display:flex;align-items:center;justify-content:space-between;
}}
.brand{{font-size:11px;font-weight:800;letter-spacing:3.5px;color:var(--mu);text-transform:uppercase;}}
.hdr-time{{font-size:11px;color:var(--mu);margin-top:3px;}}
.regime-badge{{
  font-size:12px;font-weight:700;
  padding:7px 16px;border-radius:100px;
  color:#0A0A08;letter-spacing:.3px;
}}

/* ── 결론 패널 */
.summary-panel{{
  margin:14px 16px 0;
  background:var(--s1);
  border-radius:var(--r);
  border:.5px solid var(--bd);
  overflow:hidden;
}}
.sp-top{{padding:16px 18px 14px;}}
.sp-meta{{display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap;}}
.conf-pill{{font-size:11px;font-weight:700;padding:3px 10px;border-radius:100px;}}
.trend-pill{{font-size:11px;color:var(--mu);background:var(--s3);padding:3px 9px;border-radius:6px;}}
.devil-pill{{font-size:11px;color:var(--am);background:rgba(255,181,71,.1);padding:3px 9px;border-radius:6px;border:.5px solid rgba(255,181,71,.2);}}
.summ-txt{{font-size:14px;line-height:1.65;color:var(--tx);letter-spacing:-.1px;}}
.action-bar{{
  background:rgba(20,232,122,.08);
  border-top:.5px solid rgba(20,232,122,.15);
  padding:12px 18px;
  display:flex;gap:8px;align-items:flex-start;
}}
.action-icon{{color:var(--gr);font-size:12px;flex-shrink:0;margin-top:2px;}}
.action-txt{{font-size:13px;line-height:1.55;color:rgba(237,233,223,.85);}}

/* ── KPI 섹션 */
.kpi-wrap{{padding:12px 16px 0;}}
.kpi-row1{{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;}}
.kpi-row2{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.kpi{{
  background:var(--s1);border-radius:var(--r);
  border:.5px solid var(--bd);
  padding:15px 16px 13px;
  position:relative;overflow:hidden;
}}
.kpi::before{{
  content:'';position:absolute;
  top:0;left:0;right:0;height:2.5px;
}}
.kpi.gr::before{{background:var(--gr);}}
.kpi.rd::before{{background:var(--rd);}}
.kpi.am::before{{background:var(--am);}}
.kpi-lbl{{font-size:10px;font-weight:700;color:var(--mu);text-transform:uppercase;letter-spacing:.9px;margin-bottom:9px;}}
.kpi-num{{font-size:34px;font-weight:800;letter-spacing:-2px;line-height:1;margin-bottom:5px;}}
.kpi-sub{{font-size:11px;color:var(--mu);line-height:1.3;}}
.kpi-mid{{font-size:18px;letter-spacing:-.5px;line-height:1.2;padding-top:4px;margin-bottom:5px;}}
.kpi-risk{{font-size:13px;letter-spacing:-.2px;line-height:1.3;padding-top:3px;margin-bottom:5px;}}

/* ── 섹션 공통 */
.sec{{padding:20px 16px 0;}}
.sec-hdr{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;}}
.sec-title{{font-size:11px;font-weight:700;color:var(--mu);text-transform:uppercase;letter-spacing:.9px;}}
.sec-note{{font-size:11px;color:var(--mu);opacity:.7;}}
.card{{background:var(--s1);border-radius:var(--r);border:.5px solid var(--bd);padding:16px;margin-bottom:10px;}}

/* ── 자금 흐름 */
.fgrid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.fcard{{background:var(--s1);border-radius:var(--r);border:.5px solid var(--bd);padding:14px;}}
.fhead{{display:flex;align-items:center;gap:7px;margin-bottom:12px;}}
.fdot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;}}
.fhlbl{{font-size:12px;font-weight:700;}}
.frow{{display:flex;align-items:center;gap:6px;padding:4px 0;}}
.fn{{font-size:11px;color:var(--tx);font-weight:500;width:48px;flex-shrink:0;line-height:1.2;}}
.fbg{{flex:1;height:4px;background:var(--s3);border-radius:2px;overflow:hidden;}}
.fb{{height:100%;border-radius:2px;}}
.fv{{font-size:11px;font-weight:700;width:32px;text-align:right;flex-shrink:0;}}
.fe{{font-size:12px;color:var(--mu);padding:4px 0;}}

/* ── 차트 */
.chart-card{{background:var(--s1);border-radius:var(--r);border:.5px solid var(--bd);padding:16px 16px 12px;margin-bottom:10px;}}
.ch{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px;}}
.cht{{font-size:14px;font-weight:700;}}
.chs{{font-size:11px;color:var(--mu);}}
.chart-wrap{{position:relative;}}

/* ── 정확도 카테고리 */
.arow{{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:.5px solid var(--bd);}}
.arow:last-child{{border-bottom:none;}}
.am{{display:flex;flex-direction:column;width:54px;flex-shrink:0;}}
.albl{{font-size:12px;font-weight:700;}}
.asub{{font-size:10px;color:var(--mu);margin-top:2px;}}
.abg{{flex:1;height:5px;background:var(--s3);border-radius:3px;overflow:hidden;}}
.afill{{height:100%;border-radius:3px;}}
.apct{{font-size:13px;font-weight:800;width:36px;text-align:right;flex-shrink:0;}}

/* ── 시장상태 그리드 */
.stgrid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.sti{{background:var(--s2);border-radius:10px;padding:12px;border:.5px solid var(--bd);}}
.stlbl{{font-size:10px;font-weight:700;color:var(--mu);text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;}}
.stval{{font-size:15px;font-weight:800;line-height:1.2;}}

/* ── 거시지표 */
.mrow{{display:flex;flex-wrap:wrap;gap:8px;}}
.mchip{{background:var(--s2);border-radius:10px;padding:10px 13px;border:.5px solid var(--bd);min-width:72px;}}
.mlbl{{font-size:10px;font-weight:700;color:var(--mu);text-transform:uppercase;letter-spacing:.4px;margin-bottom:5px;}}
.mval{{font-size:15px;font-weight:800;line-height:1.2;}}
.mval small{{font-size:10px;font-weight:500;opacity:.75;}}

/* ── 리스크 */
.ritem{{
  background:var(--s1);border-radius:12px;
  padding:12px 14px;margin-bottom:8px;
  border:.5px solid var(--bd);
  border-left-width:3px;
}}
.rtitle{{font-size:12px;font-weight:700;margin-bottom:5px;}}
.rdesc{{font-size:12px;color:var(--mu);line-height:1.45;}}

/* ── 경고 배너 */
.caution-bar{{
  background:rgba(255,181,71,.06);
  border:.5px solid rgba(255,181,71,.2);
  border-radius:12px;
  padding:12px 16px;
  display:flex;gap:10px;align-items:flex-start;
}}
.cb-icon{{font-size:14px;flex-shrink:0;}}
.cb-txt{{font-size:12px;line-height:1.55;color:rgba(237,233,223,.8);}}

/* ── 패턴 */
.patg{{display:grid;grid-template-columns:1fr 1fr;gap:8px;}}
.pchip{{background:var(--s2);border-radius:10px;padding:11px 13px;border:.5px solid var(--bd);}}
.plbl{{font-size:12px;font-weight:600;margin-bottom:3px;line-height:1.3;}}
.ppr{{font-size:11px;color:var(--mu);}}
.pswan{{grid-column:span 2;background:rgba(255,82,82,.05);border-color:rgba(255,82,82,.15);}}

/* ── 포트폴리오 */
.prow{{display:flex;justify-content:space-between;align-items:center;padding:11px 0;border-bottom:.5px solid var(--bd);}}
.prow:last-child{{border-bottom:none;}}
.pname{{font-size:14px;font-weight:600;}}
.pval{{font-size:17px;font-weight:800;}}
.pempty{{display:flex;flex-direction:column;align-items:center;padding:22px;gap:6px;color:var(--mu);font-size:13px;}}
.pempty span:first-child{{font-size:26px;}}

/* ── 비용 */
.crow{{display:flex;justify-content:space-between;align-items:center;padding:9px 0;border-bottom:.5px solid var(--bd);font-size:13px;}}
.crow:last-child{{border-bottom:none;}}
.clbl{{color:var(--mu);}}
.cval{{font-weight:700;}}

/* ── 공통 */
.pos{{color:var(--gr);}} .neg{{color:var(--rd);}} .neu{{color:var(--mu);}}
.no-data{{font-size:12px;color:var(--mu);padding:6px 0;}}
.footer{{text-align:center;font-size:11px;color:var(--mu);padding:20px 16px 8px;line-height:1.7;opacity:.7;}}
</style>
</head>
<body>

<!-- ① 헤더 -->
<div class="hdr">
  <div>
    <div class="brand">ARIA</div>
    <div class="hdr-time">{now.strftime("%Y.%m.%d %H:%M KST")}</div>
  </div>
  <div class="regime-badge" style="background:{rco};">{_e(rla)}</div>
</div>

<!-- ② 결론 패널 -->
<div class="summary-panel">
  <div class="sp-top">
    <div class="sp-meta">
      {"" if not conf else f'<span class="conf-pill" style="background:{cbg};color:{cfg2};">신뢰도 {_e(conf)}</span>'}
      {"" if not trend else f'<span class="trend-pill">{_e(trend)}</span>'}
      {"" if dc==0 else f'<span class="devil-pill">반론 {dc}개</span>'}
    </div>
    <p class="summ-txt">{_e(summ) if summ else "분석 로딩 중"}</p>
  </div>
  {"" if not rec else f'<div class="action-bar"><span class="action-icon">▶</span><span class="action-txt">{_e(rec[:130])}</span></div>'}
</div>

<!-- ③ KPI -->
<div class="kpi-wrap">
  <div class="kpi-row1">
    <div class="kpi {'gr' if sc>60 else 'am' if sc>40 else 'rd'}">
      <div class="kpi-lbl">감정지수</div>
      <div class="kpi-num" style="color:{sco};">{sc}</div>
      <div class="kpi-sub">{se} {_e(sl)}</div>
    </div>
    <div class="kpi {'gr' if ap>=55 else 'am' if ap>=45 else 'rd'}">
      <div class="kpi-lbl">예측 정확도</div>
      <div class="kpi-num">{ap}%</div>
      <div class="kpi-sub">방향 {adp}% · {ac}/{at}건</div>
    </div>
  </div>
  <div class="kpi-row2">
    <div class="kpi gr">
      <div class="kpi-lbl">자금유입 1위</div>
      <div class="kpi-mid" style="color:var(--gr);">{_e(ti)}</div>
      <div class="kpi-sub">30일 누적 선두</div>
    </div>
    <div class="kpi am">
      <div class="kpi-lbl">주요 리스크</div>
      <div class="kpi-risk" style="color:var(--am);">{_trim(mrisk,28)}</div>
      <div class="kpi-sub">Devil 분석</div>
    </div>
  </div>
</div>

<!-- ④ 자금 흐름 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">자금 흐름</span><span class="sec-note">30일 누적</span></div>
  <div class="fgrid">
    <div class="fcard">
      <div class="fhead"><div class="fdot" style="background:var(--gr);"></div><span class="fhlbl">유입</span></div>
      {flow_block("in")}
    </div>
    <div class="fcard">
      <div class="fhead"><div class="fdot" style="background:var(--rd);"></div><span class="fhlbl">유출</span></div>
      {flow_block("out")}
    </div>
  </div>
</div>

<!-- ⑤ 감정지수 추이 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">감정지수 추이</span><span class="sec-note">30일</span></div>
  <div class="chart-card">
    <div class="ch"><span class="cht">현재 {sc} · {_e(sl)}</span><span class="chs">{se}</span></div>
    <div class="chart-wrap" style="height:125px;"><canvas id="sentChart"></canvas></div>
  </div>
</div>

<!-- ⑥ 정확도 상세 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">예측 정확도</span><span class="sec-note">카테고리 · 샘플 수</span></div>
  <div class="card" style="padding:8px 16px;">{acc_block()}</div>
</div>

<!-- ⑦ 시장 상태 해석 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">시장 상태</span></div>
  <div class="card" style="padding:12px;">
    <div class="stgrid">
      <div class="sti"><div class="stlbl">레짐</div><div class="stval" style="color:{rco};">{_e(rla)}</div></div>
      <div class="sti"><div class="stlbl">추세</div><div class="stval">{_e(trend) if trend else "—"}</div></div>
      <div class="sti"><div class="stlbl">확신도</div><div class="stval" style="color:{cfg2};">{_e(conf) if conf else "—"}</div></div>
      <div class="sti"><div class="stlbl">반론 강도</div><div class="stval" style="color:{'var(--rd)' if dc>=4 else 'var(--am)' if dc>=2 else 'var(--gr)'};">{"강" if dc>=4 else "보통" if dc>=2 else "약"}({dc})</div></div>
    </div>
  </div>
</div>

<!-- ⑧ 거시지표 -->
{"" if not mch else f'<div class="sec"><div class="sec-hdr"><span class="sec-title">거시지표</span></div><div class="card" style="padding:12px;"><div class="mrow">{mch}</div></div></div>'}

<!-- ⑨ 경고/리스크 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">오늘의 경고</span></div>
  {risk_block()}
  {"" if not caut else f'<div class="caution-bar"><span class="cb-icon">⚠️</span><span class="cb-txt">{_e(caut[:110])}</span></div>'}
</div>

<!-- ⑩ 섹터 차트 -->
{"" if not rl8 else f'''<div class="sec">
  <div class="sec-hdr"><span class="sec-title">섹터 자금흐름</span><span class="sec-note">30일 누적</span></div>
  <div class="chart-card">
    <div class="chart-wrap" style="height:{max(130,len(rl8)*32)}px;"><canvas id="rotChart"></canvas></div>
  </div>
</div>'''}

<!-- ⑪ 레짐 전환 패턴 -->
{"" if not psm else f'<div class="sec"><div class="sec-hdr"><span class="sec-title">레짐 전환 패턴</span></div><div class="card" style="padding:12px;">{pat_block()}</div></div>'}

<!-- ⑫ 포트폴리오 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">포트폴리오</span><span class="sec-note">오늘 손익</span></div>
  <div class="card" style="padding:{'8px 16px' if port_rows else '0'};">{port_html}</div>
</div>

<!-- ⑬ 비용 -->
<div class="sec">
  <div class="sec-hdr"><span class="sec-title">이번 달 비용</span></div>
  <div class="card" style="padding:6px 16px;">
    <div class="crow"><span class="clbl">추정 비용</span><span class="cval">${cu:.2f} · 약 {ck:,}원</span></div>
    <div class="crow"><span class="clbl">실행 횟수</span><span class="cval">{cr}회</span></div>
  </div>
</div>

<div class="footer">
  분석일 {_e(adt)} · ARIA Multi-Agent v4<br>
  Yahoo Finance · FRED · FSC · FearGreedChart · PCR
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const tc='rgba(122,118,105,.55)',gc='rgba(255,255,255,.05)';
const tip={{backgroundColor:'rgba(33,30,22,.97)',titleColor:'#EDE9DF',bodyColor:'#7A7669',
  borderColor:'rgba(255,255,255,.08)',borderWidth:1,padding:10,cornerRadius:8}};
const sEl=document.getElementById('sentChart');
if(sEl)new Chart(sEl,{{type:'line',
  data:{{labels:{_j(sd)},datasets:[
    {{data:{_j(ss)},borderColor:'#14E87A',backgroundColor:'rgba(20,232,122,.06)',
     fill:true,tension:.4,pointRadius:0,pointHoverRadius:5,borderWidth:2.5}},
    {{data:Array({len(ss)}).fill(50),borderColor:'rgba(122,118,105,.3)',borderDash:[4,3],borderWidth:1.5,pointRadius:0}}
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
  data:{{labels:{_j(rl8)},datasets:[{{
    data:{_j(rv8)},
    backgroundColor:{_j(rv8)}.map(v=>v>=0?'rgba(20,232,122,.7)':'rgba(255,82,82,.65)'),
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
