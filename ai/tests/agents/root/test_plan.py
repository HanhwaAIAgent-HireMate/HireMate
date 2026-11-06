import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from root_context import make_context

from hiremate_ai.agents.root.analysis import ANALYSIS_SYSTEM
from hiremate_ai.agents.root.conversation import ConversationReview
from hiremate_ai.agents.root.find import SearchQuery
from hiremate_ai.agents.root.plan import (
    EMPTY_FIND,
    NO_MENTIONS_HINT,
    NO_SCOPE,
    PICKS_INVALID,
    PLAN_SYSTEM,
    TABS_INVALID,
    AnswerPlan,
    EditPlan,
    FindPlan,
    has_condition,
    make_plan,
    screen_text,
)
from hiremate_ai.agents.root.types import ChatContext, ChatTab
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm, ToolCall

type Applicants = dict[str, ApplicantDetail]

SAMPLE_NAMES = ("정유민", "김하늘", "박서준", "이도윤", "최지우", "한예린", "윤태오", "서민재")
FIND_KAFKA = {
    "query": {"mode": "replace", "concepts": ["Kafka 운영"], "min_score": None},
    "scope": {},
    "remove": False,
}


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    return make_context(applicants, company, posting, **{"message": "요청", **kwargs})


async def test_plan_reads_find_form(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="Kafka 운영 경험자 찾아줘")

    plan = await make_plan(FakeLlm(ToolCall("find", FIND_KAFKA)), context, [], None, [])

    assert plan.kind == "find"
    assert isinstance(plan.form, FindPlan) and plan.form.query.concepts == ["Kafka 운영"]


def test_screen_lists_referable_people_only(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"], selected=["김하늘"])
    result = [str(sample_applicants["한예린"].info.application_id)]

    text = screen_text(context, [], result, [])

    assert "[멘션] C1 정유민" in text
    assert "[선택] C2 김하늘" in text
    assert "[이전 결과] 1. C6 한예린" in text
    assert "[현재 요청] 요청" in text
    assert "박서준" not in text


def test_screen_tells_empty_result_from_no_record(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    assert "[이전 결과] 없음" in screen_text(context, [], None, [])
    assert "[이전 결과] 0명" in screen_text(context, [], [], [])


def tabbed(context: ChatContext, applicants: Applicants) -> ChatContext:
    ids = {name: applicants[name].info.application_id for name in applicants}
    tabs = [
        ChatTab(id=uuid4(), name="경력 5년 이상", current=False, application_ids=[ids["정유민"], ids["김하늘"]]),
        ChatTab(id=uuid4(), name="시스템 연동", current=False, application_ids=[ids["정유민"]]),
        ChatTab(id=uuid4(), name="새 탭", current=True, application_ids=[]),
    ]
    return context.model_copy(update={"tabs": tabs})


def test_screen_lists_tabs_with_current_and_counts(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = tabbed(context_of(sample_applicants, sample_company, sample_posting), sample_applicants)

    text = screen_text(context, [], None, [])

    assert "[탭] T1 경력 5년 이상 (선택 2명), T2 시스템 연동 (선택 1명), T3 새 탭 (현재 탭, 선택 0명)" in text
    assert "[탭]" not in screen_text(context_of(sample_applicants, sample_company, sample_posting), [], None, [])


async def test_unknown_tab_is_rewritten_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = tabbed(
        context_of(sample_applicants, sample_company, sample_posting, message="2개 탭 공통 지원자 찾아줘"),
        sample_applicants,
    )
    llm = FakeLlm(
        ToolCall("edit", {"action": "ADD", "scope": {"tabs": ["T7"]}}),
        ToolCall("edit", {"action": "ADD", "scope": {"tabs": ["T1", "T2"]}}),
    )

    plan = await make_plan(llm, context, [], None, [])

    assert isinstance(plan.form, EditPlan) and plan.form.scope.tabs == ["T1", "T2"]
    assert TABS_INVALID in llm.calls[1].user


async def test_unknown_pick_is_rewritten_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm(
        ToolCall("answer", {"scope": {"picks": ["C99"]}}),
        ToolCall("answer", {"scope": {"sources": ["all"]}}),
    )

    plan = await make_plan(llm, context, [], None, [])

    assert isinstance(plan.form, AnswerPlan) and plan.form.scope.sources == ["all"]
    assert PICKS_INVALID in llm.calls[1].user


async def test_find_without_condition_is_rewritten(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    empty = {"query": {"mode": "replace", "concepts": [], "min_score": None}, "scope": {}, "remove": False}
    llm = FakeLlm(ToolCall("find", empty), ToolCall("find", FIND_KAFKA))

    plan = await make_plan(llm, context, [], None, [])

    assert plan.kind == "find" and EMPTY_FIND in llm.calls[1].user


async def test_missing_mentions_with_previous_subject_is_rewritten_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="그 사람 선택에서 빼줘")
    subject = [str(sample_applicants["서민재"].info.application_id)]
    llm = FakeLlm(
        ToolCall("edit", {"action": "REMOVE", "scope": {"sources": ["mentions"]}}),
        ToolCall("edit", {"action": "REMOVE", "scope": {"sources": ["subject"]}}),
    )

    plan = await make_plan(llm, context, [], None, subject)

    assert plan.scope is not None and plan.scope.sources == ["subject"]
    assert NO_MENTIONS_HINT in llm.calls[1].user


async def test_edit_without_scope_is_rewritten(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, mentions=["정유민"])
    llm = FakeLlm(
        ToolCall("edit", {"action": "ADD", "scope": {}}),
        ToolCall("edit", {"action": "ADD", "scope": {"sources": ["mentions"]}}),
    )

    plan = await make_plan(llm, context, [], None, [])

    assert plan.kind == "edit" and NO_SCOPE in llm.calls[1].user


async def test_conversation_failing_review_is_rewritten(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(
        sample_applicants, sample_company, sample_posting, message="이 지원자 경력 요약해 줘", mentions=["정유민"]
    )
    llm = FakeLlm(
        ToolCall("conversation", {"message": "자료를 확인해서 요약해 드릴게요."}),
        ConversationReview(allowed=False),
        ToolCall("answer", {"scope": {"sources": ["mentions"]}}),
    )

    plan = await make_plan(llm, context, [], None, [])

    assert plan.kind == "answer"


async def test_allowed_conversation_passes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, message="고마워")
    llm = FakeLlm(ToolCall("conversation", {"message": "천만에요."}), ConversationReview(allowed=True))

    plan = await make_plan(llm, context, [], None, [])

    assert plan.kind == "conversation" and len(llm.calls) == 2


def test_career_years_alone_is_a_find_condition() -> None:
    assert has_condition(SearchQuery(min_career_years=3))
    assert has_condition(SearchQuery(max_career_years=0))


def test_find_form_tells_add_and_narrow_where_to_search() -> None:
    # 더하기를 앞 결과 안에서 찾으면 더할 사람이 없고, 좁히기에 앞 조건을 다시 적으면 앞 결과가 다시 걸러진다
    assert "선택이나 앞 결과를 범위로 쓰지 않는다" in (FindPlan.model_fields["scope"].description or "")
    assert "within_selected는 앞 조건 없이 새 조건만 적는다" in PLAN_SYSTEM
    assert "add와 within_selected는 현재 요청의 새 조건만" in (FindPlan.model_fields["query"].description or "")


def test_career_years_description_says_months_are_dropped() -> None:
    # 5년 7개월도 5로 저장하므로 '5년 넘는'을 6으로 쓰면 그 사람이 빠진다
    schema = SearchQuery.model_json_schema()["properties"]["min_career_years"]

    assert "'5년 넘는'도 5다" in schema["description"]


def test_prompt_length_and_invented_names() -> None:
    assert 1700 <= len(PLAN_SYSTEM) <= 2300
    assert not any(name in PLAN_SYSTEM for name in SAMPLE_NAMES)


def test_prompt_has_no_eval_message() -> None:
    cases = json.loads((Path(__file__).parents[2] / "eval" / "root_cases.json").read_text(encoding="utf-8"))
    messages = [turn["message"] for case in cases for turn in case["turns"]]

    assert messages
    assert not any(message in PLAN_SYSTEM or message in ANALYSIS_SYSTEM for message in messages)
