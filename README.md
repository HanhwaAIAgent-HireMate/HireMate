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
