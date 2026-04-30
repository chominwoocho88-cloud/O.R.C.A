# 3년 Backtest Expansion Runbook

Wave A 1년 bootstrap을 보존하면서 ORCA/JACKAL backtest 범위를 3년으로 확장하기 위한 운영 절차입니다. 이 문서는 Phase 6 P16 STEP 2-A에서 추가한 코드 인프라와 이후 실행 순서를 정리합니다.

## 목적

- 기존 1260 backtest lessons와 252 context snapshots를 보존합니다.
- 추가 504 trading days를 materialize해서 총 756 trading days, 약 3869 lessons로 확장합니다.
- Wave F backfill, clustering, lesson_archive를 append 방식으로 재실행해 기존 run_id를 보존합니다.
- GitHub Actions 6시간 제한을 피하기 위해 ORCA research artifact와 JACKAL materialization을 분리할 수 있게 합니다.

## 기본 원칙

- 기본값은 모두 기존 운영값을 유지합니다.
- 추가 실행은 `add_missing`과 `append`를 우선 사용합니다.
- 대량 materialization에서는 `auto_context_snapshot=false`를 사용하고, context는 Wave F backfill에서 일괄 연결합니다.
- 실제 DB 변경 workflow는 dry-run 또는 artifact 검증 후 실행합니다.

## 새 설정값

| 영역 | 설정 | 기본값 | 3년 확장 권장값 |
| --- | --- | --- | --- |
| ORCA Backtest | `months` | `13` | `36` |
| JACKAL Backtest | `JACKAL_BACKTEST_DAYS` / `--backtest-days` | `252` | `756` |
| JACKAL History | `JACKAL_HISTORY_DAYS` / `--history-days` | `750` | `1200` |
| JACKAL Materialize | `--materialize-mode` | `replace` | `add_missing` |
| Context hook | `--auto-context-snapshot` | `true` | `false` |
| Unified fetch | `USE_UNIFIED_FETCH` | `1` | `1` |
| Alpha Vantage pacing | `ALPHA_VANTAGE_SLEEP_SECONDS` | `0.8` in workflows | `0.8` |
| Wave F Backfill | `expected_snapshots` | `252` | `757` |
| Wave F Backfill | `expected_linked_lessons` | `1260` | `3869` |
| Wave F Clustering | `append_mode` | `false` | `true` |
| Wave F Archive | `append_mode` | `false` | `true` |

## STEP 2-A: 코드 준비

완료 범위:

- `jackal/backtest.py`
  - `JACKAL_BACKTEST_DAYS`로 `BACKTEST_DAYS` override 가능
  - `JACKAL_HISTORY_DAYS`로 universe price history range override 가능
  - CLI 옵션 `--backtest-days`, `--history-days`, `--materialize-mode`, `--auto-context-snapshot` 추가
  - 기본값은 252 days, 750 history days, replace, auto snapshot true

- `jackal/backtest_materialization.py`
  - `materialize_mode='replace'|'add_missing'|'fail_on_duplicate'`
  - `add_missing`은 기존 `candidate|jackal|backtest|jackal-backtest:{date}:{ticker}`를 발견하면 skip
  - `fail_on_duplicate`은 중복 발견 시 즉시 실패
  - `auto_context_snapshot=False`면 `record_backtest_lesson()` live hook을 끄고 `context_snapshot_id=NULL`로 저장

- Workflows
  - `orca_backtest.yml`: `months`, `walk_forward` 입력 추가
  - `jackal_backtest_learning.yml`: 3년 확장 입력 추가
  - `wave_f_backfill.yml`: expected count 입력 동적화
  - `wave_f_clustering.yml`: expected count, min silhouette, append mode 입력 추가
  - `wave_f_archive.yml`: expected archive count, append mode 입력 추가

- Scripts
  - `scripts/build_lesson_clusters.py --append`
  - `scripts/build_lesson_archive.py --append`
  - `--force-rebuild`와 `--append`는 상호 배타적입니다.

## STEP 2-B: ORCA 36개월 Research Session

권장 실행:

```bash
python -m orca.backtest --months 36 --walk-forward --fail-on-empty-dynamic-fetch
```

GitHub Actions:

- Workflow: `ORCA Backtest`
- Inputs:
  - `run_mode=live_backtest`
  - `months=36`
  - `walk_forward=true`

Node/action and artifact handoff verification should use `run_mode=artifact_verify_only` instead. That mode verifies the committed 3-year DB and uploads `research-state-${run_id}` without live LLM calls.

산출물:

- `research-state-${run_id}` artifact
- `data/orca_state.db` 안에 36개월 ORCA backtest session

주의:

- 이 workflow는 artifact-only 연구 workflow입니다.
- DB를 직접 commit하지 않습니다.
- JACKAL Learning에서 artifact handoff로 받아 materialize하는 흐름이 안전합니다.

## STEP 2-C: JACKAL add-missing Materialization

권장 실행:

```bash
python -m jackal.backtest \
  --mode full \
  --backtest-days 756 \
  --history-days 1200 \
  --materialize-mode add_missing \
  --auto-context-snapshot false
```

GitHub Actions:

- Workflow: `JACKAL Backtest Learning`
- Inputs:
  - `mode=full`
  - `artifact_run_id=<ORCA Backtest run id>`
  - `backtest_days=756`
  - `history_days=1200`
  - `materialize_mode=add_missing`
  - `auto_context_snapshot=false`

기대 결과:

- 기존 1260 lessons 보존
- 추가 missing dates만 materialize
- 새 lessons는 일단 `context_snapshot_id=NULL`
- 후속 Wave F backfill에서 context 연결

검증 SQL:

```sql
SELECT COUNT(*) FROM candidate_registry WHERE source_event_type='backtest';
SELECT COUNT(*) FROM candidate_lessons;
SELECT COUNT(DISTINCT analysis_date)
FROM candidate_registry
WHERE source_event_type='backtest';
SELECT COUNT(*)
FROM candidate_lessons
WHERE context_snapshot_id IS NULL;
```

목표:

- `candidate_lessons` 약 3869
- distinct `analysis_date` 약 756
- 새 lessons 일부는 context NULL일 수 있음

## STEP 2-D: Wave F Backfill 확장

권장 입력:

- `dry_run=false`
- `skip_existing=true`
- `expected_snapshots=757`
- `expected_linked_lessons=3869`
- `confirm_apply=APPLY_WAVE_F`

동작:

- 기존 252 snapshots는 보존합니다.
- 새 trading dates에 대해서만 `backtest_backfill` snapshot을 생성합니다.
- NULL context lessons를 새 snapshot에 연결합니다.

검증:

```sql
SELECT COUNT(*) FROM lesson_context_snapshot WHERE source_event_type='backtest_backfill';
SELECT COUNT(*)
FROM candidate_lessons l
JOIN candidate_registry c ON c.candidate_id = l.candidate_id
WHERE c.source_event_type='backtest'
  AND l.context_snapshot_id IS NOT NULL;
```

## STEP 2-E: Re-clustering / Archive Append

Clustering 권장 입력:

- `dry_run=false`
- `n_clusters=8`
- `append_mode=true`
- `expected_snapshots=757`
- `expected_linked_lessons=3869`
- `min_silhouette=0.11`부터 시작 후 결과 확인
- `confirm_apply=APPLY_WAVE_F`

CLI:

```bash
python scripts/build_lesson_clusters.py \
  --execute \
  --append \
  --n-clusters 8 \
  --expected-snapshots 757 \
  --expected-linked-lessons 3869 \
  --min-silhouette 0.11 \
  --verbose
```

Archive 권장 입력:

- `dry_run=false`
- `append_mode=true`
- `expected_archive_count=3869`
- `confirm_apply=APPLY_WAVE_F`

CLI:

```bash
python scripts/build_lesson_archive.py \
  --execute \
  --append \
  --expected-lessons 3869 \
  --verbose
```

Append의 의미:

- 기존 8-cluster run과 1260 archive run은 삭제하지 않습니다.
- 새 run_id가 생성됩니다.
- retrieval은 기본적으로 latest run을 사용합니다.
- 문제가 생기면 latest run만 제거하거나 git revert로 되돌릴 수 있습니다.

## STEP 2-F: 최종 검증

목표 수치:

- `candidate_lessons`: 약 3869
- `candidate_registry(backtest)`: 약 3869
- `lesson_context_snapshot(backtest_backfill)`: 약 756
- latest clustering run mappings: 약 757
- latest archive run rows: 3869

검증 SQL:

```sql
SELECT COUNT(*) FROM candidate_lessons;
SELECT COUNT(DISTINCT analysis_date)
FROM candidate_registry
WHERE source_event_type='backtest';
SELECT COUNT(*)
FROM lesson_context_snapshot
WHERE source_event_type='backtest_backfill';
SELECT run_id, COUNT(*)
FROM snapshot_cluster_mapping
GROUP BY run_id
ORDER BY run_id DESC;
SELECT run_id, COUNT(*)
FROM lesson_archive
GROUP BY run_id
ORDER BY run_id DESC;
```

테스트:

```bash
python -m unittest
```

## GitHub Actions 6시간 제한 대응

위험:

- ORCA 36개월 session + JACKAL materialization + Wave F backfill을 한 workflow에 묶으면 6시간 제한에 걸릴 수 있습니다.
- Alpha Vantage fallback이 대량 발생하면 시간이 늘어납니다.

완화:

- ORCA Backtest는 artifact-only로 먼저 실행합니다.
- JACKAL Learning은 artifact handoff로 DB를 받아 materialize합니다.
- `auto_context_snapshot=false`로 live snapshot fetch를 끕니다.
- Wave F backfill은 별도 workflow에서 range/batch 경로로 실행합니다.
- Clustering/archive는 append workflow로 분리합니다.

## Rollback

안전 rollback 순서:

1. 문제가 있는 workflow run의 DB commit을 git revert합니다.
2. append로 생성한 latest clustering/archive run만 제거하려면 DB helper를 사용합니다.
3. `materialize_mode=add_missing`으로 기존 1260 lessons는 보존되므로 기존 retrieval은 계속 동작합니다.

강한 rollback:

```bash
git revert <db-commit>
```

부분 DB rollback 예시:

```python
from orca import state

state.init_state_db()
conn = state._connect_orca()
latest_cluster_run = state.get_latest_run_id(conn)
latest_archive_run = state.get_latest_archive_run_id(conn)
state.clear_clustering_data(conn, run_id=latest_cluster_run)
state.clear_lesson_archive(conn, run_id=latest_archive_run)
conn.commit()
conn.close()
```

## 권장 실행 순서

1. ORCA Backtest workflow: `run_mode=live_backtest`, `months=36`
2. JACKAL Backtest Learning workflow: artifact handoff + `add_missing` + `auto_context_snapshot=false`
3. Wave F Backfill workflow: `expected_snapshots=757`, `expected_linked_lessons=3869`, `confirm_apply=APPLY_WAVE_F`
4. Wave F Clustering workflow: `append_mode=true`, `n_clusters=8`, `expected_snapshots=757`, `expected_linked_lessons=3869`, `confirm_apply=APPLY_WAVE_F`
5. Wave F Archive workflow: `append_mode=true`, `expected_archive_count=3869`, `confirm_apply=APPLY_WAVE_F`
6. 전체 tests와 retrieval smoke test

## 다음 단계

3년 확장 후에는 Wave F Phase 4 self-correction으로 넘어갑니다.

- retrieval accuracy 측정
- cluster별 성능 비교
- observe vs adjust A/B test
- weak cluster rebalancing
