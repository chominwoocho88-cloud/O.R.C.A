# modules/orca/

시장 분석 모듈 (자기 완결).

## 책임
- 일일 시장 regime 분석
- 4-agent LLM 파이프라인 (Hunter -> Analyst -> Devil -> Reporter)
- 학습/메모리 시스템 (lessons, archive, retrieval, clustering)
- JACKAL에 baseline 시그널 전달

## 입력
- shared.market_data: 시장 데이터
- shared.llm.client: LLM 호출
- data/memory.json: 과거 cycle 메모리

## 출력
- data/morning_baseline.json: JACKAL용 baseline
- data/memory.json: 누적 메모리
- reports/YYYY-MM-DD_mode.json: 사용자용 리포트
- data/orca_state.db: 학습 상태

## 현재 상태 (Day 5)
- 빈 폴더. 실제 코드는 orca/ 에 있음.
- Day 7~8에 코드 이동 예정.

## 마이그레이션 순서 (계획)
1. shared/market_data/ 분리 (Day 6)
2. modules/orca/pipeline/ - agents, run_cycle, pipeline (Day 7)
3. modules/orca/regime/ - analysis_market (Day 7)
4. modules/orca/lessons/ - lesson_*, retrieval (Day 8)
5. modules/orca/state/ - state.py 분리 검토 (Day 8 또는 별도)
