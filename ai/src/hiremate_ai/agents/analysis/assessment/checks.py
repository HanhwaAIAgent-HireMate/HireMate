"""Assessment Agent의 코드 검사. 볼 자료를 고르고, 모델이 낸 항목을 원문과 대조하고, 점수에서 사실만 뽑는다.

agents.guardrails.evidence_source는 지원서 문서(ApplicantDocument)만 받으므로 평가 자료는 여기서 같은 방식으로 대조한다.
"""

import re
import unicodedata
from dataclasses import dataclass

from hiremate_ai.agents.analysis.assessment.types import AssessmentInput, FindingDraft
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.db.profile import ItemCategory
from hiremate_ai.db.profile_store import NewItem

SUBMISSION_SOURCE = "평가 제출물"
NOTE_SOURCE = "평가 메모"
RESULT_SOURCE = "평가 결과"
# 낱말 하나("Kafka")는 어느 글에나 있어 근거가 되지 못한다. 공백을 뺀 글자 수 기준이다
MIN_EVIDENCE_LENGTH = 8

# 분석 Agent는 채용 결정이나 순위를 말하지 않는다. 결정은 담당자가 화면에서 한다 (아키텍처 규칙 1)
_DECISION_WORDS = re.compile(r"불합격|합격|탈락|순위|등수|채용\s*추천|뽑아야|뽑지")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_SPACES = re.compile(r"\s+")
_LEADING_MARKS = re.compile(r"^[\s·•\-*\"'“”‘’]+|[\s\"'“”‘’]+$")


@dataclass(frozen=True)
class Material:
    """모델에게 보여 주는 자료 하나. label은 프로필 항목의 출처가 된다."""

    label: str
    text: str


def materials_of(data: AssessmentInput) -> list[Material]:
    """본문이 있는 자료만 고른다. URL은 주소만 있어 자료로 쓰지 않는다."""
    found = []
    if data.submission is not None and data.submission.text.strip():
        found.append(Material(SUBMISSION_SOURCE, data.submission.text.strip()))
    if data.note is not None and data.note.strip():
        found.append(Material(NOTE_SOURCE, data.note.strip()))
    return found


def score_checks(data: AssessmentInput) -> list[NewItem]:
    """점수에서 확인이 필요한 사실만 적는다. 점수를 해석하거나 채우지 않는다."""
    items = [
        NewItem(category=ItemCategory.CHECK, content=f"{area} 점수가 없어요", source=RESULT_SOURCE)
        for area, score in data.areas.items()
        if score is None
    ]
    if data.total is None:
        items.append(NewItem(category=ItemCategory.CHECK, content="평가 총점이 없어요", source=RESULT_SOURCE))
    return items


def checked_item(finding: FindingDraft, materials: list[Material]) -> NewItem | str:
    """검사를 통과하면 프로필 항목을, 아니면 모델에게 돌려줄 이유를 낸다.

    근거 문장이 적힌 출처에 없고 다른 자료에 있으면 실제 자료로 출처를 고친다 (guardrails.verified_evidence와 같다).
    """
    content = finding.content.strip()
    evidence = _LEADING_MARKS.sub("", finding.evidence)
    if not content or not evidence:
        return "content나 evidence가 비어 있다"
    if len(_normalize(evidence)) < MIN_EVIDENCE_LENGTH:
        return "evidence가 너무 짧다. 낱말이 아니라 원문 한 문장을 옮긴다"
    if (word := blocked_attribute(f"{content} {evidence}")) is not None:
        return f"채용 판단에 쓰면 안 되는 조건({word})이 있다"
    if (word := _decision_word(content)) is not None:
        return f"채용 결정이나 순위를 말하는 표현({word})이 있다"
    source = _source_of(evidence, finding.source, materials)
    if source is None:
        return "evidence가 자료 원문에 없다. 원문 한 문장을 글자 그대로 옮긴다"
    if not set(_NUMBER.findall(content)) <= set(_NUMBER.findall(source.text)):
        return "content에 자료에 없는 숫자가 있다"
    category = ItemCategory.STRENGTH if finding.kind == "STRENGTH" else ItemCategory.CHECK
    return NewItem(category=category, content=content, evidence=evidence, source=source.label)


def _source_of(evidence: str, label: str, materials: list[Material]) -> Material | None:
    needle = _normalize(evidence)
    containing = [material for material in materials if needle in _normalize(material.text)]
    for material in containing:
        if material.label == label.strip():
            return material
    return containing[0] if containing else None


def _decision_word(text: str) -> str | None:
    match = _DECISION_WORDS.search(text)
    return match.group() if match else None


def _normalize(text: str) -> str:
    return _SPACES.sub("", unicodedata.normalize("NFKC", text))
