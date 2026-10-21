"""Communication Agent. 안내 메일 양식의 본문 자리(AI 작성 영역)만 쓴다. 발송하지 않고 데이터를 조회하지 않는다."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.agents.generation.communication.checks import problems, tidy
from hiremate_ai.contract import ContractModel
from hiremate_ai.llm.client import LlmClient

AGENT = "communication"
"""호출 로그와 backend 연동 경로(/agents/communication/...)에 쓰는 Agent 키."""

DRAFTED_REPLY = "초안을 만들었어요."
REVISED_REPLY = "요청하신 대로 고쳤어요."


class NoticeTemplateType(StrEnum):
    """안내 메일 양식 유형 (company.NoticeTemplateType)."""

    NEXT_STAGE = "NEXT_STAGE"
    REJECT = "REJECT"
    FINAL_PASS = "FINAL_PASS"
    FINAL_REJECT = "FINAL_REJECT"

    @property
    def label(self) -> str:
        return _TEMPLATE_LABELS[self]

    @property
    def guide(self) -> str:
        """본문에 쓸 내용."""
        return _TEMPLATE_GUIDES[self]


_TEMPLATE_LABELS = {
    NoticeTemplateType.NEXT_STAGE: "다음 전형 안내 (합격)",
    NoticeTemplateType.REJECT: "불합격 안내",
    NoticeTemplateType.FINAL_PASS: "최종 합격 안내",
    NoticeTemplateType.FINAL_REJECT: "최종 불합격 안내",
}

_TEMPLATE_GUIDES = {
    NoticeTemplateType.NEXT_STAGE: (
        "이번 전형에 합격했다는 결과와 다음 전형 이름만 알린다. 다음 전형의 일정, 장소, 준비 사항은 쓰지 않는다."
    ),
    NoticeTemplateType.REJECT: (
        "이번 채용에서는 함께하기 어렵게 되었다는 결과를 정중하게 알리고, 지원에 감사하며 앞날을 응원한다."
    ),
    NoticeTemplateType.FINAL_PASS: ("최종 합격을 축하하고, 입사 일정과 준비 사항은 담당자가 별도로 안내드린다고 쓴다."),
    NoticeTemplateType.FINAL_REJECT: (
        "최종 전형 결과 함께하기 어렵게 되었다는 결과를 정중하게 알리고, 긴 전형에 참여해 준 데 감사한다."
    ),
}

# 첫 초안에 보여 주는 모범 본문. 작은 모델은 규칙보다 예시의 말투와 길이를 잘 따른다.
# {stage}는 이번 전형, {next_stage}는 다음 전형 이름으로 바꿔 넣는다.
# 다음 전형 안내의 일정 · 장소 · 준비 사항은 backend가 보낼 때 본문 아래에 붙여, 본문은 결과와 다음 전형만 쓴다
_TEMPLATE_EXAMPLES = {
    NoticeTemplateType.NEXT_STAGE: (
        "{stage}에 합격하셨음을 알려드리며, 진심으로 축하드립니다.\n\n다음 전형은 {next_stage}입니다."
    ),
    NoticeTemplateType.REJECT: (
        "먼저 이번 채용에 지원해 주셔서 진심으로 감사드립니다.\n\n"
        "아쉽게도 {stage} 결과, 이번 채용에서는 함께하기 어렵게 되었음을 알려드립니다.\n\n"
        "보내주신 관심에 다시 한번 감사드리며, 앞으로의 길을 응원하겠습니다."
    ),
    NoticeTemplateType.FINAL_PASS: (
        "{stage} 결과, 최종 합격하셨음을 알려드립니다. 진심으로 축하드립니다.\n\n"
        "입사 일정과 준비 사항은 담당자가 별도로 안내드릴 예정입니다.\n\n"
        "함께하게 되어 기쁘게 생각합니다."
    ),
    NoticeTemplateType.FINAL_REJECT: (
        "긴 전형 과정에 끝까지 참여해 주셔서 진심으로 감사드립니다.\n\n"
        "아쉽게도 {stage} 결과, 이번 채용에서는 함께하기 어렵게 되었음을 알려드립니다.\n\n"
        "전형 동안 보여주신 관심과 시간에 다시 한번 감사드리며, 앞으로의 길을 응원하겠습니다."
    ),
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


class NoticeBody(BaseModel):
    """모델에게서 받는 답."""

    content: str = Field(description="메일 본문. 인사말과 맺음말 없이 2~5문장, 문단 사이에 빈 줄")


class WrittenNotice(BaseModel):
    """Communication Agent가 돌려주는 결과. reply는 HR에게 보여 줄 한 문장이다."""

    reply: str
    content: str


SYSTEM = """너는 기업 인사팀이 지원자에게 보내는 채용 안내 메일의 본문을 쓰는 Communication Agent다.
메일 앞의 인사말(지원자 이름 포함)과 뒤의 맺음말, 필수 문구는 양식에 따로 있으므로 그 사이에 들어갈 본문만 쓴다.

규칙:
1. "쓸 내용"에 적힌 것만 쓴다. 주어진 정보에 없는 사실(평가, 칭찬, 날짜, 장소 등)은 지어내지 않는다.
2. 인사말(안녕하세요 등)과 맺음말(감사합니다, 드림 등)은 쓰지 않는다.
3. 지원자 이름이나 {지원자명} 같은 중괄호 변수는 쓰지 않는다.
4. 불합격 사유, 점수, 평가 내용은 쓰지 않는다.
5. 2~5문장의 정중하고 자연스러운 한국어로 쓴다. 예시 본문보다 길게 쓰지 않는다. 한자나 외국어를 섞지 않는다.
6. 한국어 맞춤법의 띄어쓰기를 지킨다. 숫자와 단위는 붙여 쓴다(1차, 11월 3일).
7. 내용이 바뀌는 곳에서 문단을 나눈다. 한 문단은 1~2문장이고 문단 사이에는 빈 줄을 하나 넣는다."""


class NoticeCheckError(RuntimeError):
    """다시 써도 본문이 작성 규칙을 지키지 못했을 때. HR이 직접 쓴다."""


async def write_notice(llm: LlmClient, notice: NoticeDraftContext, request: str | None) -> WrittenNotice:
    """안내 본문을 쓴다. request가 있으면 HR의 수정 요청대로 지금 본문을 고친 전체 본문을 쓴다.

    본문이 작성 규칙을 어기면 이유를 붙여 한 번만 다시 쓰게 하고, 그래도 어기면 NoticeCheckError를 낸다.
    """
    user = _user_prompt(notice, request)
    content = await _write(llm, user)
    if found := problems(content, user):
        content = await _write(llm, _retry_prompt(user, content, found))
        if found := problems(content, user):
            raise NoticeCheckError("다시 써도 작성 규칙을 지키지 못했다: " + "; ".join(found))
    return WrittenNotice(reply=DRAFTED_REPLY if request is None else REVISED_REPLY, content=content)


async def _write(llm: LlmClient, user: str) -> str:
    body = await llm.structured(NoticeBody, agent=AGENT, system=SYSTEM, user=user)
    return tidy(body.content)


def _retry_prompt(user: str, content: str, found: list[str]) -> str:
    reasons = "\n".join(f"- {reason}" for reason in found)
    return f"{user}\n\n앞서 쓴 본문:\n{content}\n\n앞서 쓴 본문의 문제:\n{reasons}\n문제를 고쳐 본문 전체를 다시 쓴다."


def _user_prompt(notice: NoticeDraftContext, request: str | None) -> str:
    lines = [
        f"메일 종류: {notice.template_type.label}",
        f"회사명: {notice.company_name}",
        f"공고명: {notice.recruitment_title}",
        f"이번 전형: {notice.stage_name}",
    ]
    # 다음 전형은 합격자에게만 알린다. 불합격 메일에 넘기면 모델이 다음 전형을 안내해 버린다
    if notice.template_type is NoticeTemplateType.NEXT_STAGE:
        lines.append(f"다음 전형: {notice.next_stage_name or '(없음)'}")
    lines += [f"쓸 내용: {notice.template_type.guide}", f"양식의 작성 안내: {notice.ai_guide}"]
    if request is None:
        example = _TEMPLATE_EXAMPLES[notice.template_type].format(
            stage=notice.stage_name, next_stage=notice.next_stage_name or "다음 전형"
        )
        lines += ["", "예시 본문 (이 말투, 길이, 문단 나누기를 따른다):", example]
    else:
        lines += [
            "",
            "지금 본문:",
            notice.content,
            "",
            f"HR 요청: {request}",
            "요청대로 고친 본문 전체를 쓴다. 쓸 내용과 규칙은 그대로 지킨다.",
        ]
    return "\n".join(lines)
