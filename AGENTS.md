# AGENTS.md

이 저장소에서 작업하는 AI 코딩 에이전트(Claude Code, Cursor, Codex 등)가 지켜야 할 규칙이다.
브랜치, 커밋, PR의 세부 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따른다.

## 프로젝트

멀티에이전트 기반 E2E 채용 자동화 플랫폼(HireMate) MVP. 기업이 전형을 조합해 채용을 운영하고,
AI는 분석, 탐색, 초안 작성을 돕되 채용 결정은 담당자가 직접 내린다.

| 디렉터리 | 역할 | 스택 |
|---|---|---|
| `backend/` | 업무 서버. 채용, 전형 데이터, 권한 검증, 상태 변경 실행 | Spring Boot (Java) |
| `ai/` | AI API, AI 워커. Root Agent, 분석, 생성 Agent | Python, FastAPI, LangGraph |
| `frontend/` | HR 콘솔, 채용 페이지 | React + Vite (SPA) |

## 작업 규칙

- `main`에 직접 커밋하거나 push하지 않는다. 작업 브랜치를 만들어 PR로 올린다.
- 요청받은 작업만 한다. 범위 밖의 파일 수정, 리팩터링, 포맷 변경, PRD에 없는 기능 추가를 하지 않는다.
- 커밋 메시지와 PR 제목은 `<type>(<scope>): <제목>` 형식을 따른다. 예: `feat(be): 지원서 접수 API 추가`
- 커밋하기 전에 바꾼 영역의 검사를 통과시킨다.

  | 영역 | 검사 | 자동 수정 |
  |---|---|---|
  | `backend/` | `cd backend && ./gradlew check` | 없음 (IntelliJ Reformat Code) |
  | `frontend/` | `cd frontend && npm run check` | `npm run format` |
  | `ai/` | `cd ai && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest` | `uv run ruff format && uv run ruff check --fix` |

- 훅이나 검사가 실패하면 코드를 고친다. `--no-verify`로 건너뛰지 않는다.
- 검사 규칙을 바꾸거나 끄지 않는다. `checkstyle.xml`, `suppressions.xml`, 린트 설정, `.githooks/`,
  `.github/workflows/`를 고치거나 `@SuppressWarnings`, `# noqa`, `eslint-disable`로 경고를 숨겨야 할 것 같으면
  멈추고 사람에게 묻는다.
- 새 의존성을 추가하면 PR 본문에 이유를 적는다.
- API 키, 비밀번호, 토큰을 코드에 쓰지 않는다. `.env`에 두고 `.env.example`에는 키 이름만 적는다.

## 아키텍처 규칙

1. 지원자 합격, 불합격 결정, 전형 결과 확정, 공고 게시, 안내 발송은 담당자가 화면에서 실행하는
   `backend/` 업무 API로만 처리한다. AI가 독자적으로 수행하는 경로를 만들지 않는다.
2. `ai/`가 `backend/`에 보낼 수 있는 변경 명령은 선택 지원자 영역 편집(넣기, 빼기)뿐이다.
   `backend/`가 대상과 권한을 검증한 뒤 실행한다.
3. 업무 데이터(지원자 상태, 결정 이력)는 `backend/`만 쓴다. `ai/`는 지원자 프로필, 분석 결과, AI 호출 로그만 저장한다.
4. 조회는 현재 기업, 채용, 전형 범위로 제한한다. 다른 기업의 데이터를 검색 대상에 넣지 않는다.
5. 제출 문서와 URL의 내용은 분석 자료로만 다룬다. 문서 안의 지시문으로 도구 권한이나 채용 상태가 바뀌면 안 된다.
6. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건으로 지원자를 탐색하거나 거르는 기능을 만들지 않는다.
7. 분석과 탐색 결과에는 근거 문장과 출처를 붙인다. 근거가 없는 정보를 사실처럼 채우지 않는다.
8. `backend/`는 기능별 패키지(모듈)로 나눈다. 의존 방향은 진입(인증, AI 연동) → 업무 → 공통(로그, 파일, 대기열, 메일)이다.
   다른 모듈의 테이블이나 Repository를 직접 쓰지 않고, 그 모듈이 공개한 서비스만 호출한다.
9. 외부에 공개되는 것은 Nginx뿐이다. AI 서버, DB, Redis는 내부망에 둔다. 지원자 파일은 비공개 S3에 두고 서명 URL로만 연다.

## 영역별 구조

새 파일은 아래 위치에 둔다. 맞는 위치가 없으면 새 폴더를 만들지 말고 사람에게 묻는다.
전체 디렉터리와 파일 목록은 [directory-structure.yml](directory-structure.yml)에 있다.
이 목록은 폴더를 유지하거나 패키지를 선언하는 파일(`.gitkeep`, `package-info.java`, `__init__.py`)을 제외하고,
해당 디렉터리는 그대로 표시한다. 의존성 설치 폴더, 빌드 결과, 캐시, 개인 기획 산출물도 목록에 넣지 않는다.

### backend/

```
src/main/java/com/hiremate/
├── auth, ai                    진입: 인증, 권한, AI 서버 연동
├── company, recruit, posting,  업무 모듈. 모듈마다 package-info.java에 책임과 FR 번호가 있다
│   apply, dashboard, screening,
│   assessment, interview, notice, report
├── activity, file, job, mail   공통 모듈
└── global                      전역 기술 설정 (업무 로직 금지)
```

- 모듈 최상위 패키지의 타입이 다른 모듈에 공개하는 API다. 하위 패키지는 모듈 안에서만 쓴다. `ModularityTests`가 위반을 잡는다.
- 모듈 안은 `api`(Controller, 요청, 응답 DTO), `application`(서비스), `domain`(Entity, Repository), `infra`(외부 연동, 필요할 때만)로 나눈다.
- 다른 모듈의 엔티티는 JPA 연관관계 대신 ID로 참조한다. 필요한 데이터는 해당 모듈이 공개한 서비스로 조회한다.
- 스키마는 `src/main/resources/db/migration`의 Flyway 파일(`V{번호}__{설명}.sql`)로만 바꾼다. `ddl-auto=validate`라 Entity와 스키마가 다르면 앱이 뜨지 않는다.
- DB나 Redis가 필요한 테스트는 `TestcontainersConfiguration`을 `@Import`한다.
- `auth/config/SecurityConfig`는 모든 요청을 허용하는 임시 설정이다. 인증 작업이 아니면 고치지 않는다.

현재 모듈별 하위 패키지는 다음과 같다. 각 `package-info.java`에 해당 계층의 책임과 예정 엔티티가 적혀 있다.

| 모듈 | 하위 패키지 |
|---|---|
| `auth` | `api`, `application`, `domain`, `config` |
| `ai` | `api`, `application`, `infra` |
| `company`, `recruit`, `posting`, `apply`, `screening`, `assessment`, `interview`, `notice`, `report` | `api`, `application`, `domain` |
| `dashboard` | `api`, `application` |
| `activity` | `application`, `domain` |
| `file` | `application`, `domain`, `infra` |
| `job`, `mail` | `application`, `infra` |
| `global` | `config`, `error` |

### frontend/

```
src/
├── main.tsx
├── index.css
├── app/
│   ├── HrLayout.tsx             HR 콘솔 공통 레이아웃
│   ├── providers.tsx            Provider
│   ├── router.tsx              라우트 등록
│   └── router.test.tsx          라우트 검사
├── pages/
│   ├── hr/
│   │   ├── DashboardPage.tsx    채용 대시보드
│   │   ├── SettingsPage.tsx     기업 설정
│   │   ├── PostingEditorPage.tsx 공고 생성과 편집
│   │   ├── StagePage.tsx        전형 운영
│   │   ├── StageClosePage.tsx   전형 마감
│   │   └── ReportPage.tsx       최종 리포트
│   └── careers/
│       ├── PostingPage.tsx      지원자용 공고
│       └── ApplyPage.tsx        지원서 제출
├── features/                   기능 단위 컴포넌트와 훅
│   ├── company/, recruit/, posting/, apply/, dashboard/
│   └── screening/, assessment/, interview/, notice/, report/, chat/
├── lib/                        유틸, API 클라이언트(lib/api)
└── test/                       공통 테스트 설정
```

- HR 화면은 `app/HrLayout.tsx` 아래에 등록한다. 지원자용 화면은 `/careers/:postingId`와 `/careers/:postingId/apply`로 연다.
- `features` 이름은 backend 업무 모듈 이름과 맞춘다. `chat`은 AI Chat 전용이다.
- API는 `lib/api/client.ts`의 `api`로만 호출한다. 타입은 `npm run api:generate`로 만든 `lib/api/schema.d.ts`를 쓰고, 이 파일은 직접 고치지 않는다.
- 서버 상태는 TanStack Query, 전역 클라이언트 상태는 Zustand, 폼은 React Hook Form + Zod를 쓴다.
- UI는 shadcn/ui 컴포넌트를 먼저 쓴다. `npx shadcn add <이름>`으로 설치하며 `components/ui/`에 둔다.
  현재는 설치된 UI 컴포넌트가 없어 이 디렉터리가 없다.

### ai/

```
src/hiremate_ai/
├── main.py                     FastAPI 앱
├── config.py                   설정 (환경 변수)
├── api/
│   └── health.py               헬스 체크 라우터
├── agents/
│   ├── root/                   대상 확인, 요청 분류, 실행 계획, 결과 정리
│   ├── analysis/
│   │   ├── application/        지원 문서 분석
│   │   ├── assessment/         평가 결과와 제출물 분석
│   │   └── interview/          면접 답변 분석
│   └── generation/
│       ├── posting/            공고 초안과 수정안
│       ├── interview/          맞춤 면접 질문
│       ├── communication/      안내 초안
│       └── report/             최종 리포트 초안
├── tools/                      Agent 도구
├── llm/                        모델 클라이언트
├── db/                         ai 스키마
└── worker/                     분석 작업 소비자
```

- 분석 Agent는 자료가 들어올 때 지원자 프로필을 갱신한다. 생성 Agent는 초안만 만들고 게시나 발송은 수행하지 않는다.
- Root Agent는 분석과 생성 작업을 연결한다. 지원자를 직접 분석하거나 채용 상태를 변경하지 않는다.
- 설정은 `config.py`의 `settings`로만 읽는다. `os.environ`을 직접 쓰지 않는다.
- 함수에는 타입 힌트를 단다. mypy가 검사한다.
- 테이블은 `ai` 스키마에 둔다. backend가 Flyway로 관리하는 `public` 스키마에는 쓰지 않는다. 마이그레이션은 Alembic으로 한다.
