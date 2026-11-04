"""공고 내용은 보존하고, 기존 템플릿의 디자인 설정만 추천한다."""

import json
from typing import Literal
from uuid import UUID

from pydantic import Field

from hiremate_ai.agents.generation.posting.types import StageIcon
from hiremate_ai.contract import CompanyProfile, ContractModel, PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

Template = Literal["CLASSIC", "EDITORIAL", "BOLD", "PREMIUM", "NATURAL", "TICKET"]
Mood = Literal["TRUST", "CLEAR", "WARM", "PREMIUM", "LIVELY", "NATURAL"]


class PosterDesign(ContractModel):
    template: Template
    mood: Mood
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    decoration: int = Field(ge=0, le=2)
    enabled: bool
    show_logo: bool
    logo_file_id: UUID | None
    background_style: Literal["SOLID", "SOFT_GRADIENT"] = "SOLID"
    stage_icons: dict[str, StageIcon] = Field(default_factory=dict, max_length=10)
    readable_sections: list[int] = Field(default_factory=list, max_length=12)
    canvas_json: str | None = Field(default=None, max_length=200000)
    tagline: str | None = Field(default=None, max_length=60)


class PosterTurn(ContractModel):
    role: Literal["USER", "ASSISTANT"]
    text: str = Field(min_length=1, max_length=1000)
    design: PosterDesign | None = None
    recommendations: list["PosterRecommendation"] = Field(default_factory=list, max_length=2)
    templates: list["FreePosterTemplate"] = Field(default_factory=list, max_length=3)


class PosterContext(ContractModel):
    company: CompanyProfile
    posting: PostingContent
    design: PosterDesign | None
    brand_color: str | None
    history: list[PosterTurn] = Field(default_factory=list, max_length=12)
    stage_names: list[str] = Field(default_factory=list, max_length=10)
    section_names: list[str] = Field(default_factory=list, max_length=12)
    canva_connected: bool = False
    displayed_stage_icons: dict[str, StageIcon] = Field(default_factory=dict, max_length=10)


class PosterRecommendation(ContractModel):
    design: PosterDesign
    reason: str = Field(min_length=1, max_length=250)


class FreePosterTemplate(ContractModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=500)
    license: str = Field(min_length=1, max_length=80)
    svg: str = Field(min_length=1, max_length=100000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)


class PosterProposal(ContractModel):
    reply: str = Field(min_length=1, max_length=500)
    recommendations: list[PosterRecommendation] = Field(max_length=2)
    templates: list[FreePosterTemplate] = Field(default_factory=list, max_length=3)
    selected_template_id: str | None = Field(default=None, max_length=80)
    canva_query: str | None = Field(default=None, max_length=100)
    external_query: str | None = Field(default=None, max_length=100)
    canva_designs: list["CanvaDesign"] = Field(default_factory=list, max_length=6)


class CanvaDesign(ContractModel):
    id: str
    name: str
    edit_url: str
    thumbnail_url: str


class PosterEdits(ContractModel):
    scope: Literal["ICONS", "CONTRAST", "DESIGN", "RESTORE", "RECOMMEND", "TAGLINE"]
    reply: str = Field(min_length=1, max_length=500)
    stage_icons: dict[str, StageIcon] = Field(default_factory=dict, max_length=10)
    readable_sections: list[int] = Field(default_factory=list, max_length=12)
    recommendations: list[PosterRecommendation] = Field(default_factory=list, max_length=2)
    tagline: str | None = Field(default=None, max_length=60)


SYSTEM = (
    """너는 공고 Agent의 포스터 디자이너다. 공고 본문, 채용 조건, 회사 사실을 수정하거나 만들지 않는다.
정해진 템플릿과 디자인 속성만 추천한다. 저장, 게시, 발송은 할 수 없고 HR이 적용할 수정안만 낸다.
상단 한 줄(tagline)은 회사 소개·문화와 직무를 보고 짧고 자연스럽게 제안한다. 고정 문구를 반복하지 않는다.
실적·순위·혜택·규모·고용 보장 등 새로운 사실은 넣지 않는다. 전달된 사실을 과장하거나 없는 업종을 확정하지 않는다.
디자인 추천에는 디자인별 tagline을 함께 제안한다. 상단 문구만 수정하면 scope=TAGLINE, 최상위 tagline에 넣는다.
첫 추천은 서로 다른 템플릿 2종, 명시적 수정 요청에는 현재 디자인을 보존하며 수정안 1종을 낸다.
모호한 취향 요청도 디자인 제안으로 구체화하되, 채용 사실을 덧붙이지 않는다.
템플릿: CLASSIC 반듯한 행/정보형, EDITORIAL 잡지형/따뜻한 2열, BOLD 큰 숫자와 모듈,
PREMIUM 절제된 장식/여백/세리프 제목, NATURAL 둥근 카드와 혜택 타일, TICKET 정보 칸/절취선.
분위기: TRUST 정돈/신뢰, CLEAR 맑음/곡선/물결, WARM 따뜻함, PREMIUM 절제,
LIVELY 경쾌함, NATURAL 부드러움/자연. decoration은 장식 없음 0, 은은함 1, 강조 2.
background_style은 SOLID 단색, SOFT_GRADIENT 은은한 그라데이션이다. 배경 그라데이션 요청에 사용한다.
전형 아이콘은 기본적으로 자동 표시한다. 아이콘 수정 요청은 stage_icons에 해당 전형 이름과 아이콘만 지정한다.
stage_names에 있는 전형만 지정하고 전형 이름, 종류, 순서나 공고 본문은 변경하지 않는다.
아이콘: AUTO 자동, NONE 숨김, FILE_TEXT 문서, CLIPBOARD_CHECK 체크리스트, CODE 코드,
PRESENTATION 발표, MESSAGES 대화, USERS 사람, VIDEO 화상, BADGE_CHECK 배지, CHAIR 의자, HEALTH 검진.
예: '실무면접을 사람 아이콘으로'는 stage_icons={"실무면접":"USERS"}. 자동으로 되돌리기는 AUTO다.
아이콘만 바꾸라는 요청에는 현재 템플릿, 색상, 배경, 분위기와 장식을 그대로 유지한다.
scope는 아이콘 수정 ICONS, 글자 가독성 수정 CONTRAST, 일반 디자인 수정 DESIGN, 명시적 이전 복구 RESTORE,
새 템플릿 추천 RECOMMEND다. 요청의 목적을 선택한다. 별도 색상 요청이 없는 아이콘 변경은 반드시 ICONS다.
ICONS는 최상위 stage_icons에 수정할 아이콘을 넣는다. 예: stage_icons={"실무면접":"USERS"}.
CONTRAST는 최상위 readable_sections에 항목 번호를 넣는다. 예: readable_sections=[2].
이 두 종류는 recommendations=[]로 두어도 된다. 서버가 현재 디자인에 해당 변경만 적용해 수정안을 만든다.
아이콘 값이나 번호를 reply에만 쓰지 말고 반드시 해당 구조화 필드에 넣는다.
현재 design은 왼쪽 옵션에서 직접 수정한 최신 상태다. history보다 우선한다. 이전 복구를 명시하지 않으면
대화에 있던 이전 색상이나 템플릿을 다시 가져오지 않는다.
section_names는 화면의 1번부터 순서대로 본문 항목 제목이다. '2번 문항/항목 글자가 안 보인다'는
내용 수정이 아닌 CONTRAST 요청이다. 해당 번호를 readable_sections에 추가한다. 예: 두 번째는 [2].
이 설정은 해당 영역에 흰 배경과 진한 글자를 적용한다. 대표 색상이나 공고 문구는 변경하지 않는다.
번호가 실제 항목 범위 밖이면 recommendations=[]로 어떤 항목인지 되묻는다.
회사 소개, 문화와 공고 분량으로 추천한다. 업종을 고정관념으로 확정하지 않고 참고한다.
물/정수/청결 브랜드에는 CLEAR와 블루/하늘색, 금융에는 TRUST와 네이비/그린이 후보지만 소개를 우선한다.
로고 브랜드 색상이 있으면 기본 배색에 우선하며, HR이 색 변경을 요청하면 그 요청을 따른다.
흑백 로고이거나 색이 없으면 분위기에 맞는 색을 제안한다. 색은 #rrggbb다.
로고 ID는 지금 디자인의 값 그대로 둔다. 새 ID를 만들거나 타사 로고를 참조하지 않는다.
reason은 디자인 선택 이유만 짧게 쓴다. 없는 회사 특징, 복지, 실적을 사실로 설명하지 않는다.
canvas_json은 코드가 보존한다. 추천의 canvas_json은 null로 두고 원본 구조를 다시 쓰지 않는다.
enabled는 true로 제안한다. 요청 범위를 벗어나거나 업무 실행 요청이면 recommendations=[]로 안내한다.
"""
    + UNTRUSTED_RULE
)


async def propose_poster(llm: LlmClient, context: PosterContext, request: str) -> PosterProposal:
    proposal = await llm.structured(
        PosterEdits,
        agent="posting",
        system=SYSTEM,
        user=data_block(
            "poster-context",
            json.dumps(
                context.model_dump(
                    mode="json",
                    exclude={
                        "design": {"canvas_json"},
                        "history": {"__all__": {"design": {"canvas_json"}, "recommendations": True, "templates": True}},
                    },
                ),
                ensure_ascii=False,
            ),
        )
        + "\n담당자 디자인 요청: "
        + request,
    )
    # 모델이 로고 ID나 표시 권한을 새로 만들 수 없다.
    current = context.design
    logo = current.logo_file_id if current else None
    candidates = proposal.recommendations
    if current and proposal.scope == "TAGLINE" and proposal.tagline:
        candidates = [
            PosterRecommendation(
                design=current.model_copy(update={"tagline": proposal.tagline}),
                reason="회사 소개와 현재 직무를 바탕으로 상단 한 줄만 변경합니다.",
            )
        ]
    elif current and proposal.scope == "ICONS" and proposal.stage_icons:
        candidates = [
            PosterRecommendation(
                design=current.model_copy(update={"stage_icons": proposal.stage_icons}),
                reason="요청한 전형 아이콘만 변경하고 현재 배색을 유지합니다.",
            )
        ]
    elif current and proposal.scope == "CONTRAST" and proposal.readable_sections:
        candidates = [
            PosterRecommendation(
                design=current.model_copy(update={"readable_sections": proposal.readable_sections}),
                reason="지정한 항목에 흰 배경과 진한 글자를 적용해 가독성을 높입니다.",
            )
        ]
    if any(set(item.design.stage_icons) - set(context.stage_names) for item in candidates):
        return PosterProposal(reply="현재 공고에 있는 전형 이름을 지정해 주세요.", recommendations=[])
    recommendations = []
    for item in candidates if proposal.scope == "RECOMMEND" else candidates[:1]:
        proposed = item.design
        if current and proposal.scope == "ICONS":
            proposed = current.model_copy(update={"stage_icons": item.design.stage_icons})
        elif current and proposal.scope == "CONTRAST":
            proposed = current.model_copy(update={"readable_sections": item.design.readable_sections})
        if any(number < 1 or number > len(context.section_names) for number in proposed.readable_sections):
            return PosterProposal(reply="글자가 잘 보이지 않는 항목의 번호나 제목을 알려 주세요.", recommendations=[])
        design = proposed.model_copy(
            update={
                "logo_file_id": logo,
                "show_logo": proposed.show_logo and logo is not None,
                "stage_icons": {
                    name: icon
                    for name, icon in {
                        **(current.stage_icons if current else {}),
                        **proposed.stage_icons,
                    }.items()
                    if name in context.stage_names
                },
                "readable_sections": sorted(
                    set((current.readable_sections if current else []) + proposed.readable_sections)
                ),
                "tagline": proposed.tagline if proposed.tagline is not None else current.tagline if current else None,
                "canvas_json": current.canvas_json if current and proposal.scope != "RECOMMEND" else None,
            }
        )
        recommendations.append(item.model_copy(update={"design": design}))
    return PosterProposal(reply=proposal.reply, recommendations=recommendations)
