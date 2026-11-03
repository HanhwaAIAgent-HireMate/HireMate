"""분석 결과 저장 · 재사용. ai.application_reviews에 원본을, ai.candidate_profiles에 요약과 항목을 넣는다.

같은 입력(공고 · 서류 · 평가 기준 · 분석 버전)이면 저장된 결과를 쓰고 모델을 다시 부르지 않는다.
"""

from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.present import to_profile
from hiremate_ai.agents.analysis.application.types import ApplicationReview, ScreeningRubric
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.db.analysis_store import AnalysisArtifactStore, DbAnalysisArtifacts
from hiremate_ai.db.application_review import ApplicationReviewRecord
from hiremate_ai.db.profile import ItemAgent
from hiremate_ai.db.profile_store import ProfileScopeError, save_profile
from hiremate_ai.llm.recipe import fingerprint

type Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class ReviewStore(Protocol):
    """분석에 필요한 저장소. 라우터는 DbReviewStore를 쓰고, 테스트는 메모리 구현을 넣는다."""

    artifacts: AnalysisArtifactStore | None

    async def find(
        self, application_id: UUID, input_hash: str, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None: ...

    async def latest(
        self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None: ...

    async def save(self, review: ApplicationReview, applicant: ApplicantDetail, rubric: ScreeningRubric) -> None: ...


class DbReviewStore:
    """세션을 짧게 열고 닫는다. 모델을 기다리는 동안 DB 연결을 잡고 있지 않는다."""

    def __init__(self, sessions: Sessions) -> None:
        self._sessions = sessions
        self.artifacts: AnalysisArtifactStore | None = DbAnalysisArtifacts(sessions)

    async def find(
        self, application_id: UUID, input_hash: str, *, company_id: UUID, recruitment_id: UUID
    ) -> ApplicationReview | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ApplicationReviewRecord).where(
                    ApplicationReviewRecord.application_id == application_id,
                    ApplicationReviewRecord.input_hash == input_hash,
                    ApplicationReviewRecord.company_id == company_id,
                    ApplicationReviewRecord.recruitment_id == recruitment_id,
                )
            )
            return _parse(record)

    async def latest(self, application_id: UUID, *, company_id: UUID, recruitment_id: UUID) -> ApplicationReview | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ApplicationReviewRecord)
                .where(
                    ApplicationReviewRecord.application_id == application_id,
                    ApplicationReviewRecord.company_id == company_id,
                    ApplicationReviewRecord.recruitment_id == recruitment_id,
                )
                .order_by(ApplicationReviewRecord.created_at.desc())
                .limit(1)
            )
            return _parse(record)

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
                if record.company_id != rubric.company_id or record.recruitment_id != rubric.recruitment_id:
                    raise ProfileScopeError("저장 분석의 기업 또는 채용이 다르다")
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
    version: str,
    *,
    today: date,
    recipe: Mapping[str, Any],
) -> str:
    """분석 결과를 바꿀 수 있는 입력만 묶어 해시한다. 공고 제목이나 복지가 바뀌어도 다시 분석하지 않는다.

    평가 기준(항목 · 유형 · 판정 기준 · 버전)이 바뀌면 저장된 결과를 쓰지 않는다.
    """
    payload = {
        "cache_version": 2,
        "version": version,
        "scope": [str(rubric.company_id), str(rubric.recruitment_id), str(applicant.info.application_id)],
        "today": today.isoformat(),
        "recipe": dict(recipe),
        "policy": {
            "full_text_chars": settings.application_full_text_chars,
            "rechecks": settings.application_rechecks,
            "recheck_reserve_seconds": settings.application_recheck_reserve_seconds,
        },
        "documents": [[document.type.value, str(document.file_id), document.text] for document in applicant.documents],
        "certificates": applicant.certificates,
        "qualifications": posting.qualifications,
        "preferred": posting.preferred,
        "criteria_version": rubric.criteria_version,
        "criteria": [criterion.model_dump(mode="json") for criterion in rubric.criteria],
    }
    return fingerprint(payload)


def _parse(record: ApplicationReviewRecord | None) -> ApplicationReview | None:
    """저장된 원본을 읽는다. 분석 결과 모양이 바뀌기 전의 원본은 읽지 않고 없는 것으로 본다 (다시 분석한다)."""
    if record is None:
        return None
    try:
        review = ApplicationReview.model_validate(record.review)
        if (review.application_id, review.input_hash, review.version) != (
            record.application_id,
            record.input_hash,
            record.review_version,
        ):
            return None
        return review
    except ValidationError:
        return None
