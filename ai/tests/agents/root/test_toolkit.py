from uuid import UUID, uuid4

import pytest
from root_context import make_context

from hiremate_ai.agents.root.toolkit import context_brief, default_toolkit, keyword_search, scope_of
from hiremate_ai.agents.root.turns import Turn, TurnItem
from hiremate_ai.agents.root.types import CandidateRow, ChatContext
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.tools.candidates import CandidateMatch
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


async def test_brief_has_documents_result_and_interview(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_of(sample_applicants, sample_company, sample_posting)

    brief = await context_brief(scope_of(context), row_of(context, "정유민"))

    assert brief.startswith("C1 정유민")
    assert '<data kind="document"' in brief
    assert "한빛카드 결제플랫폼팀" in brief
    assert "결정: 미결정" in brief
    assert '<data kind="interview"' in brief
    assert "새솔은행" not in brief


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
