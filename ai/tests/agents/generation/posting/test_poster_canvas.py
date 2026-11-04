import json

import pytest

from hiremate_ai.agents.generation.posting.poster import PosterContext, PosterDesign
from hiremate_ai.agents.generation.posting.poster_canvas import (
    CanvaBinding,
    CanvaMatches,
    CanvaRegion,
    CanvaRegionMatch,
    CanvasChange,
    CanvasEdits,
    LayoutAnchor,
    LayoutRegion,
    TemplateAnchors,
    apply_canvas_changes,
    canvas_summary,
    map_canva,
    plan_template_layout,
    revise_canvas,
)
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm


async def test_source_mapping_repair_explains_the_header_boundary() -> None:
    regions = [
        LayoutRegion(id="header", text="", kind="SHAPE", left=0, top=0, width=600, height=260),
        LayoutRegion(id="company", text="회사명", kind="TEXT", left=40, top=30, width=150, height=30),
        LayoutRegion(id="title", text="채용", kind="TEXT", left=40, top=100, width=400, height=70),
        LayoutRegion(id="job", text="모집 직무", kind="TEXT", left=40, top=400, width=250, height=100),
        LayoutRegion(id="duties", text="주요 업무", kind="TEXT", left=310, top=400, width=250, height=100),
    ]
    header = [
        LayoutAnchor(binding="company", body=2),
        LayoutAnchor(binding="title", body=3),
    ]
    llm = FakeLlm(
        TemplateAnchors(sections=header),
        TemplateAnchors(sections=[LayoutAnchor(binding="tags", body=4)]),
        TemplateAnchors(sections=header),
        TemplateAnchors(sections=[LayoutAnchor(binding="conditions", body=4)]),
    )
    result = await plan_template_layout(llm, regions)
    assert result.sections[-1].binding == "conditions"
    assert "tags: 본문 번호 4의 top=400.0" in llm.calls[2].user
    assert "헤더 경계 260.0" in llm.calls[2].user
    assert "모집 직무" not in llm.calls[0].user
    assert "회사명" not in llm.calls[1].user


def canvas() -> str:
    return json.dumps(
        {
            "width": 600,
            "height": 1000,
            "objects": [
                {
                    "hmId": "title",
                    "binding": "title",
                    "left": 40,
                    "top": 60,
                    "fontSize": 32,
                    "fill": "#112233",
                    "text": "",
                },
                {"hmId": "benefits", "binding": "benefits", "left": 40, "top": 300, "text": ""},
                {"hmId": "decoration-0", "path": [["M", 0, 0], ["L", 60, 60]], "left": 0},
            ],
        }
    )


async def test_generated_palette_request_updates_the_design_color_without_changing_job_text(
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    data = json.loads(canvas())
    data["source"] = {"url": "hiremate:generated"}
    current = PosterDesign(
        template="CLASSIC",
        mood="TRUST",
        color="#082858",
        decoration=1,
        enabled=True,
        show_logo=False,
        logo_file_id=None,
        canvas_json=json.dumps(data),
    )
    context = PosterContext(company=sample_company, posting=sample_posting, design=current, brand_color=None)
    result = await revise_canvas(
        FakeLlm(CanvasEdits(scope="COLOR", reply="전체 색 변경", changes=[], palette="#7c3aed")),
        context,
        "본문까지 전체 보라색으로 바꿔줘",
    )
    assert result.recommendations[0].design.color == "#7c3aed"
    assert json.loads(result.recommendations[0].design.canvas_json or "{}") == data


def test_layout_edits_change_only_target_properties() -> None:
    value = canvas()
    updated = json.loads(
        apply_canvas_changes(
            value,
            [CanvasChange(element_id="benefits", left=310, width=240), CanvasChange(element_id="title", font_size=44)],
        )
    )
    assert updated["objects"][0]["fontSize"] == 44
    assert updated["objects"][0]["fill"] == "#112233"
    assert updated["objects"][1]["left"] == 310
    assert updated["objects"][1]["binding"] == "benefits"
    assert updated["objects"][1]["text"] == ""
    assert updated["objects"][2] == json.loads(value)["objects"][2]


def test_layout_rejects_unknown_elements_and_summary_does_not_send_paths() -> None:
    with pytest.raises(ValueError):
        apply_canvas_changes(canvas(), [CanvasChange(element_id="other-company", left=1)])
    summary = canvas_summary(canvas())
    assert summary and "path" not in str(summary)
    assert canvas_summary("invalid") is None


def test_layout_rejects_moving_content_outside_the_poster() -> None:
    with pytest.raises(ValueError, match="outside"):
        apply_canvas_changes(canvas(), [CanvasChange(element_id="benefits", left=590, width=240)])


def test_preserved_canva_background_cannot_receive_ineffective_style_edits() -> None:
    value = json.loads(canvas())
    value["objects"].append({"hmId": "canva-background", "type": "Image", "left": 0})
    with pytest.raises(ValueError, match="preserved image"):
        apply_canvas_changes(json.dumps(value), [CanvasChange(element_id="canva-background", fill="#ffffff")], "COLOR")


def test_layout_scope_keeps_color_and_typography_when_the_model_includes_extra_fields() -> None:
    original = json.loads(canvas())
    updated = json.loads(
        apply_canvas_changes(
            canvas(),
            [
                CanvasChange(element_id="title", left=80, fill="#ffffff", font_size=48),
            ],
            "LAYOUT",
        )
    )
    assert updated["objects"][0]["left"] == 80
    assert updated["objects"][0]["fill"] == original["objects"][0]["fill"]
    assert updated["objects"][0]["fontSize"] == original["objects"][0]["fontSize"]
    assert updated["objects"][1:] == original["objects"][1:]


def test_canvas_labels_distinguish_company_name_from_introduction() -> None:
    summary = canvas_summary(
        json.dumps(
            {
                "width": 600,
                "height": 1000,
                "objects": [
                    {"hmId": "company", "binding": "company"},
                    {"hmId": "intro", "binding": "intro"},
                ],
            }
        )
    )
    assert summary
    assert [item["label"] for item in summary["elements"]] == ["회사명", "회사 소개 본문"]


async def test_canva_mapping_uses_only_source_ids_and_each_posting_field_once() -> None:
    regions = [CanvaRegion(id="title", text="다른 회사 제목", left=40, top=80, width=500, height=100)]
    llm = FakeLlm(
        CanvaMatches(
            bindings=[
                CanvaRegionMatch(region_number=1, binding="title"),
                CanvaRegionMatch(region_number=1, binding="intro"),
                CanvaRegionMatch(region_number=99, binding="intro"),
                CanvaRegionMatch(region_number=1, binding="title"),
            ]
        )
    )
    result = await map_canva(llm, regions)
    assert result.bindings == [CanvaBinding(element_id="title", binding="title")]


async def test_no_change_does_not_expose_model_field_names_or_claim_content_edits(
    sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = PosterContext(
        company=sample_company,
        posting=sample_posting,
        brand_color=None,
        design=PosterDesign(
            template="CLASSIC",
            mood="TRUST",
            color="#112233",
            decoration=1,
            enabled=True,
            show_logo=False,
            logo_file_id=None,
            canvas_json=canvas(),
        ),
    )
    result = await revise_canvas(
        FakeLlm(CanvasEdits(scope="COLOR", reply="changes", changes=[])), context, "이미 흰색인 제목을 흰색으로"
    )
    assert result.recommendations == []
    assert "changes" not in result.reply
    assert "글 공고에서" in result.reply
