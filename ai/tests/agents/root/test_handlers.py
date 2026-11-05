from collections.abc import Sequence
from typing import Any
from uuid import UUID

from root_context import Recorder, make_context

from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.agents.root.find import LOCKED, RecheckItem, RecheckResult, SearchQuery
from hiremate_ai.agents.root.handlers import (
    DECISION_REPLY,
    INTERVIEWER_LOCKED,
    NOT_INTERVIEW,
    NOTHING_TO_ADD,
    NOTHING_TO_REMOVE,
    TOO_MANY,
    handle_edit,
    handle_find,
    handle_questions,
    handle_reply,
    precheck,
)
from hiremate_ai.agents.root.plan import (
    BlockedPlan,
    ClarifyPlan,
    DecisionPlan,
    EditPlan,
    FindPlan,
    QuestionsPlan,
    RootPlan,
)
from hiremate_ai.agents.root.scope import Scope
from hiremate_ai.agents.root.toolkit import NO_MEMOS, RootToolkit
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, Decision, EditAction, Intent, SelectionMode
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, InterviewerMemo, PostingContent, StageType
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.tools.candidates import CandidateMatch, SourcedSentence
from hiremate_ai.tools.scope import ToolScope

type Applicants = dict[str, ApplicantDetail]


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any) -> ChatContext:
    return make_context(applicants, company, posting, **{"message": "요청", **kwargs})


def rows_of(context: ChatContext, *names: str) -> list[CandidateRow]:
    return [row for name in names for row in context.candidates if row.name == name]


def resume_match(applicants: Applicants, name: str) -> CandidateMatch:
    """지원자 이력서의 실제 문장 하나로 검색 결과를 만든다. 재확인은 원문에 있는 문장만 근거로 받는다."""
    applicant = applicants[name]
    sentence = next(
        line.strip()
        for line in applicant.documents[0].text.splitlines()
        if len(line.strip()) >= 8 and applicant.info.name not in line and "@" not in line
    )
    return CandidateMatch(
        application_id=applicant.info.application_id,
        sentences=[SourcedSentence(sentence=sentence, source=applicant.documents[0].type.label)],
        hits=1,
    )


class SpySearch:
    def __init__(self, matches: list[CandidateMatch]) -> None:
        self.matches = matches
        self.pools: list[list[UUID]] = []

    async def __call__(self, scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        self.pools.append(list(pool))
        return [match for match in self.matches if match.application_id in pool]


def met(*numbers: int) -> RecheckResult:
    return RecheckResult(results=[RecheckItem(candidate_no=number, met=True, sentence_nos=[1]) for number in numbers])


def kafka(**fields: Any) -> FindPlan:
    query = SearchQuery.model_validate(
        {"mode": "replace", "concepts": ["결제 시스템 개발"], "min_score": None, **fields}
    )
    return FindPlan(query=query, scope=Scope(), remove=False)


async def test_find_in_result_scope_uses_pool(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    search = SpySearch([resume_match(sample_applicants, "김하늘"), resume_match(sample_applicants, "한예린")])
    rows = rows_of(context, "김하늘", "한예린")

    handled = await handle_find(
        FakeLlm(met(1, 2)), context, RootToolkit(search=search), kafka(), rows, progress=Recorder()
    )

    assert set(search.pools[0]) == {row.application_id for row in rows}
    assert handled.kind == "FIND" and handled.mode is SelectionMode.REPLACE
    assert set(handled.plan.targets) == {row.application_id for row in rows}


async def test_remove_turns_matches_into_edit_remove(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, selected=["김하늘", "박서준"])
    search = SpySearch([resume_match(sample_applicants, "박서준")])
    form = kafka().model_copy(update={"remove": True})

    handled = await handle_find(FakeLlm(met(1)), context, RootToolkit(search=search), form, None, progress=Recorder())

    assert (handled.plan.intent, handled.plan.edit, handled.kind) == (Intent.EDIT, EditAction.REMOVE, "EDIT")
    assert handled.plan.targets == [sample_applicants["박서준"].info.application_id]


async def test_remove_without_match_keeps_selection(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, selected=["김하늘"])
    form = kafka().model_copy(update={"remove": True})

    handled = await handle_find(FakeLlm(), context, RootToolkit(search=SpySearch([])), form, None, progress=Recorder())

    assert handled.plan.message == NOTHING_TO_REMOVE and handled.plan.targets == []


async def test_find_blocks_discriminatory_condition(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    llm = FakeLlm()
    form = kafka(concepts=["30대 남성"])

    handled = await handle_find(llm, context, RootToolkit(search=SpySearch([])), form, None, progress=Recorder())

    assert handled.plan.intent is Intent.BLOCKED and handled.plan.message == BLOCKED_REPLY
    assert llm.calls == []


def test_add_all_skips_unselectable_quietly(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, selected=["김하늘"])
    passed = sample_applicants["박서준"].info.application_id
    candidates = [
        row.model_copy(update={"decision": Decision.PASS}) if row.application_id == passed else row
        for row in context.candidates
    ]
    context = context.model_copy(update={"candidates": candidates})
    form = EditPlan(action=EditAction.ADD, scope=Scope(sources=["all"]))

    handled = handle_edit(context, form, context.candidates, all_scope=True)

    expected = [row.application_id for row in context.candidates if row.name not in ("김하늘", "박서준")]
    assert handled.plan.targets == expected and handled.plan.items == [] and handled.kind == "EDIT"


def test_add_all_with_nobody_left(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, selected=list(sample_applicants))
    form = EditPlan(action=EditAction.ADD, scope=Scope(sources=["all"]))

    handled = handle_edit(context, form, context.candidates, all_scope=True)

    assert handled.plan.intent is Intent.CLARIFY and handled.plan.message == NOTHING_TO_ADD


def test_questions_none_sets_targets_and_replace(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    rows = rows_of(context, "정유민")
    form = QuestionsPlan(scope=Scope(sources=["mentions"]), checks="none", replace=True)

    handled = handle_questions(context, form, rows)

    assert handled.plan.question_targets == [rows[0].application_id]
    assert handled.plan.question_replace is True
    assert handled.plan.message == "1명의 면접 질문 생성을 요청했어요."


def test_reply_kinds(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    decision = handle_reply(context, RootPlan(kind="decision", form=DecisionPlan()))
    blocked = handle_reply(context, RootPlan(kind="blocked", form=BlockedPlan()))
    clarify = handle_reply(context, RootPlan(kind="clarify", form=ClarifyPlan(message="C1 님을 말씀하시나요?")))

    assert decision.plan.message == DECISION_REPLY
    assert (blocked.plan.intent, blocked.plan.message) == (Intent.BLOCKED, BLOCKED_REPLY)
    assert clarify.plan.intent is Intent.CLARIFY and clarify.plan.message == "정유민 님을 말씀하시나요?"


def test_precheck_cases(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    document = context_of(sample_applicants, sample_company, sample_posting)
    locked = document.model_copy(update={"selectable": False})
    interview = context_of(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    edit = RootPlan(kind="edit", form=EditPlan(action=EditAction.ADD, scope=Scope(sources=["mentions"])))
    questions = RootPlan(kind="questions", form=QuestionsPlan(scope=Scope(sources=["all"]), checks="none"))
    memos = RootPlan(kind="questions", form=QuestionsPlan(scope=Scope(sources=["all"]), checks="memos"))
    many = [document.candidates[0]] * 21

    locked_plan = precheck(locked, edit, document.candidates[:1])
    not_interview = precheck(document, questions, document.candidates[:1])
    too_many = precheck(interview, questions, many)
    no_memos = precheck(interview, memos, interview.candidates[:1])

    assert locked_plan is not None and locked_plan.message == LOCKED
    assert not_interview is not None and not_interview.message == NOT_INTERVIEW
    assert too_many is not None and too_many.message == TOO_MANY
    assert no_memos is not None and no_memos.message == NO_MEMOS
    memo = InterviewerMemo(stage_id=interview.stage_id, stage_name="1차 면접", text="본인 역할 확인")
    with_memo = interview.model_copy(update={"interviewer_memos": {interview.candidates[0].application_id: [memo]}})
    assert precheck(with_memo, memos, with_memo.candidates[:1]) is None


def test_precheck_tells_interviewers_they_cannot_change_selection(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    interview = context_of(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    interviewer = interview.model_copy(update={"interviewer": True, "selectable": False})
    edit = RootPlan(kind="edit", form=EditPlan(action=EditAction.ADD, scope=Scope(sources=["mentions"])))
    find = RootPlan(kind="find", form=kafka())
    questions = RootPlan(kind="questions", form=QuestionsPlan(scope=Scope(sources=["all"]), checks="none"))

    for plan in (edit, find):
        answer = precheck(interviewer, plan, interviewer.candidates[:1])
        assert answer is not None and answer.message == INTERVIEWER_LOCKED
    # 면접관도 질문 만들기는 된다
    assert precheck(interviewer, questions, interviewer.candidates[:1]) is None


def test_handle_questions_carries_ncs(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    rows = rows_of(context, "정유민")
    form = QuestionsPlan(scope=Scope(sources=["mentions"]), checks="none", ncs="HELPFUL")

    handled = handle_questions(context, form, rows)

    assert handled.plan.question_ncs == "HELPFUL"


def test_questions_plan_defaults_to_skip_ncs() -> None:
    assert QuestionsPlan(scope=Scope(sources=["mentions"]), checks="none").ncs == "SKIP"


def test_memo_questions_never_use_ncs_in_handler(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    """확인할 점이 모두 빠져 정해진 처리기로 돌아와도 메모 질문은 NCS를 참고하지 않는다."""
    context = context_of(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    rows = rows_of(context, "정유민")
    form = QuestionsPlan(scope=Scope(sources=["mentions"]), checks="memos", ncs="REQUESTED")

    assert handle_questions(context, form, rows).plan.question_ncs == "SKIP"
