# Wave F Phase 2-B Runbook: Context Clustering Algorithm

## 목적

Wave F Phase 2-B 는 `lesson_context_snapshot` 데이터를 cluster 로 묶는 알고리즘 코드를 추가한다. 실제 DB 에 clustering 결과를 쓰는 운영 실행은 STEP 2-C 에서 CLI/workflow 로 진행한다.

이번 단계의 산출물은 다음과 같다.

- `orca/lesson_clustering.py`: numpy-only K-means clustering engine
- 19차원 feature engineering: numerical 5개 + regime one-hot 3개 + sector multi-hot 11개
- k-means++ initialization
- manual silhouette score
- nearest cluster lookup API
- dry-run 기반 검증

## Algorithm

Phase 2-B 의 기본 알고리즘은 numpy-only K-means 이다. sklearn/scipy 의존성을 추가하지 않고, GitHub Actions 와 로컬 환경에서 동일하게 실행되도록 설계했다.

기본 파라미터:

- `n_clusters=8`
- `random_seed=42`
- `max_iter=100`
- `min_cluster_size=5`
- `dry_run=True`

`dry_run=True` 가 기본값인 이유는 Phase 2-B 가 code-only 단계이기 때문이다. DB 저장은 STEP 2-C 의 명시적 실행 경로에서 수행한다.

## Feature Engineering

Feature vector 는 총 19차원이다.

- Numerical: `vix_level`, `sp500_momentum_5d`, `sp500_momentum_20d`, `nasdaq_momentum_5d`, `nasdaq_momentum_20d`
- Regime one-hot: `위험회피`, `전환중`, `위험선호`
- Sector multi-hot: Communication Services, Consumer Discretionary, Consumer Staples, Energy, Financials, Healthcare, Industrials, Materials, Real Estate, Technology, Utilities

Numerical feature 는 z-score 로 표준화한다. 표준편차가 0 인 컬럼은 division-by-zero 를 피하기 위해 std 를 1 로 대체한다.

`dominant_sectors='[]'` 인 snapshot 은 sector feature 가 all-zero 로 처리된다. Phase 1.3 결과에서 sector 가 비어 있는 4 dates 를 drop 하지 않고 유지하기 위한 선택이다.

## Public API

```python
from orca.lesson_clustering import build_clusters

result = build_clusters(n_clusters=8, dry_run=True, random_seed=42)
print(result["silhouette_score"])
print([cluster["size"] for cluster in result["cluster_summary"]])
```

주요 함수:

- `build_clusters(...)`: snapshot feature 를 로드하고 K-means clustering 을 수행한다.
- `get_cluster_for_snapshot(snapshot_id, conn=None)`: `context_cluster_id` cache 에서 snapshot 의 cluster 를 조회한다.
- `get_lessons_in_cluster(cluster_id, conn=None)`: 해당 cluster 에 속한 lesson 들을 조회한다.
- `find_nearest_cluster(snapshot_features, conn=None, run_id=None)`: 신규 snapshot feature 에 가장 가까운 cluster 를 찾는다.
- `calculate_silhouette_score(features, labels)`: numpy-only silhouette score 를 계산한다.

## Quality Metrics

`build_clusters()` 는 다음 지표를 반환한다.

- `silhouette_score`: 전체 평균 silhouette score
- `within_cluster_variance`: cluster 내부 평균 분산
- `cluster_summary`: cluster 별 size, label, centroid, representative snapshot, common sectors
- `small_clusters`: `min_cluster_size` 미만 cluster 목록
- `snapshot_assignments`: `snapshot_id -> cluster_id`

Silhouette score 의 해석:

- `> 0.50`: 잘 분리된 synthetic data 수준
- `0.15 ~ 0.30`: 실제 시장 regime 데이터에서 수용 가능한 초기 품질
- `< 0.00`: cluster assignment 재검토 필요

STEP 1 분석 기준으로 실제 252 snapshots 의 k=8 silhouette target 은 약 `0.21` 이다.

## DB 저장

`dry_run=False` 로 호출하면 Phase 2-A schema 에 결과를 저장한다.

- `lesson_clusters`
- `snapshot_cluster_mapping`
- `lesson_context_snapshot.context_cluster_id`

단, STEP 2-B 에서는 운영 실행을 하지 않는다. 저장 경로는 테스트와 STEP 2-C CLI 를 위한 준비 코드다.

## Safety

이번 단계는 새 모듈 추가가 중심이며 기존 Wave A/F 데이터는 변경하지 않는다.

- 1260 lessons 보존
- 252 snapshots 보존
- 기본 dry-run 으로 DB write 방지
- random seed 고정으로 재현성 확보
- 새 외부 dependency 없음

## Verification

타깃 테스트:

```powershell
python -m unittest tests.test_lesson_clustering_algorithm
```

Schema regression 포함:

```powershell
python -m unittest tests.test_lesson_clustering_algorithm tests.test_lesson_clustering_schema
```

전체 회귀:

```powershell
python -m unittest discover -s tests
```

실제 DB dry-run:

```powershell
@'
from orca.lesson_clustering import build_clusters

result = build_clusters(n_clusters=8, dry_run=True, random_seed=42)
print("silhouette:", result["silhouette_score"])
print("sizes:", [c["size"] for c in result["cluster_summary"]])
print("labels:", [c["cluster_label"] for c in result["cluster_summary"]])
print("representatives:", [c["representative_snapshot_id"] for c in result["cluster_summary"]])
'@ | python -
```

DB unchanged check:

```powershell
@'
import sqlite3

conn = sqlite3.connect("data/orca_state.db")
print("clusters:", conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0])
print("mappings:", conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0])
print("cached:", conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot WHERE context_cluster_id IS NOT NULL").fetchone()[0])
conn.close()
'@ | python -
```

Expected after STEP 2-B, before STEP 2-C:

- `lesson_clusters`: 0
- `snapshot_cluster_mapping`: 0
- `context_cluster_id NOT NULL`: 0

## Next

STEP 2-C will add the execution layer.

- `scripts/build_lesson_clusters.py`
- `.github/workflows/wave_f_clustering.yml`
- dry-run / force rebuild / DB commit flow
- first production clustering run: 252 snapshots -> 8 clusters

Phase 3 will use `find_nearest_cluster()` and `get_lessons_in_cluster()` for retrieval.
