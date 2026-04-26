# Wave F Phase 3 - JACKAL Hunter Historical Context Runbook

## 목적

STEP 2-B+C-B 는 JACKAL Hunter 의 Stage 4 결과에 historical context 를 붙인다.

기본값은 안전한 `observe` 모드다. 즉, 비슷한 과거 lesson 을 보여주지만 점수는 바꾸지 않는다.

## 통합 위치

파일: `jackal/hunter.py`

위치:

- `_stage4_full_analysis()`
- `apply_probability_adjustment()` 직후
- Telegram alert 생성: `_build_alert()`
- hunt log 저장: `_build_hunt_log_entry()`

## Feature Flags

`USE_HISTORICAL_CONTEXT`

- 기본값: `1`
- `0`, `false`, `no`, `off`: historical context 전체 bypass

`HISTORICAL_CONTEXT_MODE`

- 기본값: `observe`
- `observe`: retrieval 결과만 붙이고 점수 변경 없음
- `adjust`: historical context 기반으로 `final_score` 를 조정

## Observe Mode

Observe mode 동작:

- top-5 similar high-quality lessons retrieval
- `item["historical_context"]` 에 저장
- Telegram alert 에 cluster, win rate, avg value, similar examples 표시
- hunt log 에 `historical_context` 저장
- `final_score` 변경 없음

Rollback 은 필요 없지만, 완전히 끄려면:

```bash
USE_HISTORICAL_CONTEXT=0
```

## Adjust Mode

Adjust mode 는 opt-in 이다.

```bash
HISTORICAL_CONTEXT_MODE=adjust
```

Adjustment logic:

- win rate factor: historical top-5 win rate
- value factor: top-5 평균 lesson_value
- quality multiplier: high-quality lesson count
- cap: `-5.0` to `+5.0`

점수 조정만 끄려면:

```bash
HISTORICAL_CONTEXT_MODE=observe
```

## Data Source

Hunter 는 ARIA context 에서 features 를 먼저 찾는다.

우선순위:

1. `aria["historical_context_features"]`
2. `aria["market_features"]`
3. `aria["context_features"]`
4. `aria` top-level feature keys
5. DB 의 최신 `lesson_context_snapshot`

DB lookup 은 read-only 이며 snapshot 을 새로 만들지 않는다.

## Graceful Fallback

다음 상황에서는 `historical_context=None` 으로 계속 진행한다.

- feature flag off
- market features 없음
- retrieval 결과 없음
- retrieval 중 예외 발생

추천 흐름은 중단하지 않는다.

## Hunt Log

`hunt_log.json` entry 에 추가되는 필드:

- `historical_context`
- `historical_adjustment`

이 데이터는 Phase 4 self-correction 에서 “historical context 가 실제 outcome 개선에 도움이 되었는지”를 검증하는 기반이다.

## 다음 단계

STEP 2-B+C-C:

- ORCA Reporter / Telegram / Dashboard 에 cluster context 표시

STEP 2-B+C-D:

- JACKAL Backtest 통합
- `as_of_date` 필터로 look-ahead bias 방지
- retrieval log / Phase 4 A-B test 기반 구축
