# Wave F Phase 3 STEP 2-B+C-D Runbook

## 목적

이번 단계는 historical retrieval 을 운영 관찰 데이터로 남겨 Phase 4 self-correction 의 기반을 만든다.

핵심 변경은 세 가지다.

- `retrieval_log` 테이블을 추가해 어떤 context retrieval 이 어떤 판단에 쓰였는지 기록한다.
- JACKAL Backtest 에 historical context 를 연결하되 `as_of_date` 로 미래 lesson 을 차단한다.
- `measure_retrieval_accuracy()` 로 cluster / signal / mode 별 정확도 분석의 시작점을 제공한다.

기본 동작은 안전하게 유지된다.

- `log_retrieval=False` 가 기본값이다.
- `USE_HISTORICAL_CONTEXT=0` 이면 retrieval 통합은 우회된다.
- retrieval 실패 시 backtest 는 계속 진행된다.

## Retrieval Log Schema

`retrieval_log` 는 Phase 4 에서 historical context 의 예측력이 실제 outcome 과 맞았는지 분석하기 위한 원장이다.

주요 컬럼:

- `source_system`: `jackal_hunter`, `jackal_backtest`, `orca_pipeline`, `orca_backtest` 같은 호출 주체
- `source_event_type`: `live`, `backtest`, `shadow`
- `source_event_id`: candidate id, hunt id, backtest item id 등 호출 이벤트 식별자
- `trading_date`: retrieval 이 수행된 시장 날짜
- `as_of_date`: look-ahead bias 방지를 위해 적용한 cutoff date
- `top_k`, `quality_filter`, `signal_family`: retrieval 파라미터
- `cluster_id`, `cluster_label`, `cluster_distance`: 선택된 context cluster
- `lessons_count`, `win_rate`, `avg_value`, `high_quality_count`: Top-K lesson 요약
- `top_lessons_json`: lesson id, ticker, value, quality tier, analysis date 의 JSON list
- `mode`, `adjustment_value`, `adjustment_capped`: observe / adjust 모드 및 점수 보정 정보
- `actual_outcome`, `outcome_at`, `outcome_match`: Phase 4 에서 채울 실제 결과
- `hunter_run_id`, `backtest_run_id`: 실행 단위 grouping

인덱스:

- `idx_retrieval_log_source`: source system + trading date 조회
- `idx_retrieval_log_cluster`: cluster 별 성과 분석
- `idx_retrieval_log_run`: backtest run 별 분석
- `idx_retrieval_log_outcome_pending`: 아직 outcome 이 채워지지 않은 log 조회

## Store API

구현 위치:

- `orca/retrieval_log_store.py`
- `orca/state.py` 에 compatibility alias 로 노출

주요 함수:

```python
from orca import state

state.record_retrieval_log(conn, log_data)
state.update_retrieval_outcome(conn, log_id, actual_outcome, outcome_at, outcome_match)
state.get_retrieval_log(conn, log_id)
state.get_pending_outcomes(conn, before_date)
state.get_retrieval_stats_for_cluster(conn, cluster_id, since_date=None)
state.measure_retrieval_accuracy(conn, backtest_run_id=None, since_date=None)
```

`record_retrieval_log()` 는 dict 입력을 받아 누락 가능한 필드는 안전한 기본값으로 채운다.
`top_lessons_json` 은 Python list/dict 로 넘기면 JSON 문자열로 저장된다.

## Retrieval API Logging

`orca.lesson_retrieval.retrieve_similar_lessons()` 와 `retrieve_similar_lessons_for_features()` 에 logging 옵션이 추가됐다.

기본값은 `log_retrieval=False` 이므로 기존 호출은 DB write 없이 그대로 read-only 이다.

예시:

```python
from orca.lesson_retrieval import retrieve_similar_lessons

lessons = retrieve_similar_lessons(
    analysis_date="2026-04-03",
    as_of_date="2026-04-03",
    top_k=5,
    quality_filter="high",
    signal_family="momentum_pullback",
    log_retrieval=True,
    source_system="jackal_backtest",
    source_event_type="backtest",
    source_event_id="bt_run:2026-04-03:NVDA:1",
    backtest_run_id="bt_run",
)
```

`as_of_date` 가 있으면 `lesson.analysis_date < as_of_date` 인 lesson 만 검색된다.
이 비교는 backtest 에서 look-ahead bias 를 막는 핵심 안전장치다.

## JACKAL Backtest Integration

통합 위치:

- `jackal/backtest.py`
- `s2_score` 계산 직후 historical context 를 붙인다.

흐름:

1. candidate 의 `signal_family` 를 사용하거나 기술지표 기반으로 추론한다.
2. ORCA report 에서 market features 를 읽는다.
3. features 가 없으면 `analysis_date` 의 cached snapshot 으로 retrieval 한다.
4. `as_of_date=date_str` 를 반드시 넘긴다.
5. `log_retrieval=True`, `source_system="jackal_backtest"` 로 `retrieval_log` 에 남긴다.
6. observe 모드에서는 점수 변경 없이 `historical_context` 만 저장한다.
7. adjust 모드에서는 ±5 cap 을 지켜 `s2_score` 를 보정한다.

Backtest 에서는 최신 snapshot fallback 을 끄도록 `allow_latest_fallback=False` 를 사용한다.
이렇게 해야 과거 날짜 평가 중 현재 시장 snapshot 이 섞이지 않는다.

Signal family 필터가 너무 좁아 결과가 0개인 경우에는 같은 cluster 의 high-quality lesson 으로 한 번 완화한다.
단, Phase 4 로그에는 최종적으로 사용된 retrieval 만 남긴다.

## ORCA Backtest

이번 단계에서 ORCA 쪽 helper 는 logging 옵션을 받을 수 있게 확장됐다.

- `orca/historical_context.py::get_market_historical_context()`
- `as_of_date`
- `log_retrieval`
- `source_system`
- `source_event_type`
- `source_event_id`
- `backtest_run_id`

직접 ORCA Backtest 루프에 연결하는 것은 선택 사항으로 남겼다.
현재 구현은 JACKAL Backtest 를 우선 통합하고, ORCA Backtest 는 같은 helper 로 즉시 연결 가능한 상태다.

## Accuracy Measurement

Phase 4 는 `retrieval_log` 의 pending row 에 실제 outcome 을 채운 뒤 정확도를 측정한다.

예시:

```python
from orca import state

with state._connect_orca() as conn:
    stats = state.measure_retrieval_accuracy(
        conn,
        backtest_run_id="bt_run",
    )

print(stats["accuracy_overall"])
print(stats["cluster_accuracy"])
print(stats["signal_family_accuracy"])
```

반환 구조:

- `total_retrievals`: 전체 retrieval log 수
- `completed_outcomes`: actual outcome 이 채워진 수
- `accuracy_overall`: `outcome_match=1` 비율
- `cluster_accuracy`: cluster 별 정확도
- `signal_family_accuracy`: signal family 별 정확도
- `mode_accuracy`: observe / adjust 모드 별 정확도

## Outcome Update

실제 결과가 확인되면 다음처럼 outcome 을 채운다.

```python
state.update_retrieval_outcome(
    conn,
    log_id="retrieval_log_id",
    actual_outcome=7.4,
    outcome_at="2026-04-10",
    outcome_match=True,
)
```

`outcome_match` 의 기준은 Phase 4 에서 더 정교화할 수 있다.
예를 들어 retrieved lessons 의 평균 방향과 실제 outcome 방향이 같으면 match 로 볼 수 있다.

## Look-Ahead Bias Guard

Backtest 에서 반드시 지켜야 하는 규칙:

- `as_of_date=date_str` 를 항상 넘긴다.
- `allow_latest_fallback=False` 로 최신 snapshot fallback 을 막는다.
- retrieval 결과는 `lesson.analysis_date < as_of_date` 만 포함해야 한다.
- 로그의 `top_lessons_json` 에 미래 날짜 lesson 이 없어야 한다.

이 규칙은 `tests/test_retrieval_log.py` 에서 검증한다.

## Rollback

가장 빠른 rollback:

```bash
USE_HISTORICAL_CONTEXT=0
```

이 경우 JACKAL/ORCA historical context retrieval 이 bypass 된다.

로그만 끄려면 호출 측에서 `log_retrieval=False` 를 유지하면 된다.
기본값이 false 이므로 기존 live 호출은 명시적으로 켜지 않는 한 DB write 를 하지 않는다.

## Verification

권장 검증:

```bash
python -m unittest tests.test_retrieval_log -v
python -m unittest tests.test_lesson_retrieval tests.test_jackal_hunter_historical_integration tests.test_orca_historical_integration -v
python -m unittest discover -s tests -v
```

확인 포인트:

- retrieval_log table 과 indexes 가 idempotent 하게 생성된다.
- `log_retrieval=True` 일 때만 row 가 생성된다.
- `as_of_date` 가 미래 lesson 을 제외한다.
- JACKAL Backtest helper 가 `source_system="jackal_backtest"` 와 `backtest_run_id` 를 남긴다.
- `measure_retrieval_accuracy()` 가 cluster / signal / mode breakdown 을 반환한다.

## Phase 4 연결

이번 단계 이후 Phase 4 에서 가능한 작업:

- retrieval 예측 방향과 실제 outcome 비교
- cluster 별 historical context 신뢰도 측정
- signal family 별 retrieval 효용 측정
- observe 모드와 adjust 모드 A/B test
- 낮은 정확도 cluster 의 quality weight 재조정
- cluster rebalancing 또는 k 재검토

이제 Wave F Phase 3 는 retrieval 을 “보여주는 단계”에서 “측정 가능한 학습 데이터로 남기는 단계”까지 연결된다.
