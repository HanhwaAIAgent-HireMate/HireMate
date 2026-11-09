"""독립 산출물 저장과 읽기. 조회는 범위, 입력 지문, 레시피 및 완료 상태를 모두 확인한다."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.db.analysis_artifact import AnalysisArtifactRecord
from hiremate_ai.db.profile import CandidateProfile
from hiremate_ai.db.profile_store import ProfileScopeError
from hiremate_ai.llm.recipe import fingerprint

if TYPE_CHECKING:
    from hiremate_ai.agents.analysis.application.extract import ExtractedFacts
    from hiremate_ai.agents.analysis.application.reading import DocumentReading
    from hiremate_ai.agents.analysis.application.rubric_draft import RubricDraft
    from hiremate_ai.agents.analysis.interview.types import InterviewAnalysis, InterviewAnalysisInput
    from hiremate_ai.contract import ApplicantDocument, TalentFit

type Sessions = Callable[[], AbstractAsyncContextManager[AsyncSession]]
ARTIFACT_VERSION = "1"


class AnalysisArtifactReader(Protocol):
    async def find_extraction(
        self,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
    ) -> ExtractedFacts | None: ...

    async def find_reading[T: DocumentReading](
        self,
        output: type[T],
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
    ) -> T | None: ...

    async def find_interview(self, data: InterviewAnalysisInput, *, recipe_hash: str) -> InterviewAnalysis | None: ...


class AnalysisArtifactStore(AnalysisArtifactReader, Protocol):
    async def save_reading(
        self,
        reading: DocumentReading,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
    ) -> None: ...

    async def save_extraction(
        self,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
        extracted: ExtractedFacts,
    ) -> None: ...

    async def save_interview(
        self, data: InterviewAnalysisInput, analysis: InterviewAnalysis, *, recipe_hash: str
    ) -> None: ...


class DbAnalysisArtifacts:
    def __init__(self, sessions: Sessions, *, commit: bool = True) -> None:
        self._sessions = sessions
        self._commit = commit

    async def find_extraction(
        self,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
    ) -> ExtractedFacts | None:
        from hiremate_ai.agents.analysis.application.extract import ExtractedFacts

        return await self._find(
            ExtractedFacts,
            company_id,
            recruitment_id,
            application_id,
            None,
            "document_extraction",
            _document_hash(document),
            recipe_hash,
        )

    async def save_extraction(
        self,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
        extracted: ExtractedFacts,
    ) -> None:
        await self._save(
            extracted,
            company_id,
            recruitment_id,
            application_id,
            None,
            "document_extraction",
            _document_hash(document),
            recipe_hash,
        )

    async def find_reading[T: DocumentReading](
        self,
        output: type[T],
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
    ) -> T | None:
        """서류 읽기(추출 + 정리) 답. 서류 종류마다 형식(output)이 다르다."""
        return await self._find(
            output,
            company_id,
            recruitment_id,
            application_id,
            None,
            "document_reading",
            _document_hash(document),
            recipe_hash,
        )

    async def save_reading(
        self,
        reading: DocumentReading,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        document: ApplicantDocument,
        recipe_hash: str,
    ) -> None:
        await self._save(
            reading,
            company_id,
            recruitment_id,
            application_id,
            None,
            "document_reading",
            _document_hash(document),
            recipe_hash,
        )

    async def find_interview(self, data: InterviewAnalysisInput, *, recipe_hash: str) -> InterviewAnalysis | None:
        from hiremate_ai.agents.analysis.interview.types import InterviewAnalysis

        result = await self._find(
            InterviewAnalysis,
            data.company_id,
            data.recruitment_id,
            data.application_id,
            data.stage_id,
            "interview_analysis",
            fingerprint(data.model_dump(mode="json")),
            recipe_hash,
        )
        return result if result is not None and _valid_interview(data, result) else None

    async def save_interview(
        self, data: InterviewAnalysisInput, analysis: InterviewAnalysis, *, recipe_hash: str
    ) -> None:
        if not _valid_interview(data, analysis):
            return
        await self._save(
            analysis,
            data.company_id,
            data.recruitment_id,
            data.application_id,
            data.stage_id,
            "interview_analysis",
            fingerprint(data.model_dump(mode="json")),
            recipe_hash,
        )

    async def find_talents(
        self, *, company_id: UUID, recruitment_id: UUID, application_id: UUID, source_hash: str, recipe_hash: str
    ) -> TalentFit | None:
        from hiremate_ai.contract import TalentFit

        return await self._find(
            TalentFit, company_id, recruitment_id, application_id, None, "talent_fit", source_hash, recipe_hash
        )

    async def save_talents(
        self,
        fit: TalentFit,
        *,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        source_hash: str,
        recipe_hash: str,
    ) -> None:
        await self._save(fit, company_id, recruitment_id, application_id, None, "talent_fit", source_hash, recipe_hash)

    async def find_rubric_draft(
        self, *, company_id: UUID, recruitment_id: UUID, source_hash: str, recipe_hash: str
    ) -> RubricDraft | None:
        """공고(채용)의 판정 기준 초안. 지원자가 아니라 채용 단위라 지원자 칸에 채용 id를 둔다."""
        from hiremate_ai.agents.analysis.application.rubric_draft import RubricDraft

        return await self._find(
            RubricDraft, company_id, recruitment_id, recruitment_id, None, "rubric_draft", source_hash, recipe_hash
        )

    async def save_rubric_draft(
        self, draft: RubricDraft, *, company_id: UUID, recruitment_id: UUID, source_hash: str, recipe_hash: str
    ) -> None:
        await self._save(
            draft, company_id, recruitment_id, recruitment_id, None, "rubric_draft", source_hash, recipe_hash
        )

    async def _find[T: BaseModel](
        self,
        output: type[T],
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        stage_id: UUID | None,
        kind: str,
        source_hash: str,
        recipe_hash: str,
    ) -> T | None:
        digest = _input_hash(company_id, recruitment_id, application_id, stage_id, kind, source_hash, recipe_hash)
        async with self._sessions() as session:
            record = await session.scalar(
                select(AnalysisArtifactRecord).where(
                    AnalysisArtifactRecord.company_id == company_id,
                    AnalysisArtifactRecord.recruitment_id == recruitment_id,
                    AnalysisArtifactRecord.application_id == application_id,
                    AnalysisArtifactRecord.stage_id == stage_id,
                    AnalysisArtifactRecord.kind == kind,
                    AnalysisArtifactRecord.input_hash == digest,
                    AnalysisArtifactRecord.recipe_hash == recipe_hash,
                    AnalysisArtifactRecord.version == ARTIFACT_VERSION,
                )
            )
            if record is None or not isinstance(record.payload, dict) or record.payload.get("origin") != "independent":
                return None
            if record.payload.get("source_hash") != source_hash:
                return None
            try:
                return output.model_validate(record.payload.get("output"))
            except ValidationError:
                return None

    async def _save(
        self,
        output: BaseModel,
        company_id: UUID,
        recruitment_id: UUID,
        application_id: UUID,
        stage_id: UUID | None,
        kind: str,
        source_hash: str,
        recipe_hash: str,
    ) -> None:
        digest = _input_hash(company_id, recruitment_id, application_id, stage_id, kind, source_hash, recipe_hash)
        async with self._sessions() as session:
            owner = (
                await session.execute(
                    select(CandidateProfile.company_id, CandidateProfile.recruitment_id).where(
                        CandidateProfile.application_id == application_id
                    )
                )
            ).one_or_none()
            if owner is not None and (owner.company_id, owner.recruitment_id) != (company_id, recruitment_id):
                raise ProfileScopeError("저장할 분석 산출물과 지원자 프로필의 기업 또는 채용이 다르다")
            statement = insert(AnalysisArtifactRecord).values(
                company_id=company_id,
                recruitment_id=recruitment_id,
                application_id=application_id,
                stage_id=stage_id,
                kind=kind,
                input_hash=digest,
                recipe_hash=recipe_hash,
                version=ARTIFACT_VERSION,
                payload={
                    "origin": "independent",
                    "source_hash": source_hash,
                    "output": output.model_dump(mode="json"),
                },
            )
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=["company_id", "recruitment_id", "application_id", "kind", "input_hash"],
                    set_={
                        "stage_id": stage_id,
                        "recipe_hash": recipe_hash,
                        "version": ARTIFACT_VERSION,
                        "payload": statement.excluded.payload,
                    },
                )
            )
            if self._commit:
                await session.commit()
            else:
                await session.flush()


def session_artifacts(session: AsyncSession) -> DbAnalysisArtifacts:
    """호출자의 트랜잭션에 참여한다. 면접 프로필과 산출물을 함께 커밋한다."""

    @asynccontextmanager
    async def borrow() -> AsyncIterator[AsyncSession]:
        yield session

    return DbAnalysisArtifacts(borrow, commit=False)


def _document_hash(document: ApplicantDocument) -> str:
    return fingerprint([document.type.value, str(document.file_id), document.text])


def _input_hash(
    company_id: UUID,
    recruitment_id: UUID,
    application_id: UUID,
    stage_id: UUID | None,
    kind: str,
    source_hash: str,
    recipe_hash: str,
) -> str:
    return fingerprint(
        {
            "scope": [str(company_id), str(recruitment_id), str(application_id), str(stage_id)],
            "kind": kind,
            "source": source_hash,
            "recipe": recipe_hash,
            "version": ARTIFACT_VERSION,
        }
    )


def _valid_interview(data: InterviewAnalysisInput, analysis: InterviewAnalysis) -> bool:
    from hiremate_ai.agents.analysis.interview.checks import checked_item, unanswered_checks
    from hiremate_ai.agents.analysis.interview.types import FindingDraft
    from hiremate_ai.db.profile import ItemCategory, ProfileStatus

    if analysis.status is not ProfileStatus.DONE or analysis.dropped != 0 or analysis.interrupted:
        return False
    unanswered = unanswered_checks(data)
    for item in analysis.items:
        if item in unanswered:
            continue
        if item.category not in (ItemCategory.STRENGTH, ItemCategory.CHECK) or not item.evidence:
            return False
        draft = FindingDraft(
            kind="CONFIRMED" if item.category is ItemCategory.STRENGTH else "UNCONFIRMED",
            content=item.content,
            evidence=item.evidence,
        )
        checked = checked_item(draft, data)
        if isinstance(checked, str) or (checked.content, checked.evidence, checked.source) != (
            item.content,
            item.evidence,
            item.source,
        ):
            return False
    return all(item in analysis.items for item in unanswered)
