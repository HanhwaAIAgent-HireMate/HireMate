from uuid import uuid4

from root_context import make_context

from hiremate_ai.agents.analysis.application.extract import ExtractedFacts
from hiremate_ai.agents.analysis.application.review import ClaimReview, ReviewJudgement
from hiremate_ai.agents.analysis.interview.types import FindingDraft, InterviewDraft
from hiremate_ai.agents.root.delegation import INVALID_RESULT, SUB_AGENT_BUDGET, SUB_AGENT_FAILED, Delegation
from hiremate_ai.agents.root.ledger import Ledger
from hiremate_ai.agents.root.toolkit import scope_of
from hiremate_ai.agents.root.types import ChatContext, InterviewQuestion, InterviewView, QuestionSource
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.chat import LlmOutputError, new_model_call_budget, reserve_model_calls, using_model_call_budget
from hiremate_ai.llm.fake import FakeLlm, FakeReply, LlmCall

type Applicants = dict[str, ApplicantDetail]

DOCUMENT = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
ANSWER = "파티셔닝 기준을 월 단위로 정하고 성능을 측정했습니다."
STATEMENT = "정산 배치 시간을 줄였어요."
INTERVIEW_STATEMENT = "파티셔닝 기준을 구체적으로 설명했다."


def interview_context(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    applicant = applicants["정유민"]
    application_id = applicant.info.application_id
    return make_context(
        applicants,
        company,
        posting,
        message="서류와 면접 답변을 함께 검토하고 다음 질문을 준비해줘",
        stage_type=StageType.INTERVIEW,
        previous_types=[StageType.DOCUMENT],
        interviews={
            application_id: InterviewView(
                application_id=application_id,
                schedule=None,
                questions=[
                    InterviewQuestion(
                        question_id=uuid4(), text="파티셔닝 기준은 무엇인가요?", source=QuestionSource.AI, answer=ANSWER
                    )
                ],
                previous=[],
            )
        },
    ).model_copy(update={"documents": {application_id: [applicant.documents[0]]}})


def extraction(*, actor: str = "SELF") -> ExtractedFacts:
    return ExtractedFacts.model_validate(
        {"facts": [{"kind": "ACHIEVEMENT", "statement": STATEMENT, "actor": actor, "evidence": [DOCUMENT]}]}
    )


def review(*, supported: bool = True) -> ReviewJudgement:
    return ReviewJudgement(reviews=[ClaimReview(id="F1", verdict="SUPPORTED" if supported else "OVERSTATED")])


def interview_draft(*, confirmed: bool = True) -> InterviewDraft:
    return InterviewDraft(
        findings=[
            FindingDraft(kind="CONFIRMED" if confirmed else "UNCONFIRMED", content=INTERVIEW_STATEMENT, evidence=ANSWER)
        ]
    )


# 근거 번호로 받는 서류, 면접 Agent 결과 (분석 루프)


def ledger_delegation(llm: FakeLlm) -> tuple[Delegation, Ledger]:
    ledger = Ledger()
    return Delegation(llm, ledger=ledger), ledger


async def test_review_documents_adds_team_facts_as_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    delegation, ledger = ledger_delegation(FakeLlm(extraction(actor="TEAM"), review()))

    text = await delegation.documents_review(scope_of(context), "C1")

    found = ledger.get("E1")
    assert found is not None and found.cap == "CHECK" and found.agent == "Application Agent"
    assert found.quote == DOCUMENT and found.source == "이력서"
    assert f"팀 · {STATEMENT}" in text and text.startswith("D1 ")


async def test_review_documents_keeps_supported_own_fact_ok(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    delegation, ledger = ledger_delegation(FakeLlm(extraction(), review()))

    await delegation.documents_review(scope_of(context), "C1")

    found = ledger.get("E1")
    assert found is not None and found.cap == "OK"


async def test_same_candidate_is_reviewed_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(extraction(), review())
    delegation, _ = ledger_delegation(llm)

    first = await delegation.documents_review(scope_of(context), "C1")
    again = await delegation.documents_review(scope_of(context), "C1")

    assert first == again and len(llm.calls) == 2


async def test_review_interview_previous_must_be_same_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    delegation, _ = ledger_delegation(FakeLlm())

    assert await delegation.interview_review(scope_of(context), "C1", ["D9"]) == INVALID_RESULT


async def test_review_interview_registers_findings(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)
    delegation, ledger = ledger_delegation(FakeLlm(interview_draft(confirmed=False)))

    text = await delegation.interview_review(scope_of(context), "C1", None)

    found = ledger.get("E1")
    assert INTERVIEW_STATEMENT in text
    assert found is not None and found.cap == "CHECK" and found.agent == "Interview Agent" and found.quote == ANSWER


async def test_sub_agent_failure_is_tool_text(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = interview_context(sample_applicants, sample_company, sample_posting)

    def broken(call: LlmCall) -> FakeReply:
        raise LlmOutputError("형식에 맞는 답을 받지 못했다")

    delegation, _ = ledger_delegation(FakeLlm(broken))

    assert await delegation.documents_review(scope_of(context), "C1") == SUB_AGENT_FAILED.format(agent="서류 Agent")


async def test_sub_agent_keeps_the_loop_answer_and_review_calls(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    """하위 Agent는 분석 루프의 최종 답과 근거 검토가 쓸 호출 두 번을 남긴다. 모자라면 실패 대신 안내를 돌려준다."""
    context = interview_context(sample_applicants, sample_company, sample_posting)
    delegation, _ = ledger_delegation(FakeLlm(extraction(), review()))
    budget = new_model_call_budget(3)

    with using_model_call_budget(budget), reserve_model_calls(1):
        text = await delegation.documents_review(scope_of(context), "C1")

    assert text == SUB_AGENT_BUDGET.format(agent="서류 Agent")
    assert budget.remaining == 2
