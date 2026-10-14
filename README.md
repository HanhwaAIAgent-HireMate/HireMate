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
cd ai && uv sync && uv run uvicorn hiremate_ai.main:app --reload --port 8001
```

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

면접관 초대 및 배정, 기존 기업 가입, 계정 정지 및 역할 변경, 이메일 확인, 비밀번호 재설정은 아직 구현하지 않았다.
같은 기업 HR는 동일한 권한을 가지며 채용별 배정 정책은 후속 결정이 필요하다.
