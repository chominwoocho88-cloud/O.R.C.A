# JACKAL Current Signals

## Section 0: Scope & Method

조사 대상 파일:
- `jackal/hunter.py` (`1-1665`)
- `jackal/scanner.py` (`1-1990`)
- `jackal/core.py` (`1-163`)
- `jackal/evolution.py` (`1-940`)
- `jackal/probability.py` (`1-59`)
- `jackal/adapter.py` (`1-195`)

보조 참고:
- `jackal/market_data.py` — Scanner가 호출하는 기술지표 계산 공급자. Ref: `jackal/scanner.py:40-41`, `jackal/market_data.py:431-471`
- `jackal/families.py` — Hunter/Scanner/ORCA가 공유하는 family 정규화 테이블. Ref: `jackal/hunter.py:324-327`, `jackal/scanner.py:39`, `jackal/families.py:7-109`
- `jackal/tracker.py` — hunt outcome을 별도 주기로 다시 기록하는 보조 경로. Ref: `jackal/tracker.py:335-532`
- `docs/phase5/01-db-audit.md` — JACKAL write path와 state spine 조사 결과. Ref: `docs/phase5/01-db-audit.md:67-80`

조사 방법:
- 정적 코드 분석
- 함수/상수/조건식 line-by-line 확인
- `Select-String` 기반 존재 여부 검색
- 보조 파일은 호출 계약이 드러나는 부분만 확인

한계:
- 이 문서는 런타임 실행 결과가 아니라 코드 경로 기준 설명이다.
- 외부 API 응답 형식, LLM 응답 분포, 장중 스케줄 타이밍은 코드에서 추정 가능한 범위까지만 기술한다.

멈춤 조건 점검:
- 조사 대상 파일 중 `5000`줄 초과 파일 없음
- Section 1~4 구조와 실제 코드 흐름은 대응 가능
- 평가/판단 없이 기술 서술 가능한 상태

## Section 1: Hunter (`jackal/hunter.py`)

### 1.1. Input Sources

Hunter 입력 소스는 다음 여섯 묶음으로 구성된다.

1. ORCA 컨텍스트
- `load_orca_context()` 를 통해 `morning_baseline.json`, `memory.json`, `jackal_news.json` 을 읽고, baseline 부재 시 fallback regime 을 계산한다. Ref: `jackal/hunter.py:49-53`, `jackal/hunter.py:1499-1516`, `jackal/adapter.py:97-163`
- ORCA 컨텍스트에 포함되는 키:
  - `one_line`
  - `regime`
  - `top_headlines`
  - `key_inflows`
  - `key_outflows`
  - `thesis_killers`
  - `actionable`
  - `inflows_detail`
  - `outflows_detail`
  - `all_headlines`
  - `jackal_news`
  - `regime_source`
  Ref: `jackal/adapter.py:98-110`

2. Universe seed
- 고정 sector universe 는 `SECTOR_POOLS` 에 정의되어 있다. Ref: `jackal/hunter.py:100-140`
- sector별 ETF 맵은 `SECTOR_ETF` 에 정의되어 있다. Ref: `jackal/hunter.py:142-151`
- portfolio exclusions 는 `data/portfolio.json` 또는 기본 exclusions 집합에서 읽는다. Ref: `jackal/hunter.py:73-97`

3. LLM ticker expansion
- `_claude_suggest_20()` 이 ORCA headline/actionable context 와 현재 universe 를 prompt 로 넣고 최대 20개 ticker suggestion 을 받는다. Anthropic web search tool이 함께 선언된다. Ref: `jackal/hunter.py:269-304`

4. Macro gate
- VIX: `^VIX`
- 10Y yield: `^TNX`
- 3M yield: `^IRX`
- HY proxy: `HYG`
  Ref: `jackal/hunter.py:372-399`

5. Sector relative move
- `_fetch_etf_returns()` 가 sector ETF 들의 최근 5거래일 수익률을 계산한다. Ref: `jackal/hunter.py:450-472`

6. Per-ticker OHLCV
- 미국 종목은 `yf.download(... period="65d")` batch 다운로드를 사용한다. Ref: `jackal/hunter.py:487-503`
- 한국 종목은 `yf.Ticker(t).history(period="65d")` 개별 호출을 사용한다. Ref: `jackal/hunter.py:505-514`

### 1.2. Decision Logic

Hunter는 `run_hunt()` 에서 4-stage 파이프라인으로 동작한다. Ref: `jackal/hunter.py:1495-1665`

#### Stage 0. Regime availability check
- ORCA baseline 이 없어도 memory/fallback regime 으로 계속 진행한다. Ref: `jackal/hunter.py:1499-1505`
- `aria["regime"]` 가 끝까지 비어 있으면 실행을 종료한다. Ref: `jackal/hunter.py:1506-1510`

#### Stage 0-1. Macro Gate
- VIX penalty
  - `vix >= 50` → `+20`
  - `vix >= 35` → `+10`
  - `vix >= 28` → `+5`
  Ref: `jackal/hunter.py:406-415`
- Yield curve penalty
  - `curve < -0.5` → `+8`
  - `curve < 0` → `+3`
  Ref: `jackal/hunter.py:417-423`
- HYG 5일 하락 penalty
  - `hy_chg5 < -2.0` → `+7`
  - `hy_chg5 < -1.0` → `+3`
  Ref: `jackal/hunter.py:425-431`
- ORCA regime penalty
  - `"회피"` 포함 시 `+5`
  Ref: `jackal/hunter.py:433-436`
- `penalty >= 25` → `risk_level="extreme"`
- `penalty >= 10` → `risk_level="elevated"`
- else → `risk_level="normal"`
  Ref: `jackal/hunter.py:438-447`

#### Stage 1. Technical scoring (`100 -> 50`)

Universe 구성:
- ORCA `key_inflows` 와 sector keywords 가 매치되면 해당 sector 전체를 우선 universe 에 넣는다.
- 매치되지 않는 sector 는 앞 5개 ticker 만 넣는다.
- 이후 Claude 추천 20개를 합친다.
  Ref: `jackal/hunter.py:233-266`

Per-ticker score 항목:
- RSI bucket
  - `<=25:+35`
  - `<=30:+28`
  - `<=35:+18`
  - `<=40:+9`
  - `<=50:+3`
  - `>=75:-18`
  - `>=65:-8`
  Ref: `jackal/hunter.py:620-627`
- Bollinger lower-band proximity
  - `bb<=5:+30`
  - `<=10:+24`
  - `<=20:+15`
  - `<=30:+7`
  - `>=90:-13`
  - `>=80:-6`
  Ref: `jackal/hunter.py:629-635`
- RSI + BB combo
  - `rsi<=30 and bb<=15:+25`
  - `rsi<=35 and bb<=25:+15`
  - `rsi<=40 and bb<=35:+8`
  Ref: `jackal/hunter.py:637-641`
- 5-day drawdown
  - `chg5<=-10:+20`
  - `<=-7:+14`
  - `<=-5:+9`
  - `<=-3:+4`
  - `>=15:-14`
  - `>=10:-7`
  Ref: `jackal/hunter.py:643-649`
- Volume capitulation
  - `vol>=3.0 and chg1<0:+15`
  - `vol>=2.0 and chg1<0:+10`
  - `vol>=3.0:+7`
  - `vol>=2.0:+5`
  - `vol>=1.5:+2`
  Ref: `jackal/hunter.py:651-657`
- MA50 support
  - `abs(price-ma50)/ma50 < 0.03` 이고 과매도 조건 동반 시 `+5`
  - 같은 거리 조건이지만 과매도 조건이 없으면 `+1`
  Ref: `jackal/hunter.py:659-667`
- Bullish divergence
  - `tech["bullish_div"] == True` → `+15`
  Ref: `jackal/hunter.py:669-672`
- Bullish candle after drawdown
  - `bullish_candle and chg5 < -3` → `+5`
  Ref: `jackal/hunter.py:674-676`
- Sector-relative underperformance
  - `relative <= -5:+12`
  - `<= -3:+8`
  - `<= -1:+4`
  Ref: `jackal/hunter.py:678-692`
- Macro penalty application
  - Stage 0-1 penalty 가 있으면 모든 `s1_score` 에서 동일하게 차감한다.
  Ref: `jackal/hunter.py:730-733`

Stage 1 output:
- `s1_score` 내림차순 상위 50개. Ref: `jackal/hunter.py:735-739`

#### Stage 2. ORCA context scoring (`50 -> 25`)

Regime boost:
- `"선호"` 포함 → `+8`
- `"회피"` 포함 → `-5`
- `"혼조"` 포함 → `+2`
  Ref: `jackal/hunter.py:751-759`

Sector flow boost:
- ticker 가 속한 sector keyword 가 ORCA inflow 와 매치되면 `+10`
- ticker 가 속한 sector keyword 가 ORCA outflow 와 매치되면 `-8`
  Ref: `jackal/hunter.py:766-773`

KR risk-off penalty:
- `ticker.endswith(".KS") and "회피" in regime` → `-5`
  Ref: `jackal/hunter.py:778-780`

Stage 2 output:
- `s2_score = s1_score + boost`
- 상위 25개 반환
  Ref: `jackal/hunter.py:782-790`

#### Stage 3. Quick scan (`25 -> 10`)

Stage 3 입력 항목:
- `ticker`
- `rsi`
- `bb_pos`
- `change_5d`
- `vol_ratio`
- `s2_score`
- `bullish_div` 여부
- `hunt_reason`
  Ref: `jackal/hunter.py:825-831`

Stage 3 선택 기준은 prompt 내부에 문자열로 명시된다.
- `RSI 낮음 + BB 하단 + 최근 급락 + 레짐 부합`
- compact cache summary 가 있으면 실패 패턴 참고 문자열을 prompt 에 삽입한다.
  Ref: `jackal/hunter.py:797-815`, `jackal/hunter.py:837-844`

Stage 3 output:
- Claude 가 반환한 `top10`
- 부족 시 `top25` 점수순으로 보충
  Ref: `jackal/hunter.py:846-869`

#### Stage 4. Analyst -> Devil -> Final (`10 -> 5`)

Swing type 분류 규칙:
- `tech["bullish_div"]` → `강세다이버전스`
- `hunt_reason` 에 `"섹터 유입"` 또는 `"유입"` 이 있고 `rsi <= 50 and chg5 <= -2` → `섹터로테이션`
- `rsi <= 35 and chg5 <= -5 and vol >= 1.5` → `패닉셀반등`
- `regime` 에 `"위험회피"` 포함 and `rsi <= 40 and chg5 <= -4` → `패닉셀반등`
- `chg5 <= -5 and rsi <= 45` → `모멘텀눌림목`
- `ma50` 근접 and `rsi <= 45` → `MA지지반등`
- 그 외 → `기술적과매도`
  Ref: `jackal/hunter.py:898-938`

Analyst prompt 출력 스키마:
- `analyst_score`
- `day1_score`
- `swing_score`
- `swing_setup`
- `swing_type`
- `signals_fired`
- `bull_case`
- `expected_days`
- `entry_zone`
- `target_1d`
- `target_5d`
- `stop_loss`
- `risk_reward`
  Ref: `jackal/hunter.py:1005-1019`

Devil prompt 출력 스키마:
- `devil_score`
- `verdict`
- `main_risk`
- `structural_decline`
- `is_dead_cat`
- `thesis_killer_hit`
- `volume_concern`
  Ref: `jackal/hunter.py:1120-1126`

Final decision formula:
- Thesis killer or dead cat → `final_score=20`, `is_entry=False`
- `verdict=="반대"` and `devil_score>=70` → `final_score=25`, `is_entry=False`
- otherwise:
  - `raw_score = day1_score * w1 + swing_score * ws`
  - `penalty = max(0, (devil_score - 30) * 0.25)`
  - `final_score = clamp(raw_score - penalty, 0, 100)`
  Ref: `jackal/hunter.py:1161-1193`

Swing type별 `(w1, ws)`:
- `섹터로테이션` → `(0.3, 0.7)`
- `패닉셀반등` → `(0.5, 0.5)`
- `모멘텀눌림목` → `(0.35, 0.65)`
- `강세다이버전스` → `(0.4, 0.6)`
- `MA지지반등` → `(0.6, 0.4)`
- `기술적과매도` → `(0.55, 0.45)`
  Ref: `jackal/hunter.py:1177-1186`

Swing type별 entry threshold:
- `섹터로테이션:48`
- `패닉셀반등:50`
- `모멘텀눌림목:50`
- `강세다이버전스:50`
- `기술적과매도:55`
- `MA지지반등:60`
- `setup == "추가하락"` 이면 threshold 를 `99` 로 덮는다.
  Ref: `jackal/hunter.py:1194-1206`

Entry mode:
- `d1>=65 and sw>=65` → `강타점`
- `d1>=60 and sw<50` → `단기스캘핑`
- `d1<50 and sw>=65` → `분할진입`
- else → `일반`
  Ref: `jackal/hunter.py:1208-1216`

### 1.3. Quality Gate

Hunter 내부의 비발송 경로는 score stage 와 final threshold 로 구성된다.

1. Regime 없음
- baseline/memory/fallback 모두 실패해 `aria["regime"]` 가 비어 있으면 종료한다. Ref: `jackal/hunter.py:1506-1510`

2. Stage 1 empty
- `_stage1_technical()` 결과가 비면 상태 메시지만 보내고 종료한다. Ref: `jackal/hunter.py:1560-1567`

3. Stage 4 empty
- `_stage4_full_analysis()` 결과가 비면 상태 메시지만 보내고 종료한다. Ref: `jackal/hunter.py:1575-1582`

4. Final threshold 미달
- `final["is_entry"] == False` 이면 Telegram alert 는 발송되지 않는다.
- 이 경로는 top5 대상에 대해 half cooldown(`3h`) 을 설정하고 log 는 남긴다.
  Ref: `jackal/hunter.py:1597-1614`

5. API failure branch
- `signals_fired == [] and analyst_score == 50` 를 `api_failed` 로 간주한다.
- 이 경우 cooldown 을 생략한다.
  Ref: `jackal/hunter.py:1593-1596`, `jackal/hunter.py:1608-1610`

Hunter에서 shadow row 생성 여부:
- `hunter.py` 안에는 `record_jackal_shadow_signal()` 호출이 없다.
- Hunter 비발송 경로는 shadow 저장이 아니라 `hunt_log.json`/SQLite live event 저장 경로를 사용한다.
  Ref: `jackal/hunter.py:1410-1474`, `jackal/scanner.py:1565-1570`

### 1.4. Output Schema

Hunter가 중간/최종 단계에서 다루는 구조는 세 단계로 나뉜다.

#### Stage item schema
`_stage1_technical()` 에서 만들어지는 item:
- `ticker`
- `name`
- `market`
- `currency`
- `hunt_reason`
- `tech`
- `s1_score`
  Ref: `jackal/hunter.py:719-728`

Stage 2 추가 필드:
- `s2_score`
- `orca_boost`
  Ref: `jackal/hunter.py:782-784`

Stage 4 추가 필드:
- `analyst`
- `devil`
- `final`
  Ref: `jackal/hunter.py:1253-1279`

#### Watchlist snapshot schema
`data/jackal_watchlist.json` payload:
- `generated_at`
- `tickers`
- `details`
  - `name`
  - `market`
  - `currency`
  - `portfolio`
  - `source`
  - `reason`
  - `signal_family`
  - `quality_score`
  - `price`
  - `is_entry`
- `counts`
  - `total`
  - `hunter_top5`
- `market_context`
  - `regime`
  - `inflows`
  - `outflows`
  Ref: `jackal/hunter.py:307-347`

이 snapshot 은 Hunter 완료 후 다시 저장된다. Ref: `jackal/hunter.py:1584-1587`

#### Hunt live-event / log schema
`_save_log()` 에 넘기는 hunt payload:
- `timestamp`
- `ticker`
- `name`
- `price_at_hunt`
- `rsi`
- `bb_pos`
- `change_5d`
- `vol_ratio`
- `s1_score`
- `s2_score`
- `orca_regime`
- `orca_inflows`
- `signal_family`
- `signal_family_raw`
- `signal_family_label`
- `analyst_score`
- `day1_score`
- `swing_score`
- `entry_mode`
- `swing_setup`
- `signals_fired`
- `devil_verdict`
- `devil_score`
- `thesis_killer_hit`
- `final_score`
- `probability_adjustment`
- `probability_samples`
- `probability_win_rate`
- `is_entry`
- `alerted`
- `outcome_checked`
- `price_1d_later`
- `outcome_1d_pct`
- `outcome_1d_hit`
- `price_peak`
- `peak_day`
- `peak_pct`
- `outcome_swing_hit`
  Ref: `jackal/hunter.py:1616-1657`

Downstream 연결:
- `_save_log()` 는 `hunt_log.json` 을 갱신한 뒤 `sync_jackal_live_events("hunt", retained_logs)` 를 호출한다. Ref: `jackal/hunter.py:1410-1474`
- Evolution은 이 hunt live events 를 읽어 outcome/weight 학습에 사용한다. Ref: `jackal/evolution.py:204-232`

## Section 2: Scanner (`jackal/scanner.py`)

### 2.1. Universe Source

Scanner watchlist 는 세 경로를 합쳐 만든다.

1. Portfolio
- `data/portfolio.json` 의 `holdings`
- `ticker_yf` 가 없는 항목은 제외
- `jackal_scan=false` 인 항목 제외
- `asset_type in ("etf_broad_dividend", "cash")` 는 기본적으로 제외
  Ref: `jackal/scanner.py:70-124`

2. Candidate watchlist
- `list_candidates(source_system="jackal", unresolved_only=True, limit=max(limit*3, 30))`
- 기본 `limit=20`, `max_age_days=7`
- `source_event_type in {"hunt","shadow","scan"}` 만 포함
  Ref: `jackal/scanner.py:127-171`

3. Recommendation watchlist
- 최근 `jackal_recommendations` / `recommendation_log`
- 기본 `max_age_hours=72`, `limit=20`
  Ref: `jackal/scanner.py:174-207`

4. ORCA-based extra tickers
- `_suggest_extra_tickers()` 가 ARIA regime, inflows, outflows, top sector, one-line summary 를 prompt 로 넣고 최대 5개 추가 ticker 를 제안받는다.
  Ref: `jackal/scanner.py:1577-1643`

5. Final watchlist assembly
- `_merge_watchlists(portfolio, candidate_watch, recommendation_watch, extra)`
- watchlist snapshot 을 `data/jackal_watchlist.json` 에 저장한다.
  Ref: `jackal/scanner.py:210-234`, `jackal/scanner.py:1664-1680`

Watchlist 크기:
- 포트폴리오 수는 입력 파일에 따라 달라진다.
- candidate/recommendation 는 각 기본 `20` limit
- extra ticker 는 최대 `5`
- 고정 universe 개수 상수는 Scanner에 없다.
  Ref: `jackal/scanner.py:127-171`, `jackal/scanner.py:174-207`, `jackal/scanner.py:1577-1643`

### 2.2. Per-Stock Indicators

Scanner는 `fetch_technicals(ticker)` 로 per-stock 기술지표를 받는다. Ref: `jackal/scanner.py:1696-1698`, `jackal/market_data.py:431-471`

| Indicator | 파일:줄 | 계산식/참조 | 의미 |
| --- | --- | --- | --- |
| `price` | `jackal/market_data.py:327-329`, `405` | 최신 `Close` | 현재 기준 가격 |
| `change_1d` | `jackal/market_data.py:331-341`, `406` | 현재가 vs 1거래일 전 | 단기 변화율 |
| `change_3d` | `jackal/market_data.py:331-341`, `407` | 현재가 vs 3거래일 전 | 단기 변화율 |
| `change_5d` | `jackal/market_data.py:331-341`, `408` | 현재가 vs 5거래일 전 | drawdown / rebound 입력 |
| `RSI(14)` | `jackal/market_data.py:343-349`, `409` | 14일 평균 gain/loss 기반 RSI | 과매도/과열 판별 |
| `MA20` | `jackal/market_data.py:350`, `410` | 20일 단순이동평균 | 기준선 |
| `MA50` | `jackal/market_data.py:351`, `411` | 50일 단순이동평균 | support proximity |
| `bb_pos` | `jackal/market_data.py:353-359`, `412` | 20일 평균 ± 2표준편차 내 위치(%) | Bollinger 위치 |
| `vol_ratio` | `jackal/market_data.py:361-362`, `413` | 당일 거래량 / 최근 5일 평균 | volume surge / climax |
| `rsi_divergence` | `jackal/market_data.py:364-368`, `414` | 가격 하락 + RSI 5일 전 대비 +2 초과 상승 | divergence flag |
| `52w_pos` | `jackal/market_data.py:397-402`, `415` | 52주 high-low 범위 내 현재 위치(%) | 52주 저점 근접도 |
| `bb_width` | `jackal/market_data.py:380`, `416` | `(bb_upper - bb_lower) / ma20 * 100` | 볼린저 폭 |
| `bb_expanding` | `jackal/market_data.py:381-387`, `417` | 3일 전 폭 대비 `> 1.05x` | BB expansion flag |
| `vol_trend_5d` | `jackal/market_data.py:389-394`, `418` | 최근 5일 평균 거래량 vs 이전 5일 | volume trend |
| `vol_accumulation` | `jackal/market_data.py:395`, `419` | `change_5d < -2` and `vol_trend_5d > 15` | 하락 중 거래량 증가 flag |
| `ma_alignment` | `jackal/market_data.py:370-378`, `420` | `price > ma20 > ma50`, `price < ma20 < ma50`, else | MA 배열 상태 |

Scanner prompt 에 직접 들어가는 macro/context 항목:
- VIX
- HY spread
- yield curve
- DXY
- consumer sentiment
- ORCA regime / trend / sentiment / sector inflow/outflow / top/bottom sector
  Ref: `jackal/scanner.py:921-932`

구체 후보 확인:
- SMA: 있음 (`MA20`, `MA50`) — `jackal/market_data.py:350-351`
- EMA: 없음 — 조사 대상 파일/보조 파일에서 `EMA` 계산 코드 없음
- RSI: 있음 — `jackal/market_data.py:343-349`
- MACD: 없음 — 조사 대상 파일/보조 파일에서 `MACD` 계산 코드 없음
- Bollinger Band: 있음 (`20d`, `2σ`) — `jackal/market_data.py:353-359`
- ATR: 없음 — 조사 대상 파일/보조 파일에서 `ATR` 계산 코드 없음
- 거래량 변화: 있음 (`vol_ratio`, `vol_trend_5d`, `vol_accumulation`) — `jackal/market_data.py:361-395`
- 상대 강도 (RS): 시장 benchmark 대비는 없음, sector ETF 대비 상대 낙폭은 Hunter에 있음 — `jackal/hunter.py:678-692`
- 52주 고저 거리: 있음 (`52w_pos`) — `jackal/market_data.py:397-402`

### 2.3. Quality Score 계산

`quality_score` 는 `_calc_signal_quality()` 에서 계산된다. Ref: `jackal/scanner.py:515-865`

기본값:
- 시작 score = `50`
  Ref: `jackal/scanner.py:541-543`

Signal score contribution:
- `sector_rebound` → `+20`
- `volume_climax` → `+15`
- `bb_touch + rsi_oversold` → `+16`
- `bb_touch` 단독 → `+12`
- `rsi_oversold` and not `sector_rebound` → `+9`
- `momentum_dip` and `len(sig)>1` → `+5`
  Ref: `jackal/scanner.py:547-561`

Signal-specific penalties / additions:
- `rsi_divergence` 단독 또는 `rsi_divergence + ma_support` → `-20`
- `rsi_divergence + momentum_dip` and not `vol_accumulation` → `-12`
- `rsi_divergence + vol_accumulation` → `+3`
- `52w_low_zone` → `+12`
- `vol_accumulation` → `+12`
  Ref: `jackal/scanner.py:563-585`

Synergy:
- `vol_accumulation + sector_rebound` → `+8`
- `52w_low_zone + rsi_oversold` → `+6`
- `vol_accumulation + momentum_dip` → `+5`
- `bb_touch + sector_rebound + rsi_oversold` 동시 발동 → `+15`
  Ref: `jackal/scanner.py:587-600`

MA support family penalty:
- `sig == {"ma_support"}` → `-12`
- `sig == {"ma_support","momentum_dip"}` → `-5`
  Ref: `jackal/scanner.py:602-606`

PCR 연동:
- `pcr_avg > 1.3` and rebound signal 존재 → `+10`
- `pcr_avg > 1.1` and (`bb_touch` or `rsi_oversold`) → `+5`
- `pcr_avg < 0.8` and `volume_climax` → `-8`
  Ref: `jackal/scanner.py:608-620`

VIX/HY derived rebound bonus:
- `sector_rebound` and `real_panic` (`vix>30 and hy_spread>4.0`) → `+10`
- `sector_rebound` and `vix_extreme` (`vix>35`) → `+6`
- `sector_rebound` and `credit_stress and vix_high` → `+4`
- `chg5d < -8 and sector_rebound` → `+10`
- `chg5d < -5 and len(sig) >= 2` → `+5`
- rebound bonus total cap = `12`
  Ref: `jackal/scanner.py:640-673`

Negative veto:
- thesis killers 존재 → negative veto flag on
- `"전환중"` 또는 `regime.startswith("혼조")` → `score -= 15`
- `"위험회피"` and `sector_rebound` → `score += 5`
- `chg5d > 15 and "bb_touch" not in sig` → `score -= 8`
- negative veto 가 켜져 있고 rebound bonus 가 있으면 rebound bonus 를 절반으로 줄인다.
  Ref: `jackal/scanner.py:675-710`

High-uncertainty / micro gate:
- keyword list: `FOMC`, `CPI`, `관세`, `tariff`, `실적발표`, `어닝`, `earning`, `금리결정`, `고용지표`, `기준금리`, `연준`, `Fed decision`
  Ref: `jackal/scanner.py:721-724`
- hard gate:
  - `vix >= 40`
  - or `vix >= 32 and fg <= 15`
- soft gate:
  - `vix >= 32 and fear_greed unavailable`
  - or `event keyword and vix >= 28`
- micro gate:
  - not high uncertainty
  - regime contains `위험회피`, `하락추세`, or `bearish`
  - `vix >= 22`
  - `family != "crash_rebound"`
  Ref: `jackal/scanner.py:721-791`
- gate penalties:
  - hard/soft penalty map: `15`, `15`, `8`, `8`, `5`
  - `hard` and `vix >= 40` → `score = 0`
  Ref: `jackal/scanner.py:773-791`

Ticker accuracy penalty:
- `total >= 8` → `(acc_pct - 50) * 0.20`, clamped `[-10, 0]`
- `3 <= total < 8` → `(acc_pct - 50) * 0.10`, clamped `[-5, 0]`
- `<3` → no adjustment
  Ref: `jackal/scanner.py:795-815`

Family and thresholds:
- family:
  - `crash_rebound`
  - `general`
  - `ma_support_weak`
  - `ma_support_solo`
  Ref: `jackal/scanner.py:431-454`, `jackal/scanner.py:819-820`
- base skip threshold:
  - `crash_rebound:35`
  - `general:45`
  - `ma_support_weak:47`
  - `ma_support_solo:46`
  Ref: `jackal/scanner.py:824-830`
- VIX dynamic threshold:
  - family `crash_rebound` and `vix >= 30` → threshold down to at least `33`
  - family `crash_rebound` and `vix < 18` → threshold up to at most `46`
  - family `general` and `vix < 18` → threshold up to at most `50`
  Ref: `jackal/scanner.py:832-842`

Final quality outputs:
- `quality_score`
- `quality_label`
- `reasons`
- `skip`
- `skip_threshold`
- `signal_family`
- `analyst_adj`
- `final_adj`
- `vix_used`
- `vix_extreme`
- `rebound_bonus`
- `rebound_raw`
- `negative_veto`
- `negative_reasons`
  Ref: `jackal/scanner.py:850-865`

### 2.4. Signal Family

Scanner에는 family 분류가 두 층 있다.

#### Quality family
`_get_signal_family(signals)`:
- `crash_rebound`
  - `signals` 가 `_CRASH_REBOUND_SIGNALS = {"sector_rebound","volume_climax","52w_low_zone","vol_accumulation"}` 중 하나라도 포함
- `ma_support_solo`
  - `signals == {"ma_support"}`
- `ma_support_weak`
  - `signals == {"ma_support","momentum_dip"}`
- `general`
  - 그 외
  Ref: `jackal/scanner.py:434-454`

#### Cooldown family key
`_get_signal_family_key(signals)`:
- `crash_rebound`
- `oversold`
- `momentum`
- `general`
  Ref: `jackal/scanner.py:1129-1138`

#### Canonical family
Final log 저장 시에는 `canonical_family_key()` 로 Hunter/Scanner family 를 공통 taxonomy 로 정규화한다.
- `rotation`
- `panic_rebound`
- `momentum_pullback`
- `ma_reclaim`
- `divergence`
- `oversold_rebound`
- `general_rebound`
  Ref: `jackal/families.py:7-15`, `jackal/families.py:33-109`, `jackal/scanner.py:1854-1860`

Downstream 영향:
- skip threshold 가 family 별로 달라진다. Ref: `jackal/scanner.py:824-845`
- cooldown key 가 family 단위로 분리된다. Ref: `jackal/scanner.py:1141-1222`
- log/recommendation probability summary 가 canonical family 를 기록한다. Ref: `jackal/scanner.py:1892-1894`, `jackal/probability.py:18-59`

### 2.5. Skip Conditions

Skip 경로는 deterministic pre-filter 와 `quality["skip"]` 분기에서 발생한다.

#### Pre-rule signal generation
`signals_fired_pre` 생성 규칙:
- `rsi_oversold`: `rsi < 32`
- `bb_touch`: `bb_pos < 15`
- `volume_climax`: `vol_ratio > 1.8 and change_1d < -1.0`
- `momentum_dip`: `change_5d < -4.0`
- `sector_rebound`: `rsi < 40 and change_3d(or change_5d) < -2.0`
- `rsi_divergence`: `rsi_divergence == True and rsi < 35`
- `52w_low_zone`: `52w_pos < 15`
- `vol_accumulation`: `vol_accumulation == True`
- `ma_support`: `ma50` 존재 and `abs(price-ma50)/ma50 < 0.025`
  Ref: `jackal/scanner.py:1714-1729`

#### MA-support filtering
- `signals_fired_pre == ["ma_support"]` → 빈 리스트로 제거
- `"ma_support"` 가 포함되지만 strong signal 집합과 교집합이 없으면 `"ma_support"` 제거
- strong signal 집합:
  - `rsi_oversold`
  - `bb_touch`
  - `volume_climax`
  - `sector_rebound`
  - `vol_accumulation`
  - `52w_low_zone`
  Ref: `jackal/scanner.py:1731-1743`

#### Quality skip branch
- `quality["skip"] == True` 이면:
  - Claude Analyst/Devil 호출 없음
  - `results` 에 `signal_type="관망"` 으로 추가
  - `_save_shadow_log()` 호출
  - 저장은 `record_jackal_shadow_signal(entry)` 경유 SQLite state spine 으로 들어간다.
  Ref: `jackal/scanner.py:1765-1842`, `jackal/scanner.py:1565-1570`

Shadow payload 필드:
- `timestamp`
- `ticker`
- `name`
- `market`
- `price_at_scan`
- `rsi`
- `bb_pos`
- `vol_ratio`
- `vix`
- `hy_spread`
- `yield_curve`
- `orca_regime`
- `orca_sentiment`
- `orca_trend`
- `analyst_score`
- `analyst_confidence`
- `signals_fired`
- `bull_case`
- `devil_score`
- `devil_verdict`
- `devil_objections`
- `thesis_killer_hit`
- `killer_detail`
- `final_score`
- `signal_type`
- `signal_family`
- `signal_family_raw`
- `signal_family_label`
- `is_entry`
- `reason`
- `quality_score`
- `quality_label`
- `quality_reasons`
- `skip_threshold`
- `rebound_bonus`
- `vix_used`
- `shadow_record`
- `shadow_storage`
- `alerted`
- `outcome_checked`
- `outcome_price`
- `outcome_pct`
- `outcome_correct`
  Ref: `jackal/scanner.py:1788-1841`

### 2.6. Pass Conditions

Pass 경로는 `quality["skip"] == False` 이후 진행된다.

1. Analyst 호출
- `agent_analyst()` 실행
  Ref: `jackal/scanner.py:1844-1846`

2. Devil 호출
- `agent_devil()` 실행
  Ref: `jackal/scanner.py:1848-1850`

3. Final score 계산
- `_final_judgment()` 실행
- 이후 `apply_probability_adjustment()` 로 family 기반 보정
  Ref: `jackal/scanner.py:1852-1864`

4. Signal type assignment
- `verdict=="반대"` 또는 `final_score < 40` → `매도주의` 또는 `관망`
- `final_score >= STRONG_THRESHOLD(78)` → `강한매수`
- `final_score >= ALERT_THRESHOLD(65)` → `매수검토`
- else → `관망`
  Ref: `jackal/scanner.py:1865-1872`

5. Telegram alert branch
- `final["is_entry"] and final["final_score"] >= ALERT_THRESHOLD`
- 성공 시 `_set_cooldown(...)` 후 `alerted += 1`
  Ref: `jackal/scanner.py:1904-1914`

6. Scan log / live event 저장
- pass case는 `_save_log()` 를 통해 `scan_log.json` 과 `sync_jackal_live_events("scan", logs)` 에 기록된다.
  Ref: `jackal/scanner.py:1915-1962`, `jackal/scanner.py:1553-1563`

7. ORCA 전달 경로
- Scanner는 loop 시작 전 final watchlist snapshot 을 `data/jackal_watchlist.json` 에 쓴다. Ref: `jackal/scanner.py:1678-1680`, `jackal/scanner.py:222-234`
- `_save_recommendation()` 주석 기준 전달 경로:
  - `data/jackal_watchlist.json` → `ARIA Hunter` 가 읽음
  - `jackal/recommendation_log.json` → Evolution 이 읽음
  Ref: `jackal/scanner.py:1382-1435`
- pass branch 자체에서 ORCA baseline 파일을 직접 갱신하는 코드는 보이지 않는다.

## Section 3: Core (`jackal/core.py`)

### 3.1. Orchestration Role

Core는 다음 순서를 가진다.

1. Shield
- `self.shield.scan()`
- `abort` 가 true 면 전체 중단
  Ref: `jackal/core.py:55-66`

2. Hunter
- `run_hunt(force=force_hunt)`
  Ref: `jackal/core.py:67-70`

3. Compact
- `self.compact.check_and_compact(context_tokens)`
  Ref: `jackal/core.py:71-75`

4. Evolution
- `force_evolve` 이거나 `_should_evolve()` 가 true 이면 실행
- `_should_evolve()` 는 latest weight snapshot 또는 `jackal_weights.json["last_evolved_at"]` 를 보고 24시간 경과 여부를 계산한다.
  Ref: `jackal/core.py:76-88`, `jackal/core.py:103-129`

Core가 직접 호출하지 않는 것:
- `scanner.py` 는 Core orchestrator 안에서 호출되지 않는다.
  Ref: `jackal/core.py:27-30`, `jackal/core.py:67-88`

### 3.2. Mode / Command 분기

CLI 인자:
- `--force-hunt`
  - 장 마감 여부와 무관하게 Hunter 실행
- `--force-evolve`
  - 24시간 미경과 여부와 무관하게 Evolution 실행
- `--tokens`
  - Compact 컨텍스트 토큰 수 전달
  Ref: `jackal/core.py:145-158`

실행 결과 구조:
- `status`
- `elapsed`
- `hunt`
- `evolution`
  - `ran`
  - `learned`
  - `skills`
  Ref: `jackal/core.py:92-101`

## Section 4: Evolution (`jackal/evolution.py`)

### 4.1. Shadow Scoring

Evolution은 live entry 와 shadow entry 를 별도 집합으로 읽는다.

#### Live outcome set
- source: `list_jackal_live_events("hunt", limit=500)` 또는 fallback `hunt_log.json` / `scan_log.json`
- pending 조건:
  - `alerted` 또는 `is_entry`
  - `outcome_checked == False`
  - `timestamp < now(KST) - 28h`
  Ref: `jackal/evolution.py:204-232`

#### Live scoring rule
- yfinance `15d` 일봉 history 조회
- `d1_pct = returns[0]`
- `d1_correct = d1_pct > 0.3`
- `sw_window = returns[:7]`
- `peak_pct = max(sw_window)`
- `peak_day = index(max) + 1`
- `swing_hit = peak_pct >= 1.0`
- `swing_checked = len(sw_window) >= 3`
  Ref: `jackal/evolution.py:256-285`

Live outcome 저장 필드:
- `outcome_checked`
- `price_1d_later`
- `outcome_1d_pct`
- `outcome_1d_hit`
- `peak_day`
- `peak_pct`
- `outcome_swing_hit`
- `outcome_correct`
  Ref: `jackal/evolution.py:277-285`

#### Shadow scoring rule
- source: `list_pending_jackal_shadow_signals(cutoff_1d.isoformat())`
- yfinance `10d` 일봉 history 조회
- `swing_ret = max(returns[:7])`
- `swing_ok = swing_ret >= 1.0`
- `resolve_jackal_shadow_signal(shadow_id, {"shadow_swing_pct", "shadow_swing_ok"}, payload_updates={...})`
  Ref: `jackal/evolution.py:232`, `jackal/evolution.py:367-398`

Shadow aggregate:
- `shadow_stats["total"]`
- `shadow_stats["would_have_worked"]`
- batch 정확도 계산 후 `record_jackal_shadow_accuracy_batch(...)`
  Ref: `jackal/evolution.py:399-410`, `jackal/evolution.py:906-917`

#### Recommendation scoring rule
- source: `list_jackal_recommendations(limit=200)` 또는 fallback `recommendation_log.json`
- pending cutoff: `24h`
- yfinance `5d` 일봉 history
- `pct = (price_next - price_rec) / price_rec * 100`
- `correct = pct >= 0.5`
  Ref: `jackal/evolution.py:449-525`

주의할 코드 사실:
- 상단 상수에는 `OUTCOME_HOURS = 4` 가 정의되어 있다. Ref: `jackal/evolution.py:51`
- 실제 pending live/shadow cutoff 는 `28h`, recommendation cutoff 는 `24h` 로 구현돼 있다. Ref: `jackal/evolution.py:217-232`, `jackal/evolution.py:460-470`

### 4.2. Weight Update

Evolution weight 저장소:
- `signal_weights`
- `regime_weights`
- `devil_weights`
- `signal_accuracy`
- `regime_accuracy`
- `ticker_accuracy`
- `devil_accuracy`
- `rule_registry_status`
- `ticker_reliability`
- `signal_details`
  Ref: `jackal/evolution.py:58-149`

#### Outcome-based signal weight update
- 조건: `swing_checked == True`
- `adj = +0.04` if `swing_hit`
- else `adj = -0.03`
- `d1_correct == True` 면 추가 `+0.01`
- 최종 signal weight clamp 범위: `[0.3, 2.5]`
  Ref: `jackal/evolution.py:315-329`

#### Accuracy map update
- `signal_accuracy`
- `regime_accuracy`
- `ticker_accuracy`
- `devil_accuracy`
  각각 누적 `correct/total/accuracy` 를 갱신한다.
  Ref: `jackal/evolution.py:358-365`, `jackal/evolution.py:423-443`

#### Swing-type aggregate
각 `swing_type` 에 대해:
- `avg_peak_day`
- `avg_peak_gain`
- `swing_accuracy`
- `day1_accuracy`
- `sample`
  를 `weights["swing_type_optimal"]` 에 기록한다.
  Ref: `jackal/evolution.py:341-356`

#### Recommendation accuracy map
- `weights["recommendation_accuracy"]["by_regime"]`
- `weights["recommendation_accuracy"]["by_inflow"]`
- `weights["recommendation_accuracy"]["by_ticker"]`
  Ref: `jackal/evolution.py:526-551`

#### Claude adjustment path
- `_build_context()` 가 최근 7일 log 요약을 만든다. Ref: `jackal/evolution.py:557-612`
- `_ask_claude()` prompt 내 `weight_adjustments` 는 `-0.15 ~ +0.15` 범위를 요구한다. Ref: `jackal/evolution.py:643-662`
- `_apply_claude_adjustments()` 는 기존 `signal_weights` 에 delta 를 더하고 `[0.3, 2.5]` 범위로 clamp 한다. Ref: `jackal/evolution.py:892-900`

#### Rule registry auto-disable
- `sector_rebound_base`
- `volume_climax_base`
- `crash_rebound_pattern`
  는 최근 accuracy/sample 에 따라 `active=False` 로 바뀔 수 있다.
  Ref: `jackal/evolution.py:748-805`

#### Save path
- `self.weights["last_evolved_at"]` 갱신
- `record_jackal_weight_snapshot(weights, source="evolution")`
  Ref: `jackal/evolution.py:175-179`, `jackal/evolution.py:902-917`

보조 경로:
- `tracker.py` 도 hunt outcome 기준으로 `signal_accuracy`, `ticker_accuracy`, `devil_accuracy`, `regime_accuracy`, `signal_weights` 를 업데이트한다.
  Ref: `jackal/tracker.py:242-328`, `jackal/tracker.py:479-527`

### 4.3. Recommendation Outcome

Recommendation 학습 대상은 `_save_recommendation()` 으로 생성된 entries 이다.

저장 필드:
- `ticker`
- `name`
- `market`
- `reason`
- `price_at_rec`
- `recommended_at`
- `orca_regime`
- `orca_inflows`
- `orca_trend`
- `outcome_checked`
- `price_next_day`
- `outcome_pct`
- `outcome_correct`
  Ref: `jackal/scanner.py:1382-1413`

Evolution에서의 결과 반영:
- 24시간 지난 미확인 recommendation 만 처리
- `pct >= 0.5` 를 `correct=True` 로 기록
- regime / inflow / ticker 축으로 accuracy 누적
  Ref: `jackal/evolution.py:460-551`

Probability 반영 경로:
- `load_probability_summary()` 는 ORCA state 의 `summarize_candidate_probabilities()` 를 읽는다.
- `apply_probability_adjustment()` 는 qualified family 통계가 있으면 `final_score` 를 조정하고 `is_entry` 를 threshold 기준으로 다시 계산한다.
  Ref: `jackal/probability.py:11-59`

## Section 5: What JACKAL Does NOT Currently Do

이 섹션은 항목별 코드 존재 여부만 기록한다.

### 5.1. Cross-stock correlation

- 같은 섹터 종목 간 correlation matrix 계산: `없음`
- `corr(` / `correl` / `correlation` / `matrix` 검색: 조사 대상/보조 파일에서 매치 없음
- Result: `없음`

근거:
- `Select-String` 검색 결과 no matches
- sector grouping 은 `SECTOR_POOLS` 로 존재하지만 상관계수 계산 코드는 확인되지 않음. Ref: `jackal/hunter.py:100-140`

### 5.2. Sector / Theme Rotation

- sector pool 기반 universe 구성: `있음`. Ref: `jackal/hunter.py:233-266`
- sector ETF 수익률 비교: `있음`. Ref: `jackal/hunter.py:450-472`, `jackal/hunter.py:678-692`
- ORCA `rotation.json` 읽기: `있음`. Ref: `jackal/scanner.py:303-315`
- `rotation_signal.from/to` 필드 로드: `있음`. Ref: `jackal/scanner.py:311-313`
- Result: `있음`

### 5.3. Volatility Contraction / Expansion

- Bollinger Band width 계산: `있음`. Ref: `jackal/market_data.py:380-387`
- `bb_expanding` 계산: `있음`. Ref: `jackal/market_data.py:381-387`
- prompt 에 BB폭 표시: `있음`. Ref: `jackal/scanner.py:915-919`
- ATR 계산: `없음`
- squeeze 감지 코드: `없음`
- Result: `부분`

### 5.4. Chart Pattern Recognition

- `head and shoulders` / `triangle` / `flag` 인식 코드: `없음`
- 일반 support/resistance 자동 탐지 코드: `없음`
- `ma_support` 는 이동평균 근접 rule 이며 패턴 인식 전용 루틴은 아님. Ref: `jackal/scanner.py:1724-1729`
- Result: `없음`

### 5.5. Event-driven Signals

- ticker/news context 주입: `있음`. Ref: `jackal/hunter.py:154-226`, `jackal/scanner.py:1438-1452`, `jackal/adapter.py:154-162`
- heuristic gate keyword 목록에 `실적발표`, `어닝`, `earning` 포함: `있음`. Ref: `jackal/scanner.py:721-726`
- 실적발표 일정/캘린더 proximity 계산: `없음`
- per-ticker event timestamp 비교 로직: `없음`
- Result: `부분`

### 5.6. Volume Spread Analysis

- `volume profile`, `Wyckoff`, `VSA` 검색: `없음`
- volume 관련 deterministic 계산은 `vol_ratio`, `vol_trend_5d`, `vol_accumulation`, `volume_climax` 규칙 수준으로 확인됨. Ref: `jackal/market_data.py:361-395`, `jackal/scanner.py:1716-1723`
- Result: `없음`

### 5.7. Relative Strength vs Market

- 시장 benchmark(S&P, KOSPI) 대비 RS line 계산: `없음`
- KRX snapshot 에 `kospi`, `kosdaq` fetch 는 존재하지만 Scanner가 직접 signal score 에 쓰는 경로는 보이지 않음. Ref: `jackal/market_data.py:111-156`, `jackal/market_data.py:474-494`
- sector ETF 대비 상대 낙폭 계산은 Hunter에 존재한다. Ref: `jackal/hunter.py:678-692`
- Result: `부분`

### 5.8. Fundamental Overlay

- `PER`, `PBR`, `EPS`, `revenue`, `earnings growth`, fundamental metric 계산/읽기: `없음`
- 조사 대상/보조 파일에서 관련 필드/함수 확인되지 않음
- Result: `없음`

## Section 6: Summary Map

현재 코드 기준 요약:

- [x] ORCA baseline/memory/fallback regime 읽기 (`jackal/adapter.py:97-163`)
- [x] ORCA inflow/outflow 를 universe/score 에 반영 (`jackal/hunter.py:233-266`, `jackal/hunter.py:746-790`)
- [x] 고정 sector pool + Claude 추천 ticker 로 universe 구성 (`jackal/hunter.py:233-304`)
- [x] yfinance 기반 OHLCV/RSI/MA/Bollinger/volume 계산 (`jackal/hunter.py:475-587`, `jackal/market_data.py:320-423`)
- [x] Macro gate 에 VIX / yield curve / HYG 반영 (`jackal/hunter.py:358-447`)
- [x] Sector ETF 5일 수익률 기반 상대 낙폭 반영 (`jackal/hunter.py:450-472`, `jackal/hunter.py:678-692`)
- [x] Hunter 4-stage pipeline (`jackal/hunter.py:1495-1665`)
- [x] Scanner deterministic pre-rule signal set (`jackal/scanner.py:1714-1743`)
- [x] Scanner quality score base 50 + additive/subtractive rule set (`jackal/scanner.py:541-865`)
- [x] Scanner family별 skip threshold (`jackal/scanner.py:824-845`)
- [x] Scanner shadow 저장 경로 (`jackal/scanner.py:1765-1842`, `jackal/scanner.py:1565-1570`)
- [x] Scanner pass case Telegram/live-event 저장 (`jackal/scanner.py:1904-1962`)
- [x] Canonical signal family 정규화 (`jackal/families.py:7-109`)
- [x] Probability summary 기반 final score adjustment (`jackal/probability.py:18-59`)
- [x] Evolution live/shadow/recommendation outcome 학습 (`jackal/evolution.py:204-421`, `jackal/evolution.py:449-551`)
- [x] Evolution signal weight clamp `[0.3, 2.5]` (`jackal/evolution.py:315-329`, `jackal/evolution.py:892-900`)
- [x] Recommendation accuracy by regime/inflow (`jackal/evolution.py:498-551`)
- [ ] Cross-stock correlation matrix
- [x] Sector/theme rotation context
- [x] Bollinger width / expansion
- [ ] ATR
- [ ] Squeeze 감지
- [ ] Chart pattern recognition (head and shoulders / triangle / flag)
- [ ] Support/resistance 자동 탐지
- [x] News context 주입
- [ ] Earnings calendar proximity
- [ ] Volume profile / Wyckoff / VSA
- [ ] Market benchmark relative strength line
- [ ] Fundamental overlay (PER/PBR/EPS)

한 줄 요약:
- Hunter 는 sector universe + ORCA context + macro gate + staged scoring을 사용한다. Ref: `jackal/hunter.py:233-266`, `jackal/hunter.py:358-447`, `jackal/hunter.py:594-1284`
- Scanner 는 watchlist 기반 deterministic signal pre-filter 와 quality score, Analyst/Devil/Final branch, shadow 저장 경로를 사용한다. Ref: `jackal/scanner.py:127-234`, `jackal/scanner.py:515-865`, `jackal/scanner.py:1714-1962`
- Core 는 Shield -> Hunter -> Compact -> Evolution 순서로 orchestrate 하며 Scanner 를 직접 호출하지 않는다. Ref: `jackal/core.py:55-88`
- Evolution 은 hunt/shadow/recommendation 결과를 가격 데이터로 채점해 accuracy map 과 weight snapshot 을 갱신한다. Ref: `jackal/evolution.py:204-421`, `jackal/evolution.py:449-551`, `jackal/evolution.py:892-917`
