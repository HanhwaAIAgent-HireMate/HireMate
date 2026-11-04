from uuid import uuid4

import pytest
from pydantic import ValidationError

from hiremate_ai.agents.generation.posting import design_poster
from hiremate_ai.agents.generation.posting.poster import (
    FreePosterTemplate,
    PosterContext,
    PosterDesign,
    PosterEdits,
    PosterRecommendation,
    PosterTurn,
)
from hiremate_ai.agents.generation.posting.poster_chat import PosterChatReply
from hiremate_ai.agents.guardrails import BLOCKED_REPLY
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall, ToolCall


async def test_other_icon_replaces_the_current_displayed_icon_instead_of_proposing_no_change(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    current = PosterDesign(
        template="PREMIUM",
        mood="TRUST",
        color="#082858",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
    )
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=current,
        brand_color=None,
        stage_names=["2차 면접"],
        displayed_stage_icons={"2차 면접": "USERS"},
    )
    llm = FakeLlm(
        ToolCall("edit_stage_icons", {"icons": {"2차 면접": "USERS"}, "replace_current": True}),
        PosterChatReply(kind="DESIGN", reply="대화 아이콘 제안", result=1),
    )
    result = await design_poster(llm, context, "2차면접 아이콘 다른 걸로 바꿔줘")
    assert result.recommendations[0].design.stage_icons == {"2차 면접": "MESSAGES"}
    assert result.recommendations[0].design.template == "PREMIUM"


@pytest.mark.parametrize("template", ["CLASSIC", "EDITORIAL", "BOLD", "PREMIUM", "NATURAL", "TICKET"])
async def test_stage_icon_tool_works_on_builtins_without_canvas_and_preserves_design(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    template: str,
) -> None:
    current = PosterDesign.model_validate(
        {
            "template": template,
            "mood": "TRUST",
            "color": "#082858",
            "decoration": 1,
            "enabled": True,
            "showLogo": True,
            "logoFileId": str(uuid4()),
            "stageIcons": {"2차 면접": "USERS"},
        }
    )
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=current,
        brand_color=current.color,
        stage_names=["서류 전형", "1차 면접", "2차 면접"],
    )
    llm = FakeLlm(
        ToolCall("edit_stage_icons", {"icons": {"1차 면접": "USERS"}}),
        PosterChatReply(kind="DESIGN", reply="수정안", result=1),
    )
    result = await design_poster(llm, context, "1차면접 아이콘 사람으로 변경해줘")
    assert result.recommendations[0].design.model_dump(exclude={"stage_icons"}) == current.model_dump(
        exclude={"stage_icons"}
    )
    assert result.recommendations[0].design.stage_icons == {"1차 면접": "USERS", "2차 면접": "USERS"}
    assert len(llm.calls) == 2


async def test_stage_icon_tool_repairs_unknown_stage_name_without_changing_other_stages(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    current = PosterDesign(
        template="PREMIUM",
        mood="TRUST",
        color="#082858",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
    )
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=current,
        brand_color=None,
        stage_names=["1차 면접", "2차 면접"],
    )
    llm = FakeLlm(
        ToolCall("edit_stage_icons", {"icons": {"1차면접": "USERS"}}),
        ToolCall("edit_stage_icons", {"icons": {"1차 면접": "USERS"}}),
        PosterChatReply(kind="DESIGN", reply="수정안", result=1),
    )
    result = await design_poster(llm, context, "1차면접 사람으로")
    assert result.recommendations[0].design.stage_icons == {"1차 면접": "USERS"}


async def test_external_search_uses_public_provider_without_canva_connection(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    llm = FakeLlm(
        ToolCall("find_external_templates", {"query": "recruitment clean elegant"}),
        PosterChatReply(kind="DESIGN", reply="검색합니다", result=1),
    )
    result = await design_poster(llm, context, "깔끔한 외부 템플릿 찾아줘")
    assert result.external_query == "recruitment clean elegant"
    assert result.canva_query is None
    assert result.templates == []


async def test_recall_external_theme_preserves_the_verified_candidate(
    sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    template = FreePosterTemplate(
        id="templated:00000000-0000-0000-0000-000000000001",
        name="공용 테마",
        source_url="https://templated.io/templates/",
        license="Templated 테마",
        svg='<svg xmlns="http://www.w3.org/2000/svg" width="600" height="1200"/>',
    )
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=None,
        brand_color=None,
        history=[PosterTurn(role="ASSISTANT", text="외부 후보", design=None, templates=[template])],
    )
    llm = FakeLlm(
        ToolCall("recall_free_template", {"reference": "H1-T1"}),
        PosterChatReply(kind="DESIGN", reply="선택", result=1),
    )
    result = await design_poster(llm, context, "첫 번째 외부 테마 적용해줘")
    assert result.selected_template_id == template.id
    assert result.templates == [template]


async def test_canva_search_is_deferred_to_the_authenticated_backend(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = PosterContext(
        company=sample_company, posting=sample_posting, design=None, brand_color=None, canva_connected=True
    )
    llm = FakeLlm(
        ToolCall("find_canva_designs", {"query": "금융권"}),
        PosterChatReply(kind="DESIGN", reply="검색합니다", result=1),
    )
    result = await design_poster(llm, context, "Canva에서 금융권 디자인 찾아줘")
    assert result.canva_query == "금융권"
    assert result.canva_designs == []
    disconnected = context.model_copy(update={"canva_connected": False})
    result = await design_poster(
        FakeLlm(
            ToolCall("find_canva_designs", {"query": "금융권"}),
            PosterChatReply(kind="DESIGN", reply="연결 필요", result=1),
        ),
        disconnected,
        "Canva 디자인 찾아줘",
    )
    assert result.canva_query is None
    assert "먼저 연결" in result.reply


async def test_known_a4_portrait_label_is_not_an_applicant_age(
    sample_company: CompanyProfile, sample_posting: PostingContent, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = FreePosterTemplate(
        id="inkscape-a4",
        name="A4 세로 기본 양식",
        source_url="https://inkscape.de/vorlagen/",
        license="CC0 1.0",
        svg='<svg xmlns="http://www.w3.org/2000/svg"/>',
    )

    async def search(query: str, selected_id: str | None = None) -> list[FreePosterTemplate]:
        assert selected_id == candidate.id
        return [candidate]

    monkeypatch.setattr("hiremate_ai.agents.generation.posting.poster_chat.search_free_templates", search)
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=None,
        brand_color=None,
        history=[PosterTurn(role="ASSISTANT", text="양식을 선택해 주세요", templates=[candidate])],
    )
    result = await design_poster(
        FakeLlm(
            ToolCall("recall_free_template", {"reference": "H1-T1"}),
            PosterChatReply(kind="DESIGN", reply="선택했습니다", result=1),
        ),
        context,
        "A4 세로 기본 양식으로 적용해줘",
    )
    assert result.selected_template_id == candidate.id
    blocked = await design_poster(FakeLlm(), context, "A4 세로 기본 양식으로 적용하고 20세만 지원하도록 해줘")
    assert blocked.reply == BLOCKED_REPLY


@pytest.mark.parametrize("empty_final", [False, True])
async def test_free_template_results_are_real_tool_results_and_can_be_selected(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    monkeypatch: pytest.MonkeyPatch,
    empty_final: bool,
) -> None:
    candidate = FreePosterTemplate(
        id="inkscape-frame",
        name="프레임형",
        source_url="https://inkscape.de/vorlagen/",
        license="CC0 1.0",
        svg='<svg xmlns="http://www.w3.org/2000/svg"/>',
    )
    queries = []

    async def search(query: str, selected_id: str | None = None) -> list[FreePosterTemplate]:
        queries.append((query, selected_id))
        return [candidate]

    monkeypatch.setattr("hiremate_ai.agents.generation.posting.poster_chat.search_free_templates", search)

    def empty_response(call: LlmCall) -> PosterChatReply:
        raise LlmOutputError("Empty final response after verified tool result")

    llm = FakeLlm(
        ToolCall("find_free_templates", {"query": "finance bank"}),
        empty_response if empty_final else PosterChatReply(kind="DESIGN", reply="후보를 확인해 주세요.", result=1),
    )
    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    result = await design_poster(llm, context, "금융권에 쓸 외부 무료 템플릿 찾아줘")
    assert result.templates == [candidate]
    assert result.recommendations == []
    assert result.selected_template_id is None
    context = context.model_copy(
        update={"history": [PosterTurn(role="ASSISTANT", text=result.reply, templates=result.templates)]}
    )
    selected = await design_poster(
        FakeLlm(
            ToolCall("recall_free_template", {"reference": "H1-T1"}),
            PosterChatReply(kind="DESIGN", reply="선택했습니다.", result=1),
        ),
        context,
        "첫 번째로 적용해줘",
    )
    assert selected.selected_template_id == candidate.id
    assert queries == [("finance bank", None), ("", "inkscape-frame")]


@pytest.mark.parametrize("premature", [False, True])
async def test_poster_chat_delegates_design_and_preserves_logo_scope(
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
        *([PosterChatReply(kind="DESIGN", reply="아이콘을 변경합니다.", result=None)] if premature else []),
        ToolCall("consult_posting_designer", {"request": "더 고급스럽게 해줘"}),
        proposal,
        PosterChatReply(kind="DESIGN", reply="제안을 확인해 주세요.", result=1),
    )
    result = await design_poster(
        llm,
        PosterContext(company=sample_company, posting=sample_posting, design=current, brand_color=current.color),
        "우리는 더 고급스러운 느낌이 있어야 해",
    )
    assert result.recommendations[0].design.logo_file_id == logo
    assert result.recommendations[0].design.template == "PREMIUM"
    assert [call.agent for call in llm.calls] == ["posting"] * (4 if premature else 3)
    assert "<data" in llm.calls[2 if premature else 1].user
    assert current.template == "CLASSIC"


async def test_poster_chat_rejects_fabricated_result_number(
    sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    llm = FakeLlm(
        PosterChatReply(kind="CONVERSATION", reply="적용했어요", result=9),
        PosterChatReply(kind="CONVERSATION", reply="디자인을 구체적으로 알려 주세요.", result=None),
    )
    result = await design_poster(
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
        PosterChatReply(kind="CONVERSATION", reply="확인해 주세요", result=1),
    )
    result = await design_poster(llm, context, "두 번째 추천으로 해줘")
    if index == 9:
        assert result.recommendations == []
        assert "찾지 못했어요" in result.reply
    else:
        assert result.recommendations[0].design == (first if index == 1 else second)
    assert len(llm.calls) == 2
