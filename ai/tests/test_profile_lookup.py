"""프로필 조회 도구 테스트. 더미 프로필(tests/samples/profiles.json)을 저장하고 Root 도구 루프처럼 불러 본다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.contract import ApplicantDetail, CompanyProfile
from hiremate_ai.db.profile import ItemAgent
from hiremate_ai.db.profile_store import NewItem, ProfileFields, save_profile
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.fake import FakeLlm, ToolCall
from hiremate_ai.tools.profile_lookup import (
    NO_PROFILE,
    OUT_OF_SCOPE,
    ResolveRef,
    Sessions,
    profile_text,
    profile_tool,
    read_profile,
    uuid_ref,
)
from hiremate_ai.tools.scope import ToolScope

type Applicants = dict[str, ApplicantDetail]

SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


class SampleProfile(BaseModel):
    name: str
    fields: ProfileFields
    items: list[NewItem]


class Answer(BaseModel):
    """도구 루프의 최종 답 형식 (테스트용)."""

    text: str


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
    first = next(iter(applicants.values()))
    return ToolScope(
        company_id=company.company_id,
        recruitment_id=first.info.recruitment_id,
        stage_id=uuid4(),
        application_ids=frozenset(applicant.info.application_id for applicant in applicants.values()),
    )


def numbered(applicants: Applicants) -> ResolveRef:
    """Root처럼 지원자 번호(C1 = 지원 번호 1)를 지원서 id로 바꾸는 resolve 함수."""
    by_no = {f"C{applicant.info.application_no}": applicant.info.application_id for applicant in applicants.values()}
    return lambda scope, ref: by_no.get(ref.strip().upper())


def sessions_of(session: AsyncSession) -> Sessions:
    """테스트 세션을 그대로 빌려주는 Sessions. 닫지 않아야 테스트가 끝날 때 한꺼번에 되돌릴 수 있다."""

    @asynccontextmanager
    async def opened() -> AsyncIterator[AsyncSession]:
        yield session

    return opened


async def test_root_tool_loop_reads_profile_with_scope_from_code(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    tool = profile_tool(sessions_of(db_session), resolve=numbered(sample_applicants))
    # 모델은 도구를 한 번 부르고(C1 = 정유민) 답을 낸다
    llm = FakeLlm(ToolCall("get_candidate_profile", {"candidate": "C1"}), Answer(text="금융 경험이 분명해요"))

    result = await llm.tool_agent(
        Answer, agent="root", system="지원자를 분석한다", tools=[tool], context=ToolScope
    ).run("@정유민 우리 회사랑 잘 맞아?", context=scope_of(sample_company, sample_applicants))

    assert result.text == "금융 경험이 분명해요"
    # 두 번째 모델 호출에는 도구 결과가 <data> 블록으로 감싸져 들어간다
    tool_result = llm.calls[1].user
    assert '<data kind="tool" name="get_candidate_profile">' in tool_result
    assert '[도메인] 금융 (카드 결제 · 정산) — 근거: "한빛카드 결제플랫폼팀 2022.03 ~ 현재" (이력서)' in tool_result


def test_model_cannot_choose_scope() -> None:
    tool = profile_tool(session_factory("postgresql+psycopg://unused@localhost/unused"), resolve=uuid_ref)

    # 모델이 채우는 인자는 지원자 번호뿐이다. 기업 · 채용 · 전형은 코드가 runtime.context로 넣는다
    assert set(tool.args) == {"candidate"}


async def test_profile_text_shows_front_and_items_with_evidence(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    scope = scope_of(sample_company, sample_applicants)

    jung = await read_profile(db_session, scope, sample_applicants["정유민"].info.application_id)
    yoon = await read_profile(db_session, scope, sample_applicants["윤태오"].info.application_id)

    assert jung is not None and yoon is not None
    jung_text = profile_text(jung).splitlines()
    assert jung_text[:3] == [
        "분석 상태: 분석 완료",
        "요약: 카드 결제 승인 · 정산 4년, 대용량 트랜잭션 처리 경험",
        "경력 4년 · 마지막 회사 한빛카드 · 서류 점수 88 · AI 기준 통과",
    ]
    assert jung_text[3].startswith("[도메인]")  # 분류 순서: 자격 조건 → 도메인 → 직무 경험 → ...
    # 문서 본문이 빈 윤태오는 값이 없다고 적고, 근거 없는 항목은 근거가 없다고 적는다 (지어내지 않게)
    assert profile_text(yoon).splitlines() == [
        "분석 상태: 확인 필요",
        "요약: 제출 문서 본문을 읽지 못해 분석하지 못했어요",
        "경력 알 수 없음 · 서류 점수 없음 · AI 기준 판단 없음",
        "[확인 필요] 제출 문서 본문이 비어 있음. 원본 파일 확인 필요 — 근거 문장 없음 (이력서) · 미확인",
    ]


async def test_read_profile_stays_in_scope(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    await save_samples(db_session, sample_company, sample_applicants)
    scope = scope_of(sample_company, sample_applicants)
    jung = sample_applicants["정유민"].info.application_id
    other_company = ToolScope(uuid4(), scope.recruitment_id, scope.stage_id, scope.application_ids)
    other_stage = ToolScope(scope.company_id, scope.recruitment_id, uuid4(), frozenset())

    assert await read_profile(db_session, scope, jung) is not None
    assert await read_profile(db_session, other_company, jung) is None  # 다른 기업
    assert await read_profile(db_session, other_stage, jung) is None  # 이 전형의 지원자가 아님


async def test_unknown_candidate_and_missing_profile(
    db_session: AsyncSession, sample_company: CompanyProfile, sample_applicants: Applicants
) -> None:
    # 프로필을 하나도 저장하지 않았다 (분석 전)
    tool = profile_tool(sessions_of(db_session), resolve=numbered(sample_applicants))
    llm = FakeLlm(
        [
            ToolCall("get_candidate_profile", {"candidate": "C99"}),
            ToolCall("get_candidate_profile", {"candidate": "C2"}),
        ],
        Answer(text="답"),
    )

    await llm.tool_agent(Answer, agent="root", system="", tools=[tool], context=ToolScope).run(
        "질문", context=scope_of(sample_company, sample_applicants)
    )

    tool_results = llm.calls[1].user
    assert OUT_OF_SCOPE in tool_results  # 없는 번호
    assert NO_PROFILE in tool_results  # 번호는 맞지만 아직 프로필이 없음


def test_uuid_ref_reads_application_id() -> None:
    application_id = uuid4()
    scope = ToolScope(uuid4(), uuid4(), uuid4(), frozenset())

    assert uuid_ref(scope, f" {application_id} ") == application_id
    assert uuid_ref(scope, "C1") is None
