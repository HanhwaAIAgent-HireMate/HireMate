"""Communication Agent. 안내 메일 양식의 본문 자리(AI 작성 영역)만 쓴다. 발송하지 않고 데이터를 조회하지 않는다."""

from enum import StrEnum
from typing import Literal, NamedTuple
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
        "이번 채용에서는 함께하기 어렵게 되었다는 결과로 시작해 정중하게 알리고, 관심에 감사하며 앞날을 응원한다."
    ),
    NoticeTemplateType.FINAL_PASS: (
        "최종 합격을 축하하고 함께하게 되어 기쁘다는 마음을 전한다. 입사 일정과 준비 사항은 쓰지 않는다."
    ),
    NoticeTemplateType.FINAL_REJECT: (
        "최종 전형 결과 함께하기 어렵게 되었다는 결과로 시작해 정중하게 알리고, 긴 전형에 참여해 준 데 감사한다."
    ),
}

Skipped = Literal["SCHEDULE", "EVALUATION"]
"""따르지 않은 요청. SCHEDULE은 일정 · 장소 · 준비 사항 · 입사 안내, EVALUATION은 불합격 사유 · 점수 · 평가다."""


class _DraftExample(NamedTuple):
    stage: str
    next_stage: str | None
    content: str


class _RevisionExample(NamedTuple):
    content: str
    request: str
    revised: str
    skipped: tuple[Skipped, ...] = ()


# 첫 초안에 보여 주는 모범 본문(퓨샷). 작은 모델은 규칙보다 예시의 말투와 길이를 잘 따른다.
# 종류마다 전형 이름이 다른 예시를 두어, 예시 문장을 베끼지 않고 이번 전형 이름으로 바꿔 쓰게 한다.
# 다음 전형 안내의 일정 · 장소 · 준비 사항과 최종 합격 안내의 입사 안내는 backend가 보낼 때 본문 아래에 붙여,
# 본문은 결과와 인사만 쓴다. 양식의 인사말("{지원자명}님, …지원해 주셔서 감사합니다")에 이름과 지원 감사가 있어
# 결과부터 쓰고 "지원자님"처럼 부르지 않는다. 담당자가 검토해 고른 문장이다
_DRAFT_EXAMPLES = {
    NoticeTemplateType.NEXT_STAGE: [
        _DraftExample(
            "서류 전형",
            "1차 면접",
            "서류 전형에 합격하셨음을 알려드리며, 진심으로 축하드립니다.\n\n다음 전형은 1차 면접입니다.",
        ),
        _DraftExample(
            "코딩 테스트",
            "직무 면접",
            "코딩 테스트에 합격하셨음을 알려드립니다. 진심으로 축하드립니다.\n\n"
            "다음 전형은 직무 면접입니다. 면접 전형에서 뵙기를 기대하겠습니다.",
        ),
    ],
    NoticeTemplateType.REJECT: [
        _DraftExample(
            "서류 전형",
            None,
            "서류 전형 결과, 아쉽게도 이번 채용에서는 함께하기 어렵게 되었음을 알려드립니다.\n\n"
            "보내주신 관심에 다시 한번 감사드리며, 앞으로의 길을 응원하겠습니다.",
        ),
        _DraftExample(
            "1차 면접",
            None,
            "1차 면접 결과, 아쉽게도 불합격하셨음을 알려드립니다.\n\n"
            "바쁘신 가운데 면접에 참여해 주셔서 감사드립니다. 앞으로의 길을 응원하겠습니다.",
        ),
    ],
    NoticeTemplateType.FINAL_PASS: [
        _DraftExample(
            "최종 면접",
            None,
            "최종 면접 결과, 최종 합격하셨음을 알려드립니다.\n\n"
            "함께하게 될 날을 기대하며, 최종 합격을 진심으로 축하드립니다.",
        ),
        _DraftExample(
            "임원 면접",
            None,
            "임원 면접 결과, 최종 합격하셨음을 알려드립니다.\n\n"
            "치열한 전형 과정을 거쳐 최종 합격하신 것을 진심으로 축하드리며, 앞으로 함께하게 될 날을 기대하겠습니다.",
        ),
    ],
    NoticeTemplateType.FINAL_REJECT: [
        _DraftExample(
            "최종 면접",
            None,
            "최종 면접 결과, 아쉽게도 이번 채용에서 불합격하셨음을 알려드립니다.\n\n"
            "긴 전형 과정에 끝까지 참여해 주셔서 진심으로 감사드리며, 앞으로의 길을 응원하겠습니다.",
        ),
        _DraftExample(
            "임원 면접",
            None,
            "임원 면접 결과, 아쉽게도 이번 채용에서 함께하기 어렵게 되었음을 알려드립니다.\n\n"
            "긴 전형 과정 동안 당사에 소중한 시간을 내주신 점 깊이 감사드리며, 앞날을 진심으로 응원하겠습니다.",
        ),
    ],
}

# HR 요청으로 고칠 때 보여 주는 모범 답(퓨샷). 요청한 곳만 고치고, 쓰면 안 되는 요청(불합격 사유 등)은
# 빼고 나머지만 따르는 법을 보여 준다. 메일 종류와 상관없이 셋 다 보여 준다
_REVISION_EXAMPLES = [
    _RevisionExample(
        _DRAFT_EXAMPLES[NoticeTemplateType.NEXT_STAGE][1].content,
        "더 짧게 써 줘",
        "코딩 테스트에 합격하셨습니다. 축하드립니다.\n\n다음 전형은 직무 면접입니다.",
    ),
    _RevisionExample(
        _DRAFT_EXAMPLES[NoticeTemplateType.NEXT_STAGE][0].content,
        "더 따뜻하게 축하하는 느낌으로 써 줘",
        "서류 전형에 합격하신 것을 진심으로 축하드립니다.\n\n"
        "다음 전형은 1차 면접입니다. 남은 전형도 좋은 결과 있으시기를 바랍니다.",
    ),
    _RevisionExample(
        _DRAFT_EXAMPLES[NoticeTemplateType.REJECT][0].content,
        "떨어진 이유도 써 주고, 조금 더 따뜻하게",
        "서류 전형 결과, 아쉽게도 함께하지 못하게 되었습니다.\n\n"
        "소중한 시간을 내어 지원해 주셔서 진심으로 감사드리며, 앞날을 응원하겠습니다.",
        ("EVALUATION",),
    ),
    # 일정은 전형별 안내에서 받아 보낼 때 붙인다. 본문에 쓰면 두 번 나오고, 안내를 고치면 서로 어긋난다
    _RevisionExample(
        _DRAFT_EXAMPLES[NoticeTemplateType.NEXT_STAGE][0].content,
        "면접 날짜도 넣어 줘",
        _DRAFT_EXAMPLES[NoticeTemplateType.NEXT_STAGE][0].content,
        ("SCHEDULE",),
    ),
]

# 따르지 않은 요청을 HR에게 알리는 답. 모델이 쓴 문장은 검사하지 않았으므로 정해 둔 문장만 보낸다
_SKIPPED_REPLIES: dict[Skipped, str] = {
    "SCHEDULE": "일정, 장소, 준비 사항은 전형별 안내에 입력하면 메일 아래에 자동으로 붙어서 본문에는 넣지 않았어요.",
    "EVALUATION": "불합격 사유, 점수, 평가 내용은 메일에 쓰지 않아서 넣지 않았어요.",
}
# 최종 합격 안내는 전형별 안내 대신 보낼 때 입력하는 입사 안내가 붙는다
_FINAL_PASS_SCHEDULE_REPLY = (
    "입사일과 준비 사항은 보낼 때 입사 안내에 입력하면 메일 아래에 자동으로 붙어서 본문에는 넣지 않았어요."
)


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
    skipped: list[Skipped] = Field(
        default_factory=list,
        description="HR 요청 중 규칙 때문에 따르지 않은 것. SCHEDULE은 일정 · 장소 · 준비 사항, "
        "EVALUATION은 불합격 사유 · 점수 · 평가. 모두 따랐거나 처음 쓰면 빈 목록",
    )


class WrittenNotice(BaseModel):
    """Communication Agent가 돌려주는 결과. reply는 HR에게 보여 줄 한 문장이다."""

    reply: str
    content: str


SYSTEM = """너는 기업 인사팀이 지원자에게 보내는 채용 안내 메일의 본문을 쓰는 Communication Agent다.
메일 앞의 인사말(지원자 이름 포함)과 뒤의 맺음말, 필수 문구는 양식에 따로 있으므로 그 사이에 들어갈 본문만 쓴다.

규칙:
1. "쓸 내용"에 적힌 것만 쓴다. 주어진 정보에 없는 사실(평가, 칭찬, 날짜, 장소 등)은 지어내지 않는다.
2. 인사말(안녕하세요 등)과 맺음말(감사합니다, 드림 등)은 쓰지 않는다. 양식의 인사말에 지원 감사가 있으니
   본문을 감사 인사로 시작하지 않고 결과부터 쓴다.
3. 지원자 이름이나 {지원자명} 같은 중괄호 변수는 쓰지 않는다.
4. 불합격 사유, 점수, 평가 내용은 쓰지 않는다.
5. 2~5문장의 정중하고 자연스러운 한국어로 쓴다. 예시 본문보다 길게 쓰지 않는다. 한자나 외국어를 섞지 않는다.
6. 한국어 맞춤법의 띄어쓰기를 지킨다. 숫자와 단위는 붙여 쓴다(1차, 11월 3일).
7. 내용이 바뀌는 곳에서 문단을 나눈다. 한 문단은 1~2문장이고 문단 사이에는 빈 줄을 하나 넣는다.
8. 일정, 날짜, 시각, 장소, 준비 사항, 입사 안내는 본문에 쓰지 않는다. HR이 값을 알려 줘도 쓰지 않는다.
   메일을 보낼 때 시스템이 전형별 안내와 입사 안내를 본문 아래에 따로 붙인다.
9. HR 요청 중 규칙 때문에 따르지 않은 것이 있으면 그 부분만 빼고 나머지는 요청대로 고치고,
   skipped에 SCHEDULE(일정 · 장소 · 준비 사항) 또는 EVALUATION(불합격 사유 · 점수 · 평가)을 적는다."""


class NoticeCheckError(RuntimeError):
    """다시 써도 본문이 작성 규칙을 지키지 못했을 때. HR이 직접 쓴다."""


async def write_notice(llm: LlmClient, notice: NoticeDraftContext, request: str | None) -> WrittenNotice:
    """안내 본문을 쓴다. request가 있으면 HR의 수정 요청대로 지금 본문을 고친 전체 본문을 쓴다.

    본문이 작성 규칙을 어기면 이유를 붙여 한 번만 다시 쓰게 하고, 그래도 어기면 NoticeCheckError를 낸다.
    """
    user = _user_prompt(notice, request)
    body = await _write(llm, user)
    if found := problems(body.content, user):
        body = await _write(llm, _retry_prompt(user, body.content, found))
        if found := problems(body.content, user):
            raise NoticeCheckError("다시 써도 작성 규칙을 지키지 못했다: " + "; ".join(found))
    if request is None:
        return WrittenNotice(reply=DRAFTED_REPLY, content=body.content)
    return WrittenNotice(reply=_revised_reply(notice.template_type, body.skipped), content=body.content)


def _revised_reply(template_type: NoticeTemplateType, skipped: list[Skipped]) -> str:
    """고친 뒤의 답. 따르지 않은 요청이 있으면 그 까닭과 넣을 곳을 알려 HR이 반영된 줄 알지 않게 한다."""
    replies = []
    for kind in dict.fromkeys(skipped):
        if kind == "SCHEDULE" and template_type is NoticeTemplateType.FINAL_PASS:
            replies.append(_FINAL_PASS_SCHEDULE_REPLY)
        else:
            replies.append(_SKIPPED_REPLIES[kind])
    return " ".join(replies) or REVISED_REPLY


async def _write(llm: LlmClient, user: str) -> NoticeBody:
    body = await llm.structured(NoticeBody, agent=AGENT, system=SYSTEM, user=user)
    return body.model_copy(update={"content": tidy(body.content)})


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
        lines += ["", "예시 본문 (이 말투, 길이, 문단 나누기를 따르고 전형 이름은 위 정보로 바꿔 쓴다):"]
        for number, example in enumerate(_DRAFT_EXAMPLES[notice.template_type], start=1):
            stages = f"이번 전형: {example.stage}"
            if example.next_stage:
                stages += f" / 다음 전형: {example.next_stage}"
            lines += ["", f"[예시 {number}] {stages}", example.content]
    else:
        lines += ["", "고쳐 쓴 예시 (고치는 방식만 따른다. 예시의 전형 이름과 문장은 옮기지 않는다):"]
        for number, revision in enumerate(_REVISION_EXAMPLES, start=1):
            lines += [
                "",
                f"[예시 {number}] 지금 본문:",
                revision.content,
                f"HR 요청: {revision.request}",
                "고친 본문:",
                revision.revised,
                f"skipped: {', '.join(revision.skipped) or '없음'}",
            ]
        lines += [
            "",
            "지금 본문:",
            notice.content,
            "",
            f"HR 요청: {request}",
            "요청대로 고친 본문 전체를 쓴다. 쓸 내용과 규칙은 그대로 지킨다.",
        ]
    return "\n".join(lines)
