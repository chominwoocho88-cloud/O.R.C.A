# Wave F: Meta-Learning Layer 설계 문서

> **작성일**: 2026-04-24
> **상태**: Concept design (Wave A 완료 후 착수 예정)
> **작성자**: 민우 + Claude (논의 기반)

---

## 1. Motivation (왜 필요한가)

### 1.1 현재 JACKAL 학습 시스템의 상태

Wave A 를 통해 JACKAL 은 다음과 같은 학습 loop 을 갖게 됨:

```
Signal 발생 → Candidate 기록 → Outcome 관찰 → Lesson 저장 → Weight update
```

이것은 **Bayesian weight update** 수준의 학습. 외부에서 보면:
- 많은 데이터가 쌓임
- 정답률이 점진적으로 수렴
- 가끔 regime 이 바뀌면 성능 저하

### 1.2 본질적 한계 3가지

사용자 (민우) 가 제기한 문제 의식을 정리하면:

#### 한계 1: **Max 수치 문제 — Context-free learning**

현재 학습은 signal family × regime 정도의 단순 grouping 만 사용.

예시:
```
divergence_family 의 swing 정답률: 66%
```

이 66% 의 실제 구성:
- 혼조장에서 59% (쉬움)
- 전환중에서 69% (중간)
- 위험회피장에서 74% (어려움인데 divergence 가 특별히 잘 듦)

단일 숫자는 **의사결정에 부정확**. "현재 시장에서 divergence 를 얼마나 믿어야 하나?" 에 답하려면 context 별 숫자가 필요.

#### 한계 2: **무방비 저장 문제 — No lesson quality distinction**

현재 `candidate_lessons` 테이블은 모든 outcome 을 동일하게 저장.

문제 사례:
- **Outlier lesson**: 특정 뉴스 이벤트로 NVDA 가 하루 20% 급등 → "NVDA divergence 성공" 으로 학습됨. 하지만 이건 재현 불가능한 일회성.
- **Edge case lesson**: 시장 체제 전환 구간 (예: 금리 결정일 직후) 의 특이한 움직임 → 정상 체제에 잘못 적용됨.
- **Transient lesson**: 특정 3-4일 구간의 sector rotation 으로 생긴 lesson → 로테이션 끝난 후에도 계속 weight 에 영향.

→ 결과: **평균 정답률이 지표로써 점점 믿을 수 없게 됨**.

#### 한계 3: **정답률 하락 복구 메커니즘 부재**

현재:
- Accuracy 떨어지면 weight 조정
- 하지만 "왜 떨어졌는지" 판단 없음
- 과거에 유사 상황이 있었는지 조회 없음

결과:
- Regime shift 감지 못 함
- 과거 경험을 재활용 못 함
- 항상 처음부터 다시 배우는 느낌

### 1.3 진단 요약

```
현재: Pure Bayesian update
      ↓
진화 방향: Episodic memory + Meta-learning
           (Context 별 경험 기록 + 상황별 회상 + 자기 수정)
```

이것은 **단순한 기능 개선이 아니라 학습 패러다임의 전환**.

---

## 2. Proposed Architecture

### 2.1 High-level view

```
기존 (Wave A 완료):
────────────────────────────────────
Candidate → Outcome → Lesson → Weight update
(단방향, context-free)


개선 (Wave F):
────────────────────────────────────
Candidate → Outcome → Lesson
                        ↓
                 Context Snapshot
                 (시장 상태 기록)
                        ↓
                 Lesson Archive
                 (taxonomy + quality tier)
                        ↓
        ┌─ Normal path: weight update (기존)
        │
        └─ Self-correction trigger (신규)
              ↓
           Accuracy drop detected
              ↓
           Similar context retrieval
           (과거 유사 상황 찾기)
              ↓
           Historical best-strategy boost
           (그 때 맞았던 전략 일시 강화)
              ↓
           A/B observation + rollback
           (효과 있으면 영구 반영, 없으면 되돌림)
```

### 2.2 4개의 layer

#### Layer 1: Context Snapshot (시장 상태 기록)

각 candidate/lesson 기록 시점의 **시장 맥락** 을 명시적으로 저장.

무엇을 기록하나:
- **Regime**: 위험선호 / 혼조 / 위험회피 / 전환중
- **Volatility**: VIX level, VIX 7일 변동, SP500 momentum
- **Sector state**: 가장 강한 섹터, sector rotation 벡터
- **Breadth**: 신고가/신저가, advance/decline ratio
- **Event flags**: 금리결정 전후, CPI 발표일, 실적 시즌 여부

→ 같은 "divergence success" 라도 **언제 어떤 상황에서** 성공했는지 남음.

#### Layer 2: Context-aware Lesson Storage (맥락을 담은 교훈)

기존 `candidate_lessons` 에 다음을 추가:
- `context_snapshot_id`: 해당 lesson 이 발생한 시장 상태 (Layer 1 참조)
- `gain_mode`: 어떤 가산 방식이 맞았는지 (예: "volume_confirmation", "MA_bounce", "panic_reversal")
- `confidence_tier`: typical / outlier / edge_case (lesson quality 분류)
- `reproducibility_score`: 재현 가능성 점수 (0-1)

→ 단순한 "정답/오답" 이 아니라 **"왜 맞았는지" + "얼마나 믿을만한지"** 까지 저장.

#### Layer 3: Lesson Archive & Retrieval (경험 저장소 + 검색)

새 테이블 `lesson_archive`:
- Context cluster 별로 grouping
- 각 cluster 내 best strategy 식별
- 유사도 기반 검색 가능

새 함수:
- `find_similar_context(current_context, top_k=5)`: 현재 상황과 유사한 과거 상황 top-k 반환
- `get_historical_best_strategy(context_cluster_id)`: 해당 cluster 에서 가장 정답률 높은 전략 반환

→ **"이런 상황 전에 봤었고, 그때 이 방식이 맞았음"** 을 시스템이 말할 수 있음.

#### Layer 4: Self-Correction (자기 수정)

새 함수:
- `detect_accuracy_drop()`: 최근 N 일 정답률이 baseline 대비 급락 감지
- `diagnose_drop_cause(current_context, baseline_context)`: 원인 분류 (regime shift / specific signal decay / data drift)
- `self_correct(diagnosis)`: 과거 유사 상황의 best strategy 로 일시 weight boost
- `evaluate_correction_effect()`: 수정 후 N 일 성과 관찰 → 영구 반영 vs rollback

→ 시스템이 **자기 성능 저하를 인지하고 능동적으로 대응**.

---

## 3. Data Model (테이블 설계)

### 3.1 `lesson_context_snapshot`

모든 learning event 시점의 시장 맥락을 원자적으로 기록.

```sql
CREATE TABLE lesson_context_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    trading_date TEXT NOT NULL,

    -- Regime
    regime TEXT NOT NULL CHECK(regime IN ('위험선호', '혼조', '위험회피', '전환중')),
    regime_confidence REAL,  -- 0-1, 판정 신뢰도

    -- Volatility metrics
    vix_level REAL,
    vix_delta_7d REAL,
    vix_percentile_1y REAL,  -- 1년 내 백분위

    -- Market momentum
    sp500_momentum_5d REAL,
    sp500_momentum_20d REAL,
    nasdaq_momentum_5d REAL,

    -- Sector state (JSON)
    dominant_sectors TEXT,  -- JSON array, top 3 strongest sectors
    sector_rotation_vector TEXT,  -- JSON, sector-wise inflow scores
    sector_divergence_score REAL,  -- 섹터간 performance 분산도

    -- Breadth indicators
    new_highs_count INTEGER,
    new_lows_count INTEGER,
    advance_decline_ratio REAL,
    advance_decline_10d_ma REAL,

    -- Event flags
    is_earnings_season BOOLEAN,
    days_to_fomc INTEGER,  -- FOMC 까지 남은 일수 (음수면 지났음)
    days_to_cpi INTEGER,
    is_options_expiry_week BOOLEAN,

    -- Cluster assignment (Layer 3 에서 채움)
    context_cluster_id TEXT,

    -- Metadata
    source_event_type TEXT,  -- 'live', 'backtest', 'walk_forward'
    source_session_id TEXT,

    CHECK (created_at IS NOT NULL)
);

CREATE INDEX idx_snapshot_date ON lesson_context_snapshot(trading_date);
CREATE INDEX idx_snapshot_regime ON lesson_context_snapshot(regime);
CREATE INDEX idx_snapshot_cluster ON lesson_context_snapshot(context_cluster_id);
```

### 3.2 `candidate_lessons` 확장 (기존 테이블)

기존 테이블에 column 추가:

```sql
ALTER TABLE candidate_lessons ADD COLUMN context_snapshot_id TEXT
    REFERENCES lesson_context_snapshot(snapshot_id);
ALTER TABLE candidate_lessons ADD COLUMN gain_mode TEXT;
ALTER TABLE candidate_lessons ADD COLUMN confidence_tier TEXT
    CHECK(confidence_tier IN ('typical', 'outlier', 'edge_case'));
ALTER TABLE candidate_lessons ADD COLUMN reproducibility_score REAL;

CREATE INDEX idx_lessons_context ON candidate_lessons(context_snapshot_id);
CREATE INDEX idx_lessons_tier ON candidate_lessons(confidence_tier);
```

### 3.3 `lesson_archive`

Context cluster 별 best-strategy 저장.

```sql
CREATE TABLE lesson_archive (
    archive_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    last_updated TEXT NOT NULL,

    -- Context grouping
    context_cluster_id TEXT NOT NULL,
    cluster_description TEXT,  -- 사람이 읽을 수 있는 설명

    -- Strategy info
    signal_family TEXT NOT NULL,
    strategy_variant TEXT,  -- 예: 'divergence_with_volume_confirm'
    gain_mode TEXT,

    -- Performance under this context
    accuracy_d1 REAL,
    accuracy_swing REAL,
    sample_size INTEGER NOT NULL,
    avg_peak_gain REAL,
    avg_max_drawdown REAL,

    -- Quality flags
    is_validated BOOLEAN DEFAULT 0,  -- 재현성 검증 완료 여부
    validation_date TEXT,

    -- Recommendations
    recommended_weight_multiplier REAL DEFAULT 1.0,
    recommended_for_regime TEXT,  -- 어느 regime 에서 이 전략을 쓸지

    -- Provenance
    source_lesson_ids TEXT,  -- JSON array of lesson IDs that informed this archive entry

    UNIQUE(context_cluster_id, signal_family, strategy_variant)
);

CREATE INDEX idx_archive_cluster ON lesson_archive(context_cluster_id);
CREATE INDEX idx_archive_family ON lesson_archive(signal_family);
```

### 3.4 `self_correction_log`

Self-correction 이벤트 기록 (감사 + 학습 루프 디버깅용).

```sql
CREATE TABLE self_correction_log (
    correction_id TEXT PRIMARY KEY,
    triggered_at TEXT NOT NULL,

    -- Trigger info
    trigger_type TEXT,  -- 'accuracy_drop', 'regime_shift', 'manual'
    baseline_accuracy REAL,
    recent_accuracy REAL,
    accuracy_delta REAL,

    -- Diagnosis
    current_context_snapshot_id TEXT,
    matched_historical_contexts TEXT,  -- JSON array of snapshot_ids
    similarity_scores TEXT,  -- JSON

    -- Action taken
    action_type TEXT,  -- 'weight_boost', 'strategy_swap', 'fallback'
    action_details TEXT,  -- JSON
    applied_at TEXT,

    -- Evaluation (채워지는 건 나중)
    evaluation_window_days INTEGER,
    evaluation_end_date TEXT,
    post_correction_accuracy REAL,
    effect_verdict TEXT,  -- 'improved', 'neutral', 'worsened', 'rolled_back'

    -- Cleanup
    rolled_back_at TEXT,
    rollback_reason TEXT
);
```

---

## 4. Algorithms

### 4.1 Context Clustering

**목표**: `lesson_context_snapshot` 들을 유의미한 cluster 로 묶기.

**방법**:
1. Feature extraction: regime (categorical) + 정규화된 VIX/momentum/breadth (continuous)
2. Gower distance 또는 mixed-type distance 사용
3. Hierarchical clustering (Ward's method) 또는 DBSCAN
4. Cluster 수 제한: 10-20 개 (과적합 방지)
5. 각 cluster 에 인간이 이해할 수 있는 label 자동 생성
   - 예: "혼조장 + 고변동성 + 섹터 회전 심함"
   - 예: "위험회피장 + 저변동성 + 방어주 강세"

**재계산 주기**: 매월 1회 (또는 snapshot 500개 추가 시마다).

### 4.2 Similarity Metric

**목표**: 현재 context 와 가장 유사한 과거 context 찾기.

**가중치 설계**:
```python
similarity_score = (
    0.35 * regime_match          # 1.0 if same, 0.5 if adjacent, 0 otherwise
    + 0.20 * vix_similarity      # 1 / (1 + |vix_diff|)
    + 0.15 * momentum_similarity  # cosine similarity
    + 0.15 * sector_similarity    # cosine on sector vector
    + 0.10 * breadth_similarity   # normalized
    + 0.05 * event_match         # earnings season, FOMC proximity
)
```

**top-k 반환**: top-5 historical contexts + similarity scores.

### 4.3 Lesson Quality Classification

**목표**: 새 lesson 이 typical / outlier / edge_case 인지 판별.

**판단 기준**:
- **typical**: 해당 cluster 에서 평균에서 ±1 표준편차 내. 재현 가능성 높음.
- **outlier**: 평균에서 ±2 표준편차 밖. 일회성 가능성. Archive 에 반영하되 weight 낮춤.
- **edge_case**: regime 전환 구간 또는 event flag 이상치. 별도 bucket.

**재분류 주기**: Lesson 저장 시 즉시 분류, cluster 재계산 시 재분류.

### 4.4 Accuracy Drop Detection

**목표**: 최근 성능 저하 감지.

**방법**:
```python
def detect_accuracy_drop(
    lookback_days: int = 30,
    comparison_baseline_days: int = 180,
    threshold_pct: float = 0.10,  # 10% 이상 하락
    min_sample_recent: int = 20
) -> bool:
    recent = get_accuracy(last_n_days=lookback_days)
    baseline = get_accuracy(last_n_days=comparison_baseline_days, exclude_recent=lookback_days)

    if recent.sample_size < min_sample_recent:
        return False  # sample 부족, 판단 보류

    if recent.accuracy < baseline.accuracy * (1 - threshold_pct):
        return True

    return False
```

**False positive 방지**:
- 최소 sample size 20 이상 필요
- 연속 3회 (3일 연속) 감지되어야 trigger
- Regime 전환 직후 N 일 grace period

### 4.5 Self-Correction Strategy

**트리거 후 순서**:

1. **Diagnose**:
   - 현재 context snapshot 캡처
   - Baseline context 와 비교 (regime, volatility, sector)
   - 주원인 추정: regime_shift / signal_decay / data_drift

2. **Retrieve**:
   - `find_similar_context(current)` 호출
   - Top-5 유사 과거 context 가져옴
   - 각 context 의 best strategy 수집

3. **Boost**:
   - 수집된 strategy 들의 weight 에 temporary multiplier 적용
   - 기존 weight 는 건드리지 않음 (별도 override layer)
   - `recommended_weight_multiplier` 값 사용 (archive 에 저장된)

4. **Observe**:
   - N 일 (보통 10-14일) 관찰 기간
   - `self_correction_log` 에 상황 기록
   - 매일 성과 추적

5. **Decide**:
   - N 일 후 평균 accuracy 계산
   - 개선: 영구 반영 (permanent weight update)
   - 중립: 현 상태 유지 (multiplier 해제)
   - 악화: rollback (이전 weight 복원)

---

## 5. Safeguards (과적합 방지 장치)

### 5.1 Cluster 수 제한

- 최소 10개, 최대 20개
- 각 cluster 에 최소 30 snapshot 이상 있어야 유효
- 미달 cluster 는 merged 또는 무시

### 5.2 최소 sample size

- 새 strategy 를 archive 에 등록하려면 최소 50 lesson 필요
- Correction 을 trigger 하려면 최근 구간에 최소 20 lesson 필요
- Cluster 당 lesson 이 500개 넘으면 old lesson 부터 decay weighting

### 5.3 Survivorship bias 대응

- **Negative lesson 도 동일하게 저장**: 실패한 strategy 도 archive 에 기록
- Archive 에는 `accuracy` 외에 `failure_rate` 도 같이 저장
- "이 context 에서는 이 strategy 가 실패 확률이 높다" 정보 유지

### 5.4 Self-correction overfitting 방지

- 최소 관찰 기간 강제 (10일 이상 trigger 지속)
- Correction 적용 시 **A/B split**: 50% 는 새 strategy, 50% 는 기존 유지
- Rollback 메커니즘 필수
- 한 번 rollback 된 correction 은 30일 간 같은 context 에서 재시도 금지

### 5.5 Regime 분류 신뢰도

- `regime_confidence` 가 낮으면 self-correction 비활성
- 여러 independent signal 로 교차 검증:
  - VIX level
  - Breadth
  - Sector rotation direction
  - Bond yield curve
- 신뢰도 <0.6 이면 보수적 동작

### 5.6 Cold start 보호

- Archive 가 충분히 쌓이기 전 (예: snapshot 500개 미만) self-correction 비활성
- 초기 1개월간은 Context snapshot 수집만, correction 없음

---

## 6. Phased Roadmap

Wave F 는 4 phase 로 점진 구현. 각 phase 가 독립적으로 가치 있음.

### Phase 1: Context Snapshot Collection (2-3주)

**목표**: 데이터 수집 기반 구축.

**작업**:
- `lesson_context_snapshot` 테이블 생성
- 기존 lesson 기록 시점에 snapshot 동시 저장
- Regime classifier 재사용 (이미 ORCA 에 있음)
- VIX/momentum/breadth fetcher 구축
- Backfill: 기존 candidate_lessons 의 과거 데이터에 대해서도 snapshot 추정

**검증**:
- Snapshot 수집 성공률 >95%
- 모든 lesson 에 `context_snapshot_id` 존재

**가치**: 아직 활용 안 하지만 **데이터베이스 축적**. Phase 2/3 의 재료.

### Phase 2: Context Clustering + Quality Classification (2-3주)

**목표**: 수집된 snapshot 에서 의미 있는 구조 발견.

**작업**:
- Gower distance / clustering 알고리즘 구현
- Cluster 수 결정 (elbow method, silhouette score)
- 각 cluster 에 human-readable label 생성
- Lesson quality classifier (typical/outlier/edge_case)
- Cluster 별 performance profile 대시보드

**검증**:
- Cluster 10-20개, 각 >30 snapshots
- Silhouette score >0.3
- Cluster label 이 사람이 납득할 수 있는지 눈으로 검토

**가치**: **"우리 시스템이 어떤 상황에 강하고 약한지" 가시화**. 지금까지 모호했던 게 정량화됨.

### Phase 3: Historical Retrieval (2-3주)

**목표**: 현재 상황과 유사한 과거 상황 조회.

**작업**:
- Similarity metric 구현
- `find_similar_context()` 함수
- `lesson_archive` 테이블 + best-strategy 추출 로직
- 조회 UI/CLI (개발용)
- Claude prompt 에 historical context 주입

**검증**:
- Query 성능: 1초 이내 응답
- Sanity check: 동일 날짜 반복 query 시 안정성
- Manual review: "이 상황은 N월 N일과 유사함" 판단이 납득 가능한지

**가치**: **"이 상황 전에도 봤음"** 을 시스템이 말할 수 있게 됨. 의사결정 explainability 증가.

### Phase 4: Self-Correction (3-4주)

**목표**: 자가 적응 시스템 완성.

**작업**:
- Accuracy drop detector
- Diagnosis pipeline
- Temporary weight boost 메커니즘
- A/B test 구조
- `self_correction_log` 기록
- Rollback logic
- Alert/notification (Telegram)

**검증**:
- False positive rate <5%
- Correction 성공률 모니터링
- Paper trading 으로 2개월 이상 검증 후 라이브 적용

**가치**: **진짜 self-adaptive AI**. 성능 저하를 능동적으로 감지+대응.

---

## 7. Dependencies (선행 조건)

Wave F 착수 전에 완료 필요:

### 필수
- ✅ Wave A: Backtest learning spine (진행 중)
- ⏳ Wave D: Self-tracking system (Hunter/Scanner 알람 축적)
  - → Context snapshot 의 sample diversity 확보
- ⏳ Wave B: RS feature
  - → Signal 다양성 확보
- ⏳ Wave C: 52주 신고가 feature
  - → Signal 다양성 추가

### 선택 (있으면 좋음)
- Wave E: Workflow chain 안정화
- Probability layer 완성 (%% 노출 가능 수준)

**이유**: Meta-learning 은 base signal 과 sample 이 풍부해야 의미 있음. 부족한 상태에서 시작하면 통계적 신뢰도 낮음.

---

## 8. Implementation Strategy

### 8.1 Principle: Append-only & Non-breaking

기존 시스템 건드리지 않기. Layer 로 얹기.

- 기존 `candidate_lessons` 는 유지, column 추가만 함
- 기존 weight update 는 유지, override layer 만 추가
- 기존 workflow 는 유지, new workflow 로 분리

### 8.2 Feature flag

각 phase 는 환경 변수로 on/off:
```
WAVE_F_PHASE1_SNAPSHOT=true
WAVE_F_PHASE2_CLUSTERING=false
WAVE_F_PHASE3_RETRIEVAL=false
WAVE_F_PHASE4_SELF_CORRECTION=false
```

문제 시 즉시 비활성 가능.

### 8.3 Testing

각 phase 별:
- Unit test: 함수 단위 로직
- Integration test: 전체 flow
- Regression test: 기존 167+ tests 영향 없음
- **Shadow mode**: 새 기능이 실제 결정에 영향 주지 않는 상태로 1-2주 관찰

### 8.4 Rollback plan

각 phase 배포 후:
- Monitoring: accuracy, latency, error rate
- Rollback trigger: 이전 대비 10% 이상 악화 시 자동 비활성
- Rollback 절차: Feature flag off → next deployment 에서 코드 제거

---

## 9. Success Criteria

### Phase 1 성공 기준
- Snapshot 수집 성공률 >95%
- 기존 테스트 모두 통과
- DB schema migration 문제 없음

### Phase 2 성공 기준
- 10-20 cluster 형성
- Cluster 별 performance profile 가시화
- Silhouette score >0.3

### Phase 3 성공 기준
- Query 응답 <1초
- Top-k retrieval 의 relevance 인간 검토 통과
- Dashboard/CLI 로 조회 가능

### Phase 4 성공 기준
- Correction false positive <5%
- Correction 적용 후 평균 accuracy 개선 (통계적 유의)
- Rollback 메커니즘 정상 작동
- 2개월 paper trading 검증 통과

### 최종 성공 기준
- JACKAL 의 전체 swing accuracy 73% → 78%+ 향상
- Regime shift 구간에서의 성능 저하 폭 축소
- Self-correction 이 실제로 trigger 되어 효과 증명
- 사용자 (민우) 가 시스템 설명 가능성 증가 체감

---

## 10. Open Questions (더 생각할 것들)

논의 중 명확하지 않은 부분. Phase 2 이후 결정 필요:

### Q1. Cluster 의 granularity
- 너무 coarse: context-awareness 약함
- 너무 fine: 각 cluster 의 sample 부족
- → 동적으로 결정 (sample size 기준 adaptive)?

### Q2. Historical retrieval 의 recency weighting
- 5년 전 2020년 팬데믹 상황을 오늘 참조하는 게 맞나?
- 시간 감쇠 도입 (최근일수록 높은 가중치)?
- 아니면 "유사 상황이면 아무리 오래됐어도 가치 있다" 관점?

### Q3. Self-correction 의 권한 범위
- 전체 weight 를 override?
- 특정 family 만?
- 전체 JACKAL 결정?
- Claude 의 suggest 20 까지 영향?
- **보수적 시작**: 특정 family 의 weight 만 조정. 확장은 점진적.

### Q4. User feedback loop
- 사용자가 "이 correction 은 이상하다" 라고 개입할 수 있나?
- Manual override 인터페이스 필요?
- → Phase 4 에서 결정

### Q5. Regime 정의의 견고성
- 현재 regime 분류 (위험선호/혼조/위험회피/전환중) 가 정말 충분한가?
- 추가 dimension 필요? (예: 금리 상승기 vs 하락기)
- → Phase 2 cluster 분석 결과 보고 판단

---

## 11. Appendix: Current vs Future 비교

### Before (Wave A 완료 상태)

```
Signal 발생
  ↓
Candidate 기록
  ↓
Outcome 관찰 (1일, swing)
  ↓
candidate_lessons 에 기록
  ↓
weight update (family × regime 기준)
  ↓
다음 signal 발생 시 update 된 weight 적용
```

### After (Wave F 완료 상태)

```
Signal 발생
  ↓
[Layer 1] Context snapshot 캡처 (regime, vol, sector, breadth, events)
  ↓
Candidate 기록 (with snapshot_id)
  ↓
Outcome 관찰
  ↓
[Layer 2] Lesson 기록 + quality classification (typical/outlier/edge)
  ↓
[Layer 3] Lesson archive 에 반영 (cluster 별 best-strategy 업데이트)
  ↓
Weight update (기존 경로)
  ↓
[Layer 4] Accuracy drop 감지
  ↓ (drop 감지 시)
Historical retrieval (유사 과거 context)
  ↓
Temporary weight boost (historical best-strategy)
  ↓
A/B observation
  ↓
영구 반영 / neutral / rollback
```

---

## 12. Notes

### 이 문서의 위치

Phase 6 의 연장. Wave A/B/C/D/E 가 **base infrastructure** 라면 Wave F 는 **intelligence layer**.

### 철학

> "단순한 weight update 가 아닌, 경험으로부터 배우고 필요할 때 회상하고 스스로 수정하는 시스템."

이것은 **LLM 시대의 trading system 설계 방향**. Bayesian → Bayesian + Episodic + Meta.

### 영감

- Human trader 의 의사결정 방식 (경험 회상 + 현재 상황 비교)
- DeepMind 의 episodic memory 연구
- Reinforcement learning 의 experience replay

### 민우의 원 제안 (기록 보존)

> "jackal 이 교훈의 max수치에서 어떻게 작동중인지, 가졋던 교훈들의 현재 시장상태를 분석해서 어떤상태에서 어떤방식의 가산방식이 맞는지 판단하고, 그걸 따로 저장해둔뒤, 만약 정답률이 너무떨어지는 상황을 마딱들이면, 그상황에대해 지난 저장해둔정보들을 대조해보고 다시금 정답에 가까워지는 학습을 진행했으면 좋겠는데"
>
> "지금은 왠지 저장된 학습교훈이 너무 무방비하게 저장되는것같고, 조금더 저장된 데이터들의 분기. 판단. 질을 높히기위한 변화가 필요하다고 생각해"

→ 이 문제 의식이 Wave F 의 **motivation** 이자 **북극성**.

---

**End of Wave F Meta-Learning Design Document**
