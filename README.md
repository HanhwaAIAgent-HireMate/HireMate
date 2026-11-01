# HireMate

멀티에이전트 기반 E2E 채용 자동화 플랫폼 MVP

## 구성

| 디렉터리 | 역할 | 스택 |
|---|---|---|
| `backend/` | 업무 서버 | Spring Boot (Java) |
| `ai/` | AI API · AI 워커 | Python, FastAPI, LangGraph |
| `frontend/` | HR 콘솔 · 채용 페이지 | React + Vite (SPA) |

## 시작하기

필요한 도구: Docker, Node 24, [uv](https://docs.astral.sh/uv/). JDK 25는 Gradle이 없으면 내려받는다.

저장소를 받은 뒤 한 번만 실행한다. 커밋 메시지 검사와 `main` 직접 push 차단 훅이 켜진다.
backend를 빌드하거나 frontend에서 `npm install`을 해도 자동으로 켜진다.

```bash
git config core.hooksPath .githooks
```

## 로컬 실행

```bash
# backend: http://localhost:8080 (API 문서 /swagger-ui.html)
# 실행하면 저장소 루트의 compose.yaml로 PostgreSQL · Redis를 자동으로 띄운다
cd backend && ./gradlew bootRun

# frontend: http://localhost:5173 (/api 요청은 backend로 넘어간다)
cd frontend && npm install && npm run dev

# ai: http://localhost:8001
# ai만 개발할 때는 먼저 저장소 루트에서 docker compose up -d
# 모델 연결은 ai/.env.example을 ai/.env로 복사해 채운다
cd ai && uv sync && uv run alembic upgrade head && uv run uvicorn hiremate_ai.main:app --reload --port 8001

# ai 워커: 지원서 · 평가 결과 · 면접 답변 분석과 최종 리포트 작업을 Redis 대기열에서 꺼내 처리한다
# backend에서 이 Agent들을 remote로 켤 때(예: HIREMATE_AI_AGENTS_INTERVIEW_ANALYST=remote) 같이 띄운다
cd ai && uv run python -m hiremate_ai.worker
```

## 공고·포스터 실제 AI 연결

기본 실행은 고정 예시를 반환하는 `stub` 모드다. 본문 생성과 포스터 추천·수정을 실제 모델로
확인하려면 AI 서버의 모델 설정을 채운 뒤 backend에 `HIREMATE_AI_AGENTS_POSTING=remote`를 지정한다.
AI 서버 주소가 기본값과 다르면 `HIREMATE_AI_BASE_URL`도 지정한다. 다른 Agent의 모드는 그대로 유지된다.
Windows에서 `--reload` 없이 AI 서버를 실행할 때 psycopg 이벤트 루프 오류가 나면
`--loop asyncio:SelectorEventLoop`를 지정한다.

포스터의 이전 추천은 현재 공고의 최근 12개 대화 턴과 디자인 식별자로 참조한다.
본문·전형·포스터의 미저장 편집과 포스터 대화는 같은 탭의 `sessionStorage`에 임시 보관한다.
새로고침과 화면 이동 후 같은 공고를 열면 복구하며, 서버 내용이 바뀌었거나 게시한 공고에는 복구본을 적용하지 않는다.
탭을 닫거나 다른 기기에서 이어 쓰려면 먼저 화면의 임시 저장을 눌러야 한다.

실제 모델의 공고 회귀 평가는 AI 폴더에서 `LLM_EVAL=true uv run pytest tests/eval/test_posting_eval.py -v`로 실행한다.
설정된 모델을 실제 호출하며, 근무지 표현 변형·경력 조건 일치·초안 분량·추천 복원·기록 없는 요청을 검사한다.

## 규칙

- 브랜치 · 커밋 · PR: [CONTRIBUTING.md](CONTRIBUTING.md)
- AI 코딩 에이전트: [AGENTS.md](AGENTS.md)

## 백엔드 인증

같은 출처 SPA에서 이메일과 비밀번호로 로그인하며 인증 세션은 Redis에 30분 동안 보관한다.
쿠키는 HttpOnly와 SameSite=Lax이며 HTTPS 요청에서는 Secure를 적용한다. 운영 Nginx는 외부에서 온
forwarded 헤더를 덮어써야 한다. Spring Session Redis starter는 서버 인스턴스 사이에서 인증 세션을 공유하기 위해 추가했다.

| 메서드 | 경로 | 응답 및 조건 |
|---|---|---|
| GET | `/api/auth/csrf` | 공개. `token`, `headerName`, `parameterName` |
| POST | `/api/auth/signup` | CSRF 필수. 새 기업과 HR 생성, 201. 자동 로그인하지 않음 |
| POST | `/api/auth/login` | CSRF 필수. 로그인, 200. 세션 ID 및 CSRF 교체 |
| POST | `/api/auth/logout` | CSRF 필수. 세션 및 쿠키 제거, 204 |
| GET | `/api/auth/me` | 로그인 필수. `memberId`, `companyId`, `name`, `email`, `role` |

가입은 `companyName`, `name`, `email`, `password`만 사용한다. 기업과 역할을 선택할 수 없으며 신규 기업 HR로
생성한다. 이름은 공백이 아닌 최대 100자, 이메일은 유효한 최대 254자다. 이메일의 앞뒤 공백은 제거하고 소문자로
저장한다. 비밀번호는 공백이 아닌 12~128자이며 앞뒤 공백을 보존한다. PBKDF2-HMAC-SHA256, 16바이트 salt,
600000회 해시를 사용하며 비밀번호 및 해시는 응답과 세션 principal에 포함하지 않는다.

클라이언트는 시작할 때 CSRF를 조회하고 응답의 `headerName` 헤더에 `token`을 보낸다. 로그인과 로그아웃에
성공하면 CSRF를 다시 조회해야 한다. 아래 예제는 curl과 jq를 사용하며 테스트용 비밀번호를 환경 변수로 받는다.

```bash
BASE_URL=http://localhost:8080
COOKIE_JAR=$(mktemp)
read -rs HIREMATE_TEST_PASSWORD

CSRF=$(curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/api/auth/csrf" | jq -r '.token')
jq -n --arg password "$HIREMATE_TEST_PASSWORD" \
  '{companyName:"테스트 기업",name:"테스트 HR",email:"hr@example.com",password:$password}' \
  | curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" -H 'Content-Type: application/json' \
      -H "X-CSRF-TOKEN: $CSRF" --data-binary @- "$BASE_URL/api/auth/signup"

jq -n --arg password "$HIREMATE_TEST_PASSWORD" '{email:"hr@example.com",password:$password}' \
  | curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" -H 'Content-Type: application/json' \
      -H "X-CSRF-TOKEN: $CSRF" --data-binary @- "$BASE_URL/api/auth/login"
CSRF=$(curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/api/auth/csrf" | jq -r '.token')
curl -sS -b "$COOKIE_JAR" "$BASE_URL/api/auth/me"
curl -i -c "$COOKIE_JAR" -b "$COOKIE_JAR" -H "X-CSRF-TOKEN: $CSRF" -X POST "$BASE_URL/api/auth/logout"
CSRF=$(curl -sS -c "$COOKIE_JAR" -b "$COOKIE_JAR" "$BASE_URL/api/auth/csrf" | jq -r '.token')
rm "$COOKIE_JAR"
unset HIREMATE_TEST_PASSWORD
```

실패는 `application/problem+json`으로 반환한다. 입력 오류는 400 `INVALID_INPUT`, 미인증은 401
`UNAUTHENTICATED`, 잘못된 자격 증명은 401 `INVALID_CREDENTIALS`, 권한 부족은 403 `FORBIDDEN`,
CSRF 오류는 403 `INVALID_CSRF`, 이메일 중복은 409 `EMAIL_ALREADY_EXISTS`다.

업무 진입 경로인 `/api/companies`, `/api/recruitments`, `/api/stages`와 하위 경로 및 Swagger/OpenAPI 조회는
HR로 제한한다. 업무 API 구현 시 인증된 `companyId`와 실제 데이터 소유 기업을 함께 검증해야 한다. 지원자 공고와
지원 API, AI 서비스 계정 경로는 구현 전까지 공개하지 않는다.

면접관 초대, 기존 기업 가입, 계정 정지 및 역할 변경, 이메일 확인, 비밀번호 재설정은 아직 구현하지 않았다.
같은 기업 HR는 동일한 권한을 가지며 채용별 배정 정책은 후속 결정이 필요하다.


## 면접관 페이지 연결 API

계정 권한(HR/INTERVIEWER)과 면접 역할(HR/PRACTICAL)은 별개다. 면접 역할을 배정해도 계정 권한은
바뀌지 않는다. 같은 기업의 면접관 계정 두 개(인사 · 실무)를 배정하고 HR 계정은 배정하지 않는다. 면접관 계정은
설정 › 면접관에서 HR이 만들고, `/api/interviewer/**`는 면접관 계정만 쓴다.

HR 관리 API:

- GET /api/companies/current/interview-members: 배정 가능한 현재 기업 계정 목록.
- GET /api/stages/{stageId}/candidates/{applicationId}/interview/session: 배정·진행 상태.
- PUT 같은 주소: hrMemberId, practicalMemberId. 서로 다른 같은 기업의 계정만 허용한다.
  기존 배정을 바꿀 때는 조회한 expectedVersion도 보낸다. 시작 또는 답변 기록 후에는 배정을 바꿀 수 없다.

면접관 API의 기준 주소는 /api/interviewer/sessions다. 기업·사용자는 로그인 세션에서 확인한다.

| 메서드 | 기준 주소 뒤 경로 | 내용 |
|---|---|---|
| GET | 없음 | 본인 배정 목록. page=0, size=30(최대 50) |
| GET | /{stageId}/{applicationId} | myRole, personalMemo, session, questions |
| POST | /{stageId}/{applicationId}/start 또는 /end | 예정 → 진행 중 → 종료 |
| PUT | /{stageId}/questions/{questionId}/answer | answer, analyze, expectedVersion |
| POST | /{stageId}/{applicationId}/questions | text, interviewerRole. 본인 역할만 지정 |
| POST | /{stageId}/questions/{questionId}/follow-ups | text, source, check. 원래 담당 유지 |
| POST | /{stageId}/questions/{questionId}/follow-ups/suggestions | avoid 목록. 자기 담당만 AI 제안 요청 |
| DELETE | /{stageId}/questions/{questionId} | 자기 담당의 미응답 질문만 삭제 |
| PUT | /{stageId}/{applicationId}/memo | text, expectedVersion(session.version). 개인 메모 |

questions는 자기 담당이 먼저이며 각 항목에 question, canAnswer, canRequestFollowUp, canDelete,
readOnlyReason이 있다. personalMemo는 현재 면접관의 것만 반환한다. 기존 HR 공용 메모는 그대로다.
면접 시작 전 모든 질문의 담당을 지정한다. 시작·종료는 합격·불합격 결정과 별개이며, 미입력으로 자동 종료하지
않는다. 종료할 때 자동 저장만 된 답변도 분석에 넘긴다.
진행 중인 면접이 하나라도 있으면 전형 결과 확정은 409 INTERVIEW_IN_PROGRESS로 거절한다.
면접 시작과 전형 확정, 최초 배정의 동시 요청은 전형 잠금으로 순서를 보장한다.

면접관 기록은 진행 중인 전형·면접에서만 허용한다. 기존 HR 답변·질문·꼬리질문 API도 배정이 있으면
동일한 역할·상태 검사를 적용한다. HR은 시작 전 담당을 조정할 수 있지만, 답변이 있는 질문의 기존 담당과
자기소개(HR 기록)의 담당은 바꾸지 못한다. 담당이 없던 기존 질문은 답변을 보존하며 첫 담당을 지정할 수 있다.
배정된 면접에서는 답변이 있는 질문을 삭제할 수 없다. 직접 추가하는 질문은 화면에서 인사·실무를 선택해 보낸다.

자동 저장은 현재 question.version을 expectedVersion으로 보내고 응답의 새 버전으로 다음 저장을 보낸다.
analyze=false는 DB 저장, true는 답변 분석 요청이다. 오래된 버전은 409 ANSWER_CONFLICT다.
충돌 시 초안을 보존하고 최신 답변을 확인해야 한다. 새 버전을 임의로 붙여 낡은 초안을 재전송하지 않는다.
답변 저장이 실패하면 꼬리질문 제안도 요청하지 않는다. 다시 시도하면 먼저 답변을 저장한다.
종료 버튼은 진행 중인 자동 저장을 기다린 뒤 호출한다. 종료 후 늦게 도착한 저장은 서버가 거절한다.
