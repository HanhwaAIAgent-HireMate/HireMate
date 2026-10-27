"""Root가 전문 Agent를 직접 호출한다. 자료와 반환 결과는 이번 요청 안에서만 쓴다."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
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
from hiremate_ai.agents.root.answer import INTERVIEW_SOURCE, AnswerEvidence, AnswerItem, _canonical_source
from hiremate_ai.agents.root.progress import SILENT, Progress
from hiremate_ai.agents.root.toolkit import (
    DOUBTFUL,
    NO_DOCUMENTS,
    OUT_OF_SCOPE,
    AgentEvidence,
    RootToolContext,
    RootToolkit,
    candidate_ref,
    resolve_ref,
)
from hiremate_ai.agents.root.types import ChatItem
from hiremate_ai.contract import StageType
from hiremate_ai.db.analysis_store import AnalysisArtifactReader
from hiremate_ai.db.profile import ItemAgent, ItemCategory, Verification
from hiremate_ai.llm.chat import record_interrupted_model_tool
from hiremate_ai.llm.client import LlmClient

REVIEWING_APPLICATION = "서류 Agent가 제출 문서의 근거를 검토하고 있어요"
REVIEWING_INTERVIEW = "면접 Agent가 답변과 앞선 분석을 검토하고 있어요"
INVALID_RESULT = "이 지원자의 이번 요청에서 받은 결과 번호만 전달할 수 있어요."
NO_INTERVIEW = "현재 면접 전형에서 이 지원자의 답변 기록을 불러오지 않았어요."


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
    llm: LlmClient
    progress: Progress = SILENT
    results: dict[str, Consultation] = field(default_factory=dict)
    artifacts: AnalysisArtifactReader | None = None

    def tools(self) -> tuple[BaseTool, ...]:
        @tool
        async def consult_application(
            candidate: str, runtime: ToolRuntime[RootToolContext], force_review: bool = False
        ) -> str:
            """서류의 사실과 원문 근거에 전문 검토가 필요할 때 쓴다. candidate는 C1 같은 지원자 번호다.

            반환한 이번 요청의 결과 번호를 같은 지원자의 consult_interview.previous_results에 넣을 수 있다.
            팀 성과와 확인되지 않은 주장은 CHECK다. 원문 인용만으로 본인의 확정 실무로 강화하지 않는다.
            점수, 저장된 분석과 업무 상태는 바꾸지 않는다. 질문 생성 자체에는 필요 없다.
            새로 검토해 달라는 명시적 요청은 force_review=true로 저장 추출과 이번 요청의 재사용을 생략한다.
            """
            scope = runtime.context
            row = resolve_ref(scope.chat, candidate)
            if row is None:
                return OUT_OF_SCOPE
            cached = self._cached(row.application_id, ItemAgent.APPLICATION)
            if cached and not force_review:
                return self._render(cached, scope)
            documents = scope.chat.documents.get(row.application_id, [])
            if not any(document.text.strip() for document in documents):
                return NO_DOCUMENTS
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
                if self.artifacts is not None and recipe is not None and not force_review
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
            return self._save(Consultation(row.application_id, ItemAgent.APPLICATION, items), scope)

        @tool
        async def consult_interview(
            candidate: str,
            runtime: ToolRuntime[RootToolContext],
            previous_results: list[str] | None = None,
            force_review: bool = False,
        ) -> str:
            """현재 면접 답변의 전문 분석이 필요할 때 쓴다. candidate는 C1 같은 지원자 번호다.

            previous_results에는 같은 지원자의 이번 요청에서 받은 결과 번호만 넣는다. 임의 분석은 넣지 않는다.
            앞선 결과는 비교 맥락이며 이번 면접 답변 원문으로 검증한다. CHECK와 미확인 역할은 확정하지 않는다.
            질문 생성이나 업무 상태 저장은 하지 않는다. 질문 생성은 최종 questions 명령으로 요청한다.
            새 검토를 명시적으로 요청하면 force_review=true로 기존 결과를 쓰지 않는다.
            """
            scope = runtime.context
            row = resolve_ref(scope.chat, candidate)
            if row is None:
                return OUT_OF_SCOPE
            previous = tuple(dict.fromkeys(previous_results or []))
            if any(
                key not in self.results or self.results[key].application_id != row.application_id for key in previous
            ):
                return INVALID_RESULT
            view = scope.chat.interviews.get(row.application_id)
            if (
                scope.chat.stage_type is not StageType.INTERVIEW
                or view is None
                or view.application_id != row.application_id
            ):
                return NO_INTERVIEW
            cached = self._cached(row.application_id, ItemAgent.INTERVIEW, previous)
            if cached and not force_review:
                return self._render(cached, scope)
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
                if self.artifacts is not None and recipe is not None and not previous and not force_review
                else None
            )
            if analysis is None:
                analysis = await analyze_interview(data, self.llm, references=references)
            if analysis.interrupted:
                record_interrupted_model_tool("consult_interview")
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
            return self._save(
                Consultation(row.application_id, ItemAgent.INTERVIEW, items, previous, analysis.interrupted), scope
            )

        return consult_application, consult_interview

    def with_evidence(self, toolkit: RootToolkit) -> RootToolkit:
        """최종 항목 검증에도 전문 Agent가 반환한 미확인 상태와 출처를 보존한다."""

        async def evidence(scope: RootToolContext, application_ids: Sequence[UUID]) -> dict[UUID, list[AgentEvidence]]:
            found = await toolkit.evidence(scope, application_ids)
            result = {application_id: list(items) for application_id, items in found.items()}
            allowed = set(application_ids) & scope.application_ids
            transient: dict[UUID, list[AgentEvidence]] = {}
            for consultation in self.results.values():
                if consultation.application_id not in allowed:
                    continue
                for item in consultation.items:
                    for quote in item.evidence:
                        transient.setdefault(consultation.application_id, []).append(
                            AgentEvidence(
                                sentence=quote.sentence,
                                source=quote.source,
                                agent=consultation.agent,
                                verification=item.verification,
                            )
                        )
            for application_id, items in transient.items():
                doubtful = [item for item in items if item.verification in DOUBTFUL]
                combined = [*result.get(application_id, []), *items]
                result[application_id] = [
                    replace(item, verification=Verification.UNCONFIRMED)
                    if any(_same_quote(item, uncertain) for uncertain in doubtful)
                    else item
                    for item in combined
                ]
            return result

        return replace(toolkit, evidence=evidence)

    def validate_items(self, originals: Sequence[AnswerItem], checked: Sequence[ChatItem]) -> None:
        """다른 출처를 함께 인용해도 이번 검토의 미확인 주장과 근거를 확정하지 않는다."""
        for original, item in zip(originals, checked, strict=True):
            if item.status != "OK" or item.application_id is None:
                continue
            for result in self.results.values():
                if result.application_id != item.application_id:
                    continue
                for prior in result.items:
                    if prior.verification not in DOUBTFUL:
                        continue
                    same_claim = "".join(original.text.split()) == "".join(prior.text.split())
                    cited = any(
                        _same_quote(
                            AgentEvidence(sentence=quote.sentence, source=quote.source, agent=""),
                            AgentEvidence(sentence=earlier.sentence, source=earlier.source, agent=""),
                        )
                        for quote in original.evidence
                        for earlier in prior.evidence
                    )
                    if same_claim or cited:
                        raise ValueError(
                            "전문 Agent가 확인 필요로 남긴 내용과 근거는 다른 출처를 붙여도 CHECK로 유지하세요."
                        )

    def _cached(self, application_id: UUID, agent: ItemAgent, previous: tuple[str, ...] = ()) -> str | None:
        return next(
            (
                key
                for key, result in self.results.items()
                if (result.application_id, result.agent, result.previous) == (application_id, agent, previous)
            ),
            None,
        )

    def _save(self, result: Consultation, scope: RootToolContext) -> str:
        key = f"D{len(self.results) + 1}"
        self.results[key] = result
        return self._render(key, scope)

    def _render(self, key: str, scope: RootToolContext) -> str:
        result = self.results[key]
        return json.dumps(
            {
                "result": key,
                "candidate": candidate_ref(scope.chat, result.application_id),
                "agent": result.agent,
                "complete": not result.interrupted,
                "items": [
                    {**item.model_dump(mode="json"), "status": "CHECK" if item.verification in DOUBTFUL else "OK"}
                    for item in result.items
                ],
            },
            ensure_ascii=False,
        )


def _same_quote(left: AgentEvidence, right: AgentEvidence) -> bool:
    left_text = "".join(left.sentence.split())
    right_text = "".join(right.sentence.split())
    return (
        _canonical_source(left.source) == _canonical_source(right.source)
        and bool(left_text and right_text)
        and (left_text in right_text or right_text in left_text)
    )
