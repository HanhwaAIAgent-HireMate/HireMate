# HireMate

### 외부 포스터 테마 (Templated)

- `backend/.env`에 `TEMPLATED_API_KEY`를 설정한다. 키와 실제 공고는 외부 모델이나 프런트엔드에 보내지 않는다.
- 일반적인 외부 템플릿 검색은 공고 Agent의 `find_external_templates`가 영어 검색 조건을 정하고
  backend가 공개 갤러리에서 최대 3개의 서로 다른 후보를 조회한다. 사진·동영상이나 영수증·이력서 등
  채용 공고로 변환하기 부적합한 양식은 제외하므로 결과가 3개 미만일 수 있다.
- `TEMPLATED_TEMPLATE_IDS`에는 관리자가 공용으로 사용하기로 한 가상 샘플 ID만 쉼표로 등록한다.
  개인 계정 전체 디자인은 조회하지 않으며 실제 기업의 비공개 공고를 이 목록에 넣지 않는다.
- 결과는 원본 테마의 안전한 벡터·텍스트 미리보기다. 적용 시 예시 문구를 제거하고 배경·배색을 보존하며
  현재 공고를 웹 폰트로 다시 배치한다. 원본 픽셀 배치를 그대로 복제하는 방식은 아니다.
  본문은 실제 글자 높이로 늘리고 전형 절차·제출 서류는 전체 너비로 표시한다.
- 테마 적용은 `외부템플릿1`부터 새 카드로 저장한다. 선택한 카드를 삭제하면 기업 설정에 저장한 기본
  템플릿·색상으로 돌아간다. 임시 저장 버튼과 다른 화면으로 이동할 때 서버에 초안을 저장하며,
  기존 공통 알림으로 결과를 알린다. 저장 실패 시 화면 이동을 멈추고 초안을 유지한다.
- 검색·가져오기에는 GET API만 사용한다. 렌더·결제·AI 생성 API는 앱에서 호출하지 않으며,
  미리보기와 PDF는 HireMate에서 처리한다. 외부 계정의 요금·라이선스는 서비스 약관을 따른다.
- 공식 API: https://templated.io/docs/templates/gallery/

### 로컬 Canva OAuth 연결

- `backend/.env.example`을 `backend/.env`로 복사하고 Canva 개발자 앱의 Client ID와 Secret을 넣는다.
  `.env`는 Git에서 제외된다. Secret은 프런트엔드나 AI 프롬프트에 전달하지 않는다.
- Canva 개발자 페이지의 Outside Canva에서 Canva MCP를 켜고 Redirect URLs에
  `http://127.0.0.1:5173/api/companies/me/canva/callback`을 등록한다.
- 표준 로컬 환경을 다시 켠 뒤 설정 → 채용 공고 → Canva 연결에서 본인의 계정을 승인한다.
  OAuth는 PKCE와 일회성 state를 사용하며 승인한 HR의 기업·사용자·로그인 세션에 묶인다.
- 서버가 실제 MCP 초기화와 tools/list를 확인한 뒤에만 연결됨으로 표시한다.
  무료 여부를 도구 존재만으로 단정하지 않는다. OAuth 연결은 현재 로그인 세션에 유지되며
  로그아웃·세션 만료 후에는 다시 연결해야 한다. 연결 해제는 HireMate 세션의 토큰을 지운다.
- 포스터 챗에서 “Canva에서 금융권 채용 포스터 찾아줘”라고 요청하면 연결한 계정의 소유·공유 디자인을 검색한다.
  검색 결과는 같은 ID·제목의 복사본을 묶은 최대 3개이며, 추가한 카드 이름은 `외부템플릿1`부터 빈 순번으로 지정한다.
  Canva 전체 공개 템플릿 검색이나 유료 구독 신청은 수행하지 않는다. Codex의 Canva 플러그인 연결과는 독립적이다.
- 결과 카드에서 가져오기를 누르면 첫 페이지의 작업 복사본을 만들고 현재 계정의 일반 PNG 내보내기 가능 여부를 확인한다.
  원본 글자를 지운 임시 편집본에서 배경과 글 영역을 읽은 뒤 임시 편집을 취소한다. 원본은 덮어쓰지 않는다.
  현재 공고 내용은 로컬에서 연결하고 새 이름의 회사 템플릿으로 저장한다. Canva에 공고 내용은 보내지 않는다.
- 가져온 글자의 크기·정렬·너비·배치는 챗으로 수정한다. 배경 장식은 이미지로 보존하므로 Canva 원본에서 수정 후 다시 가져온다.
  LLM이 원본 영역과 공고 항목을 연결하고, 렌더러는 실제 글자 높이로 행 간격과 포스터 길이를 늘린다.
  상단 배경 이미지를 보존하고 본문은 원본의 열 구성·종이색·강조선에 맞춰 재구성한다. 원본의 채용 사실은 복사하지 않는다.
  전형 절차와 제출 서류는 각각 전체 너비의 행으로 표시한다. 기존에 가져온 양식도 편집 화면에서 새 구성으로 변환한다.
  로고는 원본 윤곽을 지우지 않고 밝은 대표색 받침을 사용한다. 원본의 빈 로고 자리 장식은 추출에서 제외한다.
  유료 요소·계정 이용 한도 때문에 내보내기가 거절되면 가져오기를 중단한다. 무료 이용량을 보장하지 않는다.

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

포스터 디자인과 대화 처리는 공고 Agent의 `generation/posting` 모듈에 있다.

포스터 챗의 “템플릿 만들어줘”는 검색과 별개의 생성 도구를 사용한다. 연결된 모델이 새 배치·서체 크기·배색·항목 순서를
설계해 서로 다른 디자인 2개를 제안한다. “다른 걸로 또 만들어줘”는 최근 대화와 현재 디자인의 같은 구성을 제외하고
다시 생성한다. Canva/Templated에서 생성했다고 표시하지 않으며 추가 유료 디자인 API는 사용하지 않는다.
미리보기에서 수정안을 적용하면 회사 템플릿에 추가한다. 채용 문구는 생성 데이터에 복사하지 않고 현재 공고에서 채운다.
본문 높이는 화면과 PDF가 사용하는 공통 렌더러에서 실측하고, 전형 절차·제출 서류는 전체 폭으로 이어 배치한다.
생성안은 본문 배치와 전형·서류 표현도 달리하며, 전체 대표색 변경은 본문과 강조색에도 적용한다.
생성 모델은 6개 편집 체계와 3개 표현 방식 중 현재 요청과 이전 제안에 맞는 조합을 고른다.
검증된 타이포·여백·배색 비례로 조합하며 최근과 같은 편집 체계·표현 조합은 제외한다.
포스터의 Noto Sans KR은 Fontsource 패키지로 직접 제공한다. 외부 글꼴 서버에 의존하지 않고,
측정 전에 한글 글꼴을 로드한 후 문서 내 SVG로 출력해 미리보기와 인쇄의 글자 폭을 일치시킨다.
`@fontsource-variable/noto-sans-kr` 추가 이유는 예시 포스터와 같은 글꼴을 화면·PDF에서 안정적으로 쓰기 위해서다.
회사 소개와 직무를 바탕으로 상단 한 줄 문구를 제안하며 별도 입력 항목은 추가하지 않는다.
채팅 수정안은 가운데 포스터에 먼저 표시하고 바뀐 영역에 공통 보라색 테두리와 `AI 수정` 표시를 붙인다.
적용 전에는 실제 디자인을 바꾸지 않으며 되돌리면 미리보기를 해제한다. 표시 테두리는 PDF에 포함하지 않는다.
작성 중인 공고 카드는 마지막으로 방문한 글 작성·포스터·게시 설정 단계로 이어진다.
편집 위치만 기업·계정·공고별로 현재 브라우저에 기억하며, 게시된 공고와 전형 진행 경로는 기존 상태를 따른다.
`/agents/posting/design`은 해당 모듈을 직접 호출하며 전형 Root를 거치지 않는다.

포스터 챗의 “외부 무료 SVG 템플릿 찾아줘”는 검증한 무료 제공처의 양식을 실제로 내려받아 후보로 보여 준다.
현재 제공처는 [inkscape.de의 CC0 기본 양식 3종](https://inkscape.de/vorlagen/)이며,
인터넷 전체 검색이나 금융권 전용 디자인 라이브러리는 아니다. API 키·유료 구독은 사용하지 않는다.
카드의 “공고에 적용” 또는 “첫 번째 무료 템플릿으로 적용해줘”로 가져온 뒤,
“제목을 크게”, “복지를 오른쪽으로”, “본문을 세리프 글꼴로”처럼 요소별 배치를 수정할 수 있다.
실제 문구는 매번 현재 공고에서 읽으며, 원본 양식의 문구는 사용하지 않는다.
원본 SVG의 실행 요소와 외부 참조는 제거하고, 편집 데이터와 출처는 기존 포스터 디자인 JSON에 저장한다.
기본 템플릿 카드를 선택하면 기존 포스터로 돌아간다. 웹 미리보기와 PDF는 같은 벡터 출력을 사용한다.
무료 편집 엔진으로 MIT 라이선스의 Fabric.js를 추가했다. 위치·서체·크기를 개별 요소로 관리하고
SVG를 가져와 다시 벡터로 출력하기 위해 필요하며, 별도 편집 서비스 구독은 없다.

포스터의 이전 추천은 현재 공고의 최근 12개 대화 턴과 디자인 식별자로 참조한다.
본문·전형·포스터의 미저장 편집과 포스터 대화는 같은 탭의 `sessionStorage`에 임시 보관한다.
포스터 화면에서는 수정한 채 다른 앱 페이지로 이동하면 먼저 업무 API로 임시 저장하고 공통 성공 알림을 표시한다.
저장에 실패하면 이동하지 않고 편집 내용과 복구본을 유지한다. 수동 임시 저장도 같은 공통 알림을 사용한다.
선택한 추가 템플릿을 삭제하면 설정에 저장된 기업 기본 템플릿과 배색으로 돌아간다.
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
| GET | /{stageId}/{applicationId} | myRole, personalMemo, personalMemoVersion, session, questions |
| POST | /{stageId}/{applicationId}/start 또는 /end | 예정 → 진행 중 → 종료 |
| PUT | /{stageId}/questions/{questionId}/answer | answer, analyze, expectedVersion |
| POST | /{stageId}/{applicationId}/questions | text, interviewerRole. 본인 역할만 지정 |
| POST | /{stageId}/questions/{questionId}/follow-ups | text, source, check. 원래 담당 유지 |
| POST | /{stageId}/questions/{questionId}/follow-ups/suggestions | avoid 목록. 자기 담당만 AI 제안 요청 |
| DELETE | /{stageId}/questions/{questionId} | 자기 담당의 미응답 질문만 삭제 |
| PUT | /{stageId}/{applicationId}/memo | text, expectedVersion(personalMemoVersion). 개인 메모 |

questions는 자기 담당이 먼저이며 각 항목에 question, canAnswer, canRequestFollowUp, canDelete,
readOnlyReason이 있다. personalMemo는 현재 면접관의 것만 반환한다. 기존 HR 공용 메모는 그대로다.
개인 메모 저장에는 personalMemoVersion을 expectedVersion으로 보낸다. session.version은 배정·진행 상태의
버전이며 메모 저장에 사용하지 않는다. 인사·실무가 서로의 개인 메모를 저장해도 충돌하지 않고, 같은 개인 메모의
오래된 버전으로 저장하면 409 MEMO_CONFLICT를 반환한다. 상대방의 개인 메모와 메모 버전은 응답에 포함하지 않는다.
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


### 면접 기록 복구

- 답변과 개인 메모의 미저장 초안은 브라우저에 기업·계정·전형·지원자·항목별로 보관한다.
  7일 이내 초안만 복구하며 서버 저장에 성공한 내용은 지운다. 같은 브라우저의 다른 계정에는 표시하지 않는다.
  브라우저 저장소를 사용할 수 없으면 복구를 보장하지 않고 화면에 복사 안내를 표시한다.
- 서버 내용이 바뀐 초안은 자동으로 덮어쓰지 않는다. 최신 내용과 비교한 뒤 초안을 다시 저장하거나 버린다.
- 별도로 추가했던 인사·실무 공유 기록은 HR·면접관 화면과 API에서 제거한다. V45 마이그레이션은
  `interview_shared_notes` 테이블만 삭제한다. 개인 메모·면접관 의견·HR 공용 메모는 유지한다.
- 꼬리질문은 생성 뒤 답변만 읽는 충분성 검토와 제안의 중복·담당·명확성 검토를 거친다.
  충분하다는 판단의 인용은 실제 답변에 있는지 확인한다. 보완·재제안 비교 포함 최대 5단계의 모델 호출로 비용·지연이 늘 수 있다.
  실제 모델 평가는 `cd ai` 후 `LLM_EVAL=true uv run pytest tests/eval/test_interview_eval.py -q -s`로 실행한다.
