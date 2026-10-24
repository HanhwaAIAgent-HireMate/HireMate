# 서류 전형 데모

더미 공고(자격요건 5 · 우대사항 5)와 가상 지원자 30명(`applicants.json`)으로 Application Agent의 서류 평가를
스토리보드 v8의 서류 전형 화면(STG-01 · STG-06)에서 확인한다. 지원자는 모두 가상 인물이다.

| 무엇 | 어디 |
|---|---|
| 평가 항목(자격요건 5 · 우대사항 5)의 유형 · 중요 표시 · 충족 / 부분 충족 / 미충족 기준 · 선발 인원(1명) | `backend/src/main/resources/application.yml`의 `hiremate.dummy.screening-rubric` |
| 공고 본문 | `seed.py`의 `POSTING`. 자격요건 · 우대사항 글은 위 설정과 같아야 짝이 맞는다 |
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

- 서류 평가 점수 = 자격요건 50점 + 우대사항 50점 (우대사항이 없으면 자격요건이 100점). 소수 첫째 자리까지 보인다.
  - 영역 점수 = 영역 만점 × Σ(계수 × 충족도) ÷ Σ계수. 계수는 일반 1, 중요 표시 1.5다 (ai 설정 `CRITERION_WEIGHT_*`).
  - 충족도: 충족 1 · 부분 충족 0.5(복합 경험형만) · 미충족 0. 조건형 · 단일형에 부분 충족이 나오면 받지 않는다.
  - 항목마다 업무 관련성 · 본인 역할 · 수행 범위 · 원문 근거를 보고 충족도 하나를 정한다. 따로 점수를 더하지 않는다.
  - 경력 'N년 이상'은 요건의 직무 · 기술에 해당하는 재직 기간만 코드가 더한다. 근무 기간을 찾지 못하면 신입이 아니라
    `경력 확인 필요`다. 자격증 조건은 코드가 이름으로 확인하고 확인 상태(본인 기재 · 증빙 제출)를 남긴다.
- 확인 필요(UNKNOWN) 항목은 1차(주변 문맥 · 본인 역할) · 2차(다른 제출 문서)로 다시 판정한다 (항목마다 최대 2번,
  분석 한 번에 150초 안). 그래도 남으면 0점으로 바꾸지 않고 총점을 보류한다(연한 회색). 카드에 보류 이유가 나온다.
- 리스트는 총점 순이다. 선발 인원 1명 × 10 = 상위 10명이 AI 추천으로 선 위에 굵게 서고, 나머지는 선 아래 회색이다
  (스토리보드 COM-02 · STG-01). 경력 줄 아래에 `자격요건 33.3/50 · 우대사항 40.0/50`이 작게 붙는다.
- 자격요건 75% 통과는 점수와 따로 센다 (부분 충족은 0.5개, 확인 필요 때문에 결과가 갈리면 판단 보류).
  하나라도 못 채운 자격요건은 점수가 높아도 이름 옆에 `✕ 신입`처럼 붙는다. 불합격 표시가 아니다.
- 지원자를 누르면 AI 분석의 '서류 평가'에 항목별 판정 · 중요 표시 · 획득 점수 / 배점 · 이유 · 충족 / 미충족 부분 ·
  확인 경력 · 출처 · 평가 기준 버전이 나온다. 공고 조건에 대한 서류 평가일 뿐 합격 여부가 아니다.
- 한예린의 포트폴리오에 든 평가 조작 문장은 따르지 않는다.
