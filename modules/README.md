# modules/

비즈니스 모듈 (vertical slices). 각 모듈은 자기 완결.

## 원칙
- 자기 완결성: 각 모듈 폴더 안에 그 모듈에 필요한 모든 것
- 단방향 의존성: shared <- modules <- integrations (만들 때)
- 모듈 간 직접 import 금지: 데이터 교환은 JSON contract 또는 integrations 통해
- 각 모듈 README.md가 시작점

## 구조
- orca/      시장 분석 모듈 (3-pipeline: Hunter -> Analyst -> Devil -> Reporter)
- jackal/    종목 발굴 모듈 (Shield -> Hunter -> Compact -> Evolution + Scanner + Tracker)
- portfolio/ 포트폴리오 관리 모듈 (계좌별 격리, 다중 사용자)

## 현재 상태 (Day 5)
- 빈 골격만 생성. 코드 이동은 Day 6~10에 점진적으로.
- 기존 orca/, jackal/ 코드는 그대로 운영 중.
