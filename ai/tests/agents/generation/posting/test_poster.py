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
