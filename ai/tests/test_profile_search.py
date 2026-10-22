"""프로필 검색 테스트. 더미 프로필 8명(tests/samples/profiles.json)을 저장한 뒤 찾아 본다.

기대 결과는 tests/samples/README.md의 지원자별 정답표를 따른다.
"""

from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.contract import ApplicantDetail, CompanyProfile
from hiremate_ai.db.profile import ItemAgent, ItemCategory, Verification
from hiremate_ai.db.profile_store import NewItem, ProfileFields, save_profile
from hiremate_ai.db.session import session_factory
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch
from hiremate_ai.tools.profile_search import profile_search, search_profiles, simple_terms
from hiremate_ai.tools.scope import ToolScope

type Applicants = dict[str, ApplicantDetail]

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


class SampleProfile(BaseModel):
    name: str
    fields: ProfileFields
    items: list[NewItem]


SAMPLE_PROFILES = TypeAdapter(list[SampleProfile]).validate_json((SAMPLES_DIR / "profiles.json").read_bytes())


async def save_samples(session: AsyncSession, company: CompanyProfile, applicants: Applicants) -> None:
    """더미 프로필 8명을 지원서 분석 Agent처럼 저장한다."""
    for sample in SAMPLE_PROFILES:
        applicant = applicants[sample.name]
        await save_profile(
            session,
            company_id=company.company_id,
            recruitment_id=applicant.info.recruitment_id,
            application_id=applicant.info.application_id,
            agent=ItemAgent.APPLICATION,
            fields=sample.fields,
            items=sample.items,
            documents=applicant.documents,
        )


def scope_of(company: CompanyProfile, applicants: Applicants) -> ToolScope:
    """현재 전형의 조회 범위. Root가 코드로 넣는 값이다."""
    first = next(iter(applicants.values()))
    return ToolScope(
        company_id=company.company_id,
        recruitment_id=first.info.recruitment_id,
        stage_id=uuid4(),
        application_ids=frozenset(applicant.info.application_id for applicant in applicants.values()),
    )


def everyone(applicants: Applicants) -> list[UUID]:
    """지원 번호 순서의 후보 id."""
    return [
        applicant.info.application_id for applicant in sorted(applicants.values(), key=lambda a: a.info.application_no)
    ]


def names(applicants: Applicants, matches: list[CandidateMatch]) -> list[str]:
    by_id = {applicant.info.application_id: name for name, applicant in applicants.items()}
    return [by_id[match.application_id] for match in matches]


async def test_finance_experience_finds_finance_applicants_only(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)

    found = await search_profiles(
        db_session, scope_of(sample_company, sample_applicants), ["금융 도메인 경험"], everyone(sample_applicants)
    )

    # 정답표: 금융 경험은 정유민 · 김하늘 · 한예린. 박서준은 "결제 도메인은 처음"이 확인 필요 항목이라 빠진다
    assert names(sample_applicants, found) == ["정유민", "김하늘", "한예린"]
    jung = found[0]
    assert jung.hits == 1
    assert [(sentence.sentence, sentence.source) for sentence in jung.sentences] == [
        ("한빛카드 결제플랫폼팀 2022.03 ~ 현재", "이력서")
    ]


async def test_returned_sentences_are_in_applicant_documents(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)

    found = await search_profiles(
        db_session,
        scope_of(sample_company, sample_applicants),
        ["정산", "Spring"],
        everyone(sample_applicants),
    )

    # Root의 재확인은 문서 출처 문장이 원문에 있는지 다시 본다. 원문 그대로의 근거 문장을 돌려줘야 한다
    by_id = {applicant.info.application_id: applicant for applicant in sample_applicants.values()}
    for match in found:
        texts = {document.text for document in by_id[match.application_id].documents}
        assert all(any(sentence.sentence in text for text in texts) for sentence in match.sentences)


async def test_more_matched_conditions_come_first_then_pool_order(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    scope = scope_of(sample_company, sample_applicants)

    found = await search_profiles(db_session, scope, ["대용량 트래픽", "카드"], everyone(sample_applicants))
    again = await search_profiles(db_session, scope, ["대용량 트래픽", "카드"], everyone(sample_applicants))

    # 정유민은 두 조건이 다 맞고, 박서준은 대용량 트래픽, 한예린은 카드(카드사 매입 데이터)만 맞는다.
    # 맞은 수가 같으면 후보를 받은 순서(지원 번호)대로다
    assert [(name, match.hits) for name, match in zip(names(sample_applicants, found), found, strict=True)] == [
        ("정유민", 2),
        ("박서준", 1),
        ("한예린", 1),
    ]
    assert found == again  # 같은 질문에는 같은 결과


async def test_only_candidates_in_pool_and_scope(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    scope = scope_of(sample_company, sample_applicants)
    pool = [sample_applicants["김하늘"].info.application_id, uuid4()]  # 두 번째는 이 전형 밖의 지원자

    found = await search_profiles(db_session, scope, ["금융"], pool)

    assert names(sample_applicants, found) == ["김하늘"]


async def test_other_company_profiles_are_not_searched(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    scope = scope_of(sample_company, sample_applicants)
    other_company = ToolScope(
        company_id=uuid4(),
        recruitment_id=scope.recruitment_id,
        stage_id=scope.stage_id,
        application_ids=scope.application_ids,
    )

    assert await search_profiles(db_session, other_company, ["금융"], everyone(sample_applicants)) == []


async def test_check_items_and_document_items_without_evidence_are_not_used(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    scope = scope_of(sample_company, sample_applicants)

    # 박서준의 "결제 도메인은 처음"은 확인 필요 항목이라 결제 경험의 근거로 쓰지 않는다
    payment = await search_profiles(db_session, scope, ["결제"], everyone(sample_applicants))
    # 서민재의 "백엔드 개발 요건 미충족 (프론트엔드 경력)"은 근거 문장이 없는 이력서 항목이라 쓰지 않는다
    frontend = await search_profiles(db_session, scope, ["프론트엔드"], everyone(sample_applicants))

    assert "박서준" not in names(sample_applicants, payment)
    assert frontend == []


async def test_assessment_items_without_evidence_are_found_by_content(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    applicant = sample_applicants["박서준"]
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.ASSESSMENT,
        stage_id=uuid4(),
        items=[
            NewItem(category=ItemCategory.STRENGTH, content="과제에서 멱등성 처리를 꼼꼼히 구현", source="평가 결과")
        ],
    )

    found = await search_profiles(
        db_session, scope_of(sample_company, sample_applicants), ["멱등성"], everyone(sample_applicants)
    )

    assert names(sample_applicants, found) == ["박서준"]
    assert [(s.sentence, s.source) for s in found[0].sentences] == [("과제에서 멱등성 처리를 꼼꼼히 구현", "평가 결과")]


async def test_conflict_and_unconfirmed_interview_items_are_not_used(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    applicant = sample_applicants["박서준"]
    # 1) 면접 분석이 확인됨 · 상충 · 미확인 항목을 하나씩 낸 것처럼 저장한다 (셋 다 답변 근거 문장이 있다)
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.INTERVIEW,
        stage_id=uuid4(),
        items=[
            NewItem(
                category=ItemCategory.STRENGTH,
                content="멱등성 처리를 직접 구현",
                evidence="같은 결제 요청이 두 번 와도 한 번만 처리되게 멱등성 키를 넣었습니다.",
                source="1차 면접 답변",
                verification=Verification.CONFIRMED,
            ),
            NewItem(
                category=ItemCategory.EXPERIENCE,
                content="파티셔닝 설계를 맡았다는 서류 내용과 다름",
                evidence="파티셔닝은 선배가 설계했고 저는 적용만 했습니다.",
                source="1차 면접 답변",
                verification=Verification.CONFLICT,
            ),
            NewItem(
                category=ItemCategory.EXPERIENCE,
                content="샤딩 운영 경험은 답변이 모호함",
                evidence="샤딩은 운영 중인 시스템에서 조금 봤던 것 같습니다.",
                source="1차 면접 답변",
                verification=Verification.UNCONFIRMED,
            ),
        ],
    )
    scope, pool = scope_of(sample_company, sample_applicants), everyone(sample_applicants)

    confirmed = await search_profiles(db_session, scope, ["멱등성"], pool)
    conflict = await search_profiles(db_session, scope, ["파티셔닝"], pool)
    unconfirmed = await search_profiles(db_session, scope, ["샤딩"], pool)

    # 2) 확인됨은 근거 문장과 함께 찾고, 상충 · 미확인은 근거로 쓰지 않는다
    assert names(sample_applicants, confirmed) == ["박서준"]
    assert [(s.sentence, s.source) for s in confirmed[0].sentences] == [
        ("같은 결제 요청이 두 번 와도 한 번만 처리되게 멱등성 키를 넣었습니다.", "1차 면접 답변")
    ]
    assert conflict == []
    assert unconfirmed == []


async def test_discriminatory_conditions_are_not_searched(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)

    found = await search_profiles(
        db_session, scope_of(sample_company, sample_applicants), ["30살 이하", "여성"], everyone(sample_applicants)
    )

    assert found == []


async def test_profile_search_fits_root_search_shape(
    database_url: str, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    search: CandidateSearch = profile_search(session_factory(database_url))

    # 저장된 프로필이 없는 DB에서도 Root가 부르는 모양 그대로 동작한다
    assert await search(scope_of(sample_company, sample_applicants), ["금융"], everyone(sample_applicants)) == []
    await session_factory(database_url).kw["bind"].dispose()


def test_simple_terms_drops_particles_and_common_words() -> None:
    assert simple_terms("금융 도메인 경험이 있는 지원자") == ["금융"]
    assert simple_terms("대용량 트래픽 처리") == ["대용량", "트래픽"]
    assert simple_terms("Spring Boot 경험") == ["spring", "boot"]
