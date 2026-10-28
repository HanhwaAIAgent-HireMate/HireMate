"""공고 내용은 보존하고, 기존 템플릿의 디자인 설정만 추천한다."""

from typing import Literal
from uuid import UUID

from pydantic import Field

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


class PosterTurn(ContractModel):
    role: Literal["USER", "ASSISTANT"]
    text: str = Field(min_length=1, max_length=1000)
    design: PosterDesign | None = None
    recommendations: list["PosterRecommendation"] = Field(default_factory=list, max_length=2)


class PosterContext(ContractModel):
    company: CompanyProfile
    posting: PostingContent
    design: PosterDesign | None
    brand_color: str | None
    history: list[PosterTurn] = Field(default_factory=list, max_length=12)


class PosterRecommendation(ContractModel):
    design: PosterDesign
    reason: str = Field(min_length=1, max_length=250)


class PosterProposal(ContractModel):
    reply: str = Field(min_length=1, max_length=500)
    recommendations: list[PosterRecommendation] = Field(max_length=2)


SYSTEM = (
    """너는 공고 Agent의 포스터 디자이너다. 공고 본문, 채용 조건, 회사 사실을 수정하거나 만들지 않는다.
정해진 템플릿과 디자인 속성만 추천한다. 저장, 게시, 발송은 할 수 없고 HR이 적용할 수정안만 낸다.
첫 추천은 서로 다른 템플릿 2종, 명시적 수정 요청에는 현재 디자인을 보존하며 수정안 1종을 낸다.
모호한 취향 요청도 디자인 제안으로 구체화하되, 채용 사실을 덧붙이지 않는다.
템플릿: CLASSIC 반듯한 행/정보형, EDITORIAL 잡지형/따뜻한 2열, BOLD 큰 숫자와 모듈,
PREMIUM 절제된 장식/여백/세리프 제목, NATURAL 둥근 카드와 혜택 타일, TICKET 정보 칸/절취선.
분위기: TRUST 정돈/신뢰, CLEAR 맑음/곡선/물결, WARM 따뜻함, PREMIUM 절제,
LIVELY 경쾌함, NATURAL 부드러움/자연. decoration은 장식 없음 0, 은은함 1, 강조 2.
background_style은 SOLID 단색, SOFT_GRADIENT 은은한 그라데이션이다. 배경 그라데이션 요청에 사용한다.
회사 소개, 문화와 공고 분량으로 추천한다. 업종을 고정관념으로 확정하지 않고 참고한다.
물/정수/청결 브랜드에는 CLEAR와 블루/하늘색, 금융에는 TRUST와 네이비/그린이 후보지만 소개를 우선한다.
로고 브랜드 색상이 있으면 기본 배색에 우선하며, HR이 색 변경을 요청하면 그 요청을 따른다.
흑백 로고이거나 색이 없으면 분위기에 맞는 색을 제안한다. 색은 #rrggbb다.
로고 ID는 지금 디자인의 값 그대로 둔다. 새 ID를 만들거나 타사 로고를 참조하지 않는다.
reason은 디자인 선택 이유만 짧게 쓴다. 없는 회사 특징, 복지, 실적을 사실로 설명하지 않는다.
enabled는 true로 제안한다. 요청 범위를 벗어나거나 업무 실행 요청이면 recommendations=[]로 안내한다.
"""
    + UNTRUSTED_RULE
)


async def propose_poster(llm: LlmClient, context: PosterContext, request: str) -> PosterProposal:
    proposal = await llm.structured(
        PosterProposal,
        agent="posting",
        system=SYSTEM,
        user=data_block("poster-context", context.model_dump_json()) + "\n담당자 디자인 요청: " + request,
    )
    # 모델이 로고 ID나 표시 권한을 새로 만들 수 없다.
    current = context.design
    logo = current.logo_file_id if current else None
    return proposal.model_copy(
        update={
            "recommendations": [
                item.model_copy(
                    update={
                        "design": item.design.model_copy(
                            update={
                                "logo_file_id": logo,
                                "show_logo": item.design.show_logo and logo is not None,
                            }
                        )
                    }
                )
                for item in proposal.recommendations
            ]
        }
    )
