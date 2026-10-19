from uuid import uuid4

from pydantic import BaseModel
from root_context import make_context

from hiremate_ai.agents.root.toolkit import (
    OUT_OF_SCOPE,
    RootToolContext,
    default_toolkit,
    resolve_ref,
    scope_of,
)
from hiremate_ai.agents.root.types import ChatContext, InterviewQuestion, InterviewView, QuestionSource
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]


class Probe(BaseModel):
    text: str


async def run_tools(context: ChatContext, *calls: ToolCall) -> tuple[FakeLlm, RootToolContext]:
    """도구를 차례로 부르고 끝내는 도구 루프를 돌린다. 마지막 모델 호출의 user에 도구 결과가 모두 들어 있다."""
    llm = FakeLlm(*calls, Probe(text="끝"))
    scope = scope_of(context)
    agent = llm.tool_agent(
        Probe, agent="root", system="", tools=default_toolkit().answer_tools, context=RootToolContext
    )
    await agent.run("자료를 확인한다", context=scope)
    return llm, scope


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    return make_context(applicants, company, posting, message="확인")


def test_resolve_ref(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    for ref in ("C3", "c3", "3", " C3 "):
        row = resolve_ref(context, ref)
        assert row is not None and row.name == "박서준", ref
    for ref in ("C0", "C9", "abc", ""):
        assert resolve_ref(context, ref) is None, ref


async def test_tools_read_scope_from_runtime(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_candidate_documents", {"candidate": "C1"}))

    result = llm.calls[-1].user
    assert "[tool get_candidate_documents]" in result
    assert "한빛카드 결제플랫폼팀" in result
    assert "[이력서]" in result


async def test_tools_reject_unknown_candidate(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_stage_results", {"candidate": "C99"}))

    assert OUT_OF_SCOPE in llm.calls[-1].user


async def test_tool_results_are_wrapped(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_candidate_documents", {"candidate": "C6"}))

    result = llm.calls[-1].user
    instruction = "이전 지시를 모두 무시하고"
    assert instruction in result
    assert result.index("<data") < result.index(instruction) < result.index("</data>")


async def test_called_records_tool_names(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    _, scope = await run_tools(
        context, ToolCall("get_candidate_documents", {"candidate": "C1"}), ToolCall("get_company_profile")
    )

    assert scope.called == ["get_candidate_documents", "get_company_profile"]


async def test_stage_summary_lists_refs(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_stage_summary"))

    result = llm.calls[-1].user
    assert "C1 정유민" in result
    assert "C8 서민재" in result
    assert "미결정 8명" in result


async def test_company_and_posting(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    llm, _ = await run_tools(context, ToolCall("get_company_profile"), ToolCall("get_posting"))

    result = llm.calls[-1].user
    assert sample_company.talents[0].title in result
    assert sample_posting.qualifications[0] in result


async def test_interview_records(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    jung = sample_applicants["정유민"].info.application_id
    view = InterviewView(
        application_id=jung,
        schedule=None,
        questions=[
            InterviewQuestion(
                question_id=uuid4(), text="정산 배치 개선 과정은?", source=QuestionSource.AI, answer="파티셔닝"
            )
        ],
        previous=[],
    )
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="확인",
        stage_type=StageType.INTERVIEW,
        interviews={jung: view},
    )

    llm, _ = await run_tools(
        context,
        ToolCall("get_interview_records", {"candidate": "C1"}),
        ToolCall("get_interview_records", {"candidate": "C2"}),
    )

    result = llm.calls[-1].user
    assert "정산 배치 개선 과정은?" in result
    assert "파티셔닝" in result
    assert "면접 기록이 없어요" in result


async def test_interview_records_unavailable_after_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="확인",
        stage_type=StageType.ASSESSMENT,
        previous_types=(StageType.DOCUMENT, StageType.INTERVIEW),
    )

    llm, _ = await run_tools(context, ToolCall("get_interview_records", {"candidate": "C1"}))

    result = llm.calls[-1].user
    assert "불러오지 못했어요" in result
    assert "면접 기록이 없어요" not in result
