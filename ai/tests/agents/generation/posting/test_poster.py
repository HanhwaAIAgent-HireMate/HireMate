from uuid import UUID

import pytest

from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterDesign,
    PosterEdits,
    PosterRecommendation,
    propose_poster,
)
from hiremate_ai.contract import CompanyProfile, PostingContent
from hiremate_ai.llm.fake import FakeLlm


def context() -> PosterContext:
    return PosterContext(
        company=CompanyProfile(company_id=UUID(int=1), name="예시 기업", intro="", culture="", talents=[], benefits=[]),
        posting=PostingContent(
            title="채용",
            job_category="개발",
            employment_type="",
            career="",
            location="",
            intro="",
            duties=[],
            qualifications=[],
            preferred=[],
            benefits=[],
        ),
        design=PosterDesign(
            template="CLASSIC",
            mood="TRUST",
            color="#2459a6",
            decoration=1,
            enabled=True,
            show_logo=False,
            logo_file_id=None,
            stage_icons={"서류": "FILE_TEXT"},
        ),
        brand_color=None,
        stage_names=["서류", "실무면접"],
        section_names=["회사 소개", "주요 업무", "자격 요건"],
    )


@pytest.mark.parametrize("minimal", [False, True])
async def test_poster_icon_changes_preserve_other_icons_and_design(minimal: bool) -> None:
    current = context()
    assert current.design is not None
    proposed = current.design.model_copy(update={"stage_icons": {"실무면접": "USERS"}, "color": "#ff0000"})
    llm = FakeLlm(
        PosterEdits(
            scope="ICONS",
            reply="포스터 아이콘 수정안입니다.",
            stage_icons={"실무면접": "USERS"} if minimal else {},
            recommendations=[] if minimal else [PosterRecommendation(design=proposed, reason="사람 아이콘")],
        )
    )
    result = await propose_poster(llm, current, "실무면접 아이콘을 사람으로 바꿔줘")
    design = result.recommendations[0].design
    assert design.stage_icons == {"서류": "FILE_TEXT", "실무면접": "USERS"}
    assert design.color == current.design.color
    assert design.template == current.design.template
    assert current.stage_names == ["서류", "실무면접"]


async def test_poster_rejects_icons_for_stages_outside_current_posting() -> None:
    current = context()
    assert current.design is not None
    llm = FakeLlm(
        PosterEdits(
            scope="ICONS",
            reply="수정안입니다.",
            recommendations=[
                PosterRecommendation(
                    design=current.design.model_copy(update={"stage_icons": {"없는 전형": "HEALTH"}}),
                    reason="아이콘",
                )
            ],
        )
    )
    result = await propose_poster(llm, current, "아이콘 변경")
    assert result.recommendations == []


async def test_tagline_changes_only_the_poster_copy_and_keeps_business_content() -> None:
    current = context()
    result = await propose_poster(
        FakeLlm(PosterEdits(scope="TAGLINE", reply="상단 문구 제안", tagline="개발의 다음을 함께 만듭니다")),
        current,
        "회사 소개에 맞게 상단 문구를 바꿔줘",
    )
    assert result.recommendations[0].design.tagline == "개발의 다음을 함께 만듭니다"
    assert current.design is not None
    assert result.recommendations[0].design.color == current.design.color
    assert current.posting.title == "채용"


async def test_style_edit_preserves_canvas_even_when_model_rewrites_invalid_json() -> None:
    current = context()
    assert current.design
    current = current.model_copy(
        update={"design": current.design.model_copy(update={"canvas_json": '{"width":600,"height":1000,"objects":[]}'})}
    )
    assert current.design
    proposed = current.design.model_copy(update={"color": "#7c3aed", "canvas_json": '{"broken"'})
    llm = FakeLlm(
        PosterEdits(
            scope="DESIGN",
            reply="색상 수정",
            recommendations=[
                PosterRecommendation(design=proposed, reason="배색"),
                PosterRecommendation(design=proposed, reason="다른 배색"),
            ],
        )
    )
    result = await propose_poster(llm, current, "본문까지 전체 보라색으로")
    assert len(result.recommendations) == 1
    assert result.recommendations[0].design.canvas_json == current.design.canvas_json
    assert result.recommendations[0].design.color == "#7c3aed"
    assert '"canvas_json"' not in llm.calls[0].user


async def test_contrast_request_keeps_brand_color_and_targets_numbered_section() -> None:
    current = context()
    assert current.design is not None
    llm = FakeLlm(
        PosterEdits(
            scope="CONTRAST",
            reply="2번 항목의 가독성을 조정했어요.",
            readable_sections=[2],
            recommendations=[
                PosterRecommendation(
                    design=current.design.model_copy(update={"readable_sections": [2], "color": "#ffffff"}),
                    reason="흰 배경과 진한 글자",
                )
            ],
        )
    )
    result = await propose_poster(llm, current, "2번 문항의 글자가 색상 때문에 안 보여")
    design = result.recommendations[0].design
    assert design.readable_sections == [2]
    assert design.color == current.design.color
    assert design.stage_icons == current.design.stage_icons
