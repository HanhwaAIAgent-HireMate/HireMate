# 서류 전형 데모

더미 공고(자격요건 5 · 우대사항 5)와 가상 지원자 30명(`applicants.json`)으로 Application Agent의 서류 평가를
스토리보드 v8의 서류 전형 화면(STG-01 · STG-06)에서 확인한다. 지원자는 모두 가상 인물이다.

| 무엇 | 어디 |
|---|---|
| 우대사항 가중치(1~5) · NCS 능력단위 · 선발 인원(1명) | `backend/src/main/resources/application.yml`의 `hiremate.dummy.screening-rubric` |
| 공고 본문 | `seed.py`의 `POSTING`. 우대사항 글은 위 설정과 같아야 짝이 맞는다 |
| 지원자 | `applicants.json`. `note`는 어떤 경우를 보려는 지원자인지 적은 것이고 제출하지 않는다 |

## 순서

```bash
# 1. DB · Redis (저장소 루트)
docker compose up -d

# 2. ai 스키마와 NCS 능력단위. 우대사항마다 능력단위의 수행준거 한 문장이 평가 조건 하나다
cd ai
uv run alembic upgrade head
uv run python scripts/ncs_load.py

# 3. ai 서버. ai/.env에 모델 연결을 넣는다 (ai/.env.example). 실제 지원자 정보는 외부 API로 보내지 않는다.
#    OpenAI로 볼 때는 LLM_MODEL=gpt-4.1-mini, LLM_STRUCTURED_OUTPUT=function_calling으로 둔다. json_schema에서는
#    일부 이력서에서 모델이 탭을 끝없이 써 출력 한도에 걸리고, 같은 질문이라 다시 물어도 똑같이 실패했다.
#    Windows에서는 --reload로 띄운다 (psycopg 비동기 연결이 기본 이벤트 루프에서 동작하지 않는다)
uv run uvicorn hiremate_ai.main:app --port 8001 --reload --reload-dir src

# 3-1. AI 워커 (ai 폴더, 다른 터미널). 지원서 분석 작업을 대기열에서 하나씩 꺼내 처리한다.
#      로컬 모델은 지원자 한 명에 몇 분 걸리므로 APPLICATION_TIMEOUT_SECONDS를 늘린다
uv run python -m hiremate_ai.worker

# 4. backend. 지원서 분석은 대기열로 AI 워커에, 카드 분석은 ai 서버로 보낸다
cd backend
HIREMATE_AI_AGENTS_APPLICATION=remote HIREMATE_AI_AGENTS_CANDIDATE_ANALYST=remote ./gradlew bootRun

# 5. frontend
cd frontend && npm run dev

# 6. 데모 데이터 (저장소 루트). 가입 · 로그인, 공고 게시, 지원서 제출, 접수 마감까지 한다
uv run scripts/demo/seed.py --email demo-hr@example.com --password <12자 이상>
```

마지막에 나오는 서류 전형 화면 주소를 열고 같은 이메일로 로그인한다.

## 화면에서 볼 것

- 리스트는 AI 적합도 점수(100점) 순이고, 점수는 행 오른쪽 끝에 붙는다. 선발 인원 1명 × 10 = 상위 10명이 AI 추천으로
  선 위에 굵게 서고, 나머지는 선 아래 회색이다 (스토리보드 COM-02 · STG-01).
  자격요건을 모두 채운 지원자가 먼저이고, 하나라도 못 채운 지원자는 이름 옆에 작게 `✕ 테스트 코드 근거 없음`처럼 붙는다.
- 지원자를 누르면 AI 분석에 'AI 적합도'가 항목별 점수와 이유로 나온다.
  - 우대사항 · NCS 평가 조건 60점: 수행준거마다 근거가 있으면 1, 없으면 0. 만족한 개수가 많을수록 오르고,
    우대사항별 충족 비율을 가중치(1~5)로 평균한다.
  - 직무 적합도 40점: 실무 경험 10, 본인 역할 8, 성과 8, 지원 동기 6, 자격증 · 학습 4, 서류 일관성 4.
- 보류(연한 회색)는 서류에서 글자를 읽지 못한 지원자뿐이다 (윤태오).
- 75% 미만으로 자격요건을 채우지 못한 지원자는 맨 아래다.
- 한예린의 포트폴리오에 든 평가 조작 문장은 따르지 않는다.
