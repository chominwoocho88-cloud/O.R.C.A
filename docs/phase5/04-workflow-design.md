# Phase 5-D-a: Workflow Preservation Design

Date: `2026-04-22`  
Scope decision: `Path B` workflow design only  
Implementation status: `design only`  
Related documents:
- [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md)
- [02-path-decision.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/02-path-decision.md)
- [03-design.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/03-design.md)
- [orca_v2_backlog.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/orca_v2_backlog.md)

## Section 1: 4 workflow 현재 구조 인벤토리

### 1.1. `orca_daily.yml`

File:
- [orca_daily.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_daily.yml)

총 줄 수:
- `163`

Trigger:
- `schedule`
  - `30 23 * * 0-4`
  - `0 14 * * 1-5`
  - `0 22 * * 6`
  - `0 21 1 * *`
- `workflow_dispatch`
  - input: `mode`

Concurrency:
- lines `3-5`
- `group: orca-repo-state`
- `cancel-in-progress: false`

Step 목록:
- lines `30-31`: `Checkout`
- lines `33-37`: `Setup Python`
- lines `39-40`: `Install dependencies`
- lines `42-63`: `MORNING Report`
- lines `65-86`: `EVENING Report`
- lines `88-102`: `WEEKLY Report`
- lines `104-124`: `MONTHLY Report`
- lines `126-163`: `Save ORCA state`

DB 접근 맵:
- `data/orca_state.db`
  - checkpoint: lines `131-139`
  - commit 대상: line `154`
- `data/jackal_state.db`
  - 현재 접근 없음
- 다른 보존 대상:
  - `data/memory.json`
  - `data/memory_archive.json`
  - `data/accuracy.json`
  - `data/orca_weights.json`
  - `data/orca_lessons.json`
  - `data/orca_cost.json`
  - `data/morning_baseline.json`
  - `data/orca_market_data.json`
  - `data/breaking_sent.json`
  - `data/sentiment.json`
  - `data/rotation.json`
  - `data/portfolio.json`
  - `data/jackal_news.json`
  - `reports/`

DB 관련 step 실제 인용:

```yaml
      - name: Save ORCA state
        run: |
          git config user.name "ORCA Bot"
          git config user.email "orca@github-actions"

          python - <<'PY'
          import sqlite3
          from pathlib import Path
          db = Path("data/orca_state.db")
          if db.exists():
              conn = sqlite3.connect(db)
              conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
              conn.close()
          PY

          git add data/memory.json 2>/dev/null || true
          git add data/memory_archive.json 2>/dev/null || true
          git add data/accuracy.json 2>/dev/null || true
          git add data/orca_weights.json 2>/dev/null || true
          git add data/orca_lessons.json 2>/dev/null || true
          git add data/orca_cost.json 2>/dev/null || true
          git add data/morning_baseline.json 2>/dev/null || true
          git add data/orca_market_data.json 2>/dev/null || true
          git add data/breaking_sent.json 2>/dev/null || true
          git add data/sentiment.json 2>/dev/null || true
          git add data/rotation.json 2>/dev/null || true
          git add data/portfolio.json 2>/dev/null || true
          git add data/jackal_news.json 2>/dev/null || true
          git add -f data/orca_state.db 2>/dev/null || true
          git add reports/ 2>/dev/null || true
          git diff --cached --quiet && exit 0

          git commit -m "ORCA: $(date +'%Y-%m-%d %H:%M') [${ORCA_MODE:-AUTO}] update"

          git push || {
            git pull --rebase origin main || git rebase --abort
            git push
          }
```

git add 대상 파일 목록:
- `data/memory.json`
- `data/memory_archive.json`
- `data/accuracy.json`
- `data/orca_weights.json`
- `data/orca_lessons.json`
- `data/orca_cost.json`
- `data/morning_baseline.json`
- `data/orca_market_data.json`
- `data/breaking_sent.json`
- `data/sentiment.json`
- `data/rotation.json`
- `data/portfolio.json`
- `data/jackal_news.json`
- `data/orca_state.db`
- `reports/`

Current preservation summary:
- `orca_state.db`: commit 기반 보존
- `jackal_state.db`: 현재 미보존
- WAL sidecar 처리:
  - `orca_state.db` 는 explicit checkpoint 후 본체만 commit
  - `jackal_state.db` 는 현재 workflow 상 handling 없음

### 1.2. `orca_jackal.yml`

File:
- [orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml)

총 줄 수:
- `202`

Trigger:
- `schedule`
  - `35 0 * * 1-5`
  - `30 4 * * 1-5`
  - `35 14 * * 1-5`
  - `30 18 * * 1-5`
- `workflow_dispatch`
  - inputs:
    - `session_mode`
    - `force_hunt`
    - `force_scan`
    - `force_evolve`

Concurrency:
- lines `8-10`
- `group: orca-repo-state`
- `cancel-in-progress: false`

Step 목록:
- lines `48-49`: `Checkout`
- lines `51-55`: `Setup Python`
- lines `57-60`: `Install dependencies`
- lines `62-82`: `Run JACKAL Hunter`
- lines `84-97`: `Run JACKAL Scanner`
- lines `99-202`: `Save JACKAL session state`

DB 접근 맵:
- `data/orca_state.db`
  - 직접 commit 대상 아님
  - lines `103-106`, `129-133` 주석에서 ORCA truth / exclusion 으로 취급
- `data/jackal_state.db`
  - 현재 접근 없음
  - whitelist / backup / restore 대상 아님
- 다른 보존 대상:
  - `jackal/hunt_log.json`
  - `jackal/hunt_cooldown.json`
  - `jackal/jackal_weights.json`
  - `jackal/scan_log.json`
  - `jackal/scan_cooldown.json`
  - `jackal/recommendation_log.json`
  - `jackal/compact_log.json`
  - `jackal/jackal_usage_log.json`
  - `data/jackal_watchlist.json`
  - `jackal/skills/`
  - `jackal/lessons/`

DB 관련 step 실제 인용:

```yaml
      - name: Save JACKAL session state
        run: |
          set -euo pipefail

          # NOTE: This is a symptom-level hotfix, not the architectural fix.
          # ORCA is treated as truth for data/orca_state.db.
          # JACKAL's SQLite writes in the same window may be lost.
          # Root fix: PR 5 (persistence boundary).
          git config user.name  "JACKAL Session"
          git config user.email "jackal-session@orca-agent"

          # Persistent artifacts owned by JACKAL. Safe to reapply after reset.
          JACKAL_FILES=(
            "jackal/hunt_log.json"
            "jackal/hunt_cooldown.json"
            "jackal/jackal_weights.json"
            "jackal/scan_log.json"
            "jackal/scan_cooldown.json"
            "jackal/recommendation_log.json"
            "jackal/compact_log.json"
            "jackal/jackal_usage_log.json"
            "data/jackal_watchlist.json"
          )

          # JACKAL skill/lesson directories. Reapplied wholesale.
          JACKAL_DIRS=(
            "jackal/skills"
            "jackal/lessons"
          )

          # Intentionally excluded (ORCA-owned or cache-only):
          #   data/orca_state.db                  ORCA truth; JACKAL writes lost in conflict window
          #   data/jackal_news.json               ORCA writes, JACKAL reads
          #   data/jackal_technicals_cache.json   cache
          #   jackal/compact_cache.json           cache
          BACKUP_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/jackal-save-XXXXXX")"
          STASH_NAME="jackal-save-$(date +%s)"
          COPIED=0

          # Back up JACKAL-owned outputs before resetting to origin/main.
          for path in "${JACKAL_FILES[@]}"; do
            if [ -e "$path" ]; then
              mkdir -p "$BACKUP_DIR/$(dirname "$path")"
              cp -p "$path" "$BACKUP_DIR/$path"
              COPIED=1
            fi
          done

          for path in "${JACKAL_DIRS[@]}"; do
            if [ -d "$path" ]; then
              mkdir -p "$BACKUP_DIR/$(dirname "$path")"
              cp -a "$path" "$BACKUP_DIR/$path"
              COPIED=1
            fi
          done

          [ "$COPIED" -eq 0 ] && exit 0

          # Keep a full stash as an extra safety net before destructive reset.
          git stash push -u -m "$STASH_NAME" >/dev/null 2>&1 || true

          for attempt in 1 2 3; do
            echo "Save JACKAL session state attempt $attempt/3"

            # Respect origin/main as source of truth for shared ORCA-owned files.
            git fetch origin main
            git reset --hard origin/main
            git clean -fd

            # Reapply only JACKAL-owned artifacts after aligning with origin/main.
            for path in "${JACKAL_FILES[@]}"; do
              if [ -e "$BACKUP_DIR/$path" ]; then
                mkdir -p "$(dirname "$path")"
                cp -p "$BACKUP_DIR/$path" "$path"
              fi
            done

            for path in "${JACKAL_DIRS[@]}"; do
              if [ -d "$BACKUP_DIR/$path" ]; then
                rm -rf "$path"
                mkdir -p "$(dirname "$path")"
                cp -a "$BACKUP_DIR/$path" "$path"
              fi
            done

            git add -- "${JACKAL_FILES[@]}" "${JACKAL_DIRS[@]}" 2>/dev/null || true

            if git diff --cached --quiet; then
              echo "No JACKAL-owned changes to save"
              exit 0
            fi

            git commit -m "?쫲 JACKAL Session: $(date +'%Y-%m-%d %H:%M') [skip ci]"

            if git push origin HEAD:main; then
              exit 0
            fi

            echo "Push failed on attempt $attempt, retrying..." >&2
            sleep "$attempt"
          done

          echo "JACKAL session save failed after 3 attempts" >&2
          exit 1
```

hotfix 패턴 관찰:
- `backup to tmp`
- `git stash push -u`
- `git fetch origin main`
- `git reset --hard origin/main`
- `git clean -fd`
- `restore from tmp`
- `git add -- ...`
- `git commit`
- `git push` with `3` retries

현재 whitelist 추출:
- `jackal/hunt_log.json`
- `jackal/hunt_cooldown.json`
- `jackal/jackal_weights.json`
- `jackal/scan_log.json`
- `jackal/scan_cooldown.json`
- `jackal/recommendation_log.json`
- `jackal/compact_log.json`
- `jackal/jackal_usage_log.json`
- `data/jackal_watchlist.json`
- `jackal/skills`
- `jackal/lessons`

현재 exclusion 추출:
- `data/orca_state.db`
- `data/jackal_news.json`
- `data/jackal_technicals_cache.json`
- `jackal/compact_cache.json`

Current preservation summary:
- `orca_state.db`: reset 시 origin/main truth 로 취급, whitelist 대상 아님
- `jackal_state.db`: 현재 whitelist / backup / restore / git add 어디에도 없음
- hotfix code exists: `Yes`

### 1.3. `jackal_tracker.yml`

File:
- [jackal_tracker.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_tracker.yml)

총 줄 수:
- `95`

Trigger:
- `schedule`
  - `0 3 * * *`
  - `0 21 * * *`
- `workflow_dispatch`
  - inputs:
    - `all_entries`
    - `dry_run`
    - `notify`

Concurrency:
- lines `8-10`
- `group: orca-repo-state`
- `cancel-in-progress: false`

Step 목록:
- lines `39-40`: `Checkout`
- lines `42-46`: `Setup Python`
- lines `48-49`: `Install dependencies`
- lines `51-62`: `Run Tracker`
- lines `64-95`: `Save Tracker results`

DB 접근 맵:
- `data/orca_state.db`
  - checkpoint: lines `70-78`
  - commit 대상: lines `82`, `91`
- `data/jackal_state.db`
  - 현재 접근 없음
- 다른 보존 대상:
  - `jackal/hunt_log.json`
  - `jackal/jackal_weights.json`

DB 관련 step 실제 인용:

```yaml
      - name: Save Tracker results
        if: github.event.inputs.dry_run != 'true'
        run: |
          git config user.name  "JACKAL Tracker"
          git config user.email "tracker@orca-agent"

          python - <<'PY'
          import sqlite3
          from pathlib import Path
          db = Path("data/orca_state.db")
          if db.exists():
              conn = sqlite3.connect(db)
              conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
              conn.close()
          PY

          git add jackal/hunt_log.json       2>/dev/null || true
          git add jackal/jackal_weights.json 2>/dev/null || true
          git add -f data/orca_state.db      2>/dev/null || true

          git stash
          git fetch origin main
          git pull --rebase origin main || git rebase --abort
          git stash pop 2>/dev/null || true

          git add jackal/hunt_log.json       2>/dev/null || true
          git add jackal/jackal_weights.json 2>/dev/null || true
          git add -f data/orca_state.db      2>/dev/null || true

          git diff --cached --quiet || \
            git commit -m "?뱧 JACKAL Tracker: outcome 異붿쟻 $(date +'%Y-%m-%d %H:%M') [skip ci]"
          git push || (git pull --rebase origin main && git push)
```

Current preservation summary:
- `orca_state.db`: explicit checkpoint + commit
- `jackal_state.db`: current workflow scope outside commit list
- push conflict handling:
  - `git stash`
  - `git fetch origin main`
  - `git pull --rebase origin main || git rebase --abort`
  - `git stash pop`
  - final `git push || (git pull --rebase origin main && git push)`

### 1.4. `jackal_scanner.yml`

File:
- [jackal_scanner.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_scanner.yml)

총 줄 수:
- `77`

Trigger:
- `workflow_dispatch`
  - input: `force`

Concurrency:
- lines `3-5`
- `group: orca-repo-state`
- `cancel-in-progress: false`

Step 목록:
- lines `22-23`: `Checkout`
- lines `25-29`: `Setup Python`
- lines `31-32`: `Install dependencies`
- lines `34-47`: `Run JACKAL Scanner`
- lines `49-77`: `Save JACKAL Scanner state`

DB 접근 맵:
- `data/orca_state.db`
  - checkpoint: lines `54-62`
  - commit 대상: line `68`
- `data/jackal_state.db`
  - 현재 접근 없음
- 다른 보존 대상:
  - `jackal/scan_log.json`
  - `jackal/scan_cooldown.json`
  - `jackal/recommendation_log.json`
  - `data/jackal_watchlist.json`

DB 관련 step 실제 인용:

```yaml
      - name: Save JACKAL Scanner state
        run: |
          git config user.name  "JACKAL Scanner"
          git config user.email "scanner@orca-agent"

          python - <<'PY'
          import sqlite3
          from pathlib import Path
          db = Path("data/orca_state.db")
          if db.exists():
              conn = sqlite3.connect(db)
              conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
              conn.close()
          PY

          git add jackal/scan_log.json            2>/dev/null || true
          git add jackal/scan_cooldown.json       2>/dev/null || true
          git add jackal/recommendation_log.json  2>/dev/null || true
          git add data/jackal_watchlist.json      2>/dev/null || true
          git add -f data/orca_state.db           2>/dev/null || true

          git diff --cached --quiet && exit 0

          git commit -m "?뱻 JACKAL Scanner: $(date +'%Y-%m-%d %H:%M') [skip ci]"

          git push || {
            git pull --rebase origin main || git rebase --abort
            git push
          }
```

Current preservation summary:
- `orca_state.db`: explicit checkpoint + commit
- `jackal_state.db`: current workflow scope outside commit list
- conflict handling:
  - no explicit stash
  - `git push || { git pull --rebase origin main || git rebase --abort; git push; }`

## Section 2: Out-of-scope 공식 기록

### 2.1. `orca_backtest.yml` 제외 근거

File:
- [orca_backtest.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_backtest.yml)

발견된 DB 접근:

```yaml
      - name: Upload research state
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: research-state-${{ github.run_id }}
          if-no-files-found: warn
          path: |
            data/orca_state.db
            data/orca_state.db-shm
            data/orca_state.db-wal
```

제외 근거:
- artifact upload 용도다
- commit 기반 main branch 보존 로직이 아니다
- 다음 scheduled run 체크아웃 상태를 직접 바꾸지 않는다
- artifact retention 이 끝나면 사라질 수 있으므로, Phase 5 목표인 persistent scheduled-state 와 별개다

### 2.2. `policy_eval.yml` 제외 근거

File:
- [policy_eval.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/policy_eval.yml)

발견된 DB 접근:

```yaml
      - name: Upload evaluation artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: policy-eval-${{ github.run_id }}
          if-no-files-found: warn
          path: |
            data/orca_state.db
            data/orca_state.db-shm
            data/orca_state.db-wal
            reports/orca_research_comparison.md
            reports/orca_research_comparison.json
            reports/orca_research_gate.md
            reports/orca_research_gate.json
```

제외 근거:
- artifact upload 용도다
- commit / push 경로가 아니다
- scheduled run 사이의 state continuity 와 직접 연결되지 않는다
- research / evaluation snapshot 범위이므로 Phase 5 scheduled persistence 와 분리해 다루는 편이 범위가 명확하다

### 2.3. Phase 6 이월 결정

Backlog:
- [orca_v2_backlog.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/orca_v2_backlog.md)

기록된 항목:
- `Deferred Improvement: research artifact scope 재검토`

의미:
- `orca_backtest.yml` / `policy_eval.yml` 이 `jackal_state.db` artifact 를 함께 가져가야 하는지는 별도 PR 에서 판단한다
- Phase 5-D 범위는 `scheduled run` 간 state preservation 이다
- 따라서 Phase 5-D-c 구현 범위는 `commit workflow 4개`로 제한한다

## Section 3: Phase 5-D 수정 원칙

### 3.1. `jackal_state.db` 보존

원칙:
- `data/jackal_state.db` 도 `data/orca_state.db` 와 동일한 수준의 commit 보존 대상으로 취급한다
- Phase 5 범위에서는 artifact 전환이 아니라 git commit 기반 보존을 유지한다
- `git add -f data/jackal_state.db` 또는 이에 준하는 whitelist 포함이 필요하다

적용 대상 workflow:
- `orca_daily.yml`
- `orca_jackal.yml`
- `jackal_tracker.yml`
- `jackal_scanner.yml`

### 3.2. hotfix 공존

대상:
- `orca_jackal.yml`

원칙:
- existing hotfix 구조는 유지한다
- backup to tmp -> reset -> restore -> add -> commit -> retry 흐름은 그대로 둔다
- whitelist / backup 대상에 `data/jackal_state.db` 를 추가한다
- WAL 처리 결정에 따라 sidecar 파일도 whitelist 에 포함할 수 있다

현재 whitelist:
- `jackal/hunt_log.json`
- `jackal/hunt_cooldown.json`
- `jackal/jackal_weights.json`
- `jackal/scan_log.json`
- `jackal/scan_cooldown.json`
- `jackal/recommendation_log.json`
- `jackal/compact_log.json`
- `jackal/jackal_usage_log.json`
- `data/jackal_watchlist.json`
- `jackal/skills`
- `jackal/lessons`

추가 후보:
- `data/jackal_state.db`
- `data/jackal_state.db-wal`
- `data/jackal_state.db-shm`

유지 원칙:
- `data/orca_state.db` 는 여전히 whitelist 제외
- JACKAL 이 shared path 로 `candidate_registry` 를 건드리는 경로는 Phase 6 candidate spine 재설계 이월

### 3.3. concurrency 유지

현재 4개 workflow 모두:
- `group: orca-repo-state`
- `cancel-in-progress: false`

Phase 5-D 원칙:
- 변경하지 않는다
- bounded fix 범위에서 직렬화 정책은 유지한다
- multi-workflow race 완화는 현재 policy 그대로 둔다

### 3.4. PR 1~5 계약 유지

관찰 결과:
- 4개 workflow 모두 Python module entrypoint 를 호출하고, state preservation 은 shell step 에서만 처리한다
- `PR 1` HealthTracker code set 은 workflow 에서 직접 변경하지 않는다
- `PR 2` learning policy 는 workflow 수정과 독립이다
- `PR 3` main thin coordinator 는 `orca_daily.yml` 호출 경로와 독립이다
- `PR 4` review scorecard 는 workflow 수정과 독립이다
- `PR 5` external data visibility 는 workflow env 주입에 의해 소비되지만, Phase 5-D 에서는 env key 자체를 바꾸지 않는다

Phase 5-D 에서 확인할 항목:
- env 변수 주입 변경 없음
- exit code 처리 구조 유지
- save step 내 추가 checkpoint 또는 `git add` 수정이 Python contract 를 깨지 않는지 검증

## Section 3.5: SQLite WAL 파일 처리

### 3.5.1. 배경

Phase 5-C helper:
- [state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:99)

실제 코드:

```python
def _connect_jackal() -> sqlite3.Connection:
    """Return connection to jackal_state.db (JACKAL learning state).

    Category 1 tables only. See docs/phase5/02-path-decision.md.
    """
    JACKAL_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(JACKAL_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn
```

WAL 모드에서 생성될 수 있는 파일:
- `data/jackal_state.db`
- `data/jackal_state.db-wal`
- `data/jackal_state.db-shm`

현재 workflow 관찰:
- `orca_daily.yml`, `jackal_tracker.yml`, `jackal_scanner.yml` 는 `orca_state.db` 에 대해 explicit `wal_checkpoint(TRUNCATE)` 를 호출한다
- `orca_jackal.yml` 는 explicit checkpoint block 이 없다

### 3.5.2. 문제 정의

WAL 모드에서 checkpoint 가 끝나지 않았으면:
- 최신 write 는 `data/jackal_state.db-wal` 에만 남아 있을 수 있다
- `data/jackal_state.db` 본체만 commit 하면 recent change 가 main DB file 로 병합되지 않을 수 있다
- workflow reset / checkout 이후 sidecar 가 사라지면 logical data loss 가 발생할 수 있다

즉 Phase 5-D 는 `jackal_state.db` 본체 보존만이 아니라, `WAL sidecar` 또는 `checkpoint timing` 중 하나를 명시적으로 설계해야 한다.

### 3.5.3. 해결 옵션 3가지

#### Option 1: WAL 파일 함께 commit

예시:

```yaml
git add -f data/jackal_state.db
git add -f data/jackal_state.db-wal
git add -f data/jackal_state.db-shm
```

장점:
- workflow 수정만으로 처리 가능하다
- Python 재진입이 없다
- checkpoint 실패 여부와 무관하게 sidecar 자체를 보존할 수 있다

단점:
- `-wal`, `-shm` 은 SQLite runtime sidecar 이다
- git diff 노이즈가 생긴다
- hotfix whitelist / backup 대상 파일이 늘어난다
- checkout 환경의 SQLite 버전 / 상태 차이에 따라 sidecar 재사용성이 불안정할 수 있다

#### Option 2: Python 쪽 명시적 checkpoint

개념:

```python
def checkpoint_jackal_db():
    conn = _connect_jackal()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    finally:
        conn.close()
```

workflow 에서는 `git add` 전 checkpoint 를 먼저 수행한 뒤 본체 파일만 add 한다.

장점:
- git 에는 `data/jackal_state.db` 본체만 남긴다
- sidecar 는 ephemeral 로 유지한다
- `orca_daily.yml`, `jackal_tracker.yml`, `jackal_scanner.yml` 의 existing ORCA checkpoint pattern 과 모양이 맞는다

단점:
- Python 코드 추가가 필요하다
- Phase 5-D-c 직전이 아니라 Phase 5-C 범위를 다시 건드리는 성격이 된다
- `orca_jackal.yml` 에도 checkpoint invocation 을 넣어야 일관된다

#### Option 3: SQLite close 동작에 의존

전제:
- `with _connect_jackal() as conn:` block 종료 후 close 시 checkpoint 가 어느 정도 시도될 수 있다

장점:
- 추가 코드가 없다
- workflow 변경이 최소다

단점:
- checkpoint 완료 보장이 없다
- 다른 connection 이 열려 있으면 최근 write 가 sidecar 에 남을 수 있다
- 보존 correctness 를 workflow 단계에서 확인할 수 없다

### 3.5.4. 추천 후보 + 근거

최종 결정은 `Phase 5-D-b` 승인 턴에서 사용자 답변으로 확정한다.

임시 비교 결론:
- `Option 3` 은 correctness guarantee 가 약해서 우선순위가 가장 낮다
- `Option 1` 은 구현 범위가 workflow-only 로 닫힌다
- `Option 2` 는 git noise 를 줄이지만 Python code 재진입이 필요하다

임시 추천 후보:
- `Option 1` 또는 `Option 2`

근거:
- `Phase 5-D` 의 bounded fix 원칙만 보면 `Option 1` 이 가장 좁다
- repository hygiene 와 long-term maintenance 만 보면 `Option 2` 가 더 깔끔하다
- 현재 3개 workflow 가 이미 `orca_state.db` 에 대해 explicit checkpoint block 을 갖고 있어서, 패턴 일관성은 `Option 2` 쪽이 높다
- 반대로 `orca_jackal.yml` 의 hotfix는 backup/restore 중심이라 sidecar whitelist 로 처리하는 `Option 1` 과도 잘 맞는다

결론:
- 구현 전 승인 질문으로 남긴다
- 본 문서에서는 `Option 1` / `Option 2` 둘 다 Phase 5-D-c step plan 에 반영한다

### 3.5.5. WAL 파일 크기 영향

관찰:
- WAL 파일은 checkpoint 전까지 증가할 수 있다
- `jackal_shadow_signals`, `jackal_live_events`, `jackal_weight_snapshots` 누적량에 따라 size 가 증가할 수 있다

Phase 5 관점:
- repo size 증가 가능성은 수용 대상이다
- 크기 관리 정책은 이번 단계에서 결정하지 않는다

Phase 6 후보:
- 정기 `VACUUM`
- 오래된 row pruning
- artifact / external store 전환

## Section 4: Workflow 별 상세 수정 계획

이 섹션은 `Section 3.5` 의 WAL 결정에 따라 두 갈래로 기록한다.

### 4.1. `orca_daily.yml`

Current behavior:
- explicit `orca_state.db` checkpoint
- `git add -f data/orca_state.db`
- no `jackal_state.db`

Option 1 계획:
- existing save step 유지
- `git add -f data/jackal_state.db` 추가
- `git add -f data/jackal_state.db-wal` 추가
- `git add -f data/jackal_state.db-shm` 추가

Option 2 계획:
- save step 내 Python checkpoint block 확장
  - `data/jackal_state.db` 도 checkpoint
- `git add -f data/jackal_state.db` 추가
- sidecar add 없음

예상 변경:
- Option 1: `1-3`줄 추가
- Option 2: checkpoint block 수정 + `1`줄 add

### 4.2. `orca_jackal.yml`

Current behavior:
- no explicit checkpoint block
- whitelist backup/restore 중심 hotfix
- `data/orca_state.db` excluded
- `data/jackal_state.db` absent

Option 1 계획:
- `JACKAL_FILES` 또는 별도 DB whitelist 에 `data/jackal_state.db` 추가
- sidecar 까지 commit 해야 하므로
  - `data/jackal_state.db-wal`
  - `data/jackal_state.db-shm`
  도 backup / restore / `git add --` 대상에 포함
- 기존 `data/orca_state.db` exclusion 주석은 유지

Option 2 계획:
- save step 초반에 explicit checkpoint block 추가
  - `data/jackal_state.db` checkpoint
- 이후 `JACKAL_FILES` 또는 별도 DB whitelist 에 `data/jackal_state.db` 본체만 추가
- sidecar 는 backup / restore 대상에서 제외

예상 변경:
- Option 1: whitelist / backup / restore / add 배열에 `1-3` entries 추가
- Option 2: Python checkpoint block + whitelist entry `1`

핵심 확인점:
- reset 전 backup 에 포함되는지
- reset 후 restore 되는지
- `git add -- "${JACKAL_FILES[@]}" "${JACKAL_DIRS[@]}"` 에 포함되는지

### 4.3. `jackal_tracker.yml`

Current behavior:
- explicit `orca_state.db` checkpoint
- `data/orca_state.db` add twice
- `jackal_state.db` absent

Option 1 계획:
- pre-pull add와 post-pull add 양쪽에 아래 추가
  - `git add -f data/jackal_state.db`
  - `git add -f data/jackal_state.db-wal`
  - `git add -f data/jackal_state.db-shm`

Option 2 계획:
- checkpoint Python block 에 `data/jackal_state.db` 추가
- pre-pull add와 post-pull add 양쪽에 `git add -f data/jackal_state.db` 추가

예상 변경:
- Option 1: `2 x (1-3)`줄
- Option 2: checkpoint block 수정 + `2`줄

### 4.4. `jackal_scanner.yml`

Current behavior:
- explicit `orca_state.db` checkpoint
- single add block
- `jackal_state.db` absent

Option 1 계획:
- existing add block에
  - `git add -f data/jackal_state.db`
  - `git add -f data/jackal_state.db-wal`
  - `git add -f data/jackal_state.db-shm`
  추가

Option 2 계획:
- checkpoint Python block 에 `data/jackal_state.db` 추가
- add block 에 `git add -f data/jackal_state.db` 추가

예상 변경:
- Option 1: `1-3`줄
- Option 2: checkpoint block 수정 + `1`줄

## Section 5: 리스크 & Mitigation

### 5.1. Risk: 첫 run 에 `jackal_state.db` 없음

상황:
- merge 직후 repo 에 `data/jackal_state.db` 가 없을 수 있다

현재 근거:
- Phase 5-C `init_state_db()` idempotency 가 검증됐다
- first run 시 필요한 경우 DB 생성 가능하다

Mitigation:
- 첫 save step 까지만 살아남으면 commit 대상에 들어간다
- 이후부터는 repo baseline 으로 유지된다

### 5.2. Risk: hotfix 가 `jackal_state.db` 지움

대상:
- `orca_jackal.yml`

상황:
- `git reset --hard origin/main`
- `git clean -fd`

문제:
- backup / restore 목록에 없으면 `jackal_state.db` 는 소실된다

Mitigation:
- `data/jackal_state.db` 를 whitelist 에 포함
- WAL decision 이 `Option 1` 이면 sidecar 도 함께 backup / restore

### 5.3. Risk: WAL 파일 유실

조건:
- `Option 1` 미선택
- explicit checkpoint 없음 또는 incomplete

문제:
- recent write 가 sidecar 에만 남을 수 있다

Mitigation:
- `Option 1`: sidecar commit
- `Option 2`: explicit checkpoint
- `Option 3`: 수용 불확실성 높음

### 5.4. Risk: workflow 경쟁

현재 상태:
- 4개 workflow 모두 `concurrency=orca-repo-state`
- 직렬화는 된다

남는 문제:
- push 시점 non-fast-forward

현재 대응 차이:
- `orca_jackal.yml`: strongest pattern
  - `fetch + reset + clean + restore + 3-retry`
- `jackal_tracker.yml`: mid-level pattern
  - `stash + fetch + pull --rebase + stash pop`
- `jackal_scanner.yml` / `orca_daily.yml`: simple `push || pull --rebase || rebase --abort; push`

Phase 5-D 범위:
- concurrency 재설계는 하지 않는다
- 현재 push handling 차이는 문서화만 한다
- `jackal_state.db` 보존 경로를 existing conflict handling 안에 맞춰 넣는다

### 5.5. Risk: DB 파일 크기 증가

상황:
- `jackal_state.db` 는 시간이 지나며 증가한다

Phase 5 해석:
- scheduled persistence correctness 를 우선한다
- repo size 증가는 수용한다

Phase 6 이월:
- vacuum
- pruning
- external persistence

## Section 6: Phase 5-D-c 작업 Step preview

### Step D-1: `orca_daily.yml`

Option 1:
- `git add -f data/jackal_state.db`
- `git add -f data/jackal_state.db-wal`
- `git add -f data/jackal_state.db-shm`

Option 2:
- checkpoint Python block 에 `jackal_state.db` 추가
- `git add -f data/jackal_state.db`

### Step D-2: `jackal_tracker.yml`

Option 1:
- pre/post add block 둘 다 sidecar 포함 추가

Option 2:
- checkpoint Python block 확장
- pre/post add block 둘 다 본체 add 추가

### Step D-3: `jackal_scanner.yml`

Option 1:
- single add block 에 sidecar 포함 추가

Option 2:
- checkpoint Python block 확장
- add block 에 본체 add 추가

### Step D-4: `orca_jackal.yml`

Option 1:
- whitelist / backup / restore / add 에 본체 + sidecar 포함

Option 2:
- explicit checkpoint block 추가
- whitelist / backup / restore / add 에 본체만 포함

주의:
- hotfix 구조는 보존
- `data/orca_state.db` exclusion 은 유지

### Step D-5: 통합 검증

검증 후보:
- YAML syntax via `yaml.safe_load`
- `actionlint` if available
- save step diff 최소화 확인
- `jackal_state.db` 포함 여부 grep 확인
- PR 1~5 smoke 재확인

## Section 7: Phase 6 이월 확정

Phase 5-D 에서 하지 않을 것:
- workflow 구조 근본 재설계
- concurrency 정책 변경
- workflow 추가 / 삭제
- `orca_backtest.yml` / `policy_eval.yml` artifact scope 확장
- existing hotfix architecture redesign
- scheduled workflow 를 artifact 중심 전달로 바꾸는 작업

이유:
- Path B 는 bounded persistence fix 다
- workflow architecture overhaul 은 별도 프로젝트 성격이다

## Section 8: Success Criteria

Phase 5-D 완료 판정:
1. 4개 workflow 모두 `data/jackal_state.db` commit 대상
2. `Section 3.5` 에서 승인된 WAL 처리 방식 적용
3. `orca_jackal.yml` hotfix 에 `jackal_state.db` 보호 포함
4. YAML syntax 검증 통과
5. 다음 scheduled run 후 `jackal_state.db` 가 repo 에 올라옴
6. 그 다음 scheduled run 에서 `COUNT > 0` 관측
7. PR 1~5 계약 유지

## Section 9: Decision Points (Phase 5-D-b 승인 대기)

다음 턴에서 사용자 승인 필요:

### Q1. WAL 처리 옵션
- `Option 1`: DB 본체 + WAL sidecar commit
- `Option 2`: explicit checkpoint 후 본체만 commit
- `Option 3`: close 동작 의존

### Q2. Option 1 선택 시 sidecar 관리 정책
- `orca_daily.yml`, `jackal_tracker.yml`, `jackal_scanner.yml` 에서 sidecar 를 모두 `git add -f` 할지
- `orca_jackal.yml` 에서는 whitelist / backup / restore 까지 sidecar 를 확장할지

### Q3. `orca_jackal.yml` hotfix backup/restore 확장 범위
- 본체만
- 본체 + sidecar
- 별도 DB array 분리 여부

승인 전 상태:
- 설계 문서에는 선택지와 영향만 정리
- 실제 yml 수정은 아직 하지 않음
