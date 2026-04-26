# Wave F Phase 3 STEP 2-B+C-C Runbook

## 목적

ORCA Daily run 의 Reporter, Telegram, GitHub Pages dashboard 에 historical context 를 표시한다.
JACKAL Hunter 통합과 달리 ORCA 는 observe-only 이며, 점수나 추천 자체를 조정하지 않는다.

## 통합 위치

- `orca/pipeline.py`: Reporter 결과 생성 직후 `historical_context` 를 report dict 에 주입한다.
- `orca/historical_context.py`: ORCA 전용 read-only retrieval helper 이다.
- `orca/present.py`: 콘솔 리포트에 `Historical Market Context` 패널을 추가한다.
- `orca/notify.py`: Telegram 메시지에 간단한 cluster/win-rate/avg-value 요약을 추가한다.
- `orca/dashboard.py`: GitHub Pages dashboard 에 historical context 카드와 top examples 를 표시한다.

## Feature Flag

- `USE_HISTORICAL_CONTEXT=1`: 기본값. historical context retrieval 을 시도한다.
- `USE_HISTORICAL_CONTEXT=0`: ORCA/JACKAL historical context 를 모두 우회한다.

ORCA 는 `HISTORICAL_CONTEXT_MODE` 를 사용하지 않는다. 해당 모드는 JACKAL Hunter 의 observe/adjust 제어용이다.

## Retrieval 정책

- `top_k=20`
- `quality_filter=high`
- `recency_decay_days=365`
- DB write 없음
- snapshot 생성 없음
- 실패 시 `None` 반환 후 기존 ORCA Daily 흐름 계속 진행

## Context Feature Resolution

`orca/historical_context.py` 는 다음 순서로 features 를 찾는다.

1. `historical_context_features`
2. `market_features`
3. `context_features`
4. `context_snapshot`
5. 입력 dict 자체
6. 최신 `lesson_context_snapshot` read-only fallback

ORCA report 는 항상 5d/20d momentum 을 들고 있지는 않으므로 최신 snapshot fallback 이 운영 안정성을 담당한다.

## 출력 해석

- `cluster_label`: 오늘 시장과 가장 가까운 historical cluster label
- `cluster_size`: 해당 cluster 의 historical sample 수
- `win_rate`: top retrieved lessons 중 positive lesson 비율
- `avg_value`: top retrieved lessons 의 평균 lesson value
- `high_quality_count`: top lessons 중 high quality 개수
- `top_lessons`: report/dashboard 에 표시되는 유사 과거 사례

## Rollback

가장 빠른 rollback:

```bash
USE_HISTORICAL_CONTEXT=0
```

이 경우 pipeline enrichment 가 생략되고 Reporter, Telegram, Dashboard 는 기존 출력만 유지한다.

## 검증

권장 검증:

```bash
python -m pytest tests/test_orca_historical_integration.py
python -m pytest
```

운영 smoke:

```python
from orca.historical_context import get_market_historical_context

ctx = get_market_historical_context()
print(ctx["cluster_label"] if ctx else "no context")
```

## 다음 단계

STEP 2-B+C-D:

- JACKAL Backtest 통합
- `as_of_date` 기반 look-ahead bias 차단
- retrieval log 추가
- Phase 4 self-correction/A-B test 준비
