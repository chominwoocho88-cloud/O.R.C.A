# Wave F Phase 2-A Runbook: Context Clustering Schema

## 목적

Wave F Phase 2-A 는 clustering 알고리즘을 실행하지 않고, 결과를 저장할 DB schema 만 준비한다.

이번 단계에서 추가되는 것은 다음 세 가지다.

- `lesson_clusters`: cluster summary, centroid, quality metrics, run metadata 저장
- `snapshot_cluster_mapping`: snapshot 과 cluster 의 run별 assignment 저장
- `lesson_context_snapshot.context_cluster_id`: 최신 active clustering run 의 denormalized lookup cache

## Schema

### `lesson_clusters`

Cluster 단위 summary row 를 저장한다.

- `cluster_id`: primary key
- `cluster_label`: 사람이 읽을 수 있는 label
- `size`: cluster 에 속한 snapshot 수
- `representative_snapshot_id`: centroid 에 가장 가까운 대표 snapshot
- `centroid_*`: VIX/momentum 중심값
- `dominant_regime`, `common_sectors`: categorical mode/summary
- `silhouette_score`, `within_variance`: quality metrics
- `avg_outcome_score`, `win_rate`, `sample_count`: Phase 3 performance profile placeholder
- `algorithm`, `n_clusters_total`, `random_seed`, `run_id`: rebuild provenance

### `snapshot_cluster_mapping`

같은 snapshot 이 다른 clustering run 에서 다른 cluster 에 배정될 수 있도록 `(snapshot_id, run_id)` 를 primary key 로 둔다.

### `context_cluster_id`

`lesson_context_snapshot` 에 nullable cache column 을 추가한다.

- clustering 실행 전: `NULL`
- clustering 실행 후: 최신 active run 의 `cluster_id`
- 새 live snapshot 생성 시: `NULL`
- 다음 clustering run 에서 다시 채워짐

## CRUD Helpers

`orca.state` 에 다음 helper 가 추가되었다.

- `record_lesson_cluster(conn, cluster_data)`
- `assign_snapshot_to_cluster(conn, snapshot_id, cluster_id, distance, run_id)`
- `get_cluster_by_id(conn, cluster_id)`
- `get_active_clusters(conn, run_id=None)`
- `get_snapshots_in_cluster(conn, cluster_id)`
- `get_lessons_in_cluster(conn, cluster_id)`
- `get_latest_run_id(conn)`
- `clear_clustering_data(conn, run_id=None)`

모든 helper 는 기존 data 를 변경하지 않고 clustering 관련 테이블과 cache column 만 다룬다.

## Safety

Phase 2-A 는 기존 Wave A/F 데이터를 건드리지 않는다.

- 1260 existing lessons 유지
- 252 context snapshots 유지
- clustering 실행 전 `lesson_clusters` 는 비어 있음
- clustering 실행 전 `context_cluster_id` 는 `NULL`

`clear_clustering_data(conn, run_id=None)` 는 cluster/mapping/cache 만 지운다. `candidate_lessons` 와 `lesson_context_snapshot` 원본 row 는 삭제하지 않는다.

## Verification

```powershell
python -m unittest tests.test_lesson_clustering_schema
python -m unittest discover -s tests
```

로컬 DB sanity check:

```powershell
@'
import sqlite3
conn = sqlite3.connect('data/orca_state.db')
print(conn.execute('SELECT COUNT(*) FROM lesson_context_snapshot').fetchone()[0])
print(conn.execute('SELECT COUNT(*) FROM candidate_lessons').fetchone()[0])
print(conn.execute('SELECT COUNT(*) FROM lesson_clusters').fetchone()[0])
print(conn.execute('SELECT COUNT(*) FROM snapshot_cluster_mapping').fetchone()[0])
print(conn.execute('SELECT COUNT(*) FROM lesson_context_snapshot WHERE context_cluster_id IS NOT NULL').fetchone()[0])
'@ | python -
```

Expected before STEP 2-B:

- snapshots: `252`
- lessons: `1260`
- clusters: `0`
- mappings: `0`
- snapshots with `context_cluster_id`: `0`

## Next

STEP 2-B will add `orca/lesson_clustering.py`.

Initial recommendation:

- algorithm: numpy-only KMeans
- default `n_clusters=8`
- feature set: z-scored VIX/momentum + regime one-hot + sector multi-hot
- quality metric: manual silhouette and within-cluster variance

STEP 2-C will add CLI/workflow execution.
