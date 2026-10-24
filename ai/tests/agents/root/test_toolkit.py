from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from root_context import make_context, save_sample_profiles, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.root.toolkit import (
    AgentEvidence,
    cited_agents,
    context_brief,
    default_toolkit,
    get_toolkit,
    keyword_search,
    merged_search,
    profile_toolkit,
    scope_of,
)
from hiremate_ai.agents.root.turns import Turn, TurnItem
from hiremate_ai.agents.root.types import CandidateRow, ChatContext
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType
from hiremate_ai.db.profile import ItemAgent, ItemCategory, Verification
from hiremate_ai.db.profile_store import NewItem, save_profile
from hiremate_ai.db.session import session_factory
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch, SourcedSentence
from hiremate_ai.tools.scope import ToolScope

type Applicants = dict[str, ApplicantDetail]


def context_of(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    return make_context(applicants, company, posting, message="찾아줘")


def ids(applicants: Applicants, *names: str) -> list[UUID]:
    return [applicants[name].info.application_id for name in names]


def names(applicants: Applicants, matches: list[CandidateMatch]) -> list[str]:
    by_id = {applicant.info.application_id: name for name, applicant in applicants.items()}
    return [by_id[match.application_id] for match in matches]


def test_scope_of_context(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    scope = scope_of(context)

    assert (scope.company_id, scope.recruitment_id, scope.stage_id) == (
        sample_company.company_id,
        context.recruitment_id,
        context.stage_id,
    )
    assert scope.application_ids == frozenset(row.application_id for row in context.candidates)
    assert scope.chat is context
    assert scope.called == []


async def test_finance_search_has_recall(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    matches = await keyword_search(scope_of(context), ["금융 도메인 경험"], ids(sample_applicants, *sample_applicants))

    found = set(names(sample_applicants, matches))
    assert {"정유민", "김하늘", "박서준", "이도윤", "최지우", "한예린"} <= found
    assert not found & {"윤태오", "서민재"}
    for match in matches:
        sentence = match.sentences[0]
        documents = context.documents[match.application_id]
        assert any(sentence.sentence in document.text for document in documents)
        assert sentence.source in {"이력서", "자기소개서", "포트폴리오"}


async def test_search_order_is_stable(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    scope = scope_of(context_of(sample_applicants, sample_company, sample_posting))
    pool = ids(sample_applicants, *sample_applicants)
    concepts = ["금융 도메인 경험", "대용량 트래픽 처리"]

    first = await keyword_search(scope, concepts, pool)
    second = await keyword_search(scope, concepts, pool)

    assert first == second
    hits = [match.hits for match in first]
    assert hits == sorted(hits, reverse=True)
    assert hits[0] == 2


async def test_search_stays_in_pool(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    scope = scope_of(context_of(sample_applicants, sample_company, sample_posting))

    matches = await keyword_search(scope, ["금융"], ids(sample_applicants, "박서준", "정유민") + [uuid4()])

    assert names(sample_applicants, matches) == ["박서준", "정유민"]


async def test_empty_documents_are_skipped(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    scope = scope_of(context_of(sample_applicants, sample_company, sample_posting))

    assert await keyword_search(scope, ["금융"], ids(sample_applicants, "윤태오")) == []


async def test_requires_root_context() -> None:
    scope = ToolScope(company_id=uuid4(), recruitment_id=uuid4(), stage_id=uuid4(), application_ids=frozenset())

    with pytest.raises(TypeError):
        await keyword_search(scope, ["금융"], [])


def test_default_toolkit_uses_keyword_search() -> None:
    toolkit = default_toolkit()

    assert toolkit.search is keyword_search
    assert {tool.name for tool in toolkit.answer_tools} == {
        "get_candidate_documents",
        "get_stage_results",
        "get_interview_records",
        "get_company_profile",
        "get_posting",
        "get_stage_summary",
        "get_previous_turns",
    }


def test_profile_toolkit_adds_profile_tool() -> None:
    toolkit = profile_toolkit(session_factory("postgresql+psycopg://unused@localhost/unused"))

    tools = {tool.name for tool in toolkit.answer_tools}
    assert tools == {tool.name for tool in default_toolkit().answer_tools} | {"get_candidate_profile"}


def test_english_synonyms() -> None:
    from hiremate_ai.agents.root.toolkit import concept_terms

    assert "collaboration" in concept_terms("협업 경험")
    assert "payment" in concept_terms("금융 도메인 경험")


async def test_false_hit_does_not_hide_real_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    kim = sample_applicants["김하늘"].info.application_id
    document = context.documents[kim][0].model_copy(
        update={"text": "웹 페이지 렌더링 개선.\n새솔은행 계정계 개발 3년."}
    )
    context = context.model_copy(update={"documents": {**context.documents, kim: [document]}})

    matches = await keyword_search(scope_of(context), ["금융 도메인 경험"], [kim])

    assert "새솔은행 계정계 개발 3년." in [sourced.sentence for sourced in matches[0].sentences]


def fixed(found: dict[str, dict[UUID, list[str]]], source: str) -> CandidateSearch:
    """조건마다 정해 둔 지원자와 문장을 돌려주는 검색."""

    async def search(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        (concept,) = concepts
        return [
            CandidateMatch(application_id, [SourcedSentence(sentence, source) for sentence in sentences], hits=1)
            for application_id, sentences in found.get(concept, {}).items()
            if application_id in pool
        ]

    return search


async def test_merged_search_counts_a_condition_found_by_any_search() -> None:
    a, b = uuid4(), uuid4()
    profiles = fixed({"금융": {a: ["카드 결제"]}}, "이력서")
    documents = fixed({"트래픽": {a: ["120만 건"]}, "금융": {b: ["은행"]}}, "자기소개서")
    scope = ToolScope(company_id=uuid4(), recruitment_id=uuid4(), stage_id=uuid4(), application_ids=frozenset())

    matches = await merged_search(profiles, documents)(scope, ["금융", "트래픽"], [b, a])

    assert matches == [
        CandidateMatch(a, [SourcedSentence("카드 결제", "이력서"), SourcedSentence("120만 건", "자기소개서")], hits=2),
        CandidateMatch(b, [SourcedSentence("은행", "자기소개서")], hits=1),
    ]


async def test_merged_search_fills_each_condition_with_later_search_up_to_limit() -> None:
    a = uuid4()
    profiles = fixed({"금융": {a: ["카드 결제", "정산"]}}, "이력서")
    documents = fixed({"금융": {a: ["정산", "은행", "보험"]}}, "이력서")
    scope = ToolScope(company_id=uuid4(), recruitment_id=uuid4(), stage_id=uuid4(), application_ids=frozenset())

    (match,) = await merged_search(profiles, documents)(scope, ["금융"], [a])

    assert [sourced.sentence for sourced in match.sentences] == ["카드 결제", "정산", "은행"]


async def test_profile_toolkit_search_puts_profile_sentences_first(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    await save_sample_profiles(db_session, sample_company, sample_applicants)
    context = context_of(sample_applicants, sample_company, sample_posting)
    search = profile_toolkit(sessions_of(db_session)).search

    matches = await search(scope_of(context), ["금융 도메인 경험"], ids(sample_applicants, *sample_applicants))

    jung = next(match for match in matches if match.application_id == sample_applicants["정유민"].info.application_id)
    assert jung.sentences[0] == SourcedSentence("한빛카드 결제플랫폼팀 2022.03 ~ 현재", "이력서")
    assert {"정유민", "김하늘", "한예린"} <= set(names(sample_applicants, matches))


async def test_profile_toolkit_search_reads_documents_of_applicants_without_profile(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    # 지원서 분석을 마친 지원자는 정유민뿐이다
    await save_sample_profiles(db_session, sample_company, sample_applicants, names=["정유민"])
    context = context_of(sample_applicants, sample_company, sample_posting)
    search = profile_toolkit(sessions_of(db_session)).search

    matches = await search(scope_of(context), ["금융 도메인 경험"], ids(sample_applicants, *sample_applicants))

    assert {"정유민", "김하늘", "한예린"} <= set(names(sample_applicants, matches))


async def test_profile_toolkit_search_finds_assessment_items_not_in_documents(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    seo = sample_applicants["서민재"].info
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=seo.recruitment_id,
        application_id=seo.application_id,
        agent=ItemAgent.ASSESSMENT,
        items=[
            NewItem(category=ItemCategory.STRENGTH, content="과제에서 Kafka 재처리를 직접 구현", source="평가 결과")
        ],
        stage_id=uuid4(),
    )
    context = context_of(sample_applicants, sample_company, sample_posting)
    pool = ids(sample_applicants, *sample_applicants)

    with_profiles = await profile_toolkit(sessions_of(db_session)).search(scope_of(context), ["Kafka 재처리"], pool)
    documents_only = await keyword_search(scope_of(context), ["Kafka 재처리"], pool)

    seo_match = next(match for match in with_profiles if match.application_id == seo.application_id)
    assert SourcedSentence("과제에서 Kafka 재처리를 직접 구현", "평가 결과") in seo_match.sentences
    assert "서민재" not in names(sample_applicants, documents_only)


def row_of(context: ChatContext, name: str) -> CandidateRow:
    return next(row for row in context.candidates if row.name == name)


def turn_with(application_id: UUID, focus: str, item_text: str) -> Turn:
    return Turn(
        message="면접 질문 만들어줘",
        kind="ANSWER",
        intent="ANSWER",
        targets=[str(application_id)],
        answer="만들었어요.",
        items=[TurnItem(application_id=str(application_id), label="확인할 점", text=item_text)],
        focus={str(application_id): focus},
        total=8,
        plan={},
    )


async def test_brief_has_documents_and_result(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 첫 서류 전형에는 면접 기록이 아직 생기지 않았다. 없는 자료로 읽지 않게 넣지 않는다
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="찾아줘", later_types=(StageType.INTERVIEW,)
    )

    brief = await context_brief(scope_of(context), row_of(context, "정유민"))

    assert brief.startswith("C1 정유민")
    assert '<data kind="document"' in brief
    assert "한빛카드 결제플랫폼팀" in brief
    assert "결정: 미결정" in brief
    assert '<data kind="interview"' not in brief
    assert "면접" not in brief
    assert "새솔은행" not in brief


async def test_brief_has_interview_in_interview_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="찾아줘", stage_type=StageType.INTERVIEW
    )

    brief = await context_brief(scope_of(context), row_of(context, "정유민"))

    assert '<data kind="interview"' in brief


async def test_brief_has_previous_notes(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)
    jung, kim = row_of(context, "정유민"), row_of(context, "김하늘")
    turns = [
        turn_with(jung.application_id, "정산 배치 설계 판단 확인", "배치 시간을 줄인 근거"),
        turn_with(kim.application_id, "계정계 장애 대응 확인", "이체 장애 당번"),
    ]

    brief = await context_brief(scope_of(context, turns), jung)

    assert '<data kind="previous"' in brief
    assert "정산 배치 설계 판단 확인" in brief
    assert "배치 시간을 줄인 근거" in brief
    assert "계정계 장애 대응 확인" not in brief


async def test_brief_without_previous_turns_has_no_previous_block(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    brief = await context_brief(scope_of(context), row_of(context, "정유민"))

    assert '<data kind="previous"' not in brief


async def test_brief_without_documents(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    brief = await context_brief(scope_of(context), row_of(context, "윤태오"))

    assert "읽을 수 있는 제출 문서 본문이 없어요" in brief


def test_default_toolkit_has_brief() -> None:
    assert default_toolkit().brief is context_brief


async def test_profile_brief_adds_profile_after_context(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    # 지원서 분석을 마친 지원자는 정유민뿐이다
    await save_sample_profiles(db_session, sample_company, sample_applicants, names=["정유민"])
    context = context_of(sample_applicants, sample_company, sample_posting)
    brief = profile_toolkit(sessions_of(db_session)).brief
    scope = scope_of(context)
    jung, kim = row_of(context, "정유민"), row_of(context, "김하늘")

    jung_brief = await brief(scope, jung)

    assert jung_brief.startswith(await context_brief(scope, jung))
    assert '<data kind="profile">' in jung_brief
    assert '[도메인] 금융 (카드 결제 · 정산) — 근거: "한빛카드 결제플랫폼팀 2022.03 ~ 현재" (이력서)' in jung_brief
    assert await brief(scope, kim) == await context_brief(scope, kim)


def test_cited_agents_names_agents_of_matching_sentences() -> None:
    first, second = uuid4(), uuid4()
    recorded = {
        first: [AgentEvidence(sentence="장애 원인을 로그로 좁혀 갔어요.", source="평가 메모", agent="assessment")],
        second: [AgentEvidence(sentence="한빛카드 결제플랫폼팀 2022.03 ~ 현재", source="이력서", agent="application")],
    }

    cited = [
        (second, "한빛카드 결제플랫폼팀"),
        (first, "장애 원인을 로그로 좁혀 갔어요."),
        (first, "한빛카드 결제플랫폼팀"),  # 다른 지원자의 근거
        (second, "없는 문장"),
    ]

    assert cited_agents(recorded, cited) == ["Application Agent", "Assessment Agent"]
    assert cited_agents(recorded, [(first, "  ")]) == []


async def test_profile_evidence_reads_items_with_evidence_in_scope(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    jung = sample_applicants["정유민"].info
    note = "장애 원인을 로그로 좁혀 가는 과정을 팀원에게 차근차근 설명했어요."
    conflict = "테스트 코드는 시간이 없어 작성하지 못했습니다."
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=jung.recruitment_id,
        application_id=jung.application_id,
        agent=ItemAgent.ASSESSMENT,
        items=[
            NewItem(category=ItemCategory.STRENGTH, content="원인 분석", evidence=note, source="평가 메모"),
            NewItem(category=ItemCategory.CHECK, content="문제해결 점수가 없어요", source="평가 결과"),
            NewItem(
                category=ItemCategory.CHECK,
                content="설명과 제출물이 다르다",
                evidence=conflict,
                source="평가 제출물",
                verification=Verification.CONFLICT,
            ),
        ],
        stage_id=uuid4(),
    )
    outside = uuid4()
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=jung.recruitment_id,
        application_id=outside,
        agent=ItemAgent.ASSESSMENT,
        items=[NewItem(category=ItemCategory.STRENGTH, content="범위 밖", evidence=note, source="평가 메모")],
        stage_id=uuid4(),
    )
    scope = scope_of(context_of(sample_applicants, sample_company, sample_posting))

    found = await profile_toolkit(sessions_of(db_session)).evidence(scope, [jung.application_id, outside])

    assert found == {
        jung.application_id: [
            AgentEvidence(sentence=note, source="평가 메모", agent="assessment", verification="EVIDENCED"),
            AgentEvidence(sentence=conflict, source="평가 제출물", agent="assessment", verification="CONFLICT"),
        ]
    }


def test_app_toolkit_is_shared() -> None:
    # 찾기 재확인 판정 기억을 요청끼리 같이 쓴다
    assert get_toolkit() is get_toolkit()


def test_default_toolkits_do_not_share_judgments() -> None:
    assert default_toolkit().judged is not default_toolkit().judged
