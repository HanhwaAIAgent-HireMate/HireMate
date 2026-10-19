"""Root Agent 테스트에서 가상 지원자로 ChatContext를 만드는 도우미. 지원자는 이름으로 가리킨다."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from hiremate_ai.agents.root.types import CandidateRow, ChatContext, Decision
from hiremate_ai.contract import AnalysisStatus, ApplicantDetail, CompanyProfile, PostingContent, StageType

STAGE_ID = UUID("9d8c7b6a-5f4e-4d3c-8b2a-1f0e9d8c7b61")


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
    mentions: Sequence[str | UUID] = (),
    checked: Sequence[str | UUID] = (),
    selected: Sequence[str] = (),
    extra_rows: Sequence[CandidateRow] = (),
) -> ChatContext:
    """가상 지원자 8명이 모두 미결정이고 기준선 위에 있는 전형. 이름이 겹치면 먼저 나온 지원자를 가리킨다."""
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
    return ChatContext(
        stage_id=STAGE_ID,
        recruitment_id=first.info.recruitment_id,
        stage_name="서류 전형" if stage_type is StageType.DOCUMENT else "1차 면접",
        stage_type=stage_type,
        previous_types=list(previous_types),
        candidates=rows,
        documents={applicant.info.application_id: applicant.documents for applicant in applicants.values()},
        document_scores={},
        mentions=pick(mentions),
        checked=pick(checked),
        company=company,
        posting=posting,
        message=message,
    )
