# contract

포스터 디자인과 AI 수정안은 `PosterDesign.json`, `PosterProposal.json`으로 왕복 검사한다.
디자인 제안은 저장/게시 명령이 아니며 담당자가 공고 API로 적용한다.

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

`InterviewQuestionsRequest`는 면접 질문 생성 요청이다. `questionCount`는 Chat에서 추가할 목표 개수이며,
개수를 생략한 Chat 요청은 backend가 2를 전달한다. 최초 자동 생성은 `null`로 기존 전형 구성을 사용한다.
중복·근거 검사로 유효한 후보가 부족하면 요청 수보다 적게 반환할 수 있고, Chat은 실제 추가 수를 안내한다.

`InterviewQuestionDraft`는 생성된 질문 `text`와 생성 시 선택한 자료·확인 목적 `reason`이다.
`interview/questions` API는 이 객체의 목록, 워커는 `questions`에 같은 목록을 반환한다.
backend가 질문과 근거를 함께 저장해 `InterviewView.Question.reason`으로 제공한다.
과거 질문과 배포 전 대기열의 문자열 결과는 근거를 추측하지 않고 `null`로 유지한다.

`ChatContext.interviewerMemos`는 현재 지원자별 현재·이전 면접의 담당자 메모다. 자동 질문 생성에는 전달하지 않는다.
Root가 명시적인 메모 참고 요청을 검토한 경우에만 `ChatPlan.questionMemos`에 실제 원문 인용 하나를 넣는다.
backend가 기업·지원자·전형과 최신 메모를 다시 검증한 뒤 질문 요청의 `memo`로 전달한다.
메모는 사실 판정의 근거가 아니며, 실제 면접 답변에 연결한 추가 확인 질문만 최대 1개 반환한다.
인상뿐이거나 인용·중복 검증에 실패하면 다른 질문으로 대체하지 않고 빈 목록을 반환한다.

`ChatStatus`는 Root `plan` SSE의 `status` 이벤트 data다. `item` 이벤트 data는 `ChatPlan.items`의 한 항목,
`done` 이벤트 data는 `ChatPlan`이다.

`ChatHistoryTurn`은 대화방의 지난 턴이다. `mentions`는 그때 멘션한 지원자, `steps`는 그때 `status` 이벤트로 낸
단계 문구(같은 문구가 이어지면 한 번), `seconds`는 요청 확인부터 턴을 남기기까지 걸린 시간이다.
두 필드가 생기기 전의 턴은 빈 목록과 `null`이다.

`ChatContext.asker`와 `ChatHistoryTurn.asker`는 질문한 담당자(memberId, name)다. 대화방(`threadId` = 기업:전형:탭)은
전형 화면의 탭마다 하나이고 같은 기업 담당자가 함께 쓰므로 턴마다 남긴다. 이 필드가 생기기 전의 턴은 `null`이다.

`ChatApplied`는 업무 서버가 선택 변경을 검증한 뒤 실제 반영한 응답이다. 원래 질문과 계획이
일치하는 기존 턴의 메시지, 항목과 대상 순서를 보정한다. 대화방이나 턴을 새로 만들지 않는다.

`PosterTurn`은 현재 공고 편집 세션의 사용자 요청, 당시 디자인과 AI 추천 순서다.
포스터 요청은 최근 12개 턴만 `PosterContext.history`로 전달하며 서버 DB에 대화방을 만들지 않는다.
업무 실행이나 회사 사실의 근거로 사용하지 않고, 이전 디자인의 정확한 선택과 복원에만 사용한다.

`PostingContent.roles`는 한 공고의 직무별 모집 내용(name, career, duties, qualifications, preferred)이다.
기존 공고와 이전 AI 응답에 없으면 빈 목록으로 읽는다. 2개 이상이면 포스터와 그 PDF에 모집 표로 표시하고,
1개이면 포스터 안의 기존 본문 형태로 표시한다. 글 공고 작성 화면과 채용 페이지의 글 본문은 기존 양식을 유지한다. 지원 직무 선택이나 직무별 전형 분리는 포함하지 않는다.
`StageDraft.icon`은 기존 전형 자료와의 호환을 위해 유지한다. 전형 편집 화면에는 아이콘 선택을 제공하지 않는다.
포스터는 전형 이름과 종류로 아이콘을 자동 표시한다. `PosterDesign.stageIcons`는 포스터 챗에서 요청한
전형 이름별 표시 수정이며 AUTO는 자동, NONE은 숨김이다. 공고 전형 데이터와 별도로 디자인에 저장한다.

`InterviewView.singleInterview`는 backend가 전체 전형의 면접 개수를 세어 전달한다.
면접이 한 번이면 최초 생성은 자기소개 + 직무·경험 3개 + 협업·가치관 1개 + 지원 동기 1개다.
Chat 추가 요청은 기존 추가 문항 수를 따른다.
