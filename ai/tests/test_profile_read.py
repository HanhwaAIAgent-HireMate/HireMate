"""화면용 프로필 조회 테스트. 분석 Agent처럼 저장한 프로필을 backend가 부르는 경로로 읽어 본다."""

from typing import Any
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.api.profile import ReadRequest, read_profile_view
from hiremate_ai.db.profile import ItemAgent, ItemCategory, ProfileStatus, Verification
from hiremate_ai.db.profile_store import NewItem, ProfileFields, save_profile
from hiremate_ai.db.session import get_session
from hiremate_ai.main import app

COMPANY_ID = UUID("3c1f5e2a-7b4d-4e8a-9f60-1a2b3c4d5e6f")
RECRUITMENT_ID = UUID("7a1e2b3c-4d5e-4f60-8a9b-0c1d2e3f4a51")
STAGE_ID = UUID("6e3d9a2f-4b5c-4d7e-9f01-2a3b4c5d6e7f")


async def save_jung(session: AsyncSession) -> UUID:
    """가상 지원자 정유민의 서류 · 면접 분석 결과를 저장한다. 확인 상태 네 가지가 모두 들어 있다."""
    application_id = uuid4()
    # 1) 지원서 분석: 근거 있음 · 미확인
    await save_profile(
        session,
        company_id=COMPANY_ID,
        recruitment_id=RECRUITMENT_ID,
        application_id=application_id,
        agent=ItemAgent.APPLICATION,
        fields=ProfileFields(
            status=ProfileStatus.DONE,
            career_years=4,
            last_company="한빛카드",
            summary="카드 결제 승인 · 정산 4년",
        ),
        items=[
            NewItem(
                category=ItemCategory.DOMAIN,
                content="금융 (카드 결제 · 정산)",
                evidence="한빛카드 결제플랫폼팀 2022.03 ~ 현재",
                source="이력서",
            ),
            NewItem(category=ItemCategory.CHECK, content="대용량 트래픽 처리 수치 확인 필요", source="이력서"),
        ],
    )
    # 2) 면접 분석: 확인됨 · 상충
    await save_profile(
        session,
        company_id=COMPANY_ID,
        recruitment_id=RECRUITMENT_ID,
        application_id=application_id,
        agent=ItemAgent.INTERVIEW,
        stage_id=STAGE_ID,
        items=[
            NewItem(
                category=ItemCategory.STRENGTH,
                content="장애 대응 당번으로 승인 서버를 직접 운영",
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
        ],
    )
    await session.commit()
    return application_id


def request(application_id: UUID, company_id: UUID = COMPANY_ID) -> ReadRequest:
    return ReadRequest(company_id=company_id, recruitment_id=RECRUITMENT_ID, application_id=application_id)


async def post_read(session: AsyncSession, body: dict[str, Any]) -> Any:
    app.dependency_overrides[get_session] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post("/agents/profile/read", json=body)
    finally:
        app.dependency_overrides.clear()


async def test_reads_items_with_verification(db_session: AsyncSession) -> None:
    application_id = await save_jung(db_session)

    view = await read_profile_view(db_session, request(application_id))

    assert (view.application_id, view.status, view.summary) == (
        application_id,
        ProfileStatus.DONE,
        "카드 결제 승인 · 정산 4년",
    )
    # 항목마다 확인 상태와 어느 단계(Agent · 전형)에서 나왔는지가 함께 간다
    states = {(item.content, item.agent, item.stage_id): item.verification for item in view.items}
    assert states == {
        ("금융 (카드 결제 · 정산)", "application", None): Verification.EVIDENCED,
        ("대용량 트래픽 처리 수치 확인 필요", "application", None): Verification.UNCONFIRMED,
        ("장애 대응 당번으로 승인 서버를 직접 운영", "interview", STAGE_ID): Verification.CONFIRMED,
        ("정산 배치 개선에서 맡은 역할이 서류와 다름", "interview", STAGE_ID): Verification.CONFLICT,
    }


async def test_other_company_and_missing_profile_read_as_empty(db_session: AsyncSession) -> None:
    application_id = await save_jung(db_session)

    other_company = await read_profile_view(db_session, request(application_id, company_id=uuid4()))
    missing = await read_profile_view(db_session, request(uuid4()))

    # 다른 기업의 프로필은 있어도 없는 것처럼 비어 있다 (규칙 4)
    for view in (other_company, missing):
        assert (view.status, view.summary, view.items) == (None, "", [])
    assert other_company.application_id == application_id


async def test_route_answers_in_contract_shape(db_session: AsyncSession) -> None:
    application_id = await save_jung(db_session)
    body = {"companyId": str(COMPANY_ID), "recruitmentId": str(RECRUITMENT_ID), "applicationId": str(application_id)}

    response = await post_read(db_session, body)

    assert response.status_code == 200
    data = response.json()
    assert (data["applicationId"], data["status"]) == (str(application_id), "DONE")
    conflict = next(item for item in data["items"] if item["verification"] == "CONFLICT")
    assert conflict == {
        "category": "CHECK",
        "agent": "interview",
        "content": "정산 배치 개선에서 맡은 역할이 서류와 다름",
        "evidence": "설계는 팀장님이 하셨고 저는 테스트를 맡았습니다.",
        "source": "1차 면접 답변",
        "verification": "CONFLICT",
        "stageId": str(STAGE_ID),
    }
