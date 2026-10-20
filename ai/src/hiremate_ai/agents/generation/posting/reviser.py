"""Posting Agent. HR의 수정 요청을 공고 수정안으로 바꾼다. 수정안만 만들고 적용 · 게시하지 않는다 (FR-02, FR-03).

모델은 바꿀 칸의 새 내용만 쓰고, 지금 공고에 합치고 바뀐 칸을 고르는 일은 코드가 한다.
모델이 바뀌었다고 말하는 칸을 믿지 않고 원래 공고와 비교해 정한다.
"""

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from hiremate_ai.agents.generation.posting.types import PostingDraftContext, PostingSuggestion, RevisionResult
from hiremate_ai.contract import PostingContent
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

NOTHING_CHANGED_REPLY = "요청에서 바꿀 부분을 찾지 못했어요. 어느 칸을 어떻게 바꿀지 알려 주세요."


class ContentEdit(BaseModel):
    """모델에게서 받는 답. 바꿀 칸만 채우고 나머지는 비워 둔다. 목록 칸은 바꾼 뒤의 목록 전체다."""

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


SYSTEM = """너는 기업 인사팀의 채용 공고 편집을 돕는 Posting Agent다.
HR의 요청을 읽고, 공고 본문에서 바꿀 칸의 새 내용만 쓴다. 바꾸지 않을 칸은 비워 둔다.

규칙:
1. 요청한 칸만 바꾼다. 요청과 관계없는 칸은 비워 둔다.
2. 목록 칸(주요 업무, 자격 요건, 우대 사항, 복지)을 바꿀 때는 바꾼 뒤의 목록 전체를 쓴다. 그대로 둘 항목도 함께 쓴다.
3. 회사가 알려 주지 않은 사실(연봉, 복지, 근무 조건, 회사 정보)은 지어내지 않는다.
4. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 자격 요건이나 우대 사항에 넣지 않는다.
5. 회사의 공고 작성 스타일이 있으면 따른다. 한국어로 쓰고, 목록 항목은 한 줄로 짧게 쓴다."""


async def revise_posting(
    llm: LlmClient, posting: PostingDraftContext, writing_style: str, request: str
) -> RevisionResult:
    """HR의 요청대로 공고 본문 수정안을 만든다. 바뀐 칸이 없으면 수정안 없이 되묻는다."""
    edit = await llm.structured(
        ContentEdit, agent=AGENT, system=SYSTEM, user=_user_prompt(posting, writing_style, request)
    )
    content, changed = _apply(posting.content, edit)
    if not changed:
        return RevisionResult(reply=NOTHING_CHANGED_REPLY, suggestion=None)
    labels = ", ".join(FIELD_LABELS[name] for name in changed)
    return RevisionResult(
        reply=f"{labels} 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요.",
        suggestion=PostingSuggestion(
            content=content,
            stages=None,
            required_extras=None,
            changed_fields=[to_camel(name) for name in changed],
        ),
    )


def _apply(content: PostingContent, edit: ContentEdit) -> tuple[PostingContent, list[str]]:
    """모델이 채운 칸을 지금 공고에 합친다. 원래와 같은 칸은 바뀐 칸에 넣지 않는다."""
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


def _user_prompt(posting: PostingDraftContext, writing_style: str, request: str) -> str:
    lines = ["지금 공고:"]
    for name, label in FIELD_LABELS.items():
        value = getattr(posting.content, name)
        if isinstance(value, list):
            lines.append(f"{label}:")
            lines += [f"- {item}" for item in value] or ["(비어 있음)"]
        else:
            lines.append(f"{label}: {value or '(비어 있음)'}")
    lines += ["", f"공고 작성 스타일: {writing_style.strip() or '(없음)'}", "", f"HR 요청: {request}"]
    return "\n".join(lines)
