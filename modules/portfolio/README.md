# modules/portfolio/

포트폴리오 관리 모듈 (다중 계좌).

## 책임
- 계좌별 포지션 추적 (CMW, CJC, ...)
- 주문 실행 (CMW만 매매 권한)
- 모니터링/조회 (CJC 등 가족 계좌)
- 권한 분리 강제 (코드 레벨)

## 입력
- shared.broker.kis: KIS API
- data/morning_baseline.json + JACKAL 후보

## 출력
- modules/portfolio/accounts/<id>/positions.json
- modules/portfolio/accounts/<id>/orders.jsonl

## 현재 상태 (Day 5)
- 빈 폴더. KIS API client 작성 후 (Stage 2, Day 11+) 시작.
- Stage 3 (Day 27~30) 본격 구현.

## 권한 모델 (계획)
- CMW: read + trade
- CJC: read only (조회 전용, 매매 금지)
- 코드 레벨에서 raise PermissionError 강제
