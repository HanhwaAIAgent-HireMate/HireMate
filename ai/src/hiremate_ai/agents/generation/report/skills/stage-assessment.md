---
name: stage-assessment
description: 평가 전형(직무역량 평가 · 과제) 결과 리포트. 평가 점수 · 등급과 앞 전형 결정을 함께 본다
---
# 평가 전형 결과 리포트

읽을 자료: get_overview(지표, 총점 key, 영역) → get_values(assessment.total, assessment.area.*, assessment.grade, document.decision).
평가 전형은 외부 평가 결과표의 점수와 등급만으로 쓴다. 평가 분석(Assessment Agent) 근거는 쓰지 않으므로
get_evidence와 ask_specialist로 평가 근거를 찾지 않는다. 점수 · 등급이 없는 지원자는 미응시로 둔다.

## 섹션 구성 (한눈에 보기 → 영역마다 섹션 하나 → 확인할 점)

1. kpi: 응시 · 합격 · 미응시 지표
2. distribution: assessment.total
3. tally: assessment.grade가 있으면 등급별 인원
4. radar 또는 bar: 합격자의 영역 점수 (만점이 같은 영역만)
5. table: 서류 결정과 평가 총점 · 등급을 나란히 (두 전형이 엇갈리는 지원자가 보이게)

## 요약에 담을 것

영역 점수가 높거나 낮았던 곳, 서류와 평가가 엇갈린 지원자, 면접에서 확인할 점. 점수 · 등급에 없는 내용(과제의 질, 풀이 방식)은
지어내지 않는다.
