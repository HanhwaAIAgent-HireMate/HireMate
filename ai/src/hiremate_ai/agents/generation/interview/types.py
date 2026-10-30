"""면접 질문 생성 결과. 선택된 근거는 생성 당시 문장과 함께 보존한다."""

from hiremate_ai.contract import ContractModel, InterviewerRole


class InterviewQuestionDraft(ContractModel):
    text: str
    reason: str | None = None
    interviewer_role: InterviewerRole | None = None
