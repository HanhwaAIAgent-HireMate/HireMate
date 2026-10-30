from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest
from root_context import make_context, save_sample_profiles, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.types import Actor, ApplicationReview, Fact, Period, Quote
from hiremate_ai.agents.root.ledger import Ledger
from hiremate_ai.agents.root.toolkit import (
    NO_PROFILE,
    NO_REVIEW,
    OUT_OF_SCOPE,
    AgentEvidence,
    ProfileLine,
    ProfileView,
    application_block,
    cited_agents,
    company_block,
    db_profile_reader,
    db_review_reader,
    default_toolkit,
    get_toolkit,
    interview_block,
    keyword_search,
    memo_block,
    merged_search,
    no_profile,
    no_review,
    profile_block,
    profile_toolkit,
    scope_of,
    stage_block,
    turns_block,
)
from hiremate_ai.agents.root.turns import Turn, TurnItem
from hiremate_ai.agents.root.types import CandidateRow, ChatContext
from hiremate_ai.contract import (
    ApplicantDetail,
    CompanyProfile,
    DocumentType,
    InterviewerMemo,
    InterviewQuestion,
    InterviewView,
    PostingContent,
    QuestionSource,
    StageType,
)
from hiremate_ai.db.profile import ItemAgent, ItemCategory, Verification
from hiremate_ai.db.profile_store import NewItem, save_profile
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


def test_out_of_scope_points_only_at_existing_steps() -> None:
    # 모델에게 없는 도구를 부르라고 하지 않는다
    assert "resolve_candidates" not in OUT_OF_SCOPE and "clarify" in OUT_OF_SCOPE


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
    assert toolkit.profile is no_profile and toolkit.review is no_review


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


# 근거 번호로 읽는 자료 (Root 분석 루프)


def _evidence_context(
    applicants: Applicants, company: CompanyProfile, posting: PostingContent, **kwargs: Any
) -> ChatContext:
    return make_context(applicants, company, posting, message="자료 확인", **kwargs)


def _caps(ledger: Ledger, refs: Sequence[str]) -> list[str]:
    return [found.cap for ref in refs if (found := ledger.get(ref)) is not None]


def test_profile_block_caps_by_verification(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)
    row = context.candidates[0]
    view = ProfileView(
        front="분석 상태: 분석 완료",
        lines=[
            ProfileLine(
                "EXPERIENCE", "카드 결제 승인 개발", "카드 승인 API를 개발했다.", "이력서", "EVIDENCED", "application"
            ),
            ProfileLine(
                "EXPERIENCE", "대용량 트래픽 처리", "하루 350만 건을 처리했다.", "이력서", "UNCONFIRMED", "application"
            ),
            ProfileLine("CHECK", "Kafka 운영 확인 필요", None, "이력서", "UNCONFIRMED", "application"),
        ],
    )
    ledger = Ledger()

    text = profile_block(ledger, context, row, view)

    assert _caps(ledger, ["E1", "E2", "E3", "E4"]) == ["OK", "OK", "CHECK", "CHECK"]
    assert "E2 [근거 확인] 카드 결제 승인 개발" in text
    result = ledger.get("E1")
    experience = ledger.get("E2")
    assert result is not None and result.source == "전형 결과"
    assert experience is not None and experience.agent == "Application Agent"


def test_profile_block_without_profile(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)

    text = profile_block(Ledger(), context, context.candidates[0], None)

    assert NO_PROFILE in text and "E1 [근거 확인]" in text


def _review(row: CandidateRow, facts: list[Fact], **fields: Any) -> ApplicationReview:
    return ApplicationReview(
        version="test", input_hash="hash", application_id=row.application_id, readable=True, facts=facts, **fields
    )


def _fact(statement: str, actor: Actor) -> Fact:
    return Fact(
        kind="EXPERIENCE",
        statement=statement,
        actor=actor,
        quotes=[Quote(document=DocumentType.RESUME, sentence=f"{statement}.")],
    )


def test_application_block_marks_team_facts_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)
    row = context.candidates[0]
    period = Period(
        company="한빛카드",
        role="백엔드 개발",
        kind="EMPLOYMENT",
        start="2022-03",
        end=None,
        months=55,
        quote=Quote(document=DocumentType.RESUME, sentence="한빛카드 2022.03 ~ 현재"),
    )
    review = _review(
        row, [_fact("결제 API를 개발했다", Actor.SELF), _fact("팀이 정산 DB를 이관했다", Actor.TEAM)], periods=[period]
    )
    ledger = Ledger()

    text = application_block(ledger, context, row, review)

    own = ledger.get("E1")
    team = ledger.get("E2")
    assert own is not None and own.cap == "OK" and own.agent == "Application Agent"
    assert team is not None and team.cap == "CHECK"
    assert "E2 [확인 필요] 팀 · 팀이 정산 DB를 이관했다" in text
    assert "한빛카드" in text


def test_application_block_without_review(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)

    assert application_block(Ledger(), context, context.candidates[0], None).endswith(NO_REVIEW)


def test_interview_answers_are_check(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    first = next(iter(sample_applicants.values())).info.application_id
    question = InterviewQuestion(
        question_id=uuid4(), text="장애 대응 경험은?", source=QuestionSource.AI, answer="제가 주도했습니다."
    )
    view = InterviewView(application_id=first, schedule=None, questions=[question], previous=[])
    context = _evidence_context(
        sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW, interviews={first: view}
    )
    analysis = ProfileView(
        front="",
        lines=[ProfileLine("STRENGTH", "장애 대응 주도", "제가 주도했습니다.", "면접 답변", "CONFIRMED", "interview")],
    )
    ledger = Ledger()

    text = interview_block(ledger, context, context.candidates[0], analysis)

    assert "장애 대응 경험은?" in text
    assert _caps(ledger, ["E1", "E2"]) == ["CHECK", "OK"]
    answer = ledger.get("E1")
    assert answer is not None and answer.source == "면접 기록"


def test_memo_block_keeps_memo_for_questions(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    row = context.candidates[0]
    memo = InterviewerMemo(stage_id=context.stage_id, stage_name="1차 면접", text="협업 사례의 본인 역할 확인 필요")
    context = context.model_copy(update={"interviewer_memos": {row.application_id: [memo]}})
    ledger = Ledger()

    text = memo_block(ledger, context, row)

    found = ledger.get("E1")
    assert "협업 사례의 본인 역할 확인 필요" in text
    assert found is not None and found.memo == memo and found.cap == "CHECK" and found.source == "면접관메모"


def test_stage_block_lines_are_ok_results(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()

    text = stage_block(ledger, context)

    refs = [line.split(" ", 1)[0] for line in text.splitlines() if line.startswith("E")]
    found = [ledger.get(ref) for ref in refs]
    assert refs and all(each is not None and each.cap == "OK" and each.source == "전형 결과" for each in found)
    owners = {each.application_id for each in found if each is not None}
    assert None in owners and context.candidates[0].application_id in owners


def test_company_block_lines_are_ok(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)
    ledger = Ledger()

    text = company_block(ledger, context)

    assert sample_company.name in text and sample_posting.title in text
    first = ledger.get("E1")
    assert first is not None and first.cap == "OK" and first.application_id is None


def test_turns_block_keeps_item_status(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = _evidence_context(sample_applicants, sample_company, sample_posting)
    row = context.candidates[0]
    turn = Turn(
        message="협업 경험 어때?",
        kind="ANSWER",
        intent="ANSWER",
        targets=[str(row.application_id)],
        answer="정리했어요.",
        items=[
            TurnItem(application_id=str(row.application_id), label="협업", text="팀 회고를 이끌었다", status="CHECK"),
            TurnItem(application_id=str(uuid4()), label="범위 밖", text="다른 전형 지원자", status="OK"),
        ],
        focus={},
        total=8,
        plan={},
    )
    ledger = Ledger()

    text = turns_block(ledger, context, [turn])

    found = ledger.get("E1")
    assert "협업 경험 어때?" in text and "범위 밖" not in text
    assert found is not None and found.cap == "CHECK" and found.source == "앞 대화 답변"
    assert found.application_id == row.application_id


async def test_db_readers_read_saved_profile_and_missing_review(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    await save_sample_profiles(db_session, sample_company, sample_applicants, names=["정유민"])
    context = _evidence_context(sample_applicants, sample_company, sample_posting)
    scope = scope_of(context)
    read = db_profile_reader(sessions_of(db_session))
    review = db_review_reader(sessions_of(db_session))

    saved = await read(scope, sample_applicants["정유민"].info.application_id)
    missing = await read(scope, sample_applicants["김하늘"].info.application_id)

    assert saved is not None and saved.lines and saved.front
    assert missing is None
    assert await review(scope, sample_applicants["정유민"].info.application_id) is None
