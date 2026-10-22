# contract

backend와 ai 서버가 주고받는 JSON의 샘플이다. 파일 하나가 타입 하나이고, 파일 이름은 타입 이름과 같다.

- backend: Java 레코드 (`com.hiremate.*`)
- ai: Pydantic 모델 (`hiremate_ai.contract`, 담당자 타입은 각자의 라우터 파일)

양쪽 테스트가 같은 샘플로 왕복 검사(샘플 → 모델 → JSON이 샘플과 같은지)를 한다. 한쪽만 필드를 바꾸면 그쪽 검사가 실패한다.

샘플을 더할 때는 다음을 함께 고친다.

1. 이 폴더에 `<타입 이름>.json`. 모든 필드를 넣는다. 값이 없는 필드는 `null`로 적는다.
2. `backend/src/test/java/com/hiremate/ai/ContractSampleTests.java`의 `SAMPLES`
3. `ai/tests/test_contract.py`의 `SAMPLES`

`Job` · `JobResult`는 Redis 작업 대기열로 오가는 메시지다. `type`은 ai 서버 경로(`{agent}/{method}`)와 같고,
`payload` · `result`는 그 경로의 요청 · 응답 본문과 같다.

`ChatStatus`는 Root `plan` SSE의 `status` 이벤트 data다. `item` 이벤트 data는 `ChatPlan.items`의 한 항목,
`done` 이벤트 data는 `ChatPlan`이다.
