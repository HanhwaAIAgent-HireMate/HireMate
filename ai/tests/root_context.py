"""Root Agent 테스트에서 가상 지원자로 ChatContext를 만들고 더미 프로필을 저장하는 도우미.

지원자는 이름으로 가리킨다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hiremate_ai.agents.root.types import (
    CandidateRow,
    ChatContext,
    ChatItem,
    ChatStage,
    Decision,
    StageStatus,
)
from hiremate_ai.contract import (
    AnalysisStatus,
    ApplicantDetail,
    CompanyProfile,
    InterviewView,
    PostingContent,
    StageType,
)
from hiremate_ai.db.profile import ItemAgent
from hiremate_ai.db.profile_store import NewItem, ProfileFields, save_profile
from hiremate_ai.llm.fake import ToolCall

STAGE_ID = UUID("9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b61")
STAGE_NAMES = {StageType.DOCUMENT: "서류 전형", StageType.ASSESSMENT: "과제 평가", StageType.INTERVIEW: "1차 면접"}
SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


class SampleProfile(BaseModel):
    name: str
    fields: ProfileFields
    items: list[NewItem]


SAMPLE_PROFILES = TypeAdapter(list[SampleProfile]).validate_json((SAMPLES_DIR / "profiles.json").read_bytes())


async def save_sample_profiles(
    session: AsyncSession,
    company: CompanyProfile,
    applicants: dict[str, ApplicantDetail],
    names: Sequence[str] | None = None,
) -> None:
    """더미 프로필(tests/samples/profiles.json)을 지원서 분석 Agent처럼 저장한다. names를 주면 그 지원자만 저장한다."""
    for sample in SAMPLE_PROFILES:
        if names is not None and sample.name not in names:
            continue
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


def sessions_of(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """테스트 세션의 연결과 트랜잭션을 함께 쓰는 세션 공장. 테스트가 끝나면 db_session과 함께 되돌린다."""
    return async_sessionmaker(bind=session.bind, join_transaction_mode="create_savepoint", expire_on_commit=False)


def extra_row(name: str) -> CandidateRow:
    """샘플에 없는 지원자 한 명 (동명이인, 비슷한 이름 확인용). 제출 문서는 없다."""
    return CandidateRow(
        application_id=uuid4(),
        name=name,
        career_years=None,
        last_company=None,
        decision=Decision.PENDING,
        selected=False,
        ai_selected=False,
        above_line=True,
        score=None,
        analysis_status=AnalysisStatus.PENDING,
    )


def make_context(
    applicants: dict[str, ApplicantDetail],
    company: CompanyProfile,
    posting: PostingContent,
    *,
    message: str,
    stage_type: StageType = StageType.DOCUMENT,
    previous_types: Sequence[StageType] = (),
    later_types: Sequence[StageType] = (),
    stage_status: StageStatus = StageStatus.ACTIVE,
    mentions: Sequence[str | UUID] = (),
    checked: Sequence[str | UUID] = (),
    selected: Sequence[str] = (),
    extra_rows: Sequence[CandidateRow] = (),
    interviews: Mapping[UUID, InterviewView] | None = None,
) -> ChatContext:
    """가상 지원자 8명이 모두 미결정이고 기준선 위에 있는 전형. 이름이 겹치면 먼저 나온 지원자를 가리킨다.

    전형 구성은 앞 전형(previous_types, 종료) → 현재 전형(stage_status) → 뒤 전형(later_types, 시작 전)이다.
    """
    rows = [
        CandidateRow(
            application_id=applicant.info.application_id,
            name=applicant.info.name,
            career_years=applicant.info.career_years,
            last_company=applicant.info.last_company,
            decision=Decision.PENDING,
            selected=applicant.info.name in selected,
            ai_selected=False,
            above_line=True,
            score=None,
            analysis_status=applicant.info.analysis_status,
        )
        for applicant in applicants.values()
    ]
    rows += extra_rows
    ids: dict[str, UUID] = {}
    for row in rows:
        ids.setdefault(row.name, row.application_id)

    def pick(people: Sequence[str | UUID]) -> list[UUID]:
        return [person if isinstance(person, UUID) else ids[person] for person in people]

    first = next(iter(applicants.values()))
    stage_name = "서류 전형" if stage_type is StageType.DOCUMENT else "1차 면접"
    stages = [
        *(ChatStage(id=uuid4(), name=STAGE_NAMES[kind], type=kind, status=StageStatus.DONE) for kind in previous_types),
        ChatStage(id=STAGE_ID, name=stage_name, type=stage_type, status=stage_status),
        *(ChatStage(id=uuid4(), name=STAGE_NAMES[kind], type=kind, status=StageStatus.PENDING) for kind in later_types),
    ]
    return ChatContext(
        stage_id=STAGE_ID,
        recruitment_id=first.info.recruitment_id,
        thread_id=f"{company.company_id}:{STAGE_ID}:test",
        stage_name=stage_name,
        selectable=True,
        stage_type=stage_type,
        stages=stages,
        candidates=rows,
        documents={applicant.info.application_id: applicant.documents for applicant in applicants.values()},
        document_scores={},
        interviews=dict(interviews or {}),
        mentions=pick(mentions),
        checked=pick(checked),
        company=company,
        posting=posting,
        message=message,
    )


@dataclass
class Recorder:
    """진행 알림을 모아 두는 Progress. 낸 순서대로 남는다."""

    statuses: list[str] = field(default_factory=list)
    depths: list[int] = field(default_factory=list)  # statuses와 같은 순서의 단계 깊이
    items: list[ChatItem] = field(default_factory=list)

    def status(self, text: str, depth: int = 0) -> None:
        self.statuses.append(text)
        self.depths.append(depth)

    def item(self, item: ChatItem) -> None:
        self.items.append(item)


def form_call(kind: str, **args: Any) -> ToolCall:
    """모델이 종류별 최종 답 도구(계획이나 분석 루프의 forms)를 부르는 응답. 값은 검증하지 않고 그대로 옮긴다."""
    return ToolCall(kind, dict(args))
