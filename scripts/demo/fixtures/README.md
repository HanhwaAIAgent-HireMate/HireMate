# 서류 평가 데이터셋

가상 백엔드 지원자 30명과 채점 정답으로 Application Agent의 판정이 정답과 맞는지, 같은 서류를 다시 분석해도 같은
판정이 나오는지 잰다. 지원자는 모두 가상 인물이다. 기본 데모(`../applicants.json`, 자격요건 5 · 우대사항 5)와 따로 둔다.

| 무엇 | 어디 |
|---|---|
| 평가 항목 | `backend/src/main/resources/application-fixtures.yml`. 자격요건 2 · 우대사항 3(정답표의 중점 평가 항목 5종), 모두 복합 경험형이다. backend를 `SPRING_PROFILES_ACTIVE=fixtures`로 띄울 때만 기본 더미 기준 대신 쓴다 |
| 공고 본문 | `../seed.py`의 `FIXTURES_POSTING`. 자격요건 · 우대사항 글은 위 평가 항목 글과 같아야 짝이 맞는다 |
| 지원자 | `applicants.json`. HM-001~HM-030의 이력서 · 자기소개서 · 포트폴리오 · 자격증. `note`는 지원자 ID이고 제출하지 않는다 |
| 자기소개서 | 문항 2개(프로젝트에서 맡은 역할 · 수행 · 결과, 협업 중 문제 발견 · 조율). 답변마다 공백 포함 500자 이내 |
| 채점 정답 | `answer-key.json`. 지원자별 금융 도메인 정답(포함 14 · 제외 13 · 확인 필요 3), 중점 평가 항목과 기대 등급(상 12 · 중 12 · 하 3 · 확인 필요 3), 정량 지표 인정 여부, 근거 문장. 채점에만 쓰고 AI에 넣지 않는다 |

## 화면으로 보기

기본 데모의 순서(`../README.md`)와 같고, 두 군데만 다르다.

```bash
# backend
SPRING_PROFILES_ACTIVE=fixtures HIREMATE_AI_AGENTS_APPLICATION=remote HIREMATE_AI_AGENTS_CANDIDATE_ANALYST=remote ./gradlew bootRun

# 데모 데이터 (저장소 루트)
uv run scripts/demo/seed.py --fixtures --email demo-hr@example.com --password <12자 이상>
```

인재상은 회사 설정의 글을 쓴다. 판정은 행동 확인 · 일부 확인 · 미확인이고, 인재상 설명에 `행동 확인: … / 일부 확인: …`
기준을 적으면 그 기준을 따른다. 조직 문화 글이 있으면 AI가 거기서 뽑은 요소도 인재상으로 붙는다.

## 일관성 측정

화면 없이 ai 패키지로 지원자마다 처음부터 여러 번 분석한다 (저장된 분석을 다시 쓰지 않는다). ai/.env의 모델을 실제로 부른다.

```bash
cd ai
uv run python scripts/consistency.py --runs 3                       # 30명 × 3회
uv run python scripts/consistency.py --runs 2 --limit 5 --out a.json  # 앞 5명만, 칸별 표기를 파일로
```

- **칸 일치**: 지원자 × 칸(평가 항목 5 · 인재상 3)마다 모든 회차의 표기가 같은 비율과, 흔들린 칸 목록
- **정답 일치**: 회차마다 중점 평가 항목 등급이 `answer-key.json`과 같은 지원자 수와, 틀린 칸의 정답 → AI 표기

표기는 표 보기와 같다. 경험형은 상(경험 + 정량 지표) · 중 · 하(하지 않았다고 기재했거나 서류에 관련 기록 없음) ·
확인 필요다.
