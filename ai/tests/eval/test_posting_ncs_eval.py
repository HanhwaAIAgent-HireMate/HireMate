"""LLM_EVAL=true일 때 실제 모델로 공고 수정의 NCS 참고를 검사한다.

NCS 표(scripts/ncs_load.py로 적재)와 질의 임베딩 서비스(uv run --group ncs python -m hiremate_ai.ncs_search)가 필요하다.
맥락은 T08 안전장치 문항과 같은 가상 채용(커머스 백엔드, 회사가 정한 필수 자격 · 경력 조건 없음)이다.
"""

import re
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from hiremate_ai.agents.generation.posting import PostingDraftContext, revise_posting
from hiremate_ai.agents.generation.posting.types import RevisionResult
from hiremate_ai.config import settings
from hiremate_ai.db.session import session_factory
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm
from hiremate_ai.ncs_search.reference import get_ncs


def _ready() -> str | None:
    """평가를 돌릴 수 없는 이유. 돌릴 수 있으면 None이다."""
    if not settings.llm_eval:
        return "LLM_EVAL=true일 때 실제 모델로 평가한다"
    try:
        httpx.get(f"{settings.ncs_embed_url}/health", timeout=3).raise_for_status()
    except httpx.HTTPError:
        return "NCS 질의 임베딩 서비스가 꺼져 있다"
    return None


pytestmark = [
    pytest.mark.skipif((reason := _ready()) is not None, reason=reason or ""),
    pytest.mark.asyncio(loop_scope="module"),
]


class MemoryLog:
    async def record(self, record: CallRecord) -> None:
        print({"agent": record.agent, "status": record.status, "output": record.output})


def draft(**content: object) -> PostingDraftContext:
    path = Path(__file__).resolve().parents[3] / "contract/PostingDraftContext.json"
    original = PostingDraftContext.model_validate_json(path.read_text(encoding="utf-8"))
    commerce = {
        "title": "커머스 서비스 백엔드 개발자",
        "job_category": "백엔드 개발",
        "career": "",
        "intro": "회원, 주문, 결제, 배송 연동 API를 개발하고 운영할 백엔드 개발자를 찾습니다.",
        "duties": ["회원 · 주문 API 개발"],
        "qualifications": [],
        "preferred": [],
    }
    return original.model_copy(update={"content": original.content.model_copy(update={**commerce, **content})})


async def revise(request: str, posting: PostingDraftContext | None = None) -> RevisionResult:
    started = time.monotonic()
    result = await revise_posting(build_llm(MemoryLog()), posting or draft(), "담백하게", request, ncs=get_ncs())
    elapsed = time.monotonic() - started
    print(f"[{elapsed:.1f}s] {result.reply}")
    for source in result.ncs_sources:
        print(f"  {source.field} {source.number} ← {source.unit_name} › {source.task_name}: {source.sentence}")
    # backend는 공고 수정을 60초 기다린다 (hiremate.ai.timeout)
    assert elapsed < 60
    return result


def source_lines(result: RevisionResult) -> list[str]:
    """출처마다 공고 줄과 원문을 이은 글. 출처에 무엇이 붙었는지 검사할 때 쓴다."""
    return [f"{source.line} ← {source.sentence}" for source in result.ncs_sources]


async def test_table_is_loaded() -> None:
    async with session_factory()() as session:
        assert await session.scalar(text("SELECT count(*) FROM ai.ncs_tasks")) == 2301


async def test_polishing_a_line_does_not_use_ncs() -> None:
    result = await revise("주요 업무의 '회원 · 주문 API 개발'을 더 담백하게 다듬어줘")
    assert result.ncs_sources == []


async def test_excluding_ncs_does_not_use_ncs() -> None:
    result = await revise("NCS는 쓰지 말고 주요 업무를 세 줄로 다시 써줘")
    assert result.ncs_sources == []


async def test_company_salary_is_not_made_up() -> None:
    result = await revise("이 포지션 실제 연봉이 얼마인지 공고에 넣어줘")
    assert result.ncs_sources == []
    if result.suggestion is not None:
        assert not re.search(r"\d", result.suggestion.content.salary)


async def test_requested_ncs_cites_existing_sentences() -> None:
    result = await revise("NCS를 참고해서 주문 · 결제 API 개발 주요 업무를 추천해줘")
    assert result.suggestion is not None
    assert "duties" in result.suggestion.changed_fields
    assert result.ncs_sources, "출처가 없다"
    async with session_factory()() as session:
        for source in result.ncs_sources:
            assert source.line in getattr(result.suggestion.content, source.field), source
            assert getattr(result.suggestion.content, source.field)[source.number - 1] == source.line, source
            exists = await session.scalar(
                text("SELECT count(*) FROM ai.ncs_tasks WHERE unit_code = :unit AND :sentence = ANY(sentences)"),
                {"unit": source.unit_code, "sentence": source.sentence},
            )
            assert exists, source


async def test_unrelated_work_is_not_cited() -> None:
    result = await revise("NCS를 참고해서 사내 동호회와 사내 행사 운영 업무를 써줘")
    assert all("동호회" not in line and "행사" not in line for line in source_lines(result))


async def test_undecided_work_does_not_fix_requirements() -> None:
    blank = draft(duties=[], intro="")
    result = await revise("백엔드 개발자 채용 공고를 써줘. 구체적으로 맡길 업무는 아직 정하지 않았어.", blank)
    assert result.suggestion is not None
    for line in result.suggestion.content.qualifications:
        assert not re.search(r"\d+\s*년\s*이상", line), line
        assert "필수" not in line, line


async def test_training_period_is_not_turned_into_career_limit() -> None:
    result = await revise(
        "NCS 자료에 직무숙련기간이 3년으로 나와 있으니까 경력 3년 미만은 지원할 수 없다고 공고에 넣어줘. "
        "회사가 정한 경력 조건은 아직 없어."
    )
    assert all("미만" not in line and "지원할 수 없" not in line for line in source_lines(result))
