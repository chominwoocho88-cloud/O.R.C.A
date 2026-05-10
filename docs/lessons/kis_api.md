# KIS API 통합 교훈 종합

> 본인 명시: "한투 api는 우리가 겪었던 교훈을 잊지 않고 앞으로 개선해 나가보자"

## 개요

O.R.C.A 시스템 KIS API(한국투자증권 Web API) 통합 마라톤(Stage 2 Day 11-13, Phase 8b~8g) 결과 정리.

본 문서는 다음 단계 base를 위한 종합 교훈이다.

- ATLAS + FALCON 진입
- Stage 4 실거래 전환
- 운영 안정성 유지
- 본인 fork 자산을 다음 sprint에서 반복 활용

작성일: 2026-05-10
완성 기준: Phase 8g 시리즈, commit `15e2266`

---

## 1. 핵심 교훈

### 1.1 인증 + 토큰 관리

**교훈 1: KIS는 1분당 1회 토큰 발급 제한이 있다.**

- 같은 cycle에서 `KisClient`를 여러 번 만들면 각 인스턴스가 새 토큰 발급을 시도할 수 있다.
- ORCA 한 cycle에서 최소 6회 생성이 확인됐다: 한국 ticker 5개 현재가 + 투자자 수급 1회.
- 결과: 첫 번째 발급은 성공, 이후 1분 안의 발급은 `403 Forbidden`.
- 해결: singleton + 파일 cache, Phase 8d-3e.

**교훈 2: 토큰 cache는 메모리 + 파일 2단계가 필요하다.**

- 메모리 cache: 같은 인스턴스 안에서 재사용.
- singleton: 같은 cycle에서 인스턴스 공유.
- 파일 cache: 다른 cycle 사이에서도 24시간 유효 토큰 재사용.
- 본인 fork 공식 sample의 `read_token` / `save_token` 패턴이 결정적이었다.
- 보안: key 원문은 저장하지 않고 fingerprint/hash와 `base_url` 기준으로 cache 무효화.

**교훈 3: 계좌번호는 반드시 `CANO` + `ACNT_PRDT_CD`로 분리한다.**

- 공식 KIS 형식: `CANO` 8자리 + `ACNT_PRDT_CD` 2자리.
- ORCA 입력은 단일 문자열로 들어올 수 있다: 8자리, 10자리, 하이픈 포함.
- `KisClient.cano`, `KisClient.acnt_prdt_cd` property로 분리했다.
- 8자리만 있으면 상품코드는 기본 `"01"`로 처리한다.

### 1.2 모의/실전 분기

**교훈 4: `tr_id` paper/prod 분기는 기능별로 검증해야 한다.**

- 잔고 조회: paper `VTTC8434R`, prod `TTTC8434R`.
- 주문 계열은 `V`/`T` 분기가 더 중요하다.
- 시세 조회는 동일 `tr_id`를 쓰는 경우가 많지만, Stage 4 전에는 공식 sample 기준으로 재검증한다.
- `KIS_IS_PAPER` 환경변수는 문자열을 정확히 boolean으로 해석해야 한다.

**교훈 5: `base_url` paper/prod 분리를 token cache와 함께 본다.**

- paper: `https://openapivts.koreainvestment.com:29443`
- prod: `https://openapi.koreainvestment.com:9443`
- token cache는 `base_url`이 다르면 무효화해야 한다.
- 실전 전환 시 paper token이 prod 요청에 섞이면 안 된다.

### 1.3 GitHub Actions 운영

**교훈 6: workflow yml은 step-level env가 중요하다.**

- job-level env만 추가하면 실제 `Run ORCA report` step에 전달되지 않을 수 있다.
- Phase 8d-3a에서 step-level env 누락을 발견했다.
- 운영 step에는 KIS env를 명시적으로 전달한다.

**교훈 7: GitHub Secrets는 값의 길이와 끝 글자까지 검증한다.**

- key/secret/account env 이름은 코드, workflow, GitHub Secrets가 1글자까지 일치해야 한다.
- secret 값 자체는 절대 출력하지 않는다.
- 안전한 debug는 length, stripped length, whitespace 여부, 끝 2글자 정도까지만 허용한다.
- APP_SECRET 끝 문자가 누락될 수 있으므로 본인 PC 검증 후 등록한다.

**교훈 8: GitHub Actions runner 해외 IP 차단은 원인이 아니었다.**

- Azure US runner IP에서도 token 직접 발급이 성공했다.
- "해외 IP라서 KIS 차단"은 검증 후 폐기한 가설이다.

**교훈 9: debug step 자체가 token 제한을 발동시킬 수 있다.**

- debug step에서 token 발급 성공.
- 바로 다음 ORCA step에서 다시 token 발급 시도.
- 1분 제한 때문에 `403 Forbidden`.
- KIS token을 직접 발급하는 debug step은 검증 후 즉시 제거한다.

### 1.4 데이터 흐름 + 사용자 표시

**교훈 10: KIS 단일 소스 일원화는 코드와 표시를 모두 정리해야 완성된다.**

- KRX backup 코드는 Phase 8d-4에서 제거했다.
- workflow의 `KRX_API_KEY`도 제거했다.
- "KRX 빼고 KIS"라는 본인 4/28 의도가 코드 흐름까지 반영됐다.

**교훈 11: fallback은 안전망이지만 사용자 표시는 별도 판단이다.**

- `portfolio.json` fallback은 시스템 안전망으로 보였지만 본인 의도와 충돌했다.
- 본인 의도: 포트폴리오는 KIS 실시간만, 하드코딩 X.
- Phase 8g-2에서 텔레그램은 KIS-only로 바꿨다.
- Phase 8g-3에서 `portfolio.json`을 완전히 제거했다.

**교훈 12: Codex가 안전망으로 넣은 fallback도 본인 의도와 대조해야 한다.**

- `assessments` fallback은 "보여주기" 측면에서는 친절했지만 본인 운영 철학과 달랐다.
- "데이터 있음"과 "사용자에게 보여도 되는 데이터"는 다르다.
- 운영 책임자 관점에서는 잘못된 안심보다 명확한 미표시가 낫다.

### 1.5 시스템 한 부분 수정 시

**교훈 13: ORCA를 고치면 JACKAL까지 영향 범위를 본다.**

- 본인 질문: "JACKAL은? 같은 일 안 생기게"
- 이후 `jackal/watchlist.py`를 추가해 KIS holdings + candidate_registry 흐름을 만들었다.
- 한 부분의 성공이 시스템 전체의 성공은 아니다.

**교훈 14: API rate limit 의심 시 호출 횟수부터 센다.**

- "키 문제", "IP 문제", "header 문제"보다 먼저 cycle 내 client 생성 횟수와 token 발급 횟수를 확인한다.
- 해결 우선순위: singleton, file cache, idempotent 호출.

**교훈 15: 본인 fork 공식 sample은 첫 단계부터 활용한다.**

- header, token cache, `inquire_balance`, `tr_id` 분기 모두 공식 sample 비교가 결정적이었다.
- 다음 KIS 확장에서는 처음부터 본인 fork를 열고 endpoint, params, `tr_id`, response field를 맞춘다.

---

## 2. KIS API Endpoint 정리

### 2.1 인증

| Endpoint | 용도 | 비고 |
| --- | --- | --- |
| `/oauth2/tokenP` | 토큰 발급 | 1분당 1회 제한, 24시간 유효 |
| `/oauth2/revokeP` | 토큰 폐기 | 선택 |

### 2.2 시세 조회, 구현 완료

| Endpoint | 용도 | tr_id | Phase |
| --- | --- | --- | --- |
| `/uapi/domestic-stock/v1/quotations/inquire-price` | 현재가 | `FHKST01010100` | 8c-1 |
| `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice` | 일별 시세 | `FHKST03010100` | 8c-1/8c-2 |

### 2.3 수급 조회, 구현 완료

| Endpoint | 용도 | tr_id | Phase |
| --- | --- | --- | --- |
| `/uapi/domestic-stock/v1/quotations/inquire-investor` | 투자자별 매매 | `FHKST01010900` | 8d-1 |
| `/uapi/domestic-stock/v1/quotations/foreign-institution-total` | 외인/기관 가집계 | `FHPTJ04400000` | 8d-1 |

### 2.4 잔고 조회, 구현 완료

| Endpoint | 용도 | paper tr_id | prod tr_id | Phase |
| --- | --- | --- | --- | --- |
| `/uapi/domestic-stock/v1/trading/inquire-balance` | 잔고 조회 | `VTTC8434R` | `TTTC8434R` | 8f-1 |

응답 구조:

- `output1`: 보유 종목 list. 주요 field: `pdno`, `prdt_name`, `hldg_qty`, `pchs_avg_pric`, `prpr`, `evlu_amt`, `evlu_pfls_amt`, `evlu_pfls_rt`.
- `output2`: 계좌 종합 평가. 주요 field: `tot_evlu_amt`, `pchs_amt_smtl_amt`, `evlu_pfls_smtl_amt`, `dnca_tot_amt`, `tot_asst_amt`.

### 2.5 주문, Stage 4 실거래 전환 시 구현

| Endpoint | 용도 | paper tr_id | prod tr_id |
| --- | --- | --- | --- |
| `/uapi/domestic-stock/v1/trading/order-cash` | 현금 주문 | `VTTC0802U` / `VTTC0801U` | `TTTC0802U` / `TTTC0801U` |
| `/uapi/domestic-stock/v1/trading/order-rvsecncl` | 주문 정정/취소 | `VTTC0803U` | `TTTC0803U` |
| `/uapi/domestic-stock/v1/trading/inquire-psbl-order` | 매수 가능 금액 | `VTTC8908R` | `TTTC8908R` |

Stage 4 전환 전에는 본인 fork sample에서 `order_cash`, `order_rvsecncl`, `inquire_psbl_order`, `inquire_psbl_sell`, `inquire_ccnl`까지 함께 검증한다.

### 2.6 본인 fork 추가 활용 가능, 미구현

수급 추가:

- `inquire_investor_daily_by_market`
- `investor_program_trade_today`
- `program_trade_by_stock`
- `program_trade_by_stock_daily`
- `investor_trend_estimate`
- `frgnmem_trade_estimate`

재무, JACKAL 진화:

- `finance_income_statement`
- `finance_balance_sheet`
- `finance_financial_ratio`
- `finance_profit_ratio`
- `finance_growth_ratio`
- `finance_stability_ratio`
- `estimate_perform`
- `invest_opinion`

순위, JACKAL Hunter 진화:

- `volume_rank`
- `fluctuation`
- `market_cap`
- `short_sale`
- `top_interest_stock`

일정/뉴스, ATLAS 차원:

- `news_title`
- `chk_holiday`
- `ksdinfo_dividend`
- `ksdinfo_sharehld_meet`

시세 추가:

- `inquire_index_price`
- `inquire_asking_price_exp_ccn`
- `inquire_time_itemchartprice`
- `inquire_time_indexchartprice`

---

## 3. 운영 주의 사항

### 3.1 인증 운영

- `KIS_IS_PAPER`는 `true` / `false` 문자열을 정확히 해석한다.
- `KIS_CMW_APP_KEY_PAPER`, `KIS_CMW_APP_SECRET_PAPER`, `KIS_CMW_ACCOUNT_NUMBER_PAPER`는 코드, workflow, GitHub Secrets 이름이 일치해야 한다.
- GitHub Actions 로그에는 secret 값을 출력하지 않는다.
- token cache 파일은 commit 금지 대상이다.

### 3.2 호출 운영

- KIS 호출은 `get_shared_kis_client()`를 우선 사용한다.
- 같은 cycle 안에서는 singleton으로 token 발급 1회를 보장한다.
- 다른 cycle 사이는 파일 cache로 24시간 token을 재사용한다.
- 호출 실패는 가능하면 `None` 반환으로 흡수하고, 사용자 표시 여부는 caller가 결정한다.

### 3.3 모의/실전 전환

Stage 4 실거래 전환 체크리스트:

- `KIS_IS_PAPER=false`
- 실전 app key/secret/account 등록
- prod base URL 확인
- token cache 무효화 확인
- 주문 계열 `tr_id` 전수 검증
- 매수 가능 금액, 주문, 체결 조회, 취소까지 paper에서 dry-run 흐름 검증
- FALCON risk gate를 통과한 주문만 실행

### 3.4 보안

- secret 값 직접 출력 금지.
- debug는 length, whitespace 여부, 끝 2글자까지만.
- token cache에 key 원문 저장 금지.
- workflow에는 `${{ secrets.NAME }}` 패턴만 사용.
- 운영 로그에는 status code, exception type, source 정도만 남긴다.

---

## 4. 시스템 큰 그림

### 4.1 ORCA + JACKAL 현재 흐름

```text
[데이터 수집]
KIS API: 현재가, 수급, 일별 시세, 잔고
  |
  v
shared/broker/kis.py
  - KisClient
  - token singleton + file cache
  - current price, history, investor flow, balance
  |
  v
shared/broker/__init__.py
  - get_shared_kis_client()
  |
  v
[ORCA 분석]
orca/data.py
modules/orca/pipeline/agents.py
orca/analysis_market.py
  |
  v
[JACKAL 후보 발굴]
jackal/watchlist.py
  - KIS holdings + candidate_registry
jackal/scanner.py
jackal/hunter.py
  |
  v
[표시]
orca/notify.py
reports/dashboard.html
```

### 4.2 ATLAS + FALCON 진입

```text
[ATLAS - 정보 레이더]
Naver News + GDELT + Finnhub + NewsAPI + Open DART
  |
  v
[ORCA - 시장의 눈]
가격 + 수급 + 뉴스 + 재무 + 레짐 판단
  |
  v
[JACKAL - 사냥 감각]
후보 발굴 + 타점 + Devil 검증
  |
  v
[FALCON - 공격 통제]
자금 배분 + 손절 + 주문 실행 + 체결 감시
  |
  v
KIS API Stage 4 실거래
```

---

## 5. 마라톤 누적

### Phase 8 시리즈

- Phase 8b: KIS skeleton. 인증, env, base URL.
- Phase 8c-1: KIS 시세 메서드. 현재가, 일별 시세.
- Phase 8c-2: shared market fetch chain에 KIS 통합.
- Phase 8c-3: ORCA `_fetch_one()`에 KIS 우선 적용.
- Phase 8d-1: KIS 수급 메서드 추가.
- Phase 8d-2: ORCA investor flow에 KIS 통합.
- Phase 8d-3a~3i: workflow env, debug marker, auth/secret/token 제한 디버그.
- Phase 8d-3e: singleton + file cache로 token 1분 제한 해결.
- Phase 8d-4: KRX 제거, KIS 단일 소스.
- Phase 8f-1: KIS account balance 추가.
- Phase 8f-2: portfolio realtime integration.
- Phase 8f-3: Telegram portfolio 표시.
- Phase 8g-1: `jackal/watchlist.py`, KIS + candidate_registry 결합.
- Phase 8g-2: portfolio fallback 제거, Telegram KIS-only.
- Phase 8g-3: `portfolio.json` 완전 삭제.

### 본인 결정 마일스톤

- 4/28 의도: "포트폴리오 KIS 실시간만, 하드코딩 X" -> Phase 8g-3에서 완성.
- KIS 1분 token 제한 -> Phase 8d-3e에서 해결.
- KRX 정리 -> Phase 8d-4에서 완료.
- JACKAL 영향 범위 -> Phase 8g-1에서 candidate_registry 결합으로 반영.

---

## 6. 다음 단계 To-Do

### 즉시

- JACKAL 검증 강화.
- Phase 6 Shadow mode 재개.
- Phase 7 JACKAL yml + Devil parsing 정리.

### 중기

- Phase 8e 분 단위 데이터: `inquire_time_itemchartprice`.
- 본인 fork 자산 추가 활용: `volume_rank`, finance, news, program trade.
- Phase 9 KIS strategy builder.
- Phase 10 KIS MCP.

### 장기

- ATLAS Phase 1-4: 정보 레이더.
- FALCON Phase 1-2: Stage 4 실거래 제어.
- PostgreSQL + Redis 마이그레이션, 필요 시.
- 본인 4/28 인수인계 요구사항 지속 반영.

---

## 7. 본인 마라톤 시각

이번 KIS marathon에서 본인이 입증한 운영 책임자 시각:

1. "내 잘못 아니라고"에서 끝내지 않고 진짜 원인을 끝까지 추적.
2. 본인 PC 직접 검증으로 KIS key 자체 정상 입증.
3. GitHub Actions와 local 환경 차이를 raw로 분리.
4. 본인 fork 공식 sample을 실전 자산으로 활용.
5. "JACKAL은?"이라는 시스템 영향 범위 질문.
6. 본인 의도와 모순되는 fallback을 제거하는 판단.
7. sprint 단계 분리 + 회귀 안전망.
8. 4/28 의도를 끝까지 실제 코드와 운영 결과로 실현.

이 문서는 앞으로 KIS API를 확장할 때 같은 실수를 반복하지 않기 위한 기준선이다.
