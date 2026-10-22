"""프로필 저장 함수 테스트. 지원서 분석 Agent가 낸 것처럼 만든 더미 결과(tests/samples/profiles.json)를 저장해 본다."""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import ApplicantDetail, CompanyProfile
from hiremate_ai.db.profile import CandidateProfile, ItemAgent, ItemCategory, ProfileStatus, Verification
from hiremate_ai.db.profile_store import NewItem, ProfileFields, ProfileScopeError, save_profile

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


class SampleProfile(BaseModel):
    """더미 분석 결과 한 명분. 2번 지원서 분석 Agent가 완성되면 실제 결과로 바뀐다."""

    name: str
    fields: ProfileFields
    items: list[NewItem]


SAMPLE_PROFILES = {
    sample.name: sample
    for sample in TypeAdapter(list[SampleProfile]).validate_json((SAMPLES_DIR / "profiles.json").read_bytes())
}


async def save_sample(
    session: AsyncSession, company: CompanyProfile, applicant: ApplicantDetail, items: list[NewItem] | None = None
) -> CandidateProfile:
    """가상 지원자 한 명의 더미 분석 결과를 지원서 분석 Agent처럼 저장한다."""
    sample = SAMPLE_PROFILES[applicant.info.name]
    return await save_profile(
        session,
        company_id=company.company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.APPLICATION,
        fields=sample.fields,
        items=sample.items if items is None else items,
        documents=applicant.documents,
    )


async def reload(session: AsyncSession, application_id: UUID) -> CandidateProfile:
    """메모리에 남은 객체를 비우고 DB에서 다시 읽는다."""
    session.expunge_all()
    profile = await session.scalar(select(CandidateProfile).where(CandidateProfile.application_id == application_id))
    assert profile is not None
    return profile


def test_dummy_profiles_cover_every_sample_applicant(sample_applicants: dict[str, ApplicantDetail]) -> None:
    assert set(SAMPLE_PROFILES) == set(sample_applicants)
    # 더미 프로필에도 차별 조건 낱말을 넣지 않는다 (규칙 6)
    assert [
        item.content for sample in SAMPLE_PROFILES.values() for item in sample.items if blocked_attribute(item.content)
    ] == []


async def test_saves_application_analysis(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    await save_sample(db_session, sample_company, applicant)
    await db_session.commit()

    profile = await reload(db_session, applicant.info.application_id)

    assert profile.company_id == sample_company.company_id
    assert profile.status == ProfileStatus.DONE
    assert (profile.career_years, profile.last_company, profile.document_score, profile.passed) == (
        4,
        "한빛카드",
        88,
        True,
    )
    assert len(profile.items) == 5
    assert {item.agent for item in profile.items} == {ItemAgent.APPLICATION}
    domain = next(item for item in profile.items if item.category == ItemCategory.DOMAIN)
    assert (domain.content, domain.source, domain.verification) == (
        "금융 (카드 결제 · 정산)",
        "이력서",
        Verification.EVIDENCED,
    )


async def test_saves_all_sample_applicants_as_given(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    for applicant in sample_applicants.values():
        await save_sample(db_session, sample_company, applicant)

    saved = {profile.application_id: profile for profile in (await db_session.scalars(select(CandidateProfile))).all()}

    for applicant in sample_applicants.values():
        sample = SAMPLE_PROFILES[applicant.info.name]
        profile = saved[applicant.info.application_id]
        # 받은 값을 그대로 저장한다. 근거가 모두 원문에 있으므로 버려지는 항목도 없다
        assert profile.document_score == sample.fields.document_score
        assert len(profile.items) == len(sample.items)
    # 문서 본문이 빈 윤태오는 확인 필요로 남는다 (정답표 7번)
    assert saved[sample_applicants["윤태오"].info.application_id].status == ProfileStatus.CHECK


async def test_drops_item_whose_evidence_is_not_in_documents(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    items = [
        NewItem(
            category=ItemCategory.EXPERIENCE,
            content="팀장 경험",
            evidence="10명 규모 팀을 이끌었습니다.",
            source="이력서",
        ),
        NewItem(category=ItemCategory.CHECK, content="대용량 근거 확인 필요", evidence=None, source="이력서"),
    ]

    profile = await save_sample(db_session, sample_company, applicant, items)

    # 원문에 없는 근거를 단 항목은 버리고, 근거가 없는 확인 필요 항목은 남긴다
    assert [item.content for item in profile.items] == ["대용량 근거 확인 필요"]


async def test_sets_verification_from_evidence_unless_agent_gives_it(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    sample = SAMPLE_PROFILES["정유민"]
    no_evidence = NewItem(category=ItemCategory.CHECK, content="대용량 근거 확인 필요", source="이력서")
    # 1) 지원서 분석은 확인 상태를 넘기지 않는다 → 근거 문장이 있으면 근거 있음, 없으면 미확인
    await save_sample(db_session, sample_company, applicant, [sample.items[0], no_evidence])
    # 2) 면접 분석은 확인됨 · 상충을 넘긴다. 근거 문장이 없으면 무엇을 넘겼든 미확인
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
                content="장애 대응 당번 경험",
                evidence="장애 당번으로 승인 서버를 직접 운영했습니다.",
                source="1차 면접 답변",
                verification=Verification.CONFIRMED,
            ),
            NewItem(
                category=ItemCategory.CHECK,
                content="정산 배치 개선에서 맡은 역할이 서류와 다름",
                evidence="설계는 팀장님이 하셨고 저는 테스트를 맡았습니다.",
                source="1차 면접 답변",
                verification=Verification.CONFLICT,
            ),
            NewItem(
                category=ItemCategory.STRENGTH,
                content="근거 없이 확인됨을 적은 항목",
                source="1차 면접 답변",
                verification=Verification.CONFIRMED,
            ),
        ],
    )
    await db_session.commit()

    profile = await reload(db_session, applicant.info.application_id)

    states = {item.content: item.verification for item in profile.items}
    assert states == {
        sample.items[0].content: Verification.EVIDENCED,
        "대용량 근거 확인 필요": Verification.UNCONFIRMED,
        "장애 대응 당번 경험": Verification.CONFIRMED,
        "정산 배치 개선에서 맡은 역할이 서류와 다름": Verification.CONFLICT,
        "근거 없이 확인됨을 적은 항목": Verification.UNCONFIRMED,
    }


async def test_corrects_source_to_document_that_has_the_sentence(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    wrong_source = NewItem(
        category=ItemCategory.COMPANY_FIT,
        content="장애 회고 문서화",
        evidence="장애 회고를 문서로 남겨 같은 문제가 반복되지 않게 했습니다.",
        source="이력서",  # 실제로는 자기소개서에 있는 문장
    )

    profile = await save_sample(db_session, sample_company, applicant, [wrong_source])

    assert profile.items[0].source == "자기소개서"


async def test_reanalysis_replaces_only_items_of_same_agent_and_stage(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    await save_sample(db_session, sample_company, applicant)
    assessment_stage = uuid4()
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.ASSESSMENT,
        stage_id=assessment_stage,
        items=[NewItem(category=ItemCategory.STRENGTH, content="과제 테스트 코드 충실", source="평가 결과")],
    )

    # 지원서를 다시 분석해 항목이 하나로 줄었다
    sample = SAMPLE_PROFILES["정유민"]
    await save_sample(db_session, sample_company, applicant, sample.items[:1])
    await db_session.commit()
    profile = await reload(db_session, applicant.info.application_id)

    application_items = [item for item in profile.items if item.agent == ItemAgent.APPLICATION]
    assessment_items = [item for item in profile.items if item.agent == ItemAgent.ASSESSMENT]
    assert [item.content for item in application_items] == [sample.items[0].content]
    assert [(item.content, item.stage_id) for item in assessment_items] == [("과제 테스트 코드 충실", assessment_stage)]


async def test_result_before_application_analysis_creates_check_profile(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["김하늘"]

    profile = await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=applicant.info.recruitment_id,
        application_id=applicant.info.application_id,
        agent=ItemAgent.INTERVIEW,
        stage_id=uuid4(),
        items=[NewItem(category=ItemCategory.STRENGTH, content="장애 대응 경험을 구체적으로 설명", source="면접 답변")],
    )

    assert profile.status == ProfileStatus.CHECK
    assert profile.document_score is None
    assert len(profile.items) == 1


async def test_rejects_profile_of_other_company(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: dict[str, ApplicantDetail]
) -> None:
    applicant = sample_applicants["정유민"]
    await save_sample(db_session, sample_company, applicant)

    with pytest.raises(ProfileScopeError):
        await save_profile(
            db_session,
            company_id=uuid4(),  # 다른 기업
            recruitment_id=applicant.info.recruitment_id,
            application_id=applicant.info.application_id,
            agent=ItemAgent.APPLICATION,
            items=[],
        )
