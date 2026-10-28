"""Root 분석 루프가 서류, 면접 Agent를 직접 부른다. 자료와 반환 결과는 이번 요청 안에서만 쓴다."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application import review_application_documents
from hiremate_ai.agents.analysis.application.extract import extraction_recipe
from hiremate_ai.agents.analysis.application.types import Actor
from hiremate_ai.agents.analysis.interview import (
    AnsweredQuestion,
    InterviewAnalysisInput,
    InterviewReference,
    PreviousInterview,
    analyze_interview,
)
from hiremate_ai.agents.analysis.interview.store import interview_recipe
from hiremate_ai.agents.root.answer import AnswerEvidence
from hiremate_ai.agents.root.ledger import INTERVIEW_SOURCE, Ledger
from hiremate_ai.agents.root.progress import SILENT, Progress
from hiremate_ai.agents.root.toolkit import (
    AGENT_NAMES,
    DOUBTFUL,
    NO_DOCUMENTS,
    OUT_OF_SCOPE,
    RootToolContext,
    candidate_ref,
    resolve_ref,
)
from hiremate_ai.agents.root.types import CandidateRow
from hiremate_ai.contract import StageType
from hiremate_ai.db.analysis_store import AnalysisArtifactReader
from hiremate_ai.db.profile import ItemAgent, ItemCategory, Verification
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError, record_interrupted_model_tool
from hiremate_ai.llm.client import LlmClient

REVIEWING_APPLICATION = "서류 Agent가 제출 문서의 근거를 검토하고 있어요"
REVIEWING_INTERVIEW = "면접 Agent가 답변과 앞선 분석을 검토하고 있어요"
INVALID_RESULT = "이 지원자의 이번 요청에서 받은 결과 번호만 전달할 수 있어요."
NO_INTERVIEW = "현재 면접 전형에서 이 지원자의 답변 기록을 불러오지 않았어요."
SUB_AGENT_FAILED = "{agent}가 검토를 끝내지 못했어요. 저장된 분석으로 답하세요."
NOT_FINISHED = "(호출 한도로 검토를 끝까지 마치지 못했어요)"
_AGENT_LABELS = {ItemAgent.APPLICATION: "서류 Agent", ItemAgent.INTERVIEW: "면접 Agent"}
_ACTOR_LABELS = {Actor.SELF: "본인", Actor.TEAM: "팀", Actor.UNCLEAR: "역할 불분명"}


class DelegatedItem(BaseModel):
    text: str
    evidence: list[AnswerEvidence]
    verification: Verification
    actor: str | None = None


@dataclass(frozen=True)
class Consultation:
    application_id: UUID
    agent: ItemAgent
    items: list[DelegatedItem]
    previous: tuple[str, ...] = ()
    interrupted: bool = False


@dataclass
class Delegation:
    """Root가 부르는 서류, 면접 Agent. ledger를 주면 결과 항목을 근거 번호표에 넣고 근거 줄로 돌려준다."""

    llm: LlmClient
    progress: Progress = SILENT
    results: dict[str, Consultation] = field(default_factory=dict)
    artifacts: AnalysisArtifactReader | None = None
    ledger: Ledger | None = None

    def review_tools(self) -> tuple[BaseTool, BaseTool]:
        """분석 루프의 도구. 결과는 근거 번호(E번호)가 붙은 줄이다."""

        @tool
        async def review_documents(candidate: str, runtime: ToolRuntime[RootToolContext]) -> str:
            """서류 Agent에게 이 지원자의 제출 문서 사실 전체를 다시 검토하게 한다. candidate는 C1 같은 번호다.

            저장된 서류 분석이 없을 때, 담당자가 다시 검토해 달라고 할 때, 사실 전체의 근거를 봐야 할 때만 부른다.
            결과 줄의 E번호를 답에 인용한다. 팀 성과와 역할이 불분명한 사실은 확인 필요다.
            점수와 저장된 분석은 바꾸지 않는다.
            """
            return await self.documents_review(runtime.context, candidate)

        @tool
        async def review_interview(
            candidate: str, runtime: ToolRuntime[RootToolContext], previous: list[str] | None = None
        ) -> str:
            """면접 분석 Agent에게 이 지원자의 현재 면접 답변을 분석하게 한다. candidate는 C1 같은 번호다.

            저장된 면접 분석이 없거나 앞 전형 결과와 비교해야 할 때만 부른다. previous에는 같은 지원자에 대해
            이번 요청에서 받은 결과 번호(D1 등)만 넣는다. 결과 줄의 E번호를 답에 인용한다.
            """
            return await self.interview_review(runtime.context, candidate, previous)

        return review_documents, review_interview

    async def documents_review(self, scope: RootToolContext, candidate: str) -> str:
        row = resolve_ref(scope.chat, candidate)
        if row is None:
            return OUT_OF_SCOPE
        if not _readable(scope, row):
            return NO_DOCUMENTS
        try:
            key = await self._application(scope, row)
        except LlmOutputError as error:
            if error.reason is LlmFailureReason.BUDGET:
                raise
            return SUB_AGENT_FAILED.format(agent=_AGENT_LABELS[ItemAgent.APPLICATION])
        return self._lines(key, scope)

    async def interview_review(self, scope: RootToolContext, candidate: str, previous: Sequence[str] | None) -> str:
        row = resolve_ref(scope.chat, candidate)
        if row is None:
            return OUT_OF_SCOPE
        earlier = tuple(dict.fromkeys(previous or []))
        problem = self._interview_problem(scope, row, earlier)
        if problem is not None:
            return problem
        try:
            key = await self._interview(scope, row, earlier)
        except LlmOutputError as error:
            if error.reason is LlmFailureReason.BUDGET:
                raise
            return SUB_AGENT_FAILED.format(agent=_AGENT_LABELS[ItemAgent.INTERVIEW])
        return self._lines(key, scope)

    async def _application(self, scope: RootToolContext, row: CandidateRow) -> str:
        """서류 Agent의 검토 결과 번호. 같은 요청에서 이미 검토했으면 다시 부르지 않는다."""
        cached = self._cached(row.application_id, ItemAgent.APPLICATION)
        if cached:
            return cached
        documents = scope.chat.documents.get(row.application_id, [])
        self.progress.status(REVIEWING_APPLICATION)
        recipe = extraction_recipe(self.llm)
        extracted = (
            [
                await self.artifacts.find_extraction(
                    company_id=scope.company_id,
                    recruitment_id=scope.recruitment_id,
                    application_id=row.application_id,
                    document=document,
                    recipe_hash=recipe,
                )
                if document.text.strip()
                else None
                for document in documents
            ]
            if self.artifacts is not None and recipe is not None
            else None
        )
        facts = await review_application_documents(self.llm, documents, extracted=extracted)
        items = [
            DelegatedItem(
                text=fact.statement,
                evidence=[
                    AnswerEvidence(sentence=quote.sentence, source=quote.document.label) for quote in fact.quotes
                ],
                verification=Verification.EVIDENCED
                if fact.supported and fact.actor is Actor.SELF
                else Verification.UNCONFIRMED,
                actor=fact.actor,
            )
            for fact in facts
        ]
        return self._store(Consultation(row.application_id, ItemAgent.APPLICATION, items))

    def _interview_problem(self, scope: RootToolContext, row: CandidateRow, previous: tuple[str, ...]) -> str | None:
        if any(key not in self.results or self.results[key].application_id != row.application_id for key in previous):
            return INVALID_RESULT
        view = scope.chat.interviews.get(row.application_id)
        if (
            scope.chat.stage_type is not StageType.INTERVIEW
            or view is None
            or view.application_id != row.application_id
        ):
            return NO_INTERVIEW
        return None

    async def _interview(self, scope: RootToolContext, row: CandidateRow, previous: tuple[str, ...]) -> str:
        """면접 분석 Agent의 결과 번호. 같은 요청에서 같은 비교 자료로 분석했으면 다시 부르지 않는다."""
        cached = self._cached(row.application_id, ItemAgent.INTERVIEW, previous)
        if cached:
            return cached
        view = scope.chat.interviews[row.application_id]
        references = [
            InterviewReference(
                content=item.text,
                evidence=evidence.sentence,
                source=evidence.source,
                verification=item.verification,
            )
            for key in previous
            for item in self.results[key].items
            for evidence in item.evidence
        ]
        data = InterviewAnalysisInput(
            company_id=scope.company_id,
            recruitment_id=scope.recruitment_id,
            stage_id=scope.stage_id,
            application_id=row.application_id,
            stage_name=scope.chat.stage_name,
            questions=[AnsweredQuestion(text=question.text, answer=question.answer) for question in view.questions],
            previous=[
                PreviousInterview(
                    stage_name=earlier.stage_name,
                    questions=[AnsweredQuestion(text=q.text, answer=q.answer) for q in earlier.questions],
                )
                for earlier in view.previous
            ],
        )
        self.progress.status(REVIEWING_INTERVIEW)
        recipe = interview_recipe(self.llm)
        analysis = (
            await self.artifacts.find_interview(data, recipe_hash=recipe)
            if self.artifacts is not None and recipe is not None and not previous
            else None
        )
        if analysis is None:
            analysis = await analyze_interview(data, self.llm, references=references)
        if analysis.interrupted:
            record_interrupted_model_tool("review_interview")
        items = [
            DelegatedItem(
                text=item.content,
                evidence=[AnswerEvidence(sentence=item.evidence, source=INTERVIEW_SOURCE)] if item.evidence else [],
                verification=Verification.UNCONFIRMED
                if item.category is ItemCategory.CHECK or not item.evidence
                else item.verification or Verification.CONFIRMED,
            )
            for item in analysis.items
        ]
        return self._store(Consultation(row.application_id, ItemAgent.INTERVIEW, items, previous, analysis.interrupted))

    def _lines(self, key: str, scope: RootToolContext) -> str:
        """결과 번호 한 줄과 항목마다 근거 번호가 붙은 줄. 미확인 항목은 확인 필요로만 올릴 수 있다."""
        if self.ledger is None:
            raise TypeError("근거 번호표 없이 근거 줄을 만들 수 없다")
        result = self.results[key]
        agent = AGENT_NAMES[result.agent]
        lines = [f"{key} {_AGENT_LABELS[result.agent]} 결과 ({candidate_ref(scope.chat, result.application_id)})"]
        for item in result.items:
            first = item.evidence[0] if item.evidence else None
            actor = _ACTOR_LABELS.get(Actor(item.actor)) if item.actor else None
            ref = self.ledger.add(
                result.application_id,
                f"{actor} · {item.text}" if actor else item.text,
                quote=first.sentence if first else None,
                source=first.source if first else _AGENT_LABELS[result.agent],
                cap="CHECK" if item.verification in DOUBTFUL else "OK",
                agent=agent,
            )
            lines.append(self.ledger.line(ref))
        if result.interrupted:
            lines.append(NOT_FINISHED)
        return "\n".join(lines)

    def _cached(self, application_id: UUID, agent: ItemAgent, previous: tuple[str, ...] = ()) -> str | None:
        return next(
            (
                key
                for key, result in self.results.items()
                if (result.application_id, result.agent, result.previous) == (application_id, agent, previous)
            ),
            None,
        )

    def _store(self, result: Consultation) -> str:
        key = f"D{len(self.results) + 1}"
        self.results[key] = result
        return key


def _readable(scope: RootToolContext, row: CandidateRow) -> bool:
    return any(document.text.strip() for document in scope.chat.documents.get(row.application_id, []))
