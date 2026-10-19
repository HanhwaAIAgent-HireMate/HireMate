from typing import Any

from root_context import make_context

from hiremate_ai.agents.root.find import candidate_pool, plan_find
from hiremate_ai.agents.root.route import DEFAULT_CLARIFY, RootRoute
from hiremate_ai.agents.root.toolkit import default_toolkit
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, Intent, SelectionMode
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm

type Applicants = dict[str, ApplicantDetail]


def adjust(context: ChatContext, **changes: dict[str, Any]) -> ChatContext:
    """이름별로 지원자 행을 바꾼다. 예: adjust(context, 정유민={"score": 90})."""
    rows = [row.model_copy(update=changes.get(row.name, {})) for row in context.candidates]
    return context.model_copy(update={"candidates": rows})


def names(context: ChatContext, plan: ChatPlan) -> list[str]:
    by_id = {row.application_id: row.name for row in context.candidates}
    return [by_id[application_id] for application_id in plan.targets]


def assessment_context(
    applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any
) -> ChatContext:
    context = make_context(applicants, company, posting, message="찾아줘", stage_type=StageType.ASSESSMENT, **kwargs)
    return adjust(context, 정유민={"score": 90.0}, 김하늘={"score": 70.0}, 박서준={"score": 82.5})


def test_pool_rules(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="찾아줘", selected=["박서준"])
    context = adjust(context, 정유민={"above_line": False}, 김하늘={"decision": Decision.PASS})

    pool = [row.name for row in candidate_pool(RootRoute(kind="FIND"), context)]
    narrowed = [row.name for row in candidate_pool(RootRoute(kind="FIND", mode=SelectionMode.NARROW), context)]

    assert "정유민" not in pool
    assert "김하늘" not in pool
    assert pool[0] == "박서준"
    assert narrowed == ["박서준"]


def test_above_line_only_matters_in_document_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = assessment_context(sample_applicants, sample_company, sample_posting)
    context = adjust(context, 정유민={"above_line": False, "score": 90.0})

    assert "정유민" in [row.name for row in candidate_pool(RootRoute(kind="FIND"), context)]


async def test_min_score_without_model(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = assessment_context(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm()

    plan = await plan_find(llm, RootRoute(kind="FIND", min_score=80), context, default_toolkit())

    assert names(context, plan) == ["정유민", "박서준"]
    assert (plan.intent, plan.mode) == (Intent.FIND, SelectionMode.REPLACE)
    assert plan.message == "지원자 {total}명 중 조건에 맞는 **{count}명**을 선택했어요."
    assert [item.text for item in plan.items] == ["평가 90점", "평가 82.5점"]
    assert plan.sources == ["평가 결과"]
    assert llm.calls == []


async def test_without_score(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = assessment_context(sample_applicants, sample_company, sample_posting)

    plan = await plan_find(FakeLlm(), RootRoute(kind="FIND", without_score=True), context, default_toolkit())

    assert names(context, plan) == ["이도윤", "최지우", "한예린", "윤태오", "서민재"]


async def test_score_gap_sorted(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = assessment_context(sample_applicants, sample_company, sample_posting)
    scores = {
        sample_applicants["정유민"].info.application_id: 70,
        sample_applicants["김하늘"].info.application_id: 95,
        sample_applicants["박서준"].info.application_id: 80,
    }
    context = context.model_copy(update={"document_scores": scores})

    plan = await plan_find(FakeLlm(), RootRoute(kind="FIND", score_gap=True), context, default_toolkit())

    assert names(context, plan) == ["김하늘", "정유민"]
    assert [item.text for item in plan.items] == [
        "평가 70점 · 서류 95점, 지원서에 비해 평가가 낮음",
        "평가 90점 · 서류 70점, 평가가 지원서보다 높음",
    ]
    assert plan.sources == ["평가 결과", "서류 점수"]


async def test_no_conditions_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="찾아줘")

    plan = await plan_find(FakeLlm(), RootRoute(kind="FIND"), context, default_toolkit())

    assert plan == ChatPlan.answer(Intent.CLARIFY, DEFAULT_CLARIFY)


async def test_narrow_and_add_messages(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = assessment_context(
        sample_applicants, sample_company, sample_posting, selected=["정유민", "김하늘", "이도윤"]
    )

    narrowed = await plan_find(
        FakeLlm(), RootRoute(kind="FIND", mode=SelectionMode.NARROW, min_score=80), context, default_toolkit()
    )
    added = await plan_find(
        FakeLlm(), RootRoute(kind="FIND", mode=SelectionMode.ADD, min_score=80), context, default_toolkit()
    )

    assert names(context, narrowed) == ["정유민"]
    assert narrowed.message == "3명 중 **{count}명**으로 좁혔어요."
    assert added.message == "조건에 맞는 **{count}명**을 선택 지원자에 더했어요."
