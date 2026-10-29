from uuid import uuid4

import pytest
from pydantic import ValidationError

from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterDesign,
    PosterEdits,
    PosterRecommendation,
    PosterTurn,
)
from hiremate_ai.agents.root.poster import PosterRootReply, plan_poster
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm, ToolCall


@pytest.mark.parametrize("premature", [False, True])
async def test_root_delegates_design_and_preserves_logo_scope(
    sample_company: CompanyProfile, sample_posting: PostingContent, premature: bool
) -> None:
    logo = uuid4()
    current = PosterDesign(
        template="CLASSIC", mood="TRUST", color="#2459a6", decoration=1, enabled=True, show_logo=True, logo_file_id=logo
    )
    proposed = current.model_copy(update={"template": "PREMIUM", "mood": "PREMIUM", "logo_file_id": uuid4()})
    proposal = PosterEdits(
        scope="DESIGN",
        reply="장식을 줄이고 여백을 늘린 수정안이에요.",
        recommendations=[PosterRecommendation(design=proposed, reason="차분하고 절제된 디자인이에요.")],
    )
    llm = FakeLlm(
        *([PosterRootReply(kind="DESIGN", reply="아이콘을 변경합니다.", result=None)] if premature else []),
        ToolCall("consult_posting_designer", {"request": "더 고급스럽게 해줘"}),
        proposal,
        PosterRootReply(kind="DESIGN", reply="제안을 확인해 주세요.", result=1),
    )
    result = await plan_poster(
        llm,
        PosterContext(company=sample_company, posting=sample_posting, design=current, brand_color=current.color),
        "우리는 더 고급스러운 느낌이 있어야 해",
    )
    assert result.recommendations[0].design.logo_file_id == logo
    assert result.recommendations[0].design.template == "PREMIUM"
    assert [call.agent for call in llm.calls] == (["root"] if premature else []) + ["root", "posting", "root"]
    assert "<data" in llm.calls[2 if premature else 1].user
    assert current.template == "CLASSIC"


async def test_root_rejects_fabricated_result_number(
    sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    llm = FakeLlm(
        PosterRootReply(kind="CONVERSATION", reply="적용했어요", result=9),
        PosterRootReply(kind="CONVERSATION", reply="디자인을 구체적으로 알려 주세요.", result=None),
    )
    result = await plan_poster(
        llm, PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None), "디자인 안내"
    )
    assert result.recommendations == []
    assert len(llm.calls) == 2


@pytest.mark.parametrize("patch", [{"color": "url(evil)"}, {"decoration": 3}, {"template": "CUSTOM"}])
def test_design_cannot_contain_arbitrary_styles(patch: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PosterDesign.model_validate(
            {
                "template": "CLASSIC",
                "mood": "TRUST",
                "color": "#2459a6",
                "decoration": 1,
                "enabled": True,
                "showLogo": False,
                "logoFileId": None,
                **patch,
            }
        )


@pytest.mark.parametrize("index", [1, 2, 9])
async def test_recall_restores_exact_prior_design_or_asks_without_inventing(
    sample_company: CompanyProfile, sample_posting: PostingContent, index: int
) -> None:
    first = PosterDesign(
        template="CLASSIC",
        mood="CLEAR",
        color="#123456",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
    )
    second = first.model_copy(update={"template": "NATURAL", "color": "#18b8b8", "background_style": "SOFT_GRADIENT"})
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=first,
        brand_color=None,
        history=[
            PosterTurn(role="USER", text="추천해줘", design=first),
            PosterTurn(
                role="ASSISTANT",
                text="두 가지 추천이에요.",
                recommendations=[
                    PosterRecommendation(design=first, reason="첫 번째"),
                    PosterRecommendation(design=second, reason="두 번째"),
                ],
            ),
        ],
    )
    llm = FakeLlm(
        ToolCall("recall_poster", {"reference": f"H2-R{index}"}),
        PosterRootReply(kind="CONVERSATION", reply="확인해 주세요", result=1),
    )
    result = await plan_poster(llm, context, "두 번째 추천으로 해줘")
    if index == 9:
        assert result.recommendations == []
        assert "찾지 못했어요" in result.reply
    else:
        assert result.recommendations[0].design == (first if index == 1 else second)
    assert len(llm.calls) == 2
