"""Interview Agent(답변 분석)의 코드 검사. 답이 없는 질문을 적고, 모델이 낸 항목을 답변 원문과 대조한다.

agents.guardrails.evidence_source는 지원서 문서(ApplicantDocument)만 받으므로 면접 답변은 여기서 같은 방식으로 대조한다.
"""

import re
import unicodedata

from hiremate_ai.agents.analysis.interview.types import FindingDraft, InterviewAnalysisInput
from hiremate_ai.agents.analysis.plain import plain
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.db.profile import ItemCategory
from hiremate_ai.db.profile_store import NewItem

QUESTION_SOURCE = "면접 질문"
# 낱말 하나("Kafka")는 어느 글에나 있어 근거가 되지 못한다. 공백을 뺀 글자 수 기준이다
MIN_EVIDENCE_LENGTH = 8
_QUESTION_PREVIEW = 60

# 분석 Agent는 채용 결정이나 순위를 말하지 않는다. 결정은 담당자가 화면에서 한다 (아키텍처 규칙 1)
_DECISION_WORDS = re.compile(r"불합격|합격|탈락|순위|등수|채용\s*추천|뽑아야|뽑지")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_SPACES = re.compile(r"\s+")
_LEADING_MARKS = re.compile(r"^[\s·•\-*\"'“”‘’]+|[\s\"'“”‘’]+$")


def answer_source(data: InterviewAnalysisInput) -> str:
    """이번 면접 답변에서 뽑은 항목의 출처."""
    return f"{data.stage_name} 답변"


def unanswered_checks(data: InterviewAnalysisInput) -> list[NewItem]:
    """답변을 기록하지 않은 질문은 그 질문으로 확인하려던 점이 아직 확인되지 않은 것으로 적는다."""
    return [
        NewItem(
            category=ItemCategory.CHECK,
            content=f"면접에서 답변을 기록하지 않았다: {_preview(question.text)}",
            source=QUESTION_SOURCE,
        )
        for question in data.questions
        if question.text.strip() and not question.answer.strip()
    ]


def checked_item(finding: FindingDraft, data: InterviewAnalysisInput) -> NewItem | str:
    """검사를 통과하면 프로필 항목을, 아니면 모델에게 돌려줄 이유를 낸다.

    근거는 이번 면접 답변 원문에 있어야 한다. 질문 글이나 이전 면접 기록에서 옮긴 문장은 근거가 아니다.
    """
    content = plain(finding.content)
    evidence = _LEADING_MARKS.sub("", finding.evidence)
    if not content or not evidence:
        return "content나 evidence가 비어 있다"
    if len(_normalize(evidence)) < MIN_EVIDENCE_LENGTH:
        return "evidence가 너무 짧다. 낱말이 아니라 답변 원문 한 문장을 옮긴다"
    if (word := blocked_attribute(f"{content} {evidence}")) is not None:
        return f"채용 판단에 쓰면 안 되는 조건({word})이 있다"
    if (word := _decision_word(content)) is not None:
        return f"채용 결정이나 순위를 말하는 표현({word})이 있다"
    needle = _normalize(evidence)
    if not any(needle in _normalize(question.answer) for question in data.questions):
        return "evidence가 이번 면접 답변 원문에 없다. 질문이 아니라 답변 한 문장을 글자 그대로 옮긴다"
    if not set(_NUMBER.findall(content)) <= set(_NUMBER.findall(_all_text(data))):
        return "content에 면접 기록에 없는 숫자가 있다"
    category = ItemCategory.STRENGTH if finding.kind == "CONFIRMED" else ItemCategory.CHECK
    return NewItem(category=category, content=content, evidence=evidence, source=answer_source(data))


def _all_text(data: InterviewAnalysisInput) -> str:
    """content의 숫자를 대조할 글. "1차 면접에서는"처럼 전형 이름의 숫자도 쓸 수 있다."""
    questions = [*data.questions, *(question for previous in data.previous for question in previous.questions)]
    names = [data.stage_name, *(previous.stage_name for previous in data.previous)]
    return "\n".join([*names, *(f"{question.text}\n{question.answer}" for question in questions)])


def _preview(text: str) -> str:
    text = _SPACES.sub(" ", text.strip())
    return text if len(text) <= _QUESTION_PREVIEW else text[: _QUESTION_PREVIEW - 1] + "…"


def _decision_word(text: str) -> str | None:
    match = _DECISION_WORDS.search(text)
    return match.group() if match else None


def _normalize(text: str) -> str:
    return _SPACES.sub("", unicodedata.normalize("NFKC", text))
