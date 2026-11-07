import json
from pathlib import Path

import pytest

from hiremate_ai.agents.generation.posting import design_poster
from hiremate_ai.agents.generation.posting.poster import PosterContext, PosterDesign, PosterTurn
from hiremate_ai.agents.generation.posting.poster_chat import PosterIntent
from hiremate_ai.agents.generation.posting.poster_generator import (
    GeneratedTheme,
    GeneratedThemes,
    ReferenceSelection,
    build_generated_canvas,
    generate_banner,
    generate_poster,
)
from hiremate_ai.agents.generation.posting.poster_references import load_poster_references
from hiremate_ai.config import settings
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm


@pytest.fixture(autouse=True)
def local_reference_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "poster_references_path", "")
    monkeypatch.setattr(settings, "poster_reference_images_path", "")


@pytest.mark.parametrize("image_mode", [False, True])
async def test_references_reach_model_and_selected_sources_are_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    image_mode: bool,
) -> None:
    references = [
        {
            "id": f"R{index}",
            "role": "개발자",
            "title": f"사례 {index}",
            "designAdaptation": f"구성 {index}의 정보 위계",
            "postingUrl": f"https://example.com/{index}",
        }
        for index in range(1, 4)
    ]
    path = tmp_path / "references.json"
    path.write_text(json.dumps({"references": references}), encoding="utf-8")
    monkeypatch.setattr(settings, "poster_references_path", str(path))
    if image_mode:
        monkeypatch.setattr(settings, "poster_reference_images_path", str(tmp_path))
        for reference in references:
            (tmp_path / f"{reference['id']}.jpg").write_bytes(b"\xff\xd8sample")
    proposed = GeneratedThemes(
        themes=[
            theme.model_copy(update={"reference_ids": [f"R{index}"]}) for index, theme in enumerate(themes().themes, 1)
        ]
    )
    invalid = proposed.model_copy(
        update={"themes": [proposed.themes[0].model_copy(update={"reference_ids": ["missing"]}), *proposed.themes[1:]]}
    )
    selection = [ReferenceSelection(reference_ids=["R1", "R2", "R3"])] if image_mode else []
    llm = FakeLlm(*selection, invalid, proposed)
    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    result = await generate_poster(llm, context, "회사의 특징을 살려 만들어줘")
    assert len(llm.calls) == (3 if image_mode else 2)
    assert all(item["designAdaptation"] in llm.calls[-1].user for item in references)
    assert len(llm.calls[-1].images) == (3 if image_mode else 0)
    assert len(result.recommendations) == 3
    for index, recommendation in enumerate(result.recommendations):
        canvas = json.loads(recommendation.design.canvas_json or "{}")
        assert canvas["designReferences"] == [references[index]]
        assert canvas["generatedTheme"]["reference_ids"] == [references[index]["id"]]
        assert canvas["referenceMode"] == ("IMAGE" if image_mode else "MEMO")


def test_missing_or_invalid_reference_index_is_optional(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "missing.json"
    monkeypatch.setattr(settings, "poster_references_path", str(path))
    assert load_poster_references() == []
    path.write_text('{"references": [{"id": "invalid"}]}', encoding="utf-8")
    assert load_poster_references() == []


@pytest.mark.parametrize(
    ("style", "prompt_fragment"), [("PHOTO", "Photorealistic"), ("ILLUSTRATION", "Editorial illustration")]
)
async def test_generated_banner_uses_local_image_model_and_keeps_text_editable(
    monkeypatch: pytest.MonkeyPatch,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    style: str,
    prompt_fragment: str,
) -> None:
    async def local_banner(prompt: str) -> str:
        assert prompt_fragment in prompt
        assert "digital banking" in prompt
        assert sample_posting.title not in prompt
        assert "#082858" in prompt
        return "data:image/jpeg;base64,/9j/AA=="

    monkeypatch.setattr("hiremate_ai.agents.generation.posting.poster_generator.generate_local_banner", local_banner)
    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    theme = themes().themes[0].model_copy(update={"banner_style": style, "banner_direction": "digital banking"})
    banner = await generate_banner(theme, context)
    objects = json.loads(build_generated_canvas(theme, banner))["objects"]
    image = next(node for node in objects if node["hmId"] == "generated-banner")
    assert image["src"] == "data:image/jpeg;base64,/9j/AA=="
    assert any(node.get("binding") == "title" for node in objects)


def themes() -> GeneratedThemes:
    first = GeneratedTheme(
        name="여백과 선",
        reason="넓은 여백과 얇은 선으로 정보를 구분합니다.",
        header="BAND",
        motif="BARS",
        color="#082858",
        paper="#f7f5ef",
        accent="#b59a58",
        columns=2,
        title_size=44,
        heading_size=18,
        body_size=14,
        header_height=300,
        margin=40,
        order=["intro", "conditions", "duties", "qualifications", "preferred", "benefits", "period", "notices"],
    )
    return GeneratedThemes(
        themes=[
            first,
            first.model_copy(
                update={
                    "name": "기하학 소식지",
                    "header": "OUTLINE",
                    "motif": "CIRCLES",
                    "columns": 1,
                    "body_layout": "PANELS",
                    "process_style": "TIMELINE",
                    "documents_style": "LIST",
                }
            ),
            first.model_copy(
                update={
                    "name": "번호와 여백",
                    "header": "INSET",
                    "motif": "NONE",
                    "columns": 1,
                    "body_layout": "SIDEBAR",
                    "process_style": "STEPS",
                    "documents_style": "COMPACT",
                }
            ),
        ]
    )


@pytest.mark.parametrize("direction", ["JOURNAL", "BLUEPRINT", "STUDIO", "LEDGER", "BANNER", "GALLERY"])
def test_designed_systems_use_coordinated_typography_and_keep_editable_fields(direction: str) -> None:
    theme = themes().themes[0].model_copy(update={"art_direction": direction, "heading_size": 24, "body_size": 18})
    doc = json.loads(build_generated_canvas(theme))
    assert doc["nativeLayout"]["appearance"]["edition"] == 3
    assert doc["generatedTheme"]["heading_size"] == 22
    assert doc["generatedTheme"]["body_size"] == 16
    assert doc["generatedTheme"]["color"] == theme.color
    assert doc["generatedTheme"]["paper"] == theme.paper
    assert doc["generatedTheme"]["accent"] == theme.accent
    assert doc["generatedTheme"]["title_size"] == theme.title_size
    assert doc["generatedTheme"]["header_height"] == theme.header_height
    assert next(node for node in doc["objects"] if node["hmId"] == "title")["fontFamily"] == "Noto Sans KR Variable"
    assert len(doc["nativeLayout"]["sections"]) == 10


def test_generation_preserves_model_typography_palette_and_header_composition() -> None:
    first = themes().themes[0].model_copy(update={"art_direction": "JOURNAL", "title_size": 40, "margin": 44})
    second = first.model_copy(update={"art_direction": "GALLERY", "title_size": 54, "accent": "#c27c46"})
    documents = [json.loads(build_generated_canvas(theme)) for theme in [first, second]]
    titles = [next(node for node in doc["objects"] if node.get("binding") == "title") for doc in documents]
    assert [node["fontSize"] for node in titles] == [40, 54]
    assert [node["textAlign"] for node in titles] == ["left", "center"]
    assert titles[0]["top"] != titles[1]["top"]
    assert documents[0]["generatedTheme"]["accent"] == first.accent
    assert documents[1]["generatedTheme"]["accent"] == second.accent
    assert all(node["left"] == 44 for node in titles)
    assert all(item.get("text", "") == "" for doc in documents for item in doc["objects"])


async def test_repeated_designed_generation_uses_different_directions_and_expressions(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    def trio(first: str, second: str, third: str, expression: str = "CALM") -> GeneratedThemes:
        return GeneratedThemes(
            themes=[
                theme.model_copy(update={"art_direction": direction, "expression": expression})
                for theme, direction in zip(themes().themes, [first, second, third], strict=True)
            ]
        )

    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    initial = trio("JOURNAL", "STUDIO", "LEDGER")
    first = await generate_poster(FakeLlm(initial), context, "템플릿 만들어줘")
    context = context.model_copy(
        update={
            "history": [
                PosterTurn(
                    role="ASSISTANT",
                    text=first.reply,
                    recommendations=first.recommendations,
                )
            ]
        }
    )
    llm = FakeLlm(initial, trio("BLUEPRINT", "BANNER", "GALLERY", "GRAPHIC"))
    second = await generate_poster(llm, context, "다른 걸로 또 만들어줘")
    assert len(llm.calls) == 2
    assert {
        json.loads(item.design.canvas_json or "{}")["generatedTheme"]["art_direction"]
        for item in second.recommendations
    } == {"BLUEPRINT", "BANNER", "GALLERY"}


@pytest.mark.parametrize("previous_template", [False, True])
async def test_create_uses_generation_not_external_search_and_preserves_facts(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
    previous_template: bool,
) -> None:
    design = PosterDesign(
        template="CLASSIC",
        mood="TRUST",
        color="#082858",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
        canvas_json='{"source":{"url":"hiremate:generated"},"objects":[]}',
    )
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        design=design if previous_template else None,
        brand_color="#082858",
    )
    llm = FakeLlm(
        PosterIntent(kind="GENERATE"),
        themes(),
    )
    result = await design_poster(llm, context, "금융권 템플릿 만들어줘")
    assert llm.calls[1].user.endswith("담당자 요청: 금융권 템플릿 만들어줘")
    assert len(result.recommendations) == 3
    assert (
        len(
            {
                json.loads(item.design.canvas_json or "{}")["nativeLayout"]["appearance"]["process"]
                for item in result.recommendations
            }
        )
        == 3
    )
    assert (
        len(
            {
                json.loads(item.design.canvas_json or "{}")["nativeLayout"]["appearance"]["documents"]
                for item in result.recommendations
            }
        )
        == 3
    )
    assert result.external_query is result.canva_query is None
    assert result.templates == []
    canvases = [json.loads(item.design.canvas_json or "{}") for item in result.recommendations]
    assert canvases[0]["source"]["id"] != canvases[1]["source"]["id"]
    for canvas in canvases:
        assert canvas["source"]["url"] == "hiremate:generated"
        assert {item["binding"] for item in canvas["nativeLayout"]["sections"]} == {
            "intro",
            "conditions",
            "duties",
            "qualifications",
            "preferred",
            "benefits",
            "period",
            "notices",
            "stages",
            "documents",
        }
        assert all(item.get("text", "") == "" for item in canvas["objects"])
        assert sample_posting.title not in json.dumps(canvas, ensure_ascii=False)
    assert context.posting == sample_posting


async def test_repeat_generation_rejects_renamed_duplicate_then_repairs(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = PosterContext(company=sample_company, posting=sample_posting, design=None, brand_color=None)
    first = await generate_poster(FakeLlm(themes()), context, "새로 만들어줘")
    context = context.model_copy(
        update={"history": [PosterTurn(role="ASSISTANT", text=first.reply, recommendations=first.recommendations)]}
    )
    repeated = GeneratedThemes(themes=[item.model_copy(update={"name": "이름만 수정"}) for item in themes().themes])
    different = GeneratedThemes(
        themes=[
            themes()
            .themes[0]
            .model_copy(update={"body_layout": "SIDEBAR", "process_style": "CARDS", "documents_style": "LIST"}),
            themes()
            .themes[1]
            .model_copy(update={"body_layout": "STRIPES", "process_style": "STEPS", "documents_style": "COMPACT"}),
            themes()
            .themes[2]
            .model_copy(update={"body_layout": "EDITORIAL", "process_style": "TIMELINE", "documents_style": "TILES"}),
        ]
    )
    llm = FakeLlm(repeated, different)
    result = await generate_poster(llm, context, "다른 걸로 또 만들어줘")
    assert len(llm.calls) == 2
    assert len(result.recommendations) == 3
    failed = await generate_poster(FakeLlm(repeated, repeated), context, "또 만들어줘")
    assert failed.recommendations == []
    assert "확인하지 못했어요" in failed.reply
