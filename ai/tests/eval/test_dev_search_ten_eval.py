"""고정된 가상 지원자 10명으로 검색 후보와 판정 변동을 실제 모델에 평가한다."""

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, replace
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from root_context import sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from eval.test_dev_search_eval import CASES, dev_context
from hiremate_ai.agents.analysis.application.extract import ExtractedFacts, extract_documents, merge
from hiremate_ai.agents.analysis.application.present import to_profile
from hiremate_ai.agents.analysis.application.types import ApplicationReview
from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.find import CriteriaResult, RecheckItem, RecheckResult, _with_context
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.toolkit import concept_terms, keyword_search, profile_toolkit, scope_of
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.db.profile import ItemAgent
from hiremate_ai.db.profile_store import save_profile
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.chat import ToolAgent
from hiremate_ai.llm.client import LlmClient, build_llm
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.ncs_search.reference import EmbedClient
from hiremate_ai.tools import profile_search as profile_module
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch
from hiremate_ai.tools.profile_search import (
    DenseProfileEmbedder,
    index_profile_embeddings,
    profile_embedding_search,
    profile_search,
)
from hiremate_ai.tools.scope import ToolScope

HERE = Path(__file__).parent
GOLD: dict[str, Any] = json.loads((HERE / "dev_search_ten_gold.json").read_text(encoding="utf-8"))
REVIEWS: dict[str, Any] = json.loads((HERE / "dev_search_ten_reviews.json").read_text(encoding="utf-8"))
FINANCE = {
    "id": "finance-work",
    "query": "금융 서비스 개발 실무 경험이 있는 지원자를 찾아줘",
    "must_include": {"이재희": "", "강혜원": "", "김다인": "", "김하늘": ""},
    "must_exclude": {"이도윤": ""},
}


class Metrics:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


async def test_judgment_trace_captures_numbered_reply_and_input() -> None:
    result = RecheckResult(results=[RecheckItem(candidate_no=1, met=True, sentence_nos=[2])])
    observer = JudgmentObserver(FakeLlm(result))

    actual = await observer.structured(RecheckResult, agent="root", system="system", user="candidate evidence")

    assert actual == result
    assert observer.judgments[0]["input"] == "candidate evidence"
    assert observer.judgments[0]["result"] == result.model_dump(mode="json")


class ExtractionObserver:
    def __init__(self, client: LlmClient) -> None:
        self.client = client
        self.first: list[ExtractedFacts] = []

    def analysis_recipe(self) -> dict[str, Any] | None:
        return self.client.analysis_recipe()

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        result = await self.client.structured(output, agent=agent, system=system, user=user)
        if isinstance(result, ExtractedFacts):
            self.first.append(result)
        return result

    def tool_agent[T: BaseModel](
        self,
        output: type[T],
        *,
        agent: str,
        system: str,
        tools: Sequence[BaseTool],
        context: type[Any] | None = None,
        forms: Mapping[str, type[BaseModel]] | None = None,
        max_calls: int | None = None,
    ) -> ToolAgent[T]:
        return self.client.tool_agent(
            output, agent=agent, system=system, tools=tools, context=context, forms=forms, max_calls=max_calls
        )


class JudgmentObserver(ExtractionObserver):
    def __init__(self, client: LlmClient) -> None:
        super().__init__(client)
        self.judgments: list[dict[str, Any]] = []

    async def structured[T: BaseModel](self, output: type[T], *, agent: str, system: str, user: str) -> T:
        result = await super().structured(output, agent=agent, system=system, user=user)
        if isinstance(result, RecheckResult | CriteriaResult):
            self.judgments.append(
                {
                    "input": user,
                    "input_sha256": sha256(user.encode()).hexdigest(),
                    "result": result.model_dump(mode="json"),
                }
            )
        return result


def capture_search(search: CandidateSearch, captured: list[CandidateMatch]) -> CandidateSearch:
    async def capture(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        found = await search(scope, concepts, pool)
        captured.extend(found)
        return found

    return capture


@pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델로 평가한다")
async def test_ten_document_extraction_with_real_model(
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = dev_context(sample_applicants, sample_company, sample_posting, "")
    metrics = Metrics()
    llm = build_llm(metrics)
    for row in context.candidates:
        if row.name not in GOLD["candidates"]:
            continue
        docs = context.documents[row.application_id]
        observer = ExtractionObserver(llm)
        started = time.monotonic()
        before_calls = len(metrics.records)
        reviewed = []
        for document in docs:
            reviewed.extend(await extract_documents(observer, [document], 1, review=True))
        assert len(observer.first) == len(docs)
        first, _ = merge(docs, observer.first, date(2026, 11, 5))
        after, _ = merge(docs, reviewed, date(2026, 11, 5))
        before_statements = {fact.statement for fact in first}
        after_statements = {fact.statement for fact in after}
        verified = [
            evidence_source(quote.sentence, [doc for doc in docs if doc.type == quote.document]) == quote.document
            for fact in after
            for quote in fact.quotes
        ]
        refs = [
            (case["id"], entry["quote"])
            for case in GOLD["cases"]
            for entry in case["include"]
            if entry["name"] == row.name
        ]

        def contains_anchor(facts: list[Any], text: str) -> bool:
            return any(
                text in quote.sentence or (len(quote.sentence) >= 20 and quote.sentence in text)
                for fact in facts
                for quote in fact.quotes
            )

        records = metrics.records[before_calls:]
        event = {
            "name": row.name,
            "documents": len(docs),
            "first_facts": len(first),
            "reviewed_facts": len(after),
            "new_or_reworded": len(after_statements - before_statements),
            "removed_or_reworded": len(before_statements - after_statements),
            "added_facts": [fact.model_dump(mode="json") for fact in after if fact.statement not in before_statements],
            "removed_facts": [fact.model_dump(mode="json") for fact in first if fact.statement not in after_statements],
            "reviewed_quotes": len(verified),
            "verified_quotes": sum(verified),
            "anchors": [
                {"case": case, "first": contains_anchor(first, quote), "reviewed": contains_anchor(after, quote)}
                for case, quote in refs
            ],
            "calls": len(records),
            "input_tokens": sum(record.input_tokens or 0 for record in records),
            "output_tokens": sum(record.output_tokens or 0 for record in records),
            "seconds": round(time.monotonic() - started, 2),
        }
        print(json.dumps(event, ensure_ascii=True), flush=True)
        assert all(verified)


@pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 임베딩 서비스로 평가한다")
async def test_ten_candidate_similarity_thresholds(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = dev_context(sample_applicants, sample_company, sample_posting, "")
    rows = [row for row in context.candidates if row.name in GOLD["candidates"]]
    context = context.model_copy(update={"candidates": rows})
    names = {row.application_id: row.name for row in rows}
    pool = [row.application_id for row in rows]
    expected = {case["id"]: {entry["name"] for entry in case["include"]} for case in GOLD["cases"]}
    async with httpx.AsyncClient(timeout=settings.ncs_embed_timeout_seconds) as http:
        embedder = DenseProfileEmbedder(EmbedClient(http, settings.ncs_embed_url))
        for row in rows:
            review = ApplicationReview.model_validate(REVIEWS["reviews"][row.name])
            fields, items = to_profile(review)
            await save_profile(
                db_session,
                company_id=context.company.company_id,
                recruitment_id=context.recruitment_id,
                application_id=row.application_id,
                agent=ItemAgent.APPLICATION,
                fields=fields,
                items=items,
                documents=context.documents[row.application_id],
            )
            await index_profile_embeddings(
                db_session,
                embedder,
                context.company.company_id,
                context.recruitment_id,
                row.application_id,
                model=settings.ncs_model,
            )
        await db_session.commit()
        sessions = sessions_of(db_session)
        scope = scope_of(context)
        profile_keyword = profile_search(sessions, terms=concept_terms)
        semantic = profile_embedding_search(sessions, embedder, model=settings.ncs_model)
        for case in [*CASES, FINANCE]:
            query = [case["query"]]
            keyword = await profile_keyword(scope, query, pool)
            documents = await keyword_search(scope, query, pool)
            keyword_names = {names[match.application_id] for match in [*keyword, *documents]}
            for threshold in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
                monkeypatch.setattr(profile_module, "MIN_PROFILE_SIMILARITY", threshold)
                dense = await semantic(scope, query, pool)
                dense_names = {names[match.application_id] for match in dense}
                positive = expected[case["id"]]
                event = {
                    "case": case["id"],
                    "threshold": threshold,
                    "keyword": sorted(keyword_names),
                    "semantic": sorted(dense_names),
                    "combined": sorted(keyword_names | dense_names),
                    "semantic_missing": sorted(positive - dense_names),
                    "combined_missing": sorted(positive - (keyword_names | dense_names)),
                }
                print(json.dumps(event, ensure_ascii=True), flush=True)


@pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델과 임베딩 서비스로 평가한다")
async def test_ten_candidate_search_with_real_model(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = dev_context(sample_applicants, sample_company, sample_posting, "")
    rows = [row for row in context.candidates if row.name in GOLD["candidates"]]
    ids = {row.application_id for row in rows}
    context = context.model_copy(
        update={
            "candidates": rows,
            "documents": {
                application_id: docs for application_id, docs in context.documents.items() if application_id in ids
            },
        }
    )
    assert len(rows) == 10
    names = {row.application_id: row.name for row in rows}
    expected = {case["id"]: {entry["name"] for entry in case["include"]} for case in GOLD["cases"]}
    excluded = {case["id"]: set(case["exclude"]) for case in GOLD["cases"]}
    metrics = Metrics()
    llm = build_llm(metrics)
    async with httpx.AsyncClient(timeout=settings.ncs_embed_timeout_seconds) as http:
        embedder = DenseProfileEmbedder(EmbedClient(http, settings.ncs_embed_url))
        for row in rows:
            review = ApplicationReview.model_validate(REVIEWS["reviews"][row.name])
            fields, items = to_profile(review)
            await save_profile(
                db_session,
                company_id=context.company.company_id,
                recruitment_id=context.recruitment_id,
                application_id=row.application_id,
                agent=ItemAgent.APPLICATION,
                fields=fields,
                items=items,
                documents=context.documents[row.application_id],
            )
            await index_profile_embeddings(
                db_session,
                embedder,
                context.company.company_id,
                context.recruitment_id,
                row.application_id,
                model=settings.ncs_model,
            )
        await db_session.commit()
        sessions = sessions_of(db_session)
        for case in [*CASES, FINANCE]:
            case_context = context.model_copy(update={"message": case["query"]})
            shared = profile_toolkit(sessions, embedder=embedder)
            for mode in ("fresh", "shared"):
                for repeat in range(1, 4):
                    toolkit = profile_toolkit(sessions, embedder=embedder) if mode == "fresh" else shared
                    captured: list[CandidateMatch] = []
                    observer = JudgmentObserver(llm)
                    before = len(metrics.records)
                    started = time.monotonic()
                    plan = await run_plan(
                        observer, case_context, replace(toolkit, search=capture_search(toolkit.search, captured))
                    )
                    elapsed = time.monotonic() - started
                    records = metrics.records[before:]
                    results = {names[target] for target in plan.targets if target in names}
                    candidates = {names[match.application_id] for match in captured}
                    positive = expected.get(case["id"])
                    event: dict[str, Any] = {
                        "case": case["id"],
                        "mode": mode,
                        "repeat": repeat,
                        "candidates": sorted(candidates),
                        "results": sorted(results),
                        "missing_examples": sorted(set(case["must_include"]) - results),
                        "unexpected_examples": sorted(set(case["must_exclude"]) & results),
                        "calls": len(records),
                        "input_tokens": sum(record.input_tokens or 0 for record in records),
                        "output_tokens": sum(record.output_tokens or 0 for record in records),
                        "seconds": round(elapsed, 2),
                        "judgment_calls": observer.judgments,
                        "evidence": [
                            {
                                "name": names[match.application_id],
                                "retrieved": [asdict(sentence) for sentence in match.sentences],
                                "context": [
                                    asdict(sentence) for sentence in _with_context(case_context, match).sentences
                                ],
                            }
                            for match in captured
                        ],
                    }
                    if positive is not None:
                        event["candidate_missing"] = sorted(positive - candidates)
                        event["result_missing"] = sorted(positive - results)
                        event["result_extra"] = sorted(results & excluded[case["id"]])
                    print(json.dumps(event, ensure_ascii=True), flush=True)
