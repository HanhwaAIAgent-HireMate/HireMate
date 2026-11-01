---
name: stage-document
description: 서류 전형 결과 리포트. 결과 확정 때 전형 전체를 정리한다
---
# 서류 전형 결과 리포트

읽을 자료: get_overview(지표, 영역) → get_values(document.criterion.*) → 필요하면 get_evidence.
서류 전형은 점수 없이 항목 판정(충족 · 부분 충족 · 미충족 · 확인 필요)으로 본다. 총점 key와 영역 점수 key는 없다.

## 섹션 구성

자료가 있는 부품만 쓴다. get_overview의 지표 · 값 key를 보고 고른다.

1. 한눈에 보기
   - kpi: 대상 · 합격 · 불합격 · 미결정 지표
   - donut: 필수 조건 지표(충족 · 미충족 · 확인 필요)가 있으면
2. AI 추천과 결정 (document.ai_pick이 있으면. AI 추천은 필수 조건을 모두 충족했거나 담당자가 올린 지원자다)
   - cross: rowKey=document.ai_pick, colKey=document.decision. AI 추천 밖에서 담당자가 올린 인원을 읽는다
   - share: document.skill.* 를 합격자(groupKey=document.decision, groupValue=PASS)와 전체로 견준다
3. 영역마다 섹션 하나 (자격요건, 우대사항)
   - tally(by=key): 그 영역 항목마다 전형 전체의 판정 비율
4. 지원자 구성 (경력 구간 지표가 있으면)
   - composition: 전체 · 합격자의 경력 구간 지표

## 요약에 담을 것

합격자들이 공통으로 충족한 자격요건, 확인 필요가 남은 항목, 다음 전형에서 확인할 점. 서류 점수나 총점을 지어내지 않는다.
