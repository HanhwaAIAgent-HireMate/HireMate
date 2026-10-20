"""Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 수정안만 만들고 적용 · 게시하지 않는다 (FR-02~04).

모델은 바꿀 칸의 새 내용만 쓰고, 지금 공고에 합치고 바뀐 칸을 고르는 일은 코드가 한다.
모델이 바뀌었다고 말하는 칸을 믿지 않고 원래 공고와 비교해 정한다.
"""

from dataclasses import dataclass, replace
from typing import Literal

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from hiremate_ai.agents.generation.posting.checks import blocked_terms, problems
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingSuggestion,
    RecruitmentStatus,
    RevisionResult,
    StageDraft,
)
from hiremate_ai.contract import DocumentType, PostingContent, StageType
from hiremate_ai.llm.client import LlmClient

AGENT = "posting"
"""호출 로그와 backend 연동 경로(/agents/posting/...)에 쓰는 Agent 키."""

FIELD_LABELS = {
    "title": "채용명",
    "job_category": "직무",
    "employment_type": "고용 형태",
    "career": "경력",
    "location": "근무지",
    "intro": "회사 소개",
    "duties": "주요 업무",
    "qualifications": "자격 요건",
    "preferred": "우대 사항",
    "benefits": "복지",
}
"""공고 본문 칸 → 화면 이름. 순서는 공고 편집 화면 순서다."""

STAGE_TYPE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}
STATUS_LABELS = {
    RecruitmentStatus.DRAFT: "작성 중",
    RecruitmentStatus.PUBLISHED: "공고 게시 중",
    RecruitmentStatus.IN_PROGRESS: "전형 진행 중",
    RecruitmentStatus.CLOSED: "종료",
}

NOTHING_CHANGED_REPLY = "요청에서 바꿀 부분을 찾지 못했어요. 어느 칸을 어떻게 바꿀지 알려 주세요."
LOCKED_REPLY = "공고를 게시한 뒤에는 전형 절차와 필수 제출 서류를 바꿀 수 없어요."
BLOCKED_REPLY = (
    "나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 자격 요건이나 우대 사항에 넣을 수 없어요. "
    "직무와 관련된 경험이나 역량으로 다시 말씀해 주세요."
)
CHECK_FAILED_REPLY = "요청대로 고친 수정안이 공고 작성 규칙을 지키지 못했어요. 요청을 조금 바꿔 다시 말씀해 주세요."

ATTEMPTS = 2
"""처음 한 번과, 검사에 걸렸을 때 이유를 붙여 다시 쓰는 한 번."""


class ContentEdit(BaseModel):
    """공고 본문에서 바꿀 칸. 바꾸지 않을 칸은 비워 둔다. 목록 칸은 바꾼 뒤의 목록 전체다."""

    title: str | None = Field(default=None, description="채용명")
    job_category: str | None = Field(default=None, description="직무")
    employment_type: str | None = Field(default=None, description="고용 형태 (예: 정규직, 계약직, 인턴)")
    career: str | None = Field(default=None, description="경력 (예: 신입, 경력 3년 이상, 경력 무관)")
    location: str | None = Field(default=None, description="근무지")
    intro: str | None = Field(default=None, description="회사 소개")
    duties: list[str] | None = Field(default=None, description="주요 업무 목록 전체")
    qualifications: list[str] | None = Field(default=None, description="자격 요건 목록 전체")
    preferred: list[str] | None = Field(default=None, description="우대 사항 목록 전체")
    benefits: list[str] | None = Field(default=None, description="복지 목록 전체")


class StageEdit(BaseModel):
    """전형 하나. 종류를 알 수 없으면 type을 비우고 question으로 되묻는다."""

    name: str = Field(description="전형 이름. HR이 말한 이름 그대로")
    type: StageType | None = Field(description="DOCUMENT(서류), ASSESSMENT(평가), INTERVIEW(면접). 알 수 없으면 null")


class PostingEdit(ContentEdit):
    """모델에게서 받는 답."""

    stages: list[StageEdit] | None = Field(
        default=None, description="전형 절차를 바꿀 때만. 바꾼 뒤의 전형 전체를 순서대로"
    )
    required_extras: list[Literal["PORTFOLIO", "CERTIFICATE"]] | None = Field(
        default=None, description="필수 제출 서류를 바꿀 때만. 이력서 · 자기소개서 밖에 필수로 받을 서류 전체"
    )
    question: str | None = Field(
        default=None, description="요청이 애매하거나 전형 종류를 알 수 없을 때 HR에게 되묻는 한 문장"
    )


SYSTEM = """너는 기업 인사팀의 채용 공고 편집을 돕는 Posting Agent다.
HR의 요청을 읽고, 공고에서 바꿀 칸의 새 내용만 쓴다. 바꾸지 않을 칸은 비워 둔다.

규칙:
1. 요청한 칸만 바꾼다. 요청과 관계없는 칸은 비워 둔다.
2. 목록 칸(주요 업무, 자격 요건, 우대 사항, 복지)을 바꿀 때는 바꾼 뒤의 목록 전체를 쓴다. 그대로 둘 항목도 함께 쓴다.
3. 회사가 알려 주지 않은 사실(연봉, 복지, 근무 조건, 회사 정보)은 지어내지 않는다.
4. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 자격 요건이나 우대 사항에 넣지 않는다.
5. 회사의 공고 작성 스타일이 있으면 따른다. 한국어로 쓰고, 목록 항목은 한 줄로 짧게 쓴다.

전형 절차:
- 전형 절차를 바꾸라는 요청일 때만 stages에 바꾼 뒤의 전형 전체를 순서대로 쓴다. 전형 이름은 HR이 말한 그대로 둔다.
- 종류는 셋이다. DOCUMENT(서류): 지원서와 제출 서류 검토. ASSESSMENT(평가): 코딩테스트, 인적성, 직무역량 평가,
  과제처럼 시험이나 과제로 평가하는 전형. INTERVIEW(면접): 실무면접, 임원면접처럼 사람이 만나 묻는 전형.
- 이름만으로 종류를 알 수 없으면(예: PT, 발표, 워크숍) 추측하지 않고 type을 비우고 question으로 되묻는다.

필수 제출 서류:
- 이력서와 자기소개서는 항상 받는다. 더 받을 수 있는 필수 서류는 PORTFOLIO(포트폴리오), CERTIFICATE(자격증)뿐이다.
- 필수 서류를 바꾸라는 요청일 때만 required_extras에 바꾼 뒤의 추가 필수 서류 전체를 쓴다.

요청이 무엇을 바꾸라는지 알 수 없으면 아무 칸도 바꾸지 않고 question으로 되묻는다."""


@dataclass(frozen=True)
class _Draft:
    """모델 답을 지금 공고에 합친 결과. changed는 바뀐 본문 칸, stages · required_extras는 바뀌었을 때만 있다."""

    content: PostingContent
    changed: list[str]
    stages: list[StageDraft] | None
    required_extras: list[DocumentType] | None
    unknown_stages: list[str]


async def revise_posting(
    llm: LlmClient, posting: PostingDraftContext, writing_style: str, request: str
) -> RevisionResult:
    """HR의 요청대로 공고 수정안을 만든다. 되묻거나 처리할 수 없으면 수정안 없이 답만 한다.

    수정안이 검사에 걸리면 이유를 붙여 한 번 더 쓰게 한다. 차별 조건은 다시 쓰게 하지 않고 바로 거절한다.
    """
    user = _user_prompt(posting, writing_style, request)
    prompt = user
    for _ in range(ATTEMPTS):
        edit = await llm.structured(PostingEdit, agent=AGENT, system=SYSTEM, user=prompt)
        draft = _draft(posting, edit)
        if draft.unknown_stages:
            return RevisionResult(reply=edit.question or _stage_question(draft.unknown_stages), suggestion=None)
        locked = posting.status is not RecruitmentStatus.DRAFT and (
            draft.stages is not None or draft.required_extras is not None
        )
        if locked:
            draft = replace(draft, stages=None, required_extras=None)
        if blocked_terms(draft.content, draft.changed):
            return RevisionResult(reply=BLOCKED_REPLY, suggestion=None)
        found = problems(draft.content, draft.changed, draft.stages, FIELD_LABELS, source=user)
        if not found:
            return _result(draft, notes=[LOCKED_REPLY if locked else None, edit.question])
        prompt = _retry_prompt(user, found)
    return RevisionResult(reply=CHECK_FAILED_REPLY, suggestion=None)


def _draft(posting: PostingDraftContext, edit: PostingEdit) -> _Draft:
    content, changed = _apply(posting.content, edit)
    stages: list[StageDraft] | None = None
    unknown: list[str] = []
    if edit.stages is not None:
        unknown = [stage.name.strip() for stage in edit.stages if stage.type is None]
        proposed = [StageDraft(name=stage.name.strip(), type=stage.type) for stage in edit.stages if stage.type]
        if not unknown and proposed != posting.stages:
            stages = proposed
    extras: list[DocumentType] | None = None
    if edit.required_extras is not None:
        proposed_extras = sorted({DocumentType(extra) for extra in edit.required_extras})
        if set(proposed_extras) != set(posting.required_extras):
            extras = proposed_extras
    return _Draft(content=content, changed=changed, stages=stages, required_extras=extras, unknown_stages=unknown)


def _apply(content: PostingContent, edit: ContentEdit) -> tuple[PostingContent, list[str]]:
    """모델이 채운 본문 칸을 지금 공고에 합친다. 원래와 같은 칸은 바뀐 칸에 넣지 않는다."""
    updates: dict[str, str | list[str]] = {}
    for name in FIELD_LABELS:
        value = getattr(edit, name)
        if value is None:
            continue
        cleaned = _clean(value)
        if cleaned != getattr(content, name):
            updates[name] = cleaned
    changed = [name for name in FIELD_LABELS if name in updates]
    return content.model_copy(update=updates), changed


def _clean(value: str | list[str]) -> str | list[str]:
    if isinstance(value, str):
        return value.strip()
    return [item.strip() for item in value if item.strip()]


def _result(draft: _Draft, notes: list[str | None]) -> RevisionResult:
    labels = [FIELD_LABELS[name] for name in draft.changed]
    fields = [to_camel(name) for name in draft.changed]
    if draft.stages is not None:
        labels.append("전형 절차")
        fields.append("stages")
    if draft.required_extras is not None:
        labels.append("필수 제출 서류")
        fields.append("requiredDocuments")
    extra = [note.strip() for note in notes if note and note.strip()]
    if not labels:
        return RevisionResult(reply=" ".join(extra) or NOTHING_CHANGED_REPLY, suggestion=None)
    reply = " ".join([f"{', '.join(labels)} 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요.", *extra])
    return RevisionResult(
        reply=reply,
        suggestion=PostingSuggestion(
            content=draft.content, stages=draft.stages, required_extras=draft.required_extras, changed_fields=fields
        ),
    )


def _stage_question(names: list[str]) -> str:
    quoted = ", ".join(f"'{name}'" for name in names)
    return f"{quoted} 전형은 서류, 평가, 면접 중 어떤 종류인가요?"


def _retry_prompt(user: str, found: list[str]) -> str:
    reasons = "\n".join(f"- {reason}" for reason in found)
    return f"{user}\n\n앞서 쓴 수정안의 문제:\n{reasons}\n문제를 고쳐 다시 쓴다."


def _user_prompt(posting: PostingDraftContext, writing_style: str, request: str) -> str:
    lines = ["지금 공고:"]
    for name, label in FIELD_LABELS.items():
        value = getattr(posting.content, name)
        if isinstance(value, list):
            lines.append(f"{label}:")
            lines += [f"- {item}" for item in value] or ["(비어 있음)"]
        else:
            lines.append(f"{label}: {value or '(비어 있음)'}")
    lines.append("전형 절차:")
    lines += [
        f"{number}. {stage.name} ({STAGE_TYPE_LABELS[stage.type]})" for number, stage in enumerate(posting.stages, 1)
    ] or ["(비어 있음)"]
    extras = [extra.label for extra in sorted(posting.required_extras)]
    lines.append(f"필수 제출 서류: {', '.join(['이력서', '자기소개서', *extras])}")
    status = STATUS_LABELS[posting.status]
    if posting.status is not RecruitmentStatus.DRAFT:
        status += " (게시한 뒤라 전형 절차와 필수 제출 서류는 바꿀 수 없다)"
    lines += [
        f"공고 상태: {status}",
        "",
        f"공고 작성 스타일: {writing_style.strip() or '(없음)'}",
        "",
        f"HR 요청: {request}",
    ]
    return "\n".join(lines)
