"""Communication Agent. 안내 메일 양식의 본문 자리(AI 작성 영역)만 쓴다. 발송하지 않고 데이터를 조회하지 않는다."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmClient

AGENT = "communication"
"""호출 로그와 backend 연동 경로(/agents/communication/...)에 쓰는 Agent 키."""


class NoticeTemplateType(StrEnum):
    """안내 메일 양식 유형 (company.NoticeTemplateType)."""

    NEXT_STAGE = "NEXT_STAGE"
    REJECT = "REJECT"
    FINAL_PASS = "FINAL_PASS"
    FINAL_REJECT = "FINAL_REJECT"

    @property
    def label(self) -> str:
        return _TEMPLATE_LABELS[self]


_TEMPLATE_LABELS = {
    NoticeTemplateType.NEXT_STAGE: "다음 전형 안내 (합격)",
    NoticeTemplateType.REJECT: "불합격 안내",
    NoticeTemplateType.FINAL_PASS: "최종 합격 안내",
    NoticeTemplateType.FINAL_REJECT: "최종 불합격 안내",
}


class NoticeDraftContext(ContractModel):
    """backend가 채워 보내는 안내 초안 정보 (notice.NoticeDraftContext)."""

    notice_id: UUID
    template_type: NoticeTemplateType
    company_name: str
    recruitment_title: str
    stage_name: str
    next_stage_name: str | None
    ai_guide: str
    content: str


class WrittenNotice(BaseModel):
    """모델에게서 받는 답."""

    reply: str = Field(description="HR에게 보여 줄 한 문장. 무엇을 썼거나 고쳤는지 알린다")
    content: str = Field(description="메일 본문(AI 작성 영역). 인사말과 맺음말은 넣지 않는다")


SYSTEM = """너는 기업 인사팀이 지원자에게 보내는 채용 안내 메일의 본문을 쓰는 Communication Agent다.
인사말, 맺음말, 필수 문구는 양식에 따로 있으므로 본문만 쓴다.

규칙:
1. 주어진 정보만 사용한다. 일정이나 장소가 없으면 지어내지 말고 "별도로 안내드리겠습니다"라고 쓴다.
2. 인사말(안녕하세요 등)과 맺음말(감사합니다, 드림 등)은 쓰지 않는다.
3. 3~5문장의 정중한 한국어로 쓴다. 한자나 외국어를 섞지 않는다.
4. 지원자를 부를 때는 {지원자명}을 그대로 쓴다. 다른 중괄호 변수는 만들지 않는다.
5. 불합격 사유, 점수, 평가 내용은 쓰지 않는다.
6. reply에는 HR에게 보여 줄 한 문장을 쓴다."""


async def write_notice(llm: LlmClient, notice: NoticeDraftContext, request: str | None) -> WrittenNotice:
    """안내 본문을 쓴다. request가 있으면 HR의 수정 요청대로 지금 본문을 고친 전체 본문을 쓴다."""
    return await llm.structured(WrittenNotice, agent=AGENT, system=SYSTEM, user=_user_prompt(notice, request))


def _user_prompt(notice: NoticeDraftContext, request: str | None) -> str:
    lines = [
        f"메일 종류: {notice.template_type.label}",
        f"회사명: {notice.company_name}",
        f"공고명: {notice.recruitment_title}",
        f"이번 전형: {notice.stage_name}",
        f"다음 전형: {notice.next_stage_name or '(없음)'}",
        f"작성 안내: {notice.ai_guide}",
    ]
    if request is not None:
        lines += ["", "지금 본문:", notice.content, "", f"HR 요청: {request}", "요청대로 고친 본문 전체를 쓴다."]
    return "\n".join(lines)
