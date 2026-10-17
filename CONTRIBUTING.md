# 기여 가이드

## 처음 한 번

```bash
git config core.hooksPath .githooks
```

커밋 메시지 형식을 검사하고 `main`에 직접 push하는 것을 막는 훅이 켜진다.

## 브랜치

`main` 하나만 쓰는 GitHub Flow다. `main`은 항상 빌드되고 실행되는 상태를 유지한다.

1. `main`에서 작업 브랜치를 만든다. 이름은 `<type>/<이슈번호>-<설명>` (예: `feat/12-apply-api`)
2. 커밋하고 push한 뒤 `main`으로 PR을 연다.
3. CI가 모두 통과하면 작성자가 바로 **Rebase and merge** 한다. 머지된 브랜치는 자동으로 지워진다.

- 리뷰는 필수가 아니다. 봐야 할 부분이 있으면 리뷰어를 지정하고 PR 본문에 적는다.
- 브랜치는 하루이틀 안에 머지한다. 길어지면 작업을 쪼갠다.
- 충돌을 줄이려면 `main`을 자주 받는다: `git pull --rebase origin main`

## 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/ko/v1.0.0/) 형식을 따른다. 형식이 틀리면 커밋이 거부된다.

```
<type>(<scope>): <제목>

<본문 (선택): 왜 바꿨는지>
```

| type | 쓰는 경우 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 동작이 바뀌지 않는 구조 개선 |
| `perf` | 성능 개선 |
| `test` | 테스트 추가 · 수정 |
| `docs` | 문서 |
| `style` | 포맷 등 동작과 무관한 변경 |
| `chore` | 그 밖의 잡무 (설정 등) |
| `build` | 빌드 설정, 의존성 |
| `ci` | CI 설정 |
| `revert` | 이전 커밋 되돌리기 |

| scope | 영역 |
|---|---|
| `be` | `backend/` |
| `fe` | `frontend/` |
| `ai` | `ai/` |
| `infra` | 배포, Docker, Nginx |

- scope는 생략할 수 있다. 여러 영역에 걸치면 생략한다.
- 제목은 한국어로 써도 된다. 50자 안팎으로, 끝에 마침표를 찍지 않는다.

```
feat(be): 지원서 접수 API 추가
fix(fe): 결과 확정 버튼 중복 클릭 막기
refactor(ai): Root Agent 실행 계획 스키마 분리
ci: 커밋 메시지 검사 추가
```

## PR

- PR 제목도 커밋 메시지 형식을 따른다. Rebase 머지하면 개별 커밋과 커밋 메시지가 `main`에 반영되므로 각 커밋도 형식을 지킨다.
- 한 PR에는 한 가지 작업만 담는다.
- CI가 실패한 PR은 머지하지 않는다.

## 자동 검사

| 언제 | 무엇을 | 어디서 |
|---|---|---|
| 커밋 | 커밋 메시지 형식 | `.githooks/commit-msg` |
| push | `main` 직접 push 차단 | `.githooks/pre-push` |
| PR | PR 제목 형식 | `.github/workflows/commit-convention.yml` |
| PR, `main` push | 비밀키 유출 (gitleaks) | `.github/workflows/secret-scan.yml` |
| PR, `main` push | backend, frontend, ai 코드 품질 및 테스트 | `.github/workflows/code-quality.yml` |
| 빌드 | Java 코드 스타일 (Checkstyle) | `backend/config/checkstyle/` |

코드 품질 CI는 변경한 경로와 관계없이 세 영역을 병렬 검사한다. backend의 `./gradlew check`는
Checkstyle과 테스트를 실행하며, Testcontainers가 러너의 Docker로 PostgreSQL과 Redis를 띄운다.

GitHub Free 플랜의 private 저장소라 서버에서 브랜치 보호를 강제할 수 없다. 검사를 우회하지 않는 것이 팀 규칙이다.

## Java 코드 스타일

Google Java Style을 기반으로 들여쓰기 4칸, 한 줄 120자로 바꾼 Checkstyle 규칙을 쓴다. 위반이 하나라도 있으면 빌드가 실패한다.

- 테스트 메서드 이름은 영어로 쓰고, 한국어 설명은 `@DisplayName`에 쓴다.
- 약어도 단어처럼 쓴다: `HrManager`, `AiClient` (`HRManager`, `AIClient`는 위반)
- 규칙 예외는 `backend/config/checkstyle/suppressions.xml`에만 추가하고 PR 본문에 이유를 적는다.
  코드 안의 `@SuppressWarnings("checkstyle:...")`나 `CHECKSTYLE.OFF` 주석은 동작하지 않는다.

IntelliJ에서 규칙에 맞게 자동 정렬하려면:

1. `CheckStyle-IDEA` 플러그인을 설치한다.
2. Settings → Tools → Checkstyle에서 버전 14.3.0을 고르고 `backend/config/checkstyle/checkstyle.xml`을 추가한다.
3. Settings → Editor → Code Style → Java → ⚙ → Import Scheme → CheckStyle Configuration으로 같은 파일을 가져온다.
   이후 Reformat Code와 Optimize Imports가 규칙에 맞게 동작한다.

## Frontend 코드 검사

```bash
cd frontend
npm ci
npm run check
```

타입 정보를 사용하는 ESLint, Prettier 포맷, Vitest 테스트, TypeScript 타입 검사와 Vite 빌드를 모두 실행한다.
포맷은 `npm run format`으로 고친다.

## AI 코드 검사

```bash
cd ai
uv sync --locked
uv run --locked ruff check
uv run --locked ruff format --check
uv run --locked mypy
uv run --locked pytest
```

Python 버전은 `ai/.python-version`, 의존성 버전은 `ai/uv.lock`을 따른다.
포맷과 자동 수정 가능한 린트 위반은 `uv run ruff format`과 `uv run ruff check --fix`로 고친다.
