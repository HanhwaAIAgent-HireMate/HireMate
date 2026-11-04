"""LLM_EVAL=true일 때 실제 모델로 공고 생성·부분 수정·추천 참조를 검사한다."""

from pathlib import Path

import pytest

from hiremate_ai.agents.generation.posting import PostingDraftContext, design_poster, revise_posting
from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterDesign,
    PosterRecommendation,
    PosterTurn,
)
from hiremate_ai.agents.generation.posting.reviser import NOTHING_CHANGED_REPLY
from hiremate_ai.config import settings
from hiremate_ai.contract import CompanyProfile
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.client import build_llm

pytestmark = [
    pytest.mark.skipif(not settings.llm_eval, reason="LLM_EVAL=true일 때 실제 모델로 평가한다"),
    pytest.mark.asyncio(loop_scope="module"),
]


class MemoryLog:
    async def record(self, record: CallRecord) -> None:
        print({"agent": record.agent, "status": record.status, "output": record.output})


def draft() -> PostingDraftContext:
    path = Path(__file__).resolve().parents[3] / "contract/PostingDraftContext.json"
    return PostingDraftContext.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("request_text", ["근무지만 부산 해운대로 변경해줘", "근무지 칸을 부산 해운대로 바꿔줘"])
async def test_location_paraphrases_only_change_location(request_text: str) -> None:
    original = draft()
    result = await revise_posting(build_llm(MemoryLog()), original, "담백하게", request_text)
    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["location"]
    assert "부산" in result.suggestion.content.location


async def test_career_condition_and_requirement_agree() -> None:
    result = await revise_posting(build_llm(MemoryLog()), draft(), "담백하게", "경력 5년 이상으로 바꿔줘")
    assert result.suggestion is not None
    assert "5년" in result.suggestion.content.career
    assert all("경력 3년 이상" not in line for line in result.suggestion.content.qualifications)


async def test_new_posting_contains_duties_without_inventing_company_conditions() -> None:
    original = draft()
    blank = original.content.model_copy(
        update={
            key: [] if isinstance(value, list) else None if key == "headcount" else ""
            for key, value in original.content.model_dump(by_alias=False).items()
        }
    )
    result = await revise_posting(
        build_llm(MemoryLog()),
        original.model_copy(update={"content": blank}),
        "담백하게",
        "백엔드 3년차 개발자 공고 생성해줘",
    )
    assert result.suggestion is not None
    content = result.suggestion.content
    assert 1 <= len(content.duties) <= 5
    assert len(content.qualifications) <= 5 and len(content.preferred) <= 5
    assert content.salary == content.employment_type == content.work_hours == ""
    assert content.benefits == []


@pytest.mark.parametrize(
    "request_text",
    [
        "이 포지션 연봉이랑 근무지를 공고에 넣어줘",
        "필수 자격증이랑 최소 경력 연수 넣어줘",
    ],
)
async def test_unknown_company_facts_say_why(request_text: str) -> None:
    original = draft()
    blank = original.content.model_copy(update={"salary": "", "location": ""})
    result = await revise_posting(
        build_llm(MemoryLog()), original.model_copy(update={"content": blank}), "담백하게", request_text
    )
    print(result.reply)
    assert result.reply != NOTHING_CHANGED_REPLY
    if result.suggestion is not None:
        assert not any(char.isdigit() for char in result.suggestion.content.salary)


async def test_second_recommendation_is_restored_exactly(sample_company: CompanyProfile) -> None:
    first = PosterDesign(
        template="CLASSIC",
        mood="TRUST",
        color="#123456",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
    )
    second = first.model_copy(update={"template": "NATURAL", "color": "#18b8b8", "background_style": "SOFT_GRADIENT"})
    context = PosterContext(
        company=sample_company,
        posting=draft().content,
        design=first,
        brand_color=None,
        history=[
            PosterTurn(role="USER", text="추천해줘", design=first),
            PosterTurn(
                role="ASSISTANT",
                text="두 가지 추천이에요",
                recommendations=[
                    PosterRecommendation(design=first, reason="첫 번째"),
                    PosterRecommendation(design=second, reason="두 번째"),
                ],
            ),
        ],
    )
    result = await design_poster(build_llm(MemoryLog()), context, "그중 두 번째 추천으로 해줘")
    assert len(result.recommendations) == 1
    assert result.recommendations[0].design == second


async def test_missing_recommendation_history_asks_instead_of_inventing(sample_company: CompanyProfile) -> None:
    context = PosterContext(company=sample_company, posting=draft().content, design=None, brand_color=None)
    result = await design_poster(build_llm(MemoryLog()), context, "그중 두 번째 추천으로 해줘")
    assert result.recommendations == []
