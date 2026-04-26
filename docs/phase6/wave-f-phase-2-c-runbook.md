# Wave F Phase 2-C Runbook: Clustering CLI and Workflow

## 목적

Wave F Phase 2-C 는 Phase 2-B 의 clustering algorithm 을 실제로 실행할 수 있는 운영 레이어를 추가한다.

이번 단계의 산출물:

- `scripts/build_lesson_clusters.py`: 로컬/Actions 공용 CLI
- `.github/workflows/wave_f_clustering.yml`: manual workflow
- dry-run default
- execute 전 자동 DB backup
- strict verification
- DB commit/push workflow

Phase 2-C 를 실행하면 252 context snapshots 가 8 clusters 로 묶이고, 1260 lessons 는 cluster 별로 retrieval 가능한 상태가 된다.

## CLI

Dry-run 이 기본이다.

```powershell
python scripts/build_lesson_clusters.py --verbose
```

실제 DB 저장:

```powershell
python scripts/build_lesson_clusters.py --execute --n-clusters 8 --verbose
```

기존 clustering run 이 있는 경우 안전하게 멈춘다. 재생성하려면 명시적으로 `--force-rebuild` 를 사용한다.

```powershell
python scripts/build_lesson_clusters.py --execute --force-rebuild --n-clusters 8 --verbose
```

주요 옵션:

- `--n-clusters`: cluster 수, 기본 `8`
- `--random-seed`: K-means seed, 기본 `42`
- `--max-iter`: K-means 최대 반복, 기본 `100`
- `--min-cluster-size`: small cluster warning 기준, 기본 `5`
- `--dry-run`: DB write 없음, 기본 모드
- `--execute`: DB write 수행
- `--force-rebuild`: 기존 clustering data 삭제 후 재생성
- `--no-backup`: 자동 backup 생략
- `--expected-snapshots`: 최소 snapshot assignment 수 검증
- `--expected-linked-lessons`: cluster mapping 으로 도달 가능한 lesson 수 검증
- `--min-silhouette`: 최소 silhouette 기준, 기본 `0.15`

## Backup

`--execute` 실행 시 자동으로 다음 형식의 backup 을 만든다.

```text
data/orca_state.db.backup-pre-clustering-{timestamp}
```

`--no-backup` 을 명시하면 backup 을 생략할 수 있지만 권장하지 않는다.

## 결과 해석

CLI 출력의 핵심 항목:

- `silhouette_score`: cluster 분리 품질. Phase 2.0 기준으로 `0.15` 이상이면 초기 운영 가능.
- `within_cluster_variance`: cluster 내부 분산. 낮을수록 응집도가 높다.
- `size`: cluster 에 속한 snapshot 수.
- `representative_snapshot_id`: centroid 에 가장 가까운 대표 snapshot.
- `cluster_label`: 사람이 읽기 쉬운 label. 예: `low_vix_bullish_growth`, `high_vix_bearish_riskoff_defensive`.
- `common_sectors`: 해당 cluster 에서 자주 나타난 dominant sectors.

Phase 2-B dry-run 기준:

- silhouette: 약 `0.1564`
- cluster size: `[82, 28, 9, 47, 23, 21, 7, 35]`
- small clusters: 없음

## GitHub Actions

Workflow:

```text
.github/workflows/wave_f_clustering.yml
```

Actions 탭에서 `Wave F Clustering` 을 수동 실행한다.

Inputs:

- `dry_run`: 기본 `true`
- `n_clusters`: 기본 `8`
- `force_rebuild`: 기본 `false`

권장 절차:

1. `dry_run=true`, `n_clusters=8`, `force_rebuild=false` 로 먼저 실행한다.
2. 로그에서 silhouette score, cluster size, representative snapshots 를 확인한다.
3. 첫 실제 실행이면 `dry_run=false`, `force_rebuild=false` 로 실행한다.
4. 기존 run 을 교체하려면 `dry_run=false`, `force_rebuild=true` 로 실행한다.
5. Strict verify 통과 후 `data/orca_state.db` 가 자동 commit/push 된다.

## Strict Verify

Workflow 와 CLI 는 다음을 확인한다.

- cluster count 가 `n_clusters` 와 일치
- snapshot mappings 가 기대치 이상
- `context_cluster_id` cache 가 채워짐
- linked lessons 가 cluster mapping 으로 조회 가능
- silhouette score 가 최소 기준 이상

기본 기대값:

- snapshots: `252`
- linked lessons: `1260`
- clusters: `8`
- minimum silhouette: `0.15`

검증 실패 시 workflow 는 commit 하지 않는다.

## Rollback

잘못된 clustering data 가 commit 된 경우 두 가지 방법이 있다.

- Git rollback: 해당 DB commit 을 `git revert` 한다.
- Rebuild: `force_rebuild=true` 로 workflow 를 재실행한다.

로컬 실행에서 문제가 생기면 자동 생성된 backup 파일로 `data/orca_state.db` 를 복원한다.

## Verification SQL

```powershell
@'
import sqlite3

conn = sqlite3.connect("data/orca_state.db")
print("clusters:", conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0])
print("mappings:", conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0])
print("cached:", conn.execute("SELECT COUNT(*) FROM lesson_context_snapshot WHERE context_cluster_id IS NOT NULL").fetchone()[0])
print("clustered lessons:", conn.execute("""
    SELECT COUNT(*)
    FROM candidate_lessons l
    JOIN snapshot_cluster_mapping m
      ON m.snapshot_id = l.context_snapshot_id
""").fetchone()[0])
conn.close()
'@ | python -
```

Expected after production run:

- `lesson_clusters`: `8`
- `snapshot_cluster_mapping`: `252`
- `context_cluster_id NOT NULL`: `252`
- clustered lessons: `1260`

## Phase 2 완료 의미

Phase 2 완료 후:

- 252 snapshots -> 8 clusters
- 1260 lessons -> cluster 별 grouping
- 새 candidate 가 들어오면 유사 market context cluster 를 찾을 수 있음
- Phase 3 retrieval 의 기반이 준비됨

Phase 3 에서는 다음을 붙인다.

- 새 candidate 분석 시 snapshot 생성
- `find_nearest_cluster()` 로 cluster lookup
- cluster 내 Top-K historical lessons retrieval
- JACKAL 추천에 historical context 반영

이 단계부터 lesson 이 단순 저장물이 아니라, 시장 상황별로 다시 꺼내 쓸 수 있는 intelligence layer 가 된다.
