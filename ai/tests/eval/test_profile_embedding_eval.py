"""가상 지원자의 금융 서비스 실무 검색을 도입 전후로 비교한다."""

import time
from uuid import UUID

import httpx
import pytest
from root_context import make_context, save_sample_profiles, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.root.graph import run_plan
from hiremate_ai.agents.root.toolkit import profile_toolkit, scope_of
from hiremate_ai.config import settings
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm
from hiremate_ai.ncs_search.reference import EmbedClient
from hiremate_ai.tools.profile_search import DenseProfileEmbedder, index_profile_embeddings

EXPECTED = {"정유민", "김하늘", "한예린"}
QUERY = "금융 서비스 개발 실무 경험이 있는 지원자를 찾아줘"


class Metrics:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


@pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델로 평가한다")
async def test_finance_search_with_real_embeddings(
    db_session: AsyncSession,
    sample_applicants: dict[str, ApplicantDetail],
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = make_context(sample_applicants, sample_company, sample_posting, message=QUERY)
    await save_sample_profiles(db_session, sample_company, sample_applicants)
    await db_session.commit()
    metrics = Metrics()
    llm = build_llm(metrics)
    names: dict[UUID, str] = {row.application_id: row.name for row in context.candidates}
    pool = [row.application_id for row in context.candidates]
    async with httpx.AsyncClient(timeout=settings.ncs_embed_timeout_seconds) as http:
        embedder = DenseProfileEmbedder(EmbedClient(http, settings.ncs_embed_url))
        for applicant in sample_applicants.values():
            await index_profile_embeddings(
                db_session,
                embedder,
                sample_company.company_id,
                applicant.info.recruitment_id,
                applicant.info.application_id,
                model=settings.ncs_model,
            )
        await db_session.commit()
        sessions = sessions_of(db_session)
        before = profile_toolkit(sessions)
        after = profile_toolkit(sessions, embedder=embedder)
        before_candidates = await before.search(scope_of(context), [QUERY], pool)
        after_candidates = await after.search(scope_of(context), [QUERY], pool)
        before_set = {names[item.application_id] for item in before_candidates}
        after_set = {names[item.application_id] for item in after_candidates}
        print(f"\n후보 기준: 기존 {len(before_set)}명, 확장 {len(after_set)}명")
        print(f"정답 후보 누락: 기존 {sorted(EXPECTED - before_set)}, 확장 {sorted(EXPECTED - after_set)}")
        assert after_set >= EXPECTED
        seen: list[set[str]] = []
        for iteration in range(1, 4):
            started = time.monotonic()
            prior_calls = len(metrics.records)
            plan = await run_plan(llm, context, after)
            result = {names[target] for target in plan.targets}
            seen.append(result)
            print(
                f"반복 {iteration}: {sorted(result)}, 누락 {sorted(EXPECTED - result)}, "
                f"추가 {sorted(result - EXPECTED)}, 호출 {len(metrics.records) - prior_calls}, "
                f"시간 {time.monotonic() - started:.2f}초"
            )
        print(
            f"모델 입력 토큰 {sum(record.input_tokens or 0 for record in metrics.records)}, "
            f"출력 토큰 {sum(record.output_tokens or 0 for record in metrics.records)}"
        )
        assert all(result == EXPECTED for result in seen)
        assert seen[0] == seen[1] == seen[2]
