"""면접 질문 생성 결과와 꼬리질문 제안 타입. 선택된 근거는 생성 당시 문장과 함께 보존한다."""

from pydantic import Field

from hiremate_ai.contract import ContractModel, InterviewerRole, InterviewQuestion, PostingContent


class InterviewQuestionDraft(ContractModel):
    text: str
    reason: str | None = None
    interviewer_role: InterviewerRole | None = None


class FollowUpsRequest(ContractModel):
    """🎤 꼬리질문 제안 요청 (backend InterviewFollowUpsRequest).

    chain 은 처음 질문부터 꼬리질문을 받을 질문까지의 질문과 답이다 (마지막이 지금 질문).
    avoid 는 [다시 제안]일 때 앞서 보여 준 제안이다. 같은 질문을 다시 내지 않는다.
    """

    posting: PostingContent
    chain: list[InterviewQuestion] = Field(min_length=1)
    avoid: list[str] = Field(default_factory=list)


class FollowUpSuggestion(ContractModel):
    """꼬리질문 하나와 그 질문으로 확인할 점 (확인 포인트)."""

    text: str
    check: str


class InterviewFollowUps(ContractModel):
    """🎤 꼬리질문 제안 결과. 답이 충분하면 needed=False, suggestions=[] (화면: "추가로 확인할 점이 없어요")."""

    needed: bool
    suggestions: list[FollowUpSuggestion] = Field(default_factory=list)


class CitedQuestionDraft(InterviewQuestionDraft):
    """NCS를 참고한 Chat 요청의 질문. ncs_cited는 이 질문이 판정을 통과한 NCS 원문을 인용했는가다.

    NCS를 참고하지 않는 요청(자동 생성, SKIP)은 지금처럼 InterviewQuestionDraft만 쓴다.
    """

    ncs_cited: bool = False
