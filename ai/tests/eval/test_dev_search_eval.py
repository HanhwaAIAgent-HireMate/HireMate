"""개발 환경의 가상 지원자 검색 평가 자료와 기존 후보 검색을 확인한다."""

import json
import time
from collections.abc import Sequence
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest
from root_context import make_context, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.analysis.application.types import ApplicationReview
from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.toolkit import profile_toolkit, scope_of
from hiremate_ai.agents.root.types import ChatContext
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, ApplicantDocument, CompanyProfile, DocumentType, PostingContent
from hiremate_ai.db.profile import ItemAgent
from hiremate_ai.db.profile_store import NewItem, ProfileFields, save_profile
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm
from hiremate_ai.tools.candidates import CandidateMatch, CandidateSearch
from hiremate_ai.tools.scope import ToolScope

HERE = Path(__file__).parent
DATA: dict[str, Any] = json.loads((HERE / "dev_search_dataset.json").read_text(encoding="utf-8"))
CASES: list[dict[str, Any]] = json.loads((HERE / "dev_search_cases.json").read_text(encoding="utf-8"))


def test_evaluation_examples_reference_real_documents() -> None:
    candidates = {candidate["name"]: candidate for candidate in DATA["candidates"]}
    assert len(candidates) == 64
    assert sum(bool(candidate["profile"]) for candidate in candidates.values()) == 1
    for case in CASES:
        for field in ("must_include", "must_exclude"):
            for name, quote in case[field].items():
                assert any(quote in document["text"] for document in candidates[name]["documents"])


def test_ten_candidate_gold_is_complete_and_cites_the_snapshot() -> None:
    gold: dict[str, Any] = json.loads((HERE / "dev_search_ten_gold.json").read_text(encoding="utf-8"))
    assert gold["dataset_sha256"] == sha256((HERE / "dev_search_dataset.json").read_bytes()).hexdigest()
    candidates = {candidate["name"]: candidate for candidate in DATA["candidates"]}
    selected = set(gold["candidates"])
    assert len(selected) == 10 and selected <= candidates.keys()
    assert len({case["id"] for case in gold["cases"]}) == len(gold["cases"]) == 5
    for case in gold["cases"]:
        included = {entry["name"] for entry in case["include"]}
        excluded = set(case["exclude"])
        uncertain = set(case.get("uncertain", []))
        assert len(included) == len(case["include"])
        assert len(excluded) == len(case["exclude"])
        assert len(uncertain) == len(case.get("uncertain", []))
        assert not (included & excluded or included & uncertain or excluded & uncertain)
        assert included | excluded | uncertain == selected
        assert {entry["name"] for entry in case.get("exclude_evidence", [])} <= excluded
        assert {entry["name"] for entry in case.get("uncertain_evidence", [])} <= uncertain
        for entry in case["include"] + case.get("exclude_evidence", []) + case.get("uncertain_evidence", []):
            assert any(
                document["type"] == entry["document_type"] and entry["quote"] in document["text"]
                for document in candidates[entry["name"]]["documents"]
            )


def test_ten_review_snapshot_quotes_match_their_documents(
    sample_applicants: dict[str, ApplicantDetail], sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    gold: dict[str, Any] = json.loads((HERE / "dev_search_ten_gold.json").read_text(encoding="utf-8"))
    snapshot: dict[str, Any] = json.loads((HERE / "dev_search_ten_reviews.json").read_text(encoding="utf-8"))
    assert snapshot["dataset_sha256"] == gold["dataset_sha256"]
    assert set(snapshot["reviews"]) == set(gold["candidates"])
    context = dev_context(sample_applicants, sample_company, sample_posting, "")
    rows = {row.name: row for row in context.candidates}
    for name, record in snapshot["reviews"].items():
        review = ApplicationReview.model_validate(record)
        assert review.application_id == rows[name].application_id
        documents = context.documents[review.application_id]
        for fact in review.facts:
            for quote in fact.quotes:
                matching = [document for document in documents if document.type == quote.document]
                assert evidence_source(quote.sentence, matching) == quote.document


def dev_context(
    applicants: dict[str, ApplicantDetail], company: CompanyProfile, posting: PostingContent, message: str
) -> ChatContext:
    context = make_context(applicants, company, posting, message=message)
    template = context.candidates[0]
    rows = []
    documents: dict[UUID, list[ApplicantDocument]] = {}
    for candidate in DATA["candidates"]:
        candidate_id = uuid5(NAMESPACE_URL, "hiremate-dev-eval/" + candidate["name"])
        rows.append(template.model_copy(update={"application_id": candidate_id, "name": candidate["name"]}))
        documents[candidate_id] = [
            ApplicantDocument(
                type=DocumentType[doc["type"]],
                file_id=uuid5(candidate_id, doc["type"]),
                file_name=doc["type"],
                size=len(doc["text"].encode()),
                text=doc["text"],
            )
            for doc in candidate["documents"]
        ]
    return context.model_copy(update={"candidates": rows, "documents": documents})


async def seed_profiles(session: AsyncSession, context: ChatContext) -> None:
    ids = {row.name: row.application_id for row in context.candidates}
    for candidate in DATA["candidates"]:
        if not candidate["profile"]:
            continue
        await save_profile(
            session,
            company_id=context.company.company_id,
            recruitment_id=context.recruitment_id,
            application_id=ids[candidate["name"]],
            agent=ItemAgent.APPLICATION,
            fields=ProfileFields(
                status="DONE", career_years=6, last_company="바름카드 승인개발팀", summary="서류 분석 완료"
            ),
            items=[NewItem.model_validate(item) for item in candidate["profile"]],
        )
    await session.commit()


async def test_dev_search_candidates_are_repeatable(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = dev_context(sample_applicants, sample_company, sample_posting, "결제 경험")
    await seed_profiles(db_session, context)
    toolkit = profile_toolkit(sessions_of(db_session))
    scope = scope_of(context)
    pool = [row.application_id for row in context.candidates]
    for case in CASES:
        first = await toolkit.search(scope, [case["query"]], pool)
        second = await toolkit.search(scope, [case["query"]], pool)
        assert first == second


class CountingLog:
    def __init__(self) -> None:
        self.count = 0

    async def record(self, record: CallRecord) -> None:
        self.count += 1


def capture_search(
    search: CandidateSearch, names: dict[UUID, str], observed: list[tuple[list[str], list[str]]]
) -> CandidateSearch:
    async def capture(scope: ToolScope, concepts: Sequence[str], pool: Sequence[UUID]) -> list[CandidateMatch]:
        matches = await search(scope, concepts, pool)
        observed.append((list(concepts), [names[match.application_id] for match in matches]))
        return matches

    return capture


@pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델로 평가한다")
async def test_dev_search_with_real_model(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = dev_context(sample_applicants, sample_company, sample_posting, "")
    await seed_profiles(db_session, context)
    names = {row.application_id: row.name for row in context.candidates}
    llm = build_llm(CountingLog())
    print("\n| 사례 | 반복 | 검색 조건 | 후보 순서 | 결과 | 확인 대상 누락 | 확인 대상 오탐 | 시간(초) |")
    print("|---|---:|---|---|---|---|---|---:|")
    for case in CASES:
        for repeat in range(1, 4):
            started = time.monotonic()
            toolkit = profile_toolkit(sessions_of(db_session))
            observed: list[tuple[list[str], list[str]]] = []
            toolkit = replace(toolkit, search=capture_search(toolkit.search, names, observed))
            plan = await run_plan(llm, context.model_copy(update={"message": case["query"]}), toolkit)
            actual = [names[target] for target in plan.targets if target in names]
            missing = sorted(set(case["must_include"]) - set(actual))
            unwanted = sorted(set(case["must_exclude"]) & set(actual))
            queries = "; ".join(", ".join(terms) for terms, _ in observed) or "검색 없음"
            candidates = "; ".join(", ".join(found) for _, found in observed) or "없음"
            print(
                f"| {case['id']} | {repeat} | {queries} | {candidates} | {', '.join(actual) or '-'} | "
                f"{', '.join(missing) or '-'} | {', '.join(unwanted) or '-'} | {time.monotonic() - started:.2f} |"
            )
