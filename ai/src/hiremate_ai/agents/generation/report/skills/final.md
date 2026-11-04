---
name: final
description: 채용 최종 리포트. 채용을 종료할 때 모든 전형의 흐름과 최종 합격자를 정리한다
---
# 채용 최종 리포트

읽을 자료: get_overview(전형, 지표, 영역) → count_values(*.decision) → get_values(영역 점수 key) → 최종 합격자 get_evidence.

범위는 채용의 모든 전형이다. 지원자는 첫 전형 지원자 전원이고, 뒤 전형 값은 그 전형까지 간 지원자에게만 있다.
최종 합격자는 마지막 전형 결정(<마지막 전형>.decision)이 합격(PASS)인 지원자다.

## 섹션 구성

자료가 있는 부품만 쓴다. get_overview의 지표 · 값 key를 보고 고른다.

1. 한눈에 보기
   - kpi: 지원 · 최종 합격 · 최종 합격률 · 전형별 합격 지표
   - tally(by=key): 전형마다 결정 key(document.decision, interview.decision 등). 전형별 합격 · 불합격 비율이 채용 흐름이다
   - composition: 전체 · 최종 합격자의 경력 구간 지표
2. 전형 사이 흐름 (결정 key가 둘 이상이면)
   - cross: rowKey=앞 전형 결정, colKey=뒤 전형 결정. 두 전형을 모두 거친 지원자만 센다
3. 영역(전형)마다 섹션 하나. 영역 id는 전형이다. get_overview에서 그 영역에 점수 key가 있는지 먼저 본다
   - 점수 key가 있는 영역(평가 등): distribution에 그 점수 key, split에 그 전형 결정 key. 합격 · 불합격의 점수 분포를 견준다.
     영역 점수 key가 여럿이면 bar로 최종 합격자의 영역 점수를 더한다
   - 점수 key가 없는 영역(서류): 점수 분포를 그리지 않는다. 결정 key(*.decision)와 판정 key는 숫자가 아니라 distribution ·
     bar · radar에 넣을 수 없다. tally(by=key)로 심사 항목(document.criterion.*) 두 개 이상의 판정 비율을 그린다
   - 영역이 없는 전형(점수 없는 면접): 따로 섹션을 두지 않는다. 그 전형 결정은 한눈에 보기의 tally와 전형 사이 흐름에 나온다
   - radar · bar · table의 applicants는 최종 합격자만, 5명까지 넣는다
   - donut · composition은 같은 group의 지표만 한 부품에 넣는다 (get_overview의 지표 group)
4. 최종 합격자
   - table: 최종 합격자의 전형별 점수 · 결정 key
   - evidence: 최종 합격자마다 근거 한두 개. 근거가 없으면 '확인되지 않았어요'

문장에는 판정 코드(PASS · FAIL · MET)를 쓰지 않고 합격 · 불합격 · 충족처럼 화면 말로 쓴다.

## 요약에 담을 것

지원부터 최종 합격까지 인원이 어떻게 줄었는지, 최종 합격자가 공통으로 보인 점, 다음 채용에서 다시 볼 점(보류가 많았던 항목 등).
최종 합격자를 서로 견주어 순위를 매기거나 누가 더 낫다고 쓰지 않는다.
