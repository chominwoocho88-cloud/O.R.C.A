# Wave F Phase 3 Runbook: Historical Lesson Retrieval

## 목적

Wave F Phase 3 는 Phase 1 의 context snapshot 과 Phase 2 의 context cluster 를 이용해, 새 candidate 분석 시 비슷한 시장 상황의 historical lessons 를 다시 꺼내 쓰는 단계다.

STEP 2-A 의 범위는 read-only retrieval API 이다.

- DB write 없음
- `allow_create_snapshot=False` 기본
- `lesson_archive` 저장 없음
- retrieval log 없음
- JACKAL/ARIA 통합 없음

통합과 저장은 다음 단계에서 진행한다.

- STEP 2-B: quality tier 정교화, recency policy, optional `lesson_archive`
- STEP 2-C: JACKAL / ARIA 통합
- STEP 2-D: retrieval log, Phase 4 self-correction 준비

## Public API

### `retrieve_similar_lessons()`

종합 entry point 다.

```python
from orca.lesson_retrieval import retrieve_similar_lessons

lessons = retrieve_similar_lessons(
    candidate_id="cand_xxx",
    top_k=5,
)
```

Context resolution priority:

1. `snapshot_id`
2. `candidate_id`
3. `analysis_date`
4. `features`

`allow_create_snapshot=False` 가 기본이다. snapshot 이 없으면 새로 만들지 않고 `LookupError` 를 발생시킨다.

### `retrieve_similar_lessons_for_features()`

시장 context feature dict 를 직접 넣는 경로다.

```python
from orca.lesson_retrieval import retrieve_similar_lessons_for_features

lessons = retrieve_similar_lessons_for_features(
    {
        "vix_level": 18.5,
        "sp500_momentum_5d": 1.2,
        "sp500_momentum_20d": 3.4,
        "nasdaq_momentum_5d": 1.5,
        "nasdaq_momentum_20d": 4.1,
        "regime": "위험선호",
        "dominant_sectors": ["Technology", "Communication Services"],
    },
    top_k=10,
)
```

## Returned Fields

각 lesson 은 다음 정보를 포함한다.

- `lesson_id`
- `ticker`
- `signal_family`
- `lesson_value`
- `quality_tier`
- `relevance_score`
- `quality_score`
- `context_score`
- `signal_score`
- `recency_score`
- `cluster_id`
- `cluster_label`
- `analysis_date`
- `signals_fired`
- `peak_pct`
- `peak_day`
- `distance_to_centroid`

정렬은 `relevance_score DESC` 이다.

## Scoring

STEP 2-A 의 scoring 은 설명 가능성을 우선한다.

```text
relevance_score =
  0.45 * quality_score
  + 0.25 * context_score
  + 0.20 * signal_score
  + 0.10 * recency_score
```

### Quality

`lesson_value` 의 percentile rank 를 사용한다.

이유:

- 현재 max value `63.06` 같은 outlier 가 있음
- raw value 를 직접 쓰면 outlier 가 ranking 을 과도하게 지배함
- percentile 은 분포 안에서 상대 순위를 안정적으로 표현함

Tier:

- `high`: percentile `> 0.67`
- `medium`: percentile `> 0.33`
- `low`: 나머지

### Context

동일 cluster lesson 만 retrieval 대상이다.

Context score:

- same cluster base: `0.7`
- centroid distance bonus: 최대 `0.3`
- distance 가 작을수록 bonus 가 크다.

### Signal

`signal_family` 가 주어지면 match 를 scoring 에 반영한다.

- match: `1.0`
- mismatch: `0.0`
- target 또는 lesson family 가 없으면 neutral `0.5`

명시적으로 `signal_family="..."` 를 넘기면 해당 family 만 filter 한다.

### Recency

`recency_decay_days=None` 이 기본이며 이 경우 `recency_score=1.0` 이다.

decay 를 켜면 다음 공식을 쓴다.

```text
exp(-days_old / recency_decay_days)
```

Recency 정책은 STEP 2-B 에서 더 정교화한다.

## Look-Ahead Bias

Backtest 에서는 반드시 `as_of_date` 를 넘긴다.

```python
lessons = retrieve_similar_lessons(
    analysis_date="2025-06-01",
    as_of_date="2025-06-01",
    top_k=20,
)
```

필터 기준:

```text
lesson.analysis_date < as_of_date
```

같은 날짜 lesson 도 아직 outcome 을 알 수 없으므로 제외한다.

## Usage Patterns

### JACKAL Hunter

```python
lessons = retrieve_similar_lessons(
    candidate_id=candidate_id,
    top_k=5,
)
```

목적:

- 비슷한 시장에서 같은 signal family 가 어떻게 작동했는지 확인
- confidence 보정
- 추천 설명에 historical evidence 추가

### ARIA Daily

```python
lessons = retrieve_similar_lessons(
    analysis_date=today,
    top_k=20,
)
```

목적:

- 오늘 시장 context 와 유사한 historical pattern 제공
- 보고서에 cluster label 과 lesson examples 추가

### Backtest

```python
lessons = retrieve_similar_lessons(
    analysis_date=analysis_date,
    as_of_date=analysis_date,
    top_k=20,
)
```

목적:

- 그 시점 이전에 알 수 있었던 lessons 만 사용
- Phase 4 A/B test 기반 마련

## Verification

타깃 테스트:

```powershell
python -m unittest tests.test_lesson_retrieval
```

전체 회귀:

```powershell
python -m unittest discover -s tests
```

실제 DB sanity check:

```powershell
@'
from orca.lesson_retrieval import retrieve_similar_lessons_for_features

lessons = retrieve_similar_lessons_for_features(
    {
        "vix_level": 14.5,
        "sp500_momentum_5d": 2.0,
        "sp500_momentum_20d": 5.0,
        "nasdaq_momentum_5d": 2.5,
        "nasdaq_momentum_20d": 6.0,
        "regime": "위험선호",
        "dominant_sectors": ["Technology", "Communication Services"],
    },
    top_k=5,
)
for lesson in lessons:
    print(lesson["ticker"], lesson["cluster_label"], lesson["relevance_score"])
'@ | python -
```

## Safety

STEP 2-A 는 read-only 이다.

- `candidate_lessons` 변경 없음
- `lesson_context_snapshot` 변경 없음
- `lesson_clusters` 변경 없음
- `snapshot_cluster_mapping` 변경 없음

단, `allow_create_snapshot=True` 를 명시하면 snapshot 생성 경로가 열릴 수 있다. 운영 통합 전에는 기본값 `False` 를 유지한다.

## Next

STEP 2-B:

- quality tier policy 정교화
- recency policy 확정
- optional `lesson_archive`

STEP 2-C:

- JACKAL Hunter integration
- ARIA Daily integration

STEP 2-D:

- retrieval log
- Phase 4 self-correction / A-B test 준비
