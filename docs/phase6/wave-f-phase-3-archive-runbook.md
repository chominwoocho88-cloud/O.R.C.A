# Wave F Phase 3 - Lesson Archive Runbook

## 목적

Wave F Phase 3 STEP 2-B+C-A 는 retrieval 이 사용할 수 있는 `lesson_archive` 를 만든다.

Phase 3 STEP 2-A 의 read-only retrieval 은 cluster 안의 lesson 을 직접 읽고 percentile 기반 quality 를 계산했다. 이번 단계는 그 quality 를 더 정교하게 계산해서 DB 에 denormalize 한다.

- 입력: `lesson_clusters`, `snapshot_cluster_mapping`, `lesson_context_snapshot`, `candidate_lessons`
- 출력: `lesson_archive`
- 기본 실행: dry-run
- 기존 lesson/snapshot/cluster 데이터는 수정하지 않음

## Schema

`lesson_archive` 는 lesson 별 quality 를 저장한다.

주요 컬럼:

- `archive_id`: archive row id
- `lesson_id`: `candidate_lessons` 의 lesson id
- `cluster_id`: lesson 이 속한 context cluster
- `run_id`: archive build run identifier
- `quality_tier`: `high`, `medium`, `low`
- `quality_score`: 0.0-1.0 composite score
- `outcome_percentile`: outcome rank score
- `win_score`: win/loss score
- `speed_score`: peak 도달 속도 score
- `signal_score`: signal family reliability score
- `cluster_fit_score`: centroid 근접도 score
- `lesson_value`, `peak_pct`, `peak_day`, `signal_family`, `ticker`, `analysis_date`: retrieval 속도를 위한 denormalized fields

인덱스:

- `idx_archive_cluster_quality`
- `idx_archive_lesson_id`
- `idx_archive_run_id`

## Quality Scoring

Composite weight:

- `outcome_percentile`: 0.40
- `win_score`: 0.25
- `speed_score`: 0.15
- `signal_score`: 0.10
- `cluster_fit_score`: 0.10

Tier:

- `high`: `quality_score > 0.67`
- `medium`: `0.33 < quality_score <= 0.67`
- `low`: `quality_score <= 0.33`

`outcome_percentile` 은 raw value 를 직접 쓰지 않는다. `63.06` 같은 outlier 가 있어도 rank percentile 로 처리해서 한 lesson 이 score scale 전체를 망가뜨리지 않게 한다.

## CLI

Dry-run:

```bash
python scripts/build_lesson_archive.py --dry-run --expected-lessons 3874 --verbose
```

Execute:

```bash
python scripts/build_lesson_archive.py --execute --append --expected-lessons 3874 --verbose
```

특정 cluster run 을 지정하려면:

```bash
python scripts/build_lesson_archive.py --execute --cluster-run-id <run_id> --force-rebuild
```

옵션:

- `--dry-run`: DB write 없음. 기본값.
- `--execute`: `lesson_archive` 에 write.
- `--force-rebuild`: 기존 archive rows 삭제 후 재생성.
- `--cluster-run-id`: 특정 clustering run 사용. 생략 시 latest run.
- `--no-backup`: execute 시 자동 backup 생략.
- `--expected-lessons`: strict verify 용 예상 archive row 수.

## GitHub Actions

Workflow: `.github/workflows/wave_f_archive.yml`

입력:

- `dry_run`: 기본 `true`
- `cluster_run_id`: 비우면 latest cluster run
- `force_rebuild`: 기본 `false`
- `confirm_apply`: `dry_run=false`일 때 `APPLY_WAVE_F` 입력

권장 실행 순서:

1. `dry_run=true` 로 먼저 실행한다.
2. archive count, tier distribution, average quality 를 확인한다.
3. `dry_run=false`, `append_mode=true`, `force_rebuild=false`, `confirm_apply=APPLY_WAVE_F` 로 실제 실행한다.
4. Strict verify 가 `3874` archive rows 를 확인한 뒤에만 DB commit/push 된다.

## Retrieval 연동

`orca.lesson_retrieval` 은 `lesson_archive` 가 있으면 latest archive run 의 `quality_score` 와 `quality_tier` 를 사용한다.

Archive 가 없으면 기존 Phase 3 STEP 2-A 방식대로 lesson_value percentile 기반 fallback 을 사용한다.

즉, archive build 전에도 retrieval 은 동작하고, archive build 후에는 더 정교한 quality 를 자동 활용한다.

## Rollback

가장 안전한 rollback:

```bash
python scripts/build_lesson_archive.py --execute --append --expected-lessons 3874
```

Archive 만 제거하려면 Python 에서:

```python
from orca import state

state.init_state_db()
conn = state._connect_orca()
state.clear_lesson_archive(conn)
conn.commit()
conn.close()
```

DB commit 후 되돌릴 필요가 있으면 `git revert` 로 `data/orca_state.db` 변경 commit 을 되돌린다.

## 다음 단계

STEP 2-B+C-B 는 JACKAL Hunter 통합이다.

계획:

- `USE_HISTORICAL_CONTEXT=1` 기본
- `HISTORICAL_CONTEXT_MODE=observe|adjust`
- 첫 통합은 `observe` 권장
- `_stage4_full_analysis()` 에서 `apply_probability_adjustment()` 직후 historical context 를 붙인다.
