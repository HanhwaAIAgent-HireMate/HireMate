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
3. CI가 모두 통과하면 작성자가 바로 **Squash and merge** 한다. 머지된 브랜치는 자동으로 지워진다.

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

- PR 제목도 커밋 메시지 형식을 따른다. Squash 머지하면 PR 제목이 `main`의 커밋 제목이 된다.
- 한 PR에는 한 가지 작업만 담는다.
- CI가 실패한 PR은 머지하지 않는다.

## 자동 검사

| 언제 | 무엇을 | 어디서 |
|---|---|---|
| 커밋 | 커밋 메시지 형식 | `.githooks/commit-msg` |
| push | `main` 직접 push 차단 | `.githooks/pre-push` |
| PR | PR 제목 형식 | `.github/workflows/commit-convention.yml` |
| PR, `main` push | 비밀키 유출 (gitleaks) | `.github/workflows/secret-scan.yml` |

GitHub Free 플랜의 private 저장소라 서버에서 브랜치 보호를 강제할 수 없다. 검사를 우회하지 않는 것이 팀 규칙이다.
