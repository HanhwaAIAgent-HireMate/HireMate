"""모델이 새 편집용 레이아웃을 설계하고 코드는 사실을 포함하지 않는 바인딩 양식을 만든다."""

import hashlib
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field

from hiremate_ai.agents.generation.posting.poster import (
    PosterContext,
    PosterDesign,
    PosterProposal,
    PosterRecommendation,
)
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

type Section = Literal["intro", "conditions", "duties", "qualifications", "preferred", "benefits", "period", "notices"]


class GeneratedTheme(ContractModel):
    name: str = Field(min_length=1, max_length=40)
    reason: str = Field(min_length=1, max_length=250)
    header: Literal["BAND", "INSET", "SPLIT", "OUTLINE"]
    motif: Literal["CIRCLES", "BARS", "FRAME", "NONE"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    paper: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    columns: Literal[1, 2]
    title_size: int = Field(ge=30, le=62)
    heading_size: int = Field(ge=15, le=24)
    body_size: int = Field(ge=12, le=18)
    header_height: int = Field(ge=240, le=380)
    margin: int = Field(ge=32, le=48)
    order: list[Section] = Field(min_length=8, max_length=8)
    body_layout: Literal["EDITORIAL", "PANELS", "SIDEBAR", "STRIPES"] = "EDITORIAL"
    process_style: Literal["CARDS", "TIMELINE", "STEPS"] = "CARDS"
    documents_style: Literal["TILES", "LIST", "COMPACT"] = "TILES"
    heading_font: Literal["SANS", "SERIF"] = "SANS"
    art_direction: Literal["CUSTOM", "JOURNAL", "BLUEPRINT", "STUDIO", "LEDGER", "BANNER", "GALLERY"] = "CUSTOM"
    expression: Literal["CALM", "GRAPHIC", "TYPE"] = "CALM"


class GeneratedThemes(ContractModel):
    themes: list[GeneratedTheme] = Field(min_length=2, max_length=2)


def _fingerprint(theme: dict[str, Any]) -> str:
    visual = {key: value for key, value in theme.items() if key not in {"name", "reason"}}
    return hashlib.sha256(json.dumps(visual, sort_keys=True).encode()).hexdigest()


def _ink(background: str) -> str:
    def channel(at: int) -> float:
        value = int(background[at : at + 2], 16) / 255
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    light = sum(channel(at) * weight for at, weight in [(1, 0.2126), (3, 0.7152), (5, 0.0722)])
    return "#ffffff" if light < 0.179 else "#101820"


def _tint(color: str, amount: float) -> str:
    return "#" + "".join(f"{round(int(color[at : at + 2], 16) * (1 - amount) + 255 * amount):02x}" for at in (1, 3, 5))


def compose_theme(theme: GeneratedTheme) -> GeneratedTheme:
    """모델은 시각 방향과 표현을 고르고 검증된 비례·타이포·색상 체계로 조합한다."""
    if theme.art_direction == "CUSTOM":
        return theme
    # 헤더, 본문, 전형, 서류까지 하나의 편집 체계로 맞춘다.
    systems: dict[str, dict[str, Any]] = {
        "JOURNAL": dict(
            header="OUTLINE",
            motif="NONE",
            columns=1,
            body_layout="SIDEBAR",
            process_style="TIMELINE",
            documents_style="LIST",
            paper="#fbfaf7",
        ),
        "BLUEPRINT": dict(
            header="BAND",
            motif="BARS",
            columns=2,
            body_layout="EDITORIAL",
            process_style="CARDS",
            documents_style="COMPACT",
            paper="#ffffff",
        ),
        "STUDIO": dict(
            header="INSET",
            motif="CIRCLES",
            columns=2,
            body_layout="PANELS",
            process_style="TIMELINE",
            documents_style="TILES",
            paper=_tint(theme.color, 0.96),
        ),
        "LEDGER": dict(
            header="OUTLINE",
            motif="FRAME",
            columns=1,
            body_layout="EDITORIAL",
            process_style="STEPS",
            documents_style="COMPACT",
            paper="#ffffff",
        ),
        "BANNER": dict(
            header="SPLIT",
            motif="BARS",
            columns=1,
            body_layout="STRIPES",
            process_style="TIMELINE",
            documents_style="LIST",
            paper="#ffffff",
        ),
        "GALLERY": dict(
            header="BAND",
            motif="CIRCLES",
            columns=2,
            body_layout="EDITORIAL",
            process_style="STEPS",
            documents_style="TILES",
            paper="#f8f9fa",
        ),
    }
    system = systems[theme.art_direction]
    return theme.model_copy(
        update={
            **system,
            "margin": 40,
            "title_size": 52 if theme.expression == "TYPE" else 46,
            "heading_size": 17,
            "body_size": 14,
            "heading_font": "SANS",
            "header_height": 286 if theme.expression == "GRAPHIC" else 252,
            "accent": _tint(theme.color, 0.66),
            **({"motif": "NONE"} if theme.expression == "TYPE" else {}),
        }
    )


def build_generated_canvas(theme: GeneratedTheme) -> str:
    """실행 가능한 HTML은 받지 않고 본문은 화면에서 매번 실측해 채운다."""
    theme = compose_theme(theme)
    ink, header_ink = _ink(theme.paper), _ink(theme.color)
    margin = theme.margin
    width = 600 - margin * 2
    objects: list[dict[str, Any]] = []

    def shape(kind: str, name: str, **properties: Any) -> None:
        objects.append({"type": kind, "hmId": name, "originX": "left", "originY": "top", **properties})

    fill = theme.color if theme.header != "OUTLINE" else theme.paper
    if theme.header == "OUTLINE":
        header_ink = ink
    left = 20 if theme.header == "INSET" else 0
    shape(
        "Rect",
        "generated-header",
        left=left,
        top=16 if theme.header == "INSET" else 0,
        width=600 - left * 2,
        height=theme.header_height,
        fill=fill,
        strokeWidth=0,
        rx=16 if theme.header == "INSET" else 0,
        ry=16 if theme.header == "INSET" else 0,
    )
    if theme.header == "OUTLINE":
        shape("Rect", "generated-top-rule", left=margin, top=14, width=width, height=3, fill=theme.color, strokeWidth=0)
    if theme.header == "SPLIT":
        shape(
            "Rect",
            "generated-spine",
            left=0,
            top=0,
            width=8,
            height=theme.header_height,
            fill=theme.accent,
            strokeWidth=0,
        )
    if theme.motif == "CIRCLES":
        for index in range(3):
            shape(
                "Circle",
                f"generated-motif-{index}",
                left=430 + index * 18,
                top=102 + index * 14,
                radius=60,
                fill="transparent",
                stroke=theme.accent,
                opacity=0.35,
                strokeWidth=1,
            )
    elif theme.motif == "BARS":
        for index in range(3):
            shape(
                "Rect",
                f"generated-motif-{index}",
                left=464 + index * 24,
                top=120 - index * 24,
                width=16,
                height=76 + index * 24,
                fill=theme.accent,
                opacity=0.16,
                strokeWidth=0,
            )
    elif theme.motif == "FRAME":
        shape(
            "Rect",
            "generated-frame",
            left=422,
            top=88,
            width=122,
            height=122,
            fill="transparent",
            stroke=theme.accent,
            strokeWidth=1,
            opacity=0.3,
        )
    for binding, top, size, text_width in [
        ("company", 30, 17, width - 160),
        ("tagline", 82 if theme.header == "INSET" else 72, 12, width - 92),
        ("title", 120 if theme.header == "INSET" else 108, theme.title_size, width - 90),
        ("tags", theme.header_height - 36, 12, width),
    ]:
        shape(
            "Textbox",
            binding,
            binding=binding,
            text="",
            left=margin,
            top=top,
            width=text_width,
            fontSize=size,
            fontWeight=700 if binding == "title" else 600 if binding == "company" else 400,
            fontFamily="Noto Sans KR Variable",
            fill=header_ink,
            splitByGrapheme=True,
            lineHeight=1.25,
        )
    sections: list[dict[str, Any]] = []
    for index, binding in enumerate([*theme.order, "stages", "documents"]):
        full = index >= 8 or binding in {"intro", "conditions", "period", "notices"}
        sections.append(
            {
                "binding": binding,
                "left": margin if full else margin + (index % theme.columns) * (width + 20) / theme.columns,
                "top": theme.header_height + 40 + index * 180,
                "width": width if full else (width - 20 * (theme.columns - 1)) / theme.columns,
                "height": 120,
                "heading": {
                    "fontSize": theme.heading_size,
                    "fill": ink,
                    "fontWeight": "bold",
                    "fontFamily": "serif" if theme.heading_font == "SERIF" else "Noto Sans KR Variable",
                },
                "body": {"fontSize": theme.body_size, "fill": ink, "fontWeight": "normal"},
                "accent": ink,
                "rule": _tint(theme.color, 0.82) if theme.art_direction != "CUSTOM" else theme.accent,
                "card": theme.color,
                "lastCard": theme.accent,
                "cardInk": header_ink,
            }
        )
    # 같은 행은 폭이 겹치지 않는 두 항목만 구성한다. 전체 폭 항목은 항상 독립된 행이다.
    row, pending = 0, False
    for section in sections:
        if theme.body_layout in {"SIDEBAR", "STRIPES"}:
            section["width"] = width
        if section["width"] == width:
            section["left"] = margin
            row += int(pending)
            section["top"] = theme.header_height + 40 + row * 180
            row, pending = row + 1, False
        elif pending:
            section["left"] = margin + (width + 20) / 2
            section["top"] = theme.header_height + 40 + row * 180
            row, pending = row + 1, False
        else:
            section["left"] = margin
            section["top"] = theme.header_height + 40 + row * 180
            pending = True
    for section in sections:
        shape(
            "Textbox",
            section["binding"],
            binding=section["binding"],
            hmNativeBody=True,
            text="",
            left=section["left"],
            top=section["top"],
            width=section["width"],
            fontSize=theme.body_size,
            fill=ink,
            fontFamily="Noto Sans KR Variable",
            fontWeight="normal",
            splitByGrapheme=True,
            lineHeight=1.5,
        )
    return json.dumps(
        {
            "width": 600,
            "height": max(1000, theme.header_height + (row + 1) * 180),
            "brandColor": theme.color,
            "source": {
                "id": f"generated:{uuid4()}",
                "name": theme.name,
                "url": "hiremate:generated",
                "license": "AI 생성",
            },
            "generatedTheme": theme.model_dump(by_alias=False),
            "nativeLayout": {
                "version": 1,
                "paper": theme.paper,
                "headerBottom": theme.header_height,
                "sections": sections,
                "appearance": {
                    "body": theme.body_layout,
                    "process": theme.process_style,
                    "documents": theme.documents_style,
                    "edition": 2 if theme.art_direction != "CUSTOM" else 1,
                    "direction": theme.art_direction,
                },
            },
            "objects": objects,
        },
        ensure_ascii=False,
    )


async def generate_poster(llm: LlmClient, context: PosterContext, request: str) -> PosterProposal:
    previous: list[dict[str, Any]] = []
    designs = [context.design]
    for turn in context.history:
        designs.extend([turn.design, *(item.design for item in turn.recommendations)])
    for design in designs:
        if design and design.canvas_json:
            try:
                theme = json.loads(design.canvas_json).get("generatedTheme")
                if isinstance(theme, dict):
                    previous.append(GeneratedTheme.model_validate(theme).model_dump(by_alias=False))
            except (ValueError, TypeError):
                continue
    seen = {_fingerprint(theme) for theme in previous}
    compositions = {
        (theme.get("body_layout"), theme.get("process_style"), theme.get("documents_style"))
        for theme in previous[-8:]
        if "body_layout" in theme
    }
    used_directions = {(theme.get("art_direction"), theme.get("expression", "CALM")) for theme in previous[-8:]}
    available = {
        direction: [
            expression for expression in ("CALM", "GRAPHIC", "TYPE") if (direction, expression) not in used_directions
        ]
        for direction in ("JOURNAL", "BLUEPRINT", "STUDIO", "LEDGER", "BANNER", "GALLERY")
    }
    issue = ""
    for _ in range(2):
        result = await llm.structured(
            GeneratedThemes,
            agent="posting",
            system=(
                "너는 새로운 채용 포스터 템플릿을 설계한다. 기존 템플릿 검색이나 6종 내장 양식 선택이 아니다. "
                "서로 다른 디자인 2개를 제안한다. header, motif, 단 구성, 서체 크기, 배색, 항목 순서를 직접 설계한다. "
                "art_direction은 CUSTOM을 제외하고 선택한다. JOURNAL 잡지의 여백과 옆 제목, "
                "BLUEPRINT 짙은 헤더와 정돈된 정보 그리드, STUDIO 부드러운 배경과 흰 카드, "
                "LEDGER 큰 타이포와 가는 선의 문서형, BANNER 강한 헤더와 가로 밴드, GALLERY 모듈형이다. "
                "expression은 CALM 차분한 비례, GRAPHIC 겹친 선/기하 장식, TYPE 장식 없는 큰 타이포다. "
                "이 두 선택은 코드가 완성된 비례·여백·배색으로 조합한다. 서로 다른 art_direction을 고른다. "
                "available에 있는 방향과 그 표현만 선택한다. 빈 목록의 방향은 고르지 않는다. "
                "이름과 reason은 한국어다. 이전 제안의 art_direction/expression 조합도 반복하지 않는다. "
                "본문 body_layout과 하단 process_style/documents_style도 다르게 설계한다. "
                "EDITORIAL 편집형, PANELS 독립 패널, SIDEBAR 옆 제목, STRIPES 가로 띠다. "
                "전형은 CARDS 카드, TIMELINE 가로 연결선, STEPS 세로 단계다. "
                "서류는 TILES 타일, LIST 목록, COMPACT 표다. 본문/하단의 최종 표현은 art_direction에 맞춘다. "
                "이전 디자인과 같은 속성 조합을 반복하지 않는다. 이름만 바꾸는 것도 금지한다. "
                "order에는 intro, conditions, duties, qualifications, preferred, benefits, period, notices를 "
                "각각 한 번 넣는다. "
                "전형 절차와 제출 서류는 코드가 맨 아래 전체 폭으로 배치한다. paper는 읽기 좋은 종이색이다. "
                "별도 색 변경 요청이 없으면 현재 대표색을 color에 유지한다. reason은 디자인 선택 이유만 쓴다. "
                "실제 회사 사실, 채용 문구, URL, HTML, 로고는 생성하지 않는다. "
                "외부 서비스에서 생성했다고 주장하지 않는다.\n" + UNTRUSTED_RULE
            ),
            user=data_block(
                "design-context",
                json.dumps(
                    {
                        "color": context.design.color if context.design else context.brand_color,
                        "company": context.company.model_dump(mode="json"),
                        "job": context.posting.job_category,
                        "density": {
                            "intro": len(context.posting.intro),
                            "duties": len(context.posting.duties),
                            "qualifications": len(context.posting.qualifications),
                        },
                        "previous": previous[-8:],
                        "available": available,
                        "variation": str(uuid4()),
                        "repair": issue,
                    },
                    ensure_ascii=False,
                ),
            )
            + "\n담당자 요청: "
            + request,
        )
        result = result.model_copy(update={"themes": [compose_theme(theme) for theme in result.themes]})
        keys = [_fingerprint(theme.model_dump(by_alias=False)) for theme in result.themes]
        if (
            any(len(set(theme.order)) != 8 for theme in result.themes)
            or len(set(keys)) != 2
            or any(key in seen for key in keys)
            or any(
                (theme.body_layout, theme.process_style, theme.documents_style) in compositions
                for theme in result.themes
                if theme.art_direction == "CUSTOM"
            )
            or any(
                theme.art_direction != "CUSTOM"
                and any(
                    (theme.art_direction, theme.expression) == (old.get("art_direction"), old.get("expression", "CALM"))
                    for old in previous[-8:]
                )
                for theme in result.themes
            )
            or (
                result.themes[0].art_direction != "CUSTOM"
                and result.themes[0].art_direction == result.themes[1].art_direction
            )
            or (
                all(theme.art_direction == "CUSTOM" for theme in result.themes)
                and result.themes[0].body_layout == result.themes[1].body_layout
            )
            or (result.themes[0].process_style, result.themes[0].documents_style)
            == (result.themes[1].process_style, result.themes[1].documents_style)
            or (result.themes[0].header, result.themes[0].motif, result.themes[0].columns)
            == (result.themes[1].header, result.themes[1].motif, result.themes[1].columns)
        ):
            issue = (
                "중복된 구성을 바꾼다. 두 후보의 body_layout과 전형/서류 표현을 서로 다르게 하고 "
                "header 또는 motif 또는 columns도 다르게 한다. order는 중복 없이 채운다."
                " 최근 제안의 body_layout/process_style/documents_style 조합도 재사용하지 않는다."
            )
            continue
        current = context.design or PosterDesign(
            template="CLASSIC",
            mood="TRUST",
            color=result.themes[0].color,
            decoration=1,
            enabled=True,
            show_logo=False,
            logo_file_id=None,
        )
        return PosterProposal(
            reply="새 템플릿 2개를 생성했어요. 미리보기를 확인하고 원하는 디자인을 적용해 주세요.",
            recommendations=[
                PosterRecommendation(
                    design=current.model_copy(
                        update={"canvas_json": build_generated_canvas(theme), "color": theme.color, "enabled": True}
                    ),
                    reason=theme.reason,
                )
                for theme in result.themes
            ],
        )
    return PosterProposal(
        reply="이전 디자인과 다른 새 구성을 확인하지 못했어요. 원하는 배치나 분위기를 덧붙여 다시 요청해 주세요.",
        recommendations=[],
    )
