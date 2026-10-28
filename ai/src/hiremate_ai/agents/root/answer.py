"""화면에 보일 답의 문장 정리와 공통 값. 지원자 번호(C2)를 이름으로 바꾸고 항목 문장을 줄인다."""

import re

from pydantic import BaseModel, Field

from hiremate_ai.agents.root.toolkit import resolve_ref
from hiremate_ai.agents.root.types import ChatContext

TEXT_LENGTH = 120
BULK_LIMIT = 20
FOCUS_WITH_REQUEST = "{focus} (담당자 요청: {request})"
INTERVIEW_AGENT = "Interview Agent"

_REF = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)(?![0-9])")
_REF_WITH_NAME = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)\s+([^\s,.!?]+)")
_GLUED_REF = re.compile(r"(?<![A-Za-z0-9])[a-z]+C(\d+)(?![0-9])")
_THINK = re.compile(r"<think>.*?</think>|</?think>", re.DOTALL)


class AnswerEvidence(BaseModel):
    """전문 Agent가 돌려준 근거 문장과 출처."""

    sentence: str = Field(description="원문 문장")
    source: str = Field(description="근거 출처")


def readable(text: str, context: ChatContext) -> str:
    """담당자가 읽을 글의 지원자 번호(C2)를 이름으로 바꾼다. "C2 김하늘"처럼 이름이 뒤따르면 번호만 뺀다.

    모델이 흘린 생각 태그는 지운다.
    """

    def with_name(match: re.Match[str]) -> str:
        row = resolve_ref(context, match.group(1))
        return match.group(2) if row is not None and match.group(2).startswith(row.name) else match.group(0)

    def name_only(match: re.Match[str]) -> str:
        row = resolve_ref(context, match.group(1))
        return row.name if row is not None else match.group(0)

    text = _GLUED_REF.sub(name_only, _THINK.sub("", text).strip())
    return _REF.sub(name_only, _REF_WITH_NAME.sub(with_name, text))


def shorten(text: str) -> str:
    trimmed = " ".join(text.split())
    return trimmed if len(trimmed) <= TEXT_LENGTH else trimmed[: TEXT_LENGTH - 1] + "…"
