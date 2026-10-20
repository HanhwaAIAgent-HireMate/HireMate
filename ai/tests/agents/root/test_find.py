from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from root_context import extra_row, make_context

from hiremate_ai.agents.root.find import (
    LIMIT_NOTE,
    NOT_FOUND,
    RECHECK_LIMIT,
    RecheckItem,
    RecheckResult,
    candidate_pool,
    plan_find,
)
from hiremate_ai.agents.root.route import DEFAULT_CLARIFY, NOT_UNDERSTOOD, RootRoute
from hiremate_ai.agents.root.toolkit import RootToolkit, default_toolkit
from hiremate_ai.agents.root.types import ChatContext, ChatPlan, Decision, Intent, SelectionMode
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.llm.prompt import UNTRUSTED_RULE
from hiremate_ai.tools.candidates import CandidateMatch, SourcedSentence
from hiremate_ai.tools.scope import ToolScope

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


FINANCE = RootRoute(kind="FIND", mode=SelectionMode.REPLACE, concepts=["금융 도메인 경험"])
SENTENCES = {
    "정유민": "카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다.",
    "김하늘": "간편결제 정산 시스템을 Spring Boot로 새로 만들었습니다.",
    "한예린": "가맹점 정산 시스템을 Java와 Spring Batch로 개발했습니다.",
}


# 기본 검색에서 "금융 도메인 경험"에 걸리는 순서. 재확인의 후보 번호는 이 순서다
FINANCE_ORDER = ["정유민", "김하늘", "박서준", "이도윤", "최지우", "한예린"]


def rechecked(order: Sequence[str], met: Mapping[str, list[int] | None], *extra: RecheckItem) -> RecheckResult:
    """이름 → 근거 문장 번호들(None이면 충족하지 않음). 후보 번호는 order(검색 순서)로 정한다."""
    return RecheckResult(
        results=[
            RecheckItem(candidate_no=order.index(name) + 1, met=numbers is not None, sentence_nos=numbers or [])
            for name, numbers in met.items()
        ]
        + list(extra)
    )


def match(applicants: Applicants, name: str, sentence: str) -> CandidateMatch:
    sourced = [SourcedSentence(sentence=sentence, source="이력서")]
    return CandidateMatch(application_id=applicants[name].info.application_id, sentences=sourced, hits=1)


class SpySearch:
    """받은 조건과 후보를 기록하고, 정해 둔 결과를 돌려준다."""

    def __init__(self, matches: list[CandidateMatch] | None = None) -> None:
        self.matches = matches or []
        self.calls: list[tuple[list[str], list[UUID]]] = []

    async def __call__(self, scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        self.calls.append((list(concepts), list(pool)))
        return self.matches


async def test_finance_keeps_rechecked(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")
    met = {"정유민": [1], "김하늘": [1], "한예린": [1], "박서준": None, "이도윤": None}
    llm = FakeLlm(rechecked(FINANCE_ORDER, met))

    plan = await plan_find(llm, FINANCE, context, default_toolkit())

    assert names(context, plan) == ["정유민", "김하늘", "한예린"]
    assert [item.label for item in plan.items] == ["정유민", "김하늘", "한예린"]
    assert plan.items[1].text == "페이온 정산개발팀 2025.01 ~ 현재"
    assert plan.sources == ["이력서"]
    assert plan.agents == []
    assert [call.agent for call in llm.calls] == ["root"]


async def test_recheck_drops_sentence_missing_from_documents(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")
    search = SpySearch(
        [
            match(sample_applicants, "정유민", SENTENCES["정유민"]),
            match(sample_applicants, "박서준", "카드사에서 결제 시스템을 5년 운영했습니다."),
        ]
    )

    plan = await plan_find(
        FakeLlm(rechecked(["정유민", "박서준"], {"정유민": [1], "박서준": [1]})),
        FINANCE,
        context,
        RootToolkit(search=search),
    )

    assert names(context, plan) == ["정유민"]
    assert plan.items[0].text == SENTENCES["정유민"]


async def test_recheck_drops_unknown_sentence_number(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")

    plan = await plan_find(
        FakeLlm(rechecked(FINANCE_ORDER, {"정유민": [1], "김하늘": [9], "한예린": [0]})),
        FINANCE,
        context,
        default_toolkit(),
    )

    assert names(context, plan) == ["정유민"]


async def test_recheck_keeps_valid_numbers_among_invalid(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")

    plan = await plan_find(FakeLlm(rechecked(FINANCE_ORDER, {"정유민": [9, 1]})), FINANCE, context, default_toolkit())

    assert names(context, plan) == ["정유민"]
    assert plan.items[0].text == SENTENCES["정유민"]


async def test_recheck_ignores_unknown_candidate_numbers(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")
    result = rechecked(
        FINANCE_ORDER,
        {"정유민": [1]},
        RecheckItem(candidate_no=99, met=True, sentence_nos=[1]),
        RecheckItem(candidate_no=0, met=True, sentence_nos=[1]),
    )

    plan = await plan_find(FakeLlm(result), FINANCE, context, default_toolkit())

    assert names(context, plan) == ["정유민"]


async def test_recheck_prompt_uses_data_blocks(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")
    llm = FakeLlm(rechecked(FINANCE_ORDER, {"정유민": [1]}))

    await plan_find(llm, FINANCE, context, default_toolkit())

    call = llm.calls[0]
    assert call.user.count("<data") == 6
    assert 'no="6"' in call.user
    assert str(sample_applicants["정유민"].info.application_id) not in call.user
    assert "모두 충족" in call.user
    assert "금융 도메인 경험" in call.user
    assert "금융 경험 있는 사람 찾아줘" in call.user
    assert "정유민" not in call.user
    assert UNTRUSTED_RULE in call.system


async def test_none_met_answers_not_found(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")

    plan = await plan_find(FakeLlm(rechecked(FINANCE_ORDER, {"박서준": None})), FINANCE, context, default_toolkit())

    assert plan == ChatPlan.answer(Intent.ANSWER, NOT_FOUND)


async def test_no_search_match_skips_model(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="양자 컴퓨팅 경험자 찾아줘")
    llm = FakeLlm()

    plan = await plan_find(llm, RootRoute(kind="FIND", concepts=["양자 컴퓨팅"]), context, default_toolkit())

    assert plan == ChatPlan.answer(Intent.ANSWER, NOT_FOUND)
    assert llm.calls == []


async def test_recheck_error_clarifies(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    def broken(call: LlmCall) -> RecheckResult:
        raise LlmOutputError("RecheckResult 형식의 답을 받지 못했다")

    context = make_context(sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘")

    plan = await plan_find(FakeLlm(broken), FINANCE, context, default_toolkit())

    assert plan == ChatPlan.answer(Intent.CLARIFY, NOT_UNDERSTOOD)


async def test_recheck_limit(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    rows = [extra_row(f"지원자{number}") for number in range(30)]
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="금융 경험 있는 사람 찾아줘", extra_rows=rows
    )
    first = sample_applicants["정유민"].info.application_id
    matches = [CandidateMatch(application_id=first, sentences=[SourcedSentence(SENTENCES["정유민"], "이력서")], hits=2)]
    matches += [
        CandidateMatch(
            application_id=row.application_id,
            sentences=[SourcedSentence("결제 시스템을 만들었습니다", "이력서")],
            hits=1,
        )
        for row in context.candidates
        if row.application_id != first
    ]
    llm = FakeLlm(rechecked(["정유민"], {"정유민": [1]}))

    plan = await plan_find(llm, FINANCE, context, RootToolkit(search=SpySearch(matches)))

    assert len(matches) > RECHECK_LIMIT
    assert llm.calls[0].user.count("<data") == RECHECK_LIMIT
    assert names(context, plan) == ["정유민"]
    assert plan.message.endswith(LIMIT_NOTE)


async def test_use_talents_adds_concepts(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="우리 회사가 중요하게 보는 사람")
    search = SpySearch()

    await plan_find(FakeLlm(), RootRoute(kind="FIND", use_talents=True), context, RootToolkit(search=search))

    concepts = search.calls[0][0]
    assert len(concepts) == len(sample_company.talents)
    for concept, talent in zip(concepts, sample_company.talents, strict=True):
        assert talent.title in concept
        assert talent.description in concept


async def test_scores_then_search(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = assessment_context(sample_applicants, sample_company, sample_posting)
    search = SpySearch()

    await plan_find(
        FakeLlm(),
        RootRoute(kind="FIND", min_score=80, concepts=["금융 도메인 경험"]),
        context,
        RootToolkit(search=search),
    )

    pool = search.calls[0][1]
    by_id = {row.application_id: row.name for row in context.candidates}
    assert [by_id[application_id] for application_id in pool] == ["정유민", "박서준"]


async def test_talents_count_when_any_one_shows(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="우리 회사가 중요하게 보는 사람")
    sentence = "장애 회고를 문서로 남겨 같은 문제가 반복되지 않게 했습니다."
    search = SpySearch([match(sample_applicants, "정유민", sentence)])
    llm = FakeLlm(rechecked(["정유민"], {"정유민": [1]}))

    plan = await plan_find(llm, RootRoute(kind="FIND", use_talents=True), context, RootToolkit(search=search))

    assert "인재상 (하나 이상 드러나야 한다)" in llm.calls[0].user
    assert "조건 (모두 충족해야 한다)" not in llm.calls[0].user
    assert names(context, plan) == ["정유민"]


async def test_several_conditions_keep_every_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="금융이랑 트래픽 경험 둘 다")
    route = RootRoute(kind="FIND", concepts=["금융 도메인 경험", "대용량 트래픽 처리"])
    llm = FakeLlm(rechecked(["정유민"], {"정유민": [1, 2]}))
    search = SpySearch(
        [
            CandidateMatch(
                application_id=sample_applicants["정유민"].info.application_id,
                sentences=[
                    SourcedSentence("한빛카드 결제플랫폼팀 2022.03 ~ 현재", "이력서"),
                    SourcedSentence(
                        "하루 120만 건 승인 트랜잭션을 처리하는 승인 서버의 응답 시간을 180ms에서 90ms로 줄였습니다.",
                        "이력서",
                    ),
                ],
                hits=2,
            )
        ]
    )

    plan = await plan_find(llm, route, context, RootToolkit(search=search))

    assert "모두 충족" in llm.calls[0].user
    assert names(context, plan) == ["정유민"]
    assert plan.items[0].text == "한빛카드 결제플랫폼팀 2022.03 ~ 현재"


async def test_talent_reference_words_are_not_conditions(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message="우리 회사가 중요하게 보는 사람")
    search = SpySearch()
    route = RootRoute(kind="FIND", use_talents=True, concepts=["회사 인재상", "중요하게 보는 요소"])

    await plan_find(FakeLlm(), route, context, RootToolkit(search=search))

    assert search.calls[0][0] == [f"{talent.title} {talent.description}" for talent in sample_company.talents]


async def test_own_condition_with_talents_keeps_both_groups(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="금융 경험 있고 인재상에 맞는 사람"
    )
    search = SpySearch([match(sample_applicants, "정유민", SENTENCES["정유민"])])
    llm = FakeLlm(rechecked(["정유민"], {"정유민": [1]}))
    route = RootRoute(kind="FIND", use_talents=True, concepts=["금융 도메인 경험"])

    await plan_find(llm, route, context, RootToolkit(search=search))

    user = llm.calls[0].user
    assert "조건 (모두 충족해야 한다):\n- 금융 도메인 경험" in user
    assert "인재상 (하나 이상 드러나야 한다)" in user
