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
1. shared/market_data/ 분리 (Day 6) 완료
2. pipeline.py 이동 (Day 7) 완료 - 작은 파일 먼저 검증
3. agents.py 이동 (Day 8) 완료
4. run_cycle.py 이동 (Day 9) 완료 - ORCA pipeline 핵심 3 파일 모두 이동
5. modules/orca/regime/ - analysis_market (후속)
6. modules/orca/lessons/ - lesson_*, retrieval (다음 sprint)
7. modules/orca/state/ - state.py 4069줄 분할 검토 (별도 sprint)
