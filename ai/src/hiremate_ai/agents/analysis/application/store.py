"""분석 결과 저장 · 재사용. ai.application_reviews에 원본을, ai.candidate_profiles에 요약과 항목을 넣는다.

같은 입력(공고 · 서류 · 평가 기준 · NCS 평가 조건 · 분석 버전)이면 저장된 결과를 쓰고 모델을 다시 부르지 않는다.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.ncs import criteria_of, ncs_units
from hiremate_ai.agents.analysis.application.present import to_profile
from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.application_review import ApplicationReviewRecord
from hiremate_ai.db.profile import ItemAgent
from hiremate_ai.db.profile_store import save_profile
from hiremate_ai.tools.ncs import NcsUnit

type Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class ReviewStore(Protocol):
    """분석에 필요한 저장소. 라우터는 DbReviewStore를 쓰고, 테스트는 메모리 구현을 넣는다."""

    async def units(self, codes: Sequence[str]) -> dict[str, NcsUnit]: ...

    async def find(self, application_id: UUID, input_hash: str) -> ApplicationReview | None: ...

    async def latest(self, application_id: UUID) -> ApplicationReview | None: ...

    async def save(self, review: ApplicationReview, applicant: ApplicantDetail, rubric: ScreeningRubric) -> None: ...


class DbReviewStore:
    """세션을 짧게 열고 닫는다. 모델을 기다리는 동안 DB 연결을 잡고 있지 않는다."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions

    async def units(self, codes: Sequence[str]) -> dict[str, NcsUnit]:
        async with self._sessions() as session:
            return await ncs_units(session, codes)

    async def find(self, application_id: UUID, input_hash: str) -> ApplicationReview | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ApplicationReviewRecord).where(
                    ApplicationReviewRecord.application_id == application_id,
                    ApplicationReviewRecord.input_hash == input_hash,
                )
            )
            return ApplicationReview.model_validate(record.review) if record else None

    async def latest(self, application_id: UUID) -> ApplicationReview | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ApplicationReviewRecord)
                .where(ApplicationReviewRecord.application_id == application_id)
                .order_by(ApplicationReviewRecord.created_at.desc())
                .limit(1)
            )
            return ApplicationReview.model_validate(record.review) if record else None

    async def save(self, review: ApplicationReview, applicant: ApplicantDetail, rubric: ScreeningRubric) -> None:
        """원본을 넣고(같은 입력이면 바꿔 쓰고) 프로필을 갱신한다. 둘을 한 트랜잭션으로 커밋한다."""
        async with self._sessions() as session:
            record = await session.scalar(
                select(ApplicationReviewRecord).where(
                    ApplicationReviewRecord.application_id == review.application_id,
                    ApplicationReviewRecord.input_hash == review.input_hash,
                )
            )
            if record is None:
                session.add(
                    ApplicationReviewRecord(
                        application_id=review.application_id,
                        company_id=rubric.company_id,
                        recruitment_id=rubric.recruitment_id,
                        input_hash=review.input_hash,
                        review_version=review.version,
                        review=review.model_dump(mode="json"),
                    )
                )
            else:
                record.review_version = review.version
                record.review = review.model_dump(mode="json")
            fields, items = to_profile(review)
            await save_profile(
                session,
                company_id=rubric.company_id,
                recruitment_id=rubric.recruitment_id,
                application_id=review.application_id,
                agent=ItemAgent.APPLICATION,
                fields=fields,
                items=items,
                documents=applicant.documents,
            )
            await session.commit()


def input_hash(
    applicant: ApplicantDetail,
    posting: PostingContent,
    rubric: ScreeningRubric,
    units: dict[str, NcsUnit],
    version: str,
) -> str:
    """분석 결과를 바꿀 수 있는 입력만 묶어 해시한다. 공고 제목이나 복지가 바뀌어도 다시 분석하지 않는다."""
    payload = {
        "version": version,
        "documents": [[document.type.value, str(document.file_id), document.text] for document in applicant.documents],
        "certificates": applicant.certificates,
        "qualifications": posting.qualifications,
        "preferred": posting.preferred,
        "rubric": [preference.model_dump(mode="json") for preference in rubric.preferred],
        "units": {
            code: [[criterion.no, criterion.text] for criterion in criteria_of(unit)]
            for code, unit in sorted(units.items())
        },
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
