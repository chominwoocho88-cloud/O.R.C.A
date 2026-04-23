# Phase 6 Feature Enhancement Investigation
작성 시점:
2026-04-23
상태:
analysis only
범위:
새 investigation 문서 1개 작성
범위 밖:
기존 코드 수정 0
범위 밖:
기존 docs 수정 0
범위 밖:
기존 tests 수정 0
목적:
사용자 요청 4개 묶음을
현재 JACKAL 코드 기준으로 조사하고,
다음 구현 세션의 우선순위와 진입점을 정리한다.
핵심 전제:
새 signal 도입 전에는 backtest가 필요하다.
핵심 전제:
점수와 확률은 다르다.
핵심 전제:
qualified probability summary 또는 backtest 근거가 없으면
`상승 확률` 같은 제품 문구는 쓰지 않는 편이 안전하다.
표기 규칙:
`[검증됨]`은 repo 코드 또는 샘플 산출물에서 직접 확인한 사실이다.
표기 규칙:
`[조사 필요]`는 이번 세션에서 더 좁혀야 하는 항목이다.
표기 규칙:
`[의견]`은 우선순위 또는 제품 운영 관점의 권고다.
빠른 결론 1:
현재 JACKAL은 rebound-first baseline이다.
빠른 결론 2:
Request 1 원요청의 candle pattern은 보류가 합리적이다.
빠른 결론 3:
Request 1 Extension에서는 RS와 52주 신고가 근접이 가장 유력하다.
빠른 결론 4:
Request 2의 설명 상세화는 새 데이터 없이도 즉시 개선 가능하다.
빠른 결론 5:
Request 3의 Devil silent는
`반박 없음`
하나로 해석하면 안 된다.
빠른 결론 6:
다음 구현 세션의 가장 자연스러운 순서는
Request 2
→ Request 3
→ RS
→ 52주 신고가 근접
순이다.
목차:
Section 0 Meta
Section 1 현재 JACKAL 능력 baseline
Section 2 Request 1 - Momentum + Candle Pattern
Section 3 Request 1 Extension - Alternative Signals
Section 4 Request 2 - 추천 이유 상세화
Section 5 Request 3 - Devil Silent 조사
Section 6 우선 순위 및 의존
Section 7 각 요청의 도입 전 조건
Section 8 Backtest 인프라 현황
Section 9 결론 및 다음 세션 진입점
Appendix A 코드 근거 인덱스
Appendix B 학문 참고 문헌 메모
Appendix C 출력/설명 필드 인벤토리
Appendix D Devil silent 증거 맵
Appendix E 요청별 체크리스트
# Section 0: Meta
## 0.1 문서 목적
이 문서는 구현 문서가 아니다.
이 문서는 조사 문서다.
이 문서는 설계 결정을 강제하지 않는다.
이 문서는 다음 세션에서
무엇을 먼저 구현하면 좋은지,
무엇은 보류하는 편이 정직한지,
무엇은 backtest가 선행돼야 하는지를
정리하기 위한 메모다.
## 0.2 조사 대상 파일
주요 조사 파일:
`jackal/families.py`
주요 조사 파일:
`jackal/quality_engine.py`
주요 조사 파일:
`jackal/hunter.py`
주요 조사 파일:
`jackal/scanner.py`
주요 조사 파일:
`jackal/market_data.py`
주요 조사 파일:
`jackal/backtest.py`
주요 조사 파일:
`jackal/probability.py`
주요 조사 파일:
`jackal/core.py`
주요 조사 파일:
`orca/agents.py`
주요 조사 파일:
`orca/postprocess.py`
주요 조사 파일:
`orca/analysis_review.py`
주요 조사 파일:
`orca/run_cycle.py`
보조 문서:
`docs/jackal/current-signals.md`
보조 문서:
`docs/orca_v2_backlog.md`
샘플 산출물:
`reports/2026-04-22_morning.json`
샘플 로그:
`jackal/hunt_log.json`
## 0.3 조사 방법
정적 코드 읽기
파일:line 기준 근거 정리
기능 존재 여부에 대한 문자열 검색
샘플 report와 log 구조 확인
학문 참고문헌 PDF 확인
## 0.4 조사 결과를 읽는 법
`[검증됨]`은
현재 repo 코드와 샘플 산출물에서 직접 확인한 사실이다.
`[조사 필요]`는
이번 세션에서 단정하기 어려운 부분이다.
`[의견]`은
우선순위나 도입 순서에 대한 권고다.
## 0.5 선행 주의사항
첫째,
차트 패턴은 실무 사용은 넓지만 학문적으로는 논란이 많다.
둘째,
momentum factor 문헌은 존재하지만,
그 사실이 자동으로
`내일 상승 확률`
문구를 정당화해 주지는 않는다.
셋째,
현재 JACKAL의 내부 점수는 확률과 동일하지 않다.
넷째,
qualified sample이 없는 probability summary는
마케팅성 확률 문구의 근거로 쓰면 안 된다.
다섯째,
Devil silent는 현재 로그 구조상 원인을 완전 복원하기 어렵다.
## 0.6 현재 운영 흐름 메모
[검증됨]
`jackal/core.py`는
Shield
→ Hunter
→ Compact
→ Evolution 흐름을 가진다.
Ref:
`jackal/core.py:55-90`
[검증됨]
`README.md`와 workflow 기준의 user-visible session은
Hunter
→ Scanner 흐름이다.
Ref:
`README.md:79-85`
`README.md:97-101`
`.github/workflows/orca_jackal.yml:1-18`
`.github/workflows/orca_jackal.yml:62-97`
## 0.7 문서 사용 순서 권장
먼저 읽을 곳:
Section 1
두 번째로 읽을 곳:
Section 3.6 비교표
세 번째로 읽을 곳:
Section 6 우선 순위 및 의존
네 번째로 읽을 곳:
Section 9 결론 및 다음 세션 진입점
## 0.8 이번 문서의 최상위 권장
[의견]
Request 2는 가장 먼저 구현해도 되는 항목이다.
[의견]
Request 3은 가장 빨리 원인 분해가 가능한 항목이다.
[의견]
새 signal 후보 중에서는
RS가 가장 방어 가능하다.
[의견]
그 다음은
52주 신고가 근접이다.
[의견]
candle pattern은 맨 뒤로 미루는 편이 좋다.
# Section 1: 현재 JACKAL 능력 baseline
## 1.1 baseline 한 줄 정의
[검증됨]
현재 JACKAL은
`rebound-first baseline`
이라고 요약할 수 있다.
의미:
과매도,
급락,
지지 회복,
공포 완화,
눌림목 해석이 중심이다.
비의미:
이미 강한 종목이 더 강하게 가는
continuation leader engine은 아니다.
## 1.2 core 역할과 실행 관점
[검증됨]
`jackal/core.py` 상단 docstring은
JACKAL core를
`새 스윙 기회 탐색 엔진`
이라고 정의한다.
Ref:
`jackal/core.py:1-11`
[검증됨]
core는 Hunter를 실행하지만
Scanner를 직접 실행하지 않는다.
Ref:
`jackal/core.py:67-80`
[검증됨]
다만 실제 workflow는
Hunter 후에 Scanner를 실행한다.
Ref:
`.github/workflows/orca_jackal.yml:62-97`
이 차이는 중요하다.
이유:
사용자가 체감하는 Telegram 출력은
Hunter와 Scanner 둘 다 포함할 수 있기 때문이다.
## 1.3 현재 family taxonomy
### 1.3.1 canonical family 목록
[검증됨]
공유 canonical family는 총 7개다.
Ref:
`jackal/families.py:7-15`
`rotation`
`panic_rebound`
`momentum_pullback`
`ma_reclaim`
`divergence`
`oversold_rebound`
`general_rebound`
### 1.3.2 mapping 구조
[검증됨]
`canonical_family_key()`는
Hunter swing type,
Scanner raw family,
signals_fired를 종합해
위 7개 family로 매핑한다.
Ref:
`jackal/families.py:33-109`
### 1.3.3 각 family의 현재 의미
[검증됨]
`rotation`은
섹터 유입 + sector-rebound 성격이다.
Ref:
`jackal/families.py:66-69`
`jackal/families.py:94-97`
[검증됨]
`panic_rebound`는
volume climax와 급락 후 반등 성격이다.
Ref:
`jackal/families.py:69-70`
`jackal/families.py:98-101`
[검증됨]
`momentum_pullback`은
이름은 momentum이지만,
실제론 눌림목 / 조정 후 반등 해석에 더 가깝다.
Ref:
`jackal/families.py:71-72`
`jackal/families.py:102-103`
[검증됨]
`ma_reclaim`은
이동평균선 지지 / 재탈환 구간이다.
Ref:
`jackal/families.py:77-78`
`jackal/families.py:104-105`
[검증됨]
`divergence`는
RSI divergence 또는 bullish_div 기반이다.
Ref:
`jackal/families.py:81-82`
`jackal/families.py:90-93`
[검증됨]
`oversold_rebound`는
RSI 과매도,
BB touch,
52주 저점권을 묶는 전형적 과매도 반등이다.
Ref:
`jackal/families.py:73-74`
`jackal/families.py:85-86`
`jackal/families.py:106-107`
[검증됨]
taxonomy 전체를 보면
continuation보다 rebound에 가깝다.
## 1.4 Hunter 기준 기술지표 baseline
[검증됨]
Hunter technical snapshot은
price,
change_1d,
change_3d,
change_5d,
RSI,
MA20,
MA50,
BB 위치,
거래량 배수,
bullish divergence,
bullish candle을 계산한다.
Ref:
`jackal/hunter.py:540-600`
### 1.4.1 bullish candle의 현재 정의
[검증됨]
`bullish_candle`은
캔들 패턴이 아니라
그날 종가가 시가보다 높은지 여부만 본다.
Ref:
`jackal/hunter.py:585-590`
[검증됨]
따라서 Hammer,
Doji,
Morning Star,
Engulfing 같은 shape 인식은 현재 없다.
### 1.4.2 Stage 1 scoring 방향
[검증됨]
낮은 RSI에 가점,
높은 RSI에 벌점을 준다.
Ref:
`jackal/hunter.py:635-642`
[검증됨]
BB 하단 근접에 가점,
상단 과열에 벌점을 준다.
Ref:
`jackal/hunter.py:644-650`
[검증됨]
최근 5일 낙폭에 가점,
최근 5일 급등에 벌점을 준다.
Ref:
`jackal/hunter.py:670-676`
[검증됨]
거래량 급등 + 하락은 capitulation 성격으로 점수화한다.
Ref:
`jackal/hunter.py:678-695`
[검증됨]
MA50 근접은 보조 신호다.
Ref:
`jackal/hunter.py:697-711`
[검증됨]
bullish divergence와
bullish candle after drawdown에 가점을 준다.
Ref:
`jackal/hunter.py:713-720`
[검증됨]
섹터 ETF 대비 더 많이 빠진 종목에 가점을 준다.
Ref:
`jackal/hunter.py:722-740`
### 1.4.3 Stage 1 방향성 결론
[검증됨]
Hunter Stage 1은
`이미 강한 추세의 지속`
보다
`조정 후 반등`
을 선호한다.
## 1.5 Hunter swing type 분류
[검증됨]
Hunter의 `_classify_swing_type()`은 다음 유형을 반환한다.
Ref:
`jackal/hunter.py:946-1003`
`강세다이버전스`
`섹터로테이션`
`패닉셀반등`
`모멘텀눌림목`
`MA지지반등`
`기술적과매도`
### 1.5.1 momentum_pullback의 실제 의미
[검증됨]
`모멘텀눌림목`은
최근 5일 수익률이 음수 쪽이고
RSI도 낮아진 장면을 본다.
Ref:
`jackal/hunter.py:987-993`
[검증됨]
따라서 continuation leader와는 다르다.
## 1.6 Scanner deterministic baseline
[검증됨]
Scanner pre-rule signal은 아래와 같다.
Ref:
`jackal/quality_engine.py:26-53`
`rsi_oversold`
`bb_touch`
`volume_climax`
`momentum_dip`
`sector_rebound`
`rsi_divergence`
`52w_low_zone`
`vol_accumulation`
`ma_support`
### 1.6.1 raw family baseline
[검증됨]
Scanner raw family는 아래 4개다.
Ref:
`jackal/quality_engine.py:54-63`
`crash_rebound`
`ma_support_solo`
`ma_support_weak`
`general`
### 1.6.2 quality score baseline
[검증됨]
quality score는 base 50에서 시작한다.
Ref:
`jackal/quality_engine.py:80-83`
[검증됨]
`reasons` 배열은 이미 설명 재료가 풍부하다.
Ref:
`jackal/quality_engine.py:83-130`
예시:
`sector_rebound(93%)+20`
예시:
`BB+RSI조합(97%+88%)+16`
예시:
`52주저점구간+12`
예시:
`하락중거래량증가(매집,84%)+12`
### 1.6.3 negative veto와 과열 처리
[검증됨]
quality engine은
Thesis Killer,
혼조/전환중 레짐,
최근 5일 과열,
고불확실성 gate를 별도로 본다.
Ref:
`jackal/quality_engine.py:200-230`
`jackal/quality_engine.py:257-306`
[검증됨]
최근 5일 과열은 negative veto 방향이다.
Ref:
`jackal/quality_engine.py:217-227`
이는 continuation 전략과 결이 다르다.
## 1.7 market_data baseline
[검증됨]
`jackal/market_data.py`는 1년 daily history를 fetch한다.
Ref:
`jackal/market_data.py:431-471`
[검증됨]
snapshot에는 아래 값이 있다.
Ref:
`jackal/market_data.py:343-418`
RSI
MA20
MA50
BB 위치
volume ratio
RSI divergence
MA alignment
BB width
BB expanding
volume trend 5d
vol_accumulation
52주 위치 값
### 1.7.1 Extension 조사에 중요한 현재 보유 지표
[검증됨]
Squeeze 관련 원재료로
`bb_width`
와
`bb_expanding`
이 이미 있다.
Ref:
`jackal/market_data.py:380-387`
[검증됨]
52주 관련 원재료로
`high_52w`,
`low_52w`,
`52w_pos`
가 이미 있다.
Ref:
`jackal/market_data.py:397-415`
[검증됨]
volume 관련 원재료로
`vol_trend_5d`,
`vol_accumulation`
이 이미 있다.
Ref:
`jackal/market_data.py:389-395`
[검증됨]
market benchmark RS line은 없다.
[검증됨]
Volume Profile / POC는 없다.
[검증됨]
OBV / A-D line도 없다.
## 1.8 Alert / report baseline
### 1.8.1 Hunter alert 구조
[검증됨]
Hunter `_build_alert()`는
종목,
가격,
1일/5일 변화,
final score,
day1/swing score,
RSI/BB/거래량,
hunt reason,
bull case,
Devil main risk,
entry/target/stop,
expected days,
swing type를 보여 준다.
Ref:
`jackal/hunter.py:1472-1493`
[검증됨]
설명량은 짧다.
이유:
`hunt_reason`
짧게 잘림
이유:
`bull_case`
짧게 잘림
이유:
`main_risk`
짧게 잘림
### 1.8.2 Scanner alert 구조
[검증됨]
Scanner alert는 Hunter보다 풍부하지만,
여전히 점수 카드형이다.
Ref:
`jackal/scanner.py:847-972`
포함 항목:
score / signal_type / confidence
포함 항목:
peak day / swing_acc / MAE
포함 항목:
Analyst / Devil / Final 점수
포함 항목:
signals display
포함 항목:
짧은 bull_case
포함 항목:
Devil 첫 objection 또는 verdict
### 1.8.3 report.json baseline
[검증됨]
ORCA run cycle은
`jackal_candidate_review`
와
`jackal_probability_summary`
를 report에 붙인다.
Ref:
`orca/run_cycle.py:352-372`
`orca/postprocess.py:96-155`
[검증됨]
`jackal_candidate_review`는
후보별 장문 설명 저장소가 아니라
summary object다.
Ref:
`orca/analysis_review.py:344-525`
[검증됨]
샘플 report에서는
candidate review가 비어 있는 경우가 있다.
Ref:
`reports/2026-04-22_morning.json:126-146`
[검증됨]
샘플 report에서는
probability summary도 비어 있다.
Ref:
`reports/2026-04-22_morning.json:148-166`
## 1.9 Devil baseline
### 1.9.1 ORCA Devil
[검증됨]
ORCA Devil prompt는
시장 레벨 counter-argument agent다.
Ref:
`orca/agents.py:371-440`
### 1.9.2 Hunter Devil
[검증됨]
Hunter Devil은
`main_risk` 중심 반박을 반환한다.
Ref:
`jackal/hunter.py:1188-1194`
[검증됨]
parse/fallback에서
`main_risk` 기본값은 빈 문자열이다.
Ref:
`jackal/hunter.py:1201-1211`
### 1.9.3 Scanner Devil
[검증됨]
Scanner Devil은
`objections` 배열 중심 반박을 반환한다.
Ref:
`jackal/scanner.py:703-710`
[검증됨]
fallback 경로는
`objections: []`
를 반환한다.
Ref:
`jackal/scanner.py:719-728`
## 1.10 baseline 결론
[검증됨]
현재 JACKAL은 rebound-first baseline이다.
[검증됨]
현재 JACKAL에는 candle pattern recognition이 없다.
[검증됨]
현재 JACKAL에는 market benchmark RS가 없다.
[검증됨]
현재 JACKAL은 52주 low 쪽은 쓰지만,
52주 high continuation은 쓰지 않는다.
[검증됨]
현재 JACKAL은 BB width를 계산하지만 squeeze signal은 없다.
[검증됨]
현재 JACKAL은 단순 volume accumulation heuristic은 있지만,
고급 장기 매집 모델은 없다.
[검증됨]
현재 JACKAL은 설명 재료는 충분하지만,
표현 surface가 짧다.
[검증됨]
현재 JACKAL은 Devil silent 상태를 명시적으로 구분하지 않는다.
# Section 2: Request 1 - Momentum + Candle Pattern
## 2.1 사용자 요청을 시스템 요구로 번역
사용자 원문은 사실상 아래 세 요구가 섞여 있다.
요구 A:
상승장 안에서
내일도 더 갈 가능성이 높은 종목을 찾기
요구 B:
그래프 생김새를 같이 분석하기
요구 C:
망치형,
별형,
도지 같은 candle pattern에 가점을 주기
이 세 요구는 비슷해 보이지만,
실제로는 구현 경로가 다르다.
요구 A는
continuation / momentum 문제다.
요구 B는
broad chart structure 문제다.
요구 C는
candlestick pattern recognition 문제다.
## 2.2 현재 signal과의 중복 여부
### 2.2.1 가장 가까운 기존 family
[검증됨]
가장 가까운 canonical family는
`momentum_pullback`
이다.
Ref:
`jackal/families.py:10`
`jackal/families.py:71-72`
`jackal/families.py:102-103`
[검증됨]
하지만 이 family는
상승 지속이라기보다
눌림목 / 조정 후 반등 해석이다.
증거:
Hunter의 `모멘텀눌림목` 분류는
5일 수익률이 음수 쪽이고
RSI도 낮아진 장면을 본다.
Ref:
`jackal/hunter.py:987-993`
결론:
부분 중복은 있으나
직접 대체는 아니다.
### 2.2.2 상승 가속류 signal 존재 여부
[검증됨]
현재 코드에는
다음 성격의 deterministic signal이 없다.
시장 benchmark 대비 leader 선별
신고가 돌파 지속
trend continuation after breakout
candlestick continuation confirmation
momentum acceleration scoring
근거:
quality_engine pre-rule에 없다.
Ref:
`jackal/quality_engine.py:26-53`
근거:
family taxonomy에도 없다.
Ref:
`jackal/families.py:7-109`
근거:
현재 baseline은
최근 급등과 과열에 불리하다.
Ref:
`jackal/hunter.py:640-642`
`jackal/hunter.py:670-676`
`jackal/quality_engine.py:217-227`
결론:
원 요청을 정면으로 수용하려면
새 scoring 축 또는 새 family가 필요할 가능성이 높다.
## 2.3 candle pattern 현재 상태
### 2.3.1 현재 있는 것
[검증됨]
OHLCV fetch는 이미 있다.
Ref:
`jackal/market_data.py:431-471`
[검증됨]
simple bullish candle 판단은 있다.
Ref:
`jackal/hunter.py:585-590`
[검증됨]
backtest도 historical OHLC를 읽는 구조가 있다.
Ref:
`jackal/backtest.py:88-161`
### 2.3.2 현재 없는 것
[검증됨]
Hammer 계산 없음
[검증됨]
Doji 계산 없음
[검증됨]
Morning Star 계산 없음
[검증됨]
Engulfing 계산 없음
[검증됨]
body / shadow 비율 helper 없음
[검증됨]
다중 봉 조합 pattern helper 없음
근거:
repo 검색에서
`hammer`
`doji`
`morning star`
`candlestick`
`망치`
`도지`
`샛별`
직접 구현 흔적을 찾지 못했다.
실행일:
2026-04-23
### 2.3.3 quality_engine와의 연결 여부
[검증됨]
quality_engine는
candlestick pattern input을 받지 않는다.
Ref:
`jackal/quality_engine.py:26-53`
[검증됨]
따라서 pattern을 넣으려면
pattern detection 함수뿐 아니라
score integration도 새로 필요하다.
## 2.4 학문적 주의
### 2.4.1 차트 패턴 예측력 논란
[검증됨]
Japanese candlestick charting은
실무 문화에서 널리 쓰이지만,
학문적으로는 일관된 alpha 근거가 약하다.
[검증됨]
이번 조사에서 직접 확인한 참고문헌 중
Marshall et al. 2007
`The profitability of Japanese candlestick charting in the U.S. equities market`
은
candlestick rule의 통계적/경제적 유의성이 약하다는 방향의 근거로 자주 인용된다.
[의견]
따라서 candle pattern은
핵심 signal보다
보조 annotation 또는 tie-breaker로 취급하는 편이 정직하다.
### 2.4.2 momentum factor와의 구분
[검증됨]
원 요청의
`상승 지속 확률`
은 본질적으로 momentum factor 문제다.
[검증됨]
Jegadeesh & Titman 1993은
momentum 문헌의 대표 출발점이다.
[검증됨]
그러나 이 문헌은 주로
수개월 단위 winner/loser 지속성의 근거이지,
`내일 상승 확률`
을 직접 보장하는 문헌은 아니다.
### 2.4.3 short horizon 주의
[의견]
일 단위 continuation 예측은
noise,
event shock,
regime shift 영향이 훨씬 크다.
[의견]
따라서
`내일도 상승할 가능성이 높은 종목`
이라는 문구는
backtest 없이 쓰기 위험하다.
### 2.4.4 결론
[검증됨]
원 요청 전체에서
상대적으로 학문 근거가 강한 부분은 momentum이다.
[검증됨]
원 요청 전체에서
가장 약한 부분은 candle pattern이다.
## 2.5 구현 필요 단위
원 요청을 실제 기능으로 만들려면
아래 단위가 필요하다.
시장 상승장 정의
종목 continuation 정의
pattern detection 함수
score 통합 규칙
alert 설명 문구
backtest 비교 레이어
## 2.6 현재 코드와의 거리
### 2.6.1 가까운 점
OHLCV는 이미 있다.
historical backtest 기반도 있다.
alert 생성 위치도 명확하다.
### 2.6.2 먼 점
continuation 친화적 family가 없다.
candle pattern recognition이 없다.
quality_engine 입력 구조에 pattern slot이 없다.
현재 점수 구조는 과열 continuation에 우호적이지 않다.
## 2.7 예상 구현 범위 메모
[의견]
if 승인 시 예상 터치포인트는 아래다.
`jackal/candle_patterns.py`
`jackal/quality_engine.py`
`jackal/market_data.py`
`jackal/hunter.py`
`jackal/families.py`
`jackal/backtest.py`
[의견]
사용자 제시치인
300-500 lines는
pattern 종류를 적게 잡으면 가능할 수 있다.
[의견]
다만 검증까지 포함하면
실제 작업량은 그보다 커질 가능성이 높다.
## 2.8 backtest 요구사항
도입 전 최소 확인 항목:
Day1 hit
7일 peak hit
MAE
regime slice별 성능
기존 신호 대비 incremental value
[검증됨]
현재 backtest outcome 정의는 이미 있다.
Ref:
`jackal/backtest.py:228-255`
`d1_hit` 기준:
다음날 수익률 > 0.3%
`swing_hit` 기준:
첫 7일 peak >= 1.0%
## 2.9 tentative 권장
[의견]
원 요청의 candle pattern은
현재 시점에서는 보류가 합리적이다.
보류 사유 1:
baseline과 결이 다르다.
보류 사유 2:
학문 근거가 약하다.
보류 사유 3:
RS와 52주 신고가라는 더 강한 대안이 있다.
보류 사유 4:
Request 2와 Request 3이 더 빠른 사용자 가치가 있다.
# Section 3: Request 1 Extension - Alternative Signals
## 3.1 RS (Relative Strength)
### 3.1.1 개념
RS는
개별 종목이
benchmark 또는 peer보다 얼마나 강한지 보는 신호다.
이번 요청 맥락에서는
`상승장 안에서도 더 강한 종목을 추려 내는 필터`
역할을 한다.
### 3.1.2 현재 JACKAL에 있는 유사 요소
[검증됨]
Hunter에는
sector ETF 대비 상대 낙폭 계산이 있다.
Ref:
`jackal/hunter.py:722-740`
[검증됨]
이 로직은
sector보다 더 많이 빠진 종목을 반등 후보로 보는 쪽이다.
[검증됨]
즉,
market benchmark relative strength와는 다르다.
### 3.1.3 현재 JACKAL에 없는 것
[검증됨]
SPY / QQQ / KOSPI 대비 종목 RS line이 없다.
[검증됨]
RS percentile도 없다.
[검증됨]
benchmark-relative continuation family도 없다.
### 3.1.4 데이터 요구
[검증됨]
필요한 추가 데이터는 benchmark 가격 시계열 정도다.
미국주 후보 benchmark:
`SPY` 또는 `QQQ`
한국주 후보 benchmark:
`^KS11` 또는 KOSPI proxy
[검증됨]
현재 1년 daily history fetch 구조와 잘 맞는다.
Ref:
`jackal/market_data.py:431-471`
### 3.1.5 구현 난이도
[의견]
낮음~중간이다.
단순 버전:
최근 N일 종목 수익률 - benchmark 수익률
조금 더 나은 버전:
가격 / benchmark 비율선의 기울기
고급 버전:
multi-window percentile
### 3.1.6 학문적 근거
[검증됨]
RS는 이번 후보 중 가장 강한 근거를 가진다.
대표 문헌:
Jegadeesh & Titman 1993
주의:
이 문헌은 장기 momentum 근거이지,
1일 continuation 보증은 아니다.
그럼에도
candle pattern보다 학문적으로 훨씬 방어 가능하다.
### 3.1.7 기존 signal과의 중복
[검증됨]
중복은 부분적이다.
중복되는 부분:
sector-relative underperformance
중복되지 않는 부분:
market benchmark relative strength
중복되지 않는 부분:
leader selection logic
### 3.1.8 quality score나 family에 넣는 방식
방식 A:
새 family 추가
장점:
continuation identity가 분명하다.
단점:
family 수가 늘고 probability summary도 새 family를 학습해야 한다.
방식 B:
quality component 추가
장점:
기존 구조에 잘 들어간다.
단점:
leader 전략의 정체성이 약해질 수 있다.
방식 C:
filter + boost만 적용
장점:
보수적 도입이 쉽다.
단점:
사용자 체감이 작을 수 있다.
### 3.1.9 tentative 권장
[의견]
RS는 Extension 후보 중 1순위다.
## 3.2 52주 신고가 근접
### 3.2.1 개념
현재가가 52주 high에 얼마나 가까운지 보고,
breakout 직전 또는 강세 지속 가능성을 보는 접근이다.
### 3.2.2 현재 JACKAL overlap
[검증됨]
52주 high / low 기반 위치 값은 이미 계산된다.
Ref:
`jackal/market_data.py:397-415`
[검증됨]
현재 점수화되는 것은
`52w_low_zone`
뿐이다.
Ref:
`jackal/quality_engine.py:41`
`jackal/quality_engine.py:115-127`
[검증됨]
즉,
현재는 52주 저점권 반등은 보지만,
52주 고점권 continuation은 보지 않는다.
### 3.2.3 구현 난이도
[의견]
매우 낮다.
이유:
기초 데이터가 이미 있다.
이유:
threshold 설계만으로 1차 버전이 가능하다.
예시:
`52w_pos >= 90`
예시:
`52w_pos >= 95 and volume support`
### 3.2.4 학문적 근거
[검증됨]
George & Hwang 2004
`The 52-Week High and Momentum Investing`
은
이번 후보 중 매우 강한 근거를 제공한다.
### 3.2.5 기존 signal과의 중복
[검증됨]
완전 중복은 아니다.
부분 overlap은 있다.
이미 있는 것:
`52w_pos`
이미 있는 것:
`52w_low_zone`
새로 추가되는 것:
high-side proximity or breakout persistence
### 3.2.6 tentative 권장
[의견]
52주 신고가 근접은 RS 다음 2순위다.
## 3.3 Volume Profile (매물대)
### 3.3.1 개념
가격대별 누적 거래량을 쌓아
지지/저항 성격이 강한 가격대를 찾는 접근이다.
### 3.3.2 현재 JACKAL overlap
[검증됨]
현재 JACKAL에는 Volume Profile / POC가 없다.
[검증됨]
하지만 유사한 기초는 있다.
`ma_support`
`vol_ratio`
`vol_trend_5d`
`vol_accumulation`
Ref:
`jackal/market_data.py:361-395`
`jackal/quality_engine.py:118-130`
### 3.3.3 구현 난이도
[의견]
중간이다.
이유:
계산보다 signal 정의가 어렵다.
결정할 것:
window 길이
결정할 것:
bucket 크기
결정할 것:
POC와 현재가 관계를 점수로 바꾸는 규칙
결정할 것:
MA support와의 차별 설명
### 3.3.4 학문적 근거
[검증됨]
직접적인 Volume Profile alpha 근거는
이번 조사에서 강하게 확보하지 못했다.
[의견]
실무 근거는 있으나,
RS/52주 신고가보다 학문 방어력은 약하다.
### 3.3.5 tentative 권장
[의견]
우선순위는 중간이다.
## 3.4 Volatility Contraction (Squeeze)
### 3.4.1 개념
변동성이 수축했다가 확장되는 구간을 보고
breakout 준비 상태를 추정하는 접근이다.
### 3.4.2 현재 JACKAL overlap
[검증됨]
`bb_width`가 이미 있다.
Ref:
`jackal/market_data.py:380`
[검증됨]
`bb_expanding`도 이미 있다.
Ref:
`jackal/market_data.py:381-387`
[검증됨]
Scanner prompt에도 `bb_width`가 노출된다.
Ref:
`jackal/scanner.py:593-596`
[검증됨]
그러나 explicit squeeze flag는 없다.
Ref:
`docs/orca_v2_backlog.md:136-160`
### 3.4.3 구현 난이도
[의견]
낮다.
이유:
핵심 원재료가 이미 있다.
남는 일:
compression threshold 정의
남는 일:
expansion 확인 기간 정의
남는 일:
방향성 결합 규칙 설계
### 3.4.4 학문적 근거
[의견]
실무 사용은 넓지만,
정량 근거는 RS/52주 신고가보다 약하다.
### 3.4.5 기존 signal과의 중복
[검증됨]
BB 계열과의 중복이 크다.
### 3.4.6 tentative 권장
[의견]
우선순위는 중간 이하다.
## 3.5 Accumulation (장기 매집)
### 3.5.1 개념
OBV,
A/D line,
누적적 volume-price 흐름을 통해
조용한 매집 구간을 찾는 접근이다.
### 3.5.2 현재 JACKAL overlap
[검증됨]
현재 `vol_accumulation` heuristic은 이미 있다.
Ref:
`jackal/market_data.py:389-395`
[검증됨]
하지만 이 값은
장기 매집 모델이 아니라,
`하락 + 거래량 증가`
에 가까운 간단한 rule이다.
[검증됨]
quality_engine도 이 heuristic을 적극 사용한다.
Ref:
`jackal/quality_engine.py:42`
`jackal/quality_engine.py:118-130`
### 3.5.3 현재 없는 것
OBV 없음
A/D line 없음
장기 매집 종료 감지 없음
분출 직전 판단 로직 없음
### 3.5.4 구현 난이도
[의견]
중간~높음이다.
이유:
OBV 계산은 쉽지만,
`매집 중`
과
`매집 완료`
를 구분하기 어렵다.
### 3.5.5 학문적 근거
[의견]
거래량 관련 문헌은 존재하지만,
장기 매집 종료 후 분출 timing을 강하게 뒷받침하는 직접 근거는 이번 조사 범위에서 제한적이었다.
### 3.5.6 tentative 권장
[의견]
우선순위는 낮다.
## 3.6 비교표
| 접근 | 학문적 근거 | 구현 복잡도 | 기존 signal과 중복 | 우선순위 (tentative) |
|---|---|---|---|---|
| 차트 패턴 (원 요청) | 약함 | 중간 | 부분 중복 (`bullish_candle`만 존재) | 낮음 / 보류 |
| RS | 강함 | 낮음~중간 | 부분 중복 (sector-relative만 존재) | 매우 높음 |
| 52주 신고가 근접 | 강함 | 매우 낮음 | 부분 중복 (`52w_pos`, `52w_low_zone`) | 매우 높음 |
| Volume Profile | 중간 이하 | 중간 | 부분 중복 (`ma_support`, volume 계열) | 중간 |
| Squeeze | 약함 | 낮음 | 중복 큼 (`bb_width`, `bb_expanding`) | 중간 이하 |
| 매집 감지 | 중간 이하 | 중간~높음 | 부분 중복 (`vol_accumulation`) | 낮음 |
## 3.7 추천 로드맵 (tentative)
[의견]
가장 자연스러운 순서는 아래다.
1.
RS
2.
52주 신고가 근접
3.
Volume Profile 또는 Squeeze
4.
Accumulation
5.
candle pattern
[의견]
원 요청의 직관은 유지하되,
실제 구현은 candle보다 RS/52w 쪽에서 시작하는 것이 더 낫다.
# Section 4: Request 2 - 추천 이유 상세화
## 4.1 현재 message/report 분석
### 4.1.1 Hunter message
[검증됨]
Hunter alert는
설명 조각이 짧다.
Ref:
`jackal/hunter.py:1472-1493`
핵심 조각:
`hunt_reason`
핵심 조각:
`bull_case`
핵심 조각:
`main_risk`
[검증됨]
즉,
왜 추천했는지 길게 읽히는 구조는 아니다.
### 4.1.2 Scanner message
[검증됨]
Scanner alert는 Hunter보다 풍부하지만,
여전히 점수 카드형이다.
Ref:
`jackal/scanner.py:847-972`
보여 주는 것:
score / signal_type / confidence
보여 주는 것:
peak day / swing_acc / MAE
보여 주는 것:
signals display
보여 주는 것:
짧은 bull_case
보여 주는 것:
Devil 한 줄
### 4.1.3 report.json
[검증됨]
`jackal_candidate_review`는
후보별 장문 설명을 쌓는 객체가 아니라
집계와 하이라이트 요약이다.
Ref:
`orca/analysis_review.py:344-365`
`orca/analysis_review.py:499-513`
[검증됨]
샘플 report에서 reviewed_count가 0이면
설명도 사실상 비어 있다.
Ref:
`reports/2026-04-22_morning.json:126-146`
## 4.2 즉시 개선 가능 영역
[검증됨]
새 데이터 없이도 아래는 바로 개선 가능하다.
`signals_fired` 나열
`quality.reasons` 상위 3개 서술
canonical family 설명
regime / trend 맥락 연결
Devil 반론 분리 노출
peak day / MAE를 이용한 스윙 적합성 설명
근거:
`jackal/quality_engine.py:83-130`
`jackal/scanner.py:879-945`
`jackal/scanner.py:1500-1535`
## 4.3 추가 데이터가 필요한 영역
유사 과거 패턴 검색
benchmark 대비 RS 문구
historical similarity 기반 추천 이유
섹터 percentile 비교
family별 regime-sliced 성능의 실시간 설명
## 4.4 스윙 적합성 설명에 이미 있는 재료
[검증됨]
Hunter는 `day1_score`와 `swing_score`를 분리한다.
Ref:
`jackal/hunter.py:1221-1227`
[검증됨]
Scanner는 signal별 peak day / swing_acc / MAE 기본값을 보여 준다.
Ref:
`jackal/scanner.py:882-945`
[의견]
따라서
`왜 스윙에 좋은지`
는 새 모델 없이도 꽤 괜찮게 설명할 수 있다.
## 4.5 확률 제공 주의사항
[검증됨]
현재 코드에서 확률처럼 보이는 숫자는 두 종류다.
종류 A:
Hunter의 `day1_score`, `swing_score`
종류 B:
probability summary의 `probability_win_rate`
[검증됨]
A는 모델 점수 성격이 강하다.
Ref:
`jackal/hunter.py:1221-1227`
[검증됨]
B는 qualified sample이 있을 때만 의미가 있다.
Ref:
`jackal/probability.py:36-51`
[검증됨]
sample report에서는
qualified sample이 0인 경우가 있다.
Ref:
`reports/2026-04-22_morning.json:148-166`
[의견]
따라서 제품 문구는
`검증된 확률`
과
`내부 점수 기반 의견`
을 분리해야 한다.
## 4.6 구현 난이도 분류
쉬움:
템플릿 개선
쉬움:
reasons 재배열
쉬움:
Devil 한 줄 분리
중간:
quality breakdown UI
중간:
regime/MAE/swing suitability 설명 강화
어려움:
historical similarity
어려움:
검증된 확률 수치 노출
## 4.7 tentative 권장
[의견]
Request 2는 즉시 구현 세션으로 가져가도 된다.
[의견]
새 signal 추가보다 먼저 해도 사용자 만족이 높을 가능성이 크다.
# Section 5: Request 3 - Devil Silent 조사
## 5.1 현재 Devil 구현
### 5.1.1 ORCA Devil
[검증됨]
ORCA Devil prompt는
시장 레벨 counter-argument agent다.
Ref:
`orca/agents.py:371-440`
### 5.1.2 Hunter Devil
[검증됨]
Hunter Devil prompt는
`main_risk`를 핵심 텍스트 필드로 요구한다.
Ref:
`jackal/hunter.py:1188-1194`
[검증됨]
parse 성공 후에도 `main_risk` 기본값은 빈 문자열이다.
Ref:
`jackal/hunter.py:1201-1205`
[검증됨]
예외 fallback에서도 `main_risk`는 빈 문자열이다.
Ref:
`jackal/hunter.py:1207-1211`
### 5.1.3 Scanner Devil
[검증됨]
Scanner Devil prompt는
`objections` 배열을 요구한다.
Ref:
`jackal/scanner.py:703-710`
[검증됨]
no JSON block fallback은 `objections: []`를 반환한다.
Ref:
`jackal/scanner.py:719-724`
[검증됨]
예외 fallback도 `objections: []`를 반환한다.
Ref:
`jackal/scanner.py:725-728`
## 5.2 Silent 원인 분류 (a-e)
(a)
Devil이 실제로 강한 반박이 없었다.
(b)
Devil 호출이 실패했다.
(c)
Devil 응답은 있었지만 parsing이 실패했다.
(d)
응답은 있었지만 Telegram 포맷에서 생략됐다.
(e)
prompt 또는 schema가 `반박 없음` 상태를 명확히 요구하지 않는다.
## 5.3 현재 코드 기준 실제 경로 분석
### 5.3.1 Hunter 경로
[검증됨]
Hunter alert는 Devil line을 항상 출력한다.
Ref:
`jackal/hunter.py:1485-1487`
[검증됨]
그런데 `main_risk`가 빈 문자열일 수 있다.
Ref:
`jackal/hunter.py:1201-1211`
따라서 Hunter에서는
보이는 형태가
`줄은 있는데 내용이 비어 보임`
일 수 있다.
### 5.3.2 Scanner 경로
[검증됨]
Scanner는 첫 objection이 없으면
Devil 설명을 생략하거나 verdict만 보여 준다.
Ref:
`jackal/scanner.py:869-873`
`jackal/scanner.py:965-969`
따라서 Scanner에서 사용자가 느끼는 silent는
실제 반박 없음,
fallback,
render 생략이 모두 섞여 있을 수 있다.
## 5.4 과거 로그 흔적
[검증됨]
`jackal/hunt_log.json` 표본에서
`부분동의, 30`이 8건,
`반대, 78`이 2건이었다.
실행일:
2026-04-23
[검증됨]
하지만 hunt log는 `main_risk`를 저장하지 않는다.
Ref:
`jackal/hunter.py:1748-1760`
[검증됨]
즉,
현재 로그만으로
(a) 실제 반박 없음
과
(b)/(c) fallback성 빈 값
을 구분할 수 없다.
## 5.5 silent 상태의 의미 구분
[의견]
현재 사용자가 보는 `Devil이 조용함`은
아래 중 무엇인지 알 수 없다는 점이 핵심 문제다.
의미 1:
건강한 무반박
의미 2:
파싱 실패
의미 3:
API 실패
의미 4:
render suppress
의미 5:
약한 반박이 있었지만 짧게 잘림
## 5.6 원인별 검증 방법
원인 a 확인:
no_objection 상태 필드 저장
원인 b 확인:
API exception 카운트 저장
원인 c 확인:
parse_ok 불리언 저장
원인 d 확인:
rendered_comment_length 또는 display_status 저장
원인 e 확인:
prompt에서 명시 상태 강제
## 5.7 tentative 권장
[의견]
가장 먼저 필요한 것은
silent state taxonomy와 logging이다.
[의견]
그 다음이 Telegram 문구 분리다.
예:
`Devil: 반박 없음`
예:
`Devil: 응답 실패`
예:
`Devil: 파싱 실패`
예:
`Devil: 약한 반박만 존재`
# Section 6: 우선 순위 및 의존
## 6.1 요청 간 관계
[검증됨]
Request 2는 새 signal 없이도 진행 가능하다.
[검증됨]
Request 3도 새 alpha 개발과 별개로 진행 가능하다.
[검증됨]
Request 1 계열은 backtest 의존도가 가장 높다.
## 6.2 권장 순서
[의견]
즉시:
Request 2 설명 상세화
[의견]
즉시:
Request 3 Devil silent 구분
[의견]
중기:
Request 1 Extension A RS
[의견]
중기:
Request 1 Extension B 52주 신고가 근접
[의견]
장기:
Volume Profile / Squeeze / Accumulation
[의견]
보류:
Request 1 원 요청의 candle pattern
## 6.3 왜 이 순서가 좋은가
이 순서는
사용자 체감 가치,
구현 난이도,
학문 근거,
검증 가능성을 함께 만족한다.
# Section 7: 각 요청의 도입 전 조건
## 7.1 Request 1 (candle) 도입 전 필요
pattern 정의 명문화
pattern 단독 성능 검증
기존 signal 대비 비교
1년 이상 backtest
win rate + expectancy + MAE 확인
## 7.2 Request 1 Extension 도입 전 필요
RS:
benchmark 규칙 확정
RS:
market별 benchmark 매핑 확정
52주 신고가:
threshold 확정
52주 신고가:
volume filter 동반 여부 결정
Volume Profile:
window / bucket / POC 규칙 설계
Squeeze:
compression과 expansion 정의 설계
Accumulation:
OBV/A-D 도입 여부와 기존 heuristic 관계 확정
## 7.3 Request 2 도입 전 필요
쉬운 부분:
템플릿 설계와 리뷰
어려운 부분:
확률 문구의 기준 확정
## 7.4 Request 3 도입 전 필요
silent taxonomy 확정
로그 저장 필드 확정
사용자-facing 상태 문구 확정
# Section 8: Backtest 인프라 현황
## 8.1 JACKAL backtest
[검증됨]
`jackal/backtest.py`는 historical indicator 계산을 이미 제공한다.
Ref:
`jackal/backtest.py:88-161`
[검증됨]
결과 추적 기준도 이미 있다.
Ref:
`jackal/backtest.py:228-255`
Day1 hit 기준:
다음날 수익률 > 0.3%
Swing hit 기준:
첫 7일 peak >= 1.0%
## 8.2 probability summary 인프라
[검증됨]
ORCA run cycle은 probability summary를 report에 붙인다.
Ref:
`orca/run_cycle.py:352-372`
[검증됨]
qualified sample이 있어야 probability adjustment가 의미를 가진다.
Ref:
`jackal/probability.py:36-51`
## 8.3 새 signal별 backtest 가능 여부
RS:
가능
52주 신고가:
가능
Volume Profile:
가능하나 정의 설계 필요
Squeeze:
가능
Accumulation:
가능하나 라벨링과 정의가 어려움
Candle pattern:
가능하나 학문적 보수성이 필요
# Section 9: 결론 및 다음 세션 진입점
## 9.1 요청별 상태 요약
Request 2 쉬운 부분:
즉시 구현 가능
Request 3:
즉시 조사 기반 fix 세션 가능
Request 1 원 요청:
보류 권장
Request 1 Extension A RS:
다음 구현 세션 우선 후보
Request 1 Extension B 52주 신고가:
그 다음 후보
## 9.2 최종 권장
[의견]
가장 좋은 순서는 아래다.
1.
설명 강화
2.
Devil silent 상태 구분
3.
RS
4.
52주 신고가 근접
5.
Volume Profile 또는 Squeeze
6.
Accumulation
7.
candle pattern
## 9.3 다음 세션 진입점
세션 A:
Telegram 설명 템플릿 개선
세션 B:
Devil 상태 로깅 및 표시 개선
세션 C:
RS signal 설계 + backtest 범위 정의
세션 D:
52주 신고가 proximity 설계
# Appendix A: 코드 근거 인덱스
- core 역할: `jackal/core.py:1-11`
- core 실행 흐름: `jackal/core.py:55-90`
- README session 설명: `README.md:79-85`
- git 부재 caveat: `README.md:97-101`
- workflow overview: `.github/workflows/orca_jackal.yml:1-18`
- workflow Hunter step: `.github/workflows/orca_jackal.yml:62-83`
- workflow Scanner step: `.github/workflows/orca_jackal.yml:84-97`
- canonical families: `jackal/families.py:7-15`
- canonical mapping: `jackal/families.py:33-109`
- Hunter technical snapshot: `jackal/hunter.py:540-600`
- Hunter stage1 scoring: `jackal/hunter.py:609-744`
- Hunter swing type: `jackal/hunter.py:946-1003`
- Hunter Devil prompt: `jackal/hunter.py:1124-1211`
- Hunter day1/swing note: `jackal/hunter.py:1221-1227`
- Hunter alert: `jackal/hunter.py:1472-1493`
- Hunter persisted devil fields: `jackal/hunter.py:1748-1760`
- Scanner pre-rule signals: `jackal/quality_engine.py:26-53`
- Scanner raw family: `jackal/quality_engine.py:54-63`
- quality reasons core: `jackal/quality_engine.py:83-130`
- quality veto: `jackal/quality_engine.py:200-230`
- uncertainty gate: `jackal/quality_engine.py:257-306`
- family skip thresholds: `jackal/quality_engine.py:334-383`
- final judgment: `jackal/quality_engine.py:385-437`
- market_data technicals: `jackal/market_data.py:343-418`
- technical fetch: `jackal/market_data.py:431-471`
- Scanner Devil: `jackal/scanner.py:651-728`
- Scanner alert: `jackal/scanner.py:847-972`
- Scanner persisted payload: `jackal/scanner.py:1500-1535`
- backtest module overview: `jackal/backtest.py:1-23`
- backtest indicators: `jackal/backtest.py:88-161`
- backtest outcome tracking: `jackal/backtest.py:228-255`
- probability helper: `jackal/probability.py:18-59`
- ORCA Devil system: `orca/agents.py:371-440`
- candidate review summary: `orca/analysis_review.py:344-525`
- candidate review attach: `orca/postprocess.py:96-155`
- probability summary attach: `orca/run_cycle.py:352-372`
- sample report candidate review empty: `reports/2026-04-22_morning.json:126-146`
- sample report probability summary empty: `reports/2026-04-22_morning.json:148-166`
- backlog RS note: `docs/orca_v2_backlog.md:115-134`
- backlog squeeze note: `docs/orca_v2_backlog.md:136-160`
- current-signals baseline map: `docs/jackal/current-signals.md:1065-1093`
# Appendix B: 학문 참고 문헌 메모
- Jegadeesh & Titman (1993)
- 메모: momentum factor의 대표 고전이다.
- 메모: 다만 주로 중기 horizon 근거로 읽어야 한다.
- 메모: 1일 continuation 보증 문헌으로 읽으면 안 된다.
- George & Hwang (2004)
- 메모: 52주 신고가 근접이 momentum 설명에 유의미하다는 대표 문헌이다.
- 메모: 이번 후보 중 52주 신고가 근접의 학문 근거를 가장 직접적으로 뒷받침한다.
- Marshall et al. (2007)
- 메모: 일본식 candlestick charting의 U.S. equities 수익성에 회의적 근거로 자주 인용된다.
- 메모: candle pattern을 핵심 alpha로 도입하기 전에 보수적으로 보게 만드는 문헌이다.
- Lo & MacKinlay (1988)
- 메모: random walk를 단순하게 이해하면 안 된다는 점을 환기한다.
- 메모: 하지만 짧은 horizon pattern 예측을 쉽게 만들어 주지는 않는다.
# Appendix C: 출력/설명 필드 인벤토리
- Hunter alert 필드: ticker/name/price/change/final_score/day1_score/swing_score/RSI/BB/vol_ratio/hunt_reason/bull_case/main_risk/entry/target/stop/expected_days/swing_type
- Scanner alert 필드: score/signal_type/confidence/peak_day/swing_acc/MAE/Analyst/Devil/Final/signals_display/bull_case/Devil objection
- Persisted scanner payload 필드: signal_family/signal_family_raw/signal_family_label/analyst_score/analyst_confidence/signals_fired/bull_case/devil_score/devil_verdict/devil_objections/thesis_killer_hit/killer_detail/final_score/signal_type/is_entry/reason/probability_adjustment/probability_samples/probability_win_rate
- Request 2 재활용 가능 필드: signals_fired
- Request 2 재활용 가능 필드: quality.reasons
- Request 2 재활용 가능 필드: signal_family / signal_family_label
- Request 2 재활용 가능 필드: orca_regime / orca_trend
- Request 2 재활용 가능 필드: peak_day / swing_acc / MAE
- Request 2 재활용 가능 필드: devil_objections
- Request 2 재활용 가능 필드: probability_samples / probability_win_rate
# Appendix D: Devil silent 증거 맵
- 증거 1: Hunter는 parse 후 main_risk 기본값이 빈 문자열이다. Ref: `jackal/hunter.py:1201-1205`
- 증거 2: Hunter는 예외 fallback에서도 main_risk가 빈 문자열이다. Ref: `jackal/hunter.py:1207-1211`
- 증거 3: Hunter alert는 Devil line을 항상 출력한다. Ref: `jackal/hunter.py:1485-1487`
- 증거 4: Scanner는 첫 objection이 없으면 Devil 설명을 생략하거나 verdict만 보여 준다. Ref: `jackal/scanner.py:869-873`, `jackal/scanner.py:965-969`
- 증거 5: Scanner no JSON block fallback은 objections 빈 배열을 반환한다. Ref: `jackal/scanner.py:719-724`
- 증거 6: Scanner 예외 fallback도 objections 빈 배열을 반환한다. Ref: `jackal/scanner.py:725-728`
- 증거 7: Hunt log에는 devil_verdict와 devil_score는 있으나 main_risk는 저장되지 않는다. Ref: `jackal/hunter.py:1748-1760`
- 증거 8: 현재 hunt_log 표본에서는 부분동의 30 점수가 다수다. 실행일: 2026-04-23
- 판단 메모: silent는 실제 무반박과 fallback을 현 로그만으로는 구분할 수 없다.
- 권장 메모: no_objection / api_failed / parse_failed / render_suppressed 상태를 분리 저장하는 편이 좋다.
# Appendix E: 요청별 체크리스트
## Request 1 원 요청
- 시장 상승장 정의를 먼저 고정할 것
- 종목 continuation 정의를 candle과 분리할 것
- pattern은 독립 alpha가 아니라 보조 신호로 시작할 것
- Hammer/Doji/Morning Star 정의를 숫자로 명시할 것
- quality_engine에 pattern slot을 넣을지 별도 helper로 둘지 결정할 것
- 기존 overheat penalty와 충돌 여부를 확인할 것
- backtest에서 existing rebound family와 비교할 것
- Telegram에서 확률 문구를 바로 노출하지 말 것
## Request 1 Extension RS
- 미국주 benchmark를 SPY로 할지 QQQ로 할지 결정할 것
- 한국주 benchmark를 KOSPI로 고정할지 종목군별로 다르게 둘지 결정할 것
- 단순 초과수익률 버전과 ratio-line 버전을 비교할 것
- new family vs quality component 방식을 선택할 것
- regime별 성능 차이를 별도 집계할 것
- 과열 추격 신호로 변질되지 않도록 volume/MAE도 같이 볼 것
## Request 1 Extension 52주 신고가
- 52w_pos threshold를 90/95/98 중 어디에 둘지 실험할 것
- 신고가 근접과 실제 돌파를 구분할 것
- 거래량 동반 여부를 필터로 둘지 결정할 것
- 기존 52w_low_zone과 family 수준에서 공존 가능한지 확인할 것
- false breakout 비율을 체크할 것
## Request 1 Extension Volume Profile
- window를 3개월/6개월/1년 중 무엇으로 둘지 정할 것
- bucket granularity를 어떻게 둘지 정할 것
- POC와 현재가 거리의 score 변환 규칙을 정할 것
- 지지/저항 해석이 MA support와 어떻게 다른지 문구를 만들 것
- OHLCV만으로 충분한지 거래대금 보정이 필요한지 확인할 것
## Request 1 Extension Squeeze
- bb_width percentile 기준을 정할 것
- expansion 확인 기간을 1일/3일/5일 중 무엇으로 둘지 정할 것
- 방향성 결정에 RS/volume을 함께 쓸지 정할 것
- 독립 signal보다 filter로 시작할지 결정할 것
## Request 1 Extension Accumulation
- OBV 도입 여부를 먼저 정할 것
- A/D line을 같이 볼지 정할 것
- 단순 vol_accumulation heuristic과의 관계를 정리할 것
- 매집 종료와 분출 시작을 어떤 수치로 볼지 좁힐 것
## Request 2 설명 상세화
- 긴 설명과 짧은 카드 문구를 분리할 것
- 신호 이유와 반론을 같이 보여 줄지 정할 것
- 확률 문구는 qualified sample이 있을 때만 허용할 것
- 왜 스윙에 좋은지와 왜 당일 추격이 위험한지를 함께 설명할 것
- family별 기본 템플릿을 만들 것
## Request 3 Devil silent
- silent taxonomy를 확정할 것
- state log 필드를 설계할 것
- fallback 기본값과 no-objection을 구분할 것
- Hunter와 Scanner의 렌더링 차이를 통일할지 결정할 것
- Telegram에서 사용자에게 어떻게 보여 줄지 문구를 정할 것
