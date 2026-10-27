"""모델이 제시한 지원자 번호와 근거를 검증하고 화면에 표시할 항목으로 바꾼다.

요청의 의미와 대상을 해석하지 않는다. 자료의 원문과 프로필 검증 상태만 확인한다.
"""

import re
from collections.abc import Mapping, Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hiremate_ai.agents.analysis.assessment.checks import NOTE_SOURCE, SUBMISSION_SOURCE
from hiremate_ai.agents.analysis.assessment.checks import RESULT_SOURCE as SCORE_SOURCE
from hiremate_ai.agents.guardrails import evidence_source
from hiremate_ai.agents.root.toolkit import (
    DOUBTFUL,
    AgentEvidence,
    candidate_summary_text,
    cited_agents,
    company_text,
    posting_text,
    recorded_evidence,
    recorded_matches,
    resolve_ref,
    stage_result_text,
    stage_summary_text,
)
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatItem
from hiremate_ai.contract import DocumentType, InterviewerMemo

TEXT_LENGTH = 120
BULK_LIMIT = 20
FOCUS_WITH_REQUEST = "{focus} (담당자 요청: {request})"
INTERVIEW_AGENT = "Interview Agent"
INTERVIEW_SOURCE = "면접 기록"
MEMO_SOURCE = "면접관메모"
RESULT_SOURCE = "전형 결과"
COMPANY_SOURCE = "회사 소개"
POSTING_SOURCE = "공고"
PROFILE_SOURCES = (SUBMISSION_SOURCE, NOTE_SOURCE)

_DOCUMENT_LABELS = {document.label: document for document in DocumentType}
_REF = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)(?![0-9])")
_REF_WITH_NAME = re.compile(r"(?<![A-Za-z0-9])[Cc](\d+)\s+([^\s,.!?]+)")
_GLUED_REF = re.compile(r"(?<![A-Za-z0-9])[a-z]+C(\d+)(?![0-9])")
_THINK = re.compile(r"<think>.*?</think>|</?think>", re.DOTALL)
_JSON_FRAGMENT = re.compile(r"[}\]]{2,}(?=\s*(?:[,`*]|$))")
_INTERNAL_REFERENCE = re.compile(
    r"(?<![\w.])(?:items|message|evidence)(?:\.[a-z_]+)?[`\"']?\s*"
    r"(?:를|로|에서|에|은|는|이|가|의|필드|배열|목록|참고|:|=)",
    re.IGNORECASE,
)


class AnswerEvidence(BaseModel):
    sentence: str = Field(
        description="조회한 원문의 문장을 글자 그대로 쓴다. 여러 문장은 합치지 않고 evidence의 별도 항목으로 나눈다"
    )
    source: str = Field(
        description=(
            "근거 출처: 이력서, 자기소개서, 포트폴리오, 자격증, 면접 기록, 전형 결과, "
            "평가 제출물, 평가 메모, 면접관메모, 회사 소개, 공고"
        )
    )


class AnswerItem(BaseModel):
    model_config = ConfigDict(json_schema_extra={"required": ["candidate", "label", "text", "status", "evidence"]})

    candidate: str | None = Field(
        default=None,
        description=(
            "이 항목의 지원자 번호(C1 같은). 비교도 지원자마다 항목을 나눈다. "
            "JSON null은 지원자를 다루지 않는 공통 사실에만 쓴다. 빈 문자열을 쓰지 않는다"
        ),
    )
    label: str = Field(description="항목 이름")
    text: str = Field(description="한 줄 설명")
    status: Literal["OK", "CHECK"] = Field(description="근거가 충분하면 OK, 추가 확인이 필요하면 CHECK")
    evidence: list[AnswerEvidence] = Field(default=[], description="원문 근거와 출처")

    @field_validator("candidate", mode="before")
    @classmethod
    def empty_candidate(cls, value: object) -> object:
        """모델이 공통 항목을 빈 문자열로 보낸 경우만 명시적인 무대상으로 맞춘다."""
        return None if value == "" else value


def _invalid_message(message: str) -> bool:
    return not message.strip() or bool(_JSON_FRAGMENT.search(message) or _INTERNAL_REFERENCE.search(message))


def verify_items(
    items: Sequence[AnswerItem],
    context: ChatContext,
    only: CandidateRow | None = None,
    recorded: Mapping[UUID, Sequence[AgentEvidence]] | None = None,
) -> tuple[list[ChatItem], list[str], list[str]]:
    """번호를 지원자로 바꾸고 근거를 원문과 맞춰 본다. (항목, 남은 근거의 출처, 근거를 낸 분석 Agent)를 돌려준다.

    없는 번호의 항목은 버린다. 번호를 비운 항목은 글에 번호가 하나만 있으면 그 지원자로,
    근거를 단 항목이고 대상이 한 명이면 그 대상으로 본다(근거는 지원자 문서와 맞춰 봐야 한다).
    근거를 댔지만 하나도 확인되지 않았거나, 근거 없이 지원자를 OK라 한 항목은 CHECK다.
    recorded는 분석 Agent가 프로필에 남긴 근거다. 평가 자료 근거를 여기서 확인하고, 같은 문장을 낸 Agent를 알린다.
    남은 근거가 모두 분석 Agent가 미확인 또는 상충으로 적은 문장이면 원문에 있어도 CHECK다 (NFR-03).
    """
    recorded = recorded or {}
    verified: list[ChatItem] = []
    sources: list[str] = []
    cited: list[tuple[UUID, str]] = []
    for item in items:
        if item.candidate is not None:
            row = resolve_ref(context, item.candidate)
            if row is None:
                continue
        else:
            row = _mentioned_row(context, f"{item.label} {item.text}", only if item.evidence else None)
        checked = [(evidence, _verified_source(context, row, evidence, recorded)) for evidence in item.evidence]
        kept = [source for _, source in checked if source]
        unsupported = item.status == "OK" and not kept
        doubtful = (
            row is not None
            and bool(kept)
            and all(_doubtful(recorded, row, evidence) for evidence, source in checked if source)
        )
        status = "CHECK" if unsupported or doubtful or MEMO_SOURCE in kept else item.status
        sources += [source for source in dict.fromkeys(kept) if source not in sources]
        if row is not None:
            cited += [(row.application_id, evidence.sentence) for evidence, source in checked if source]
        verified.append(
            ChatItem(
                application_id=row.application_id if row else None,
                label=readable(item.label, context),
                text=_shorten(readable(item.text, context)),
                status=status,
            )
        )
    return verified, sources, cited_agents(recorded, cited)


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


def _mentioned_row(context: ChatContext, text: str, only: CandidateRow | None) -> CandidateRow | None:
    refs = {row.application_id: row for match in _REF.finditer(text) if (row := resolve_ref(context, match.group(1)))}
    if len(refs) == 1:
        return next(iter(refs.values()))
    return only if not refs else None


def _doubtful(recorded: Mapping[UUID, Sequence[AgentEvidence]], row: CandidateRow, evidence: AnswerEvidence) -> bool:
    """근거 문장이 같은 출처의 프로필 항목에 미확인 또는 상충으로만 적혀 있는가. 프로필에 없는 문장은 아니다."""
    source = _canonical_source(evidence.source)
    states = [
        each.verification
        for each in recorded_matches(recorded, row.application_id, evidence.sentence)
        if _canonical_source(each.source) == source
    ]
    return bool(states) and all(state in DOUBTFUL for state in states)


def _verified_source(
    context: ChatContext,
    row: CandidateRow | None,
    evidence: AnswerEvidence,
    recorded: Mapping[UUID, Sequence[AgentEvidence]],
) -> str | None:
    """근거가 원문에 있으면 출처 이름(문서는 실제 문서로 고친다), 없으면 None.

    출처는 정해 둔 이름으로 맞춘다("이력서 경력란" → 이력서). 맞출 수 없는 출처의 근거는 버린다.
    전형 결과와 평가 결과는 backend가 준 실제 값과 맞춰 본다.
    평가 제출물과 평가 메모는 Assessment Agent가 원문과 맞춰 프로필에 남긴 근거에 있어야 한다.
    """
    source = _canonical_source(evidence.source)
    if source == MEMO_SOURCE:
        return source if row is not None and memo_evidence(context, row, evidence) is not None else None
    if source in PROFILE_SOURCES:
        saved = recorded_evidence(recorded, row.application_id, evidence.sentence) if row is not None else None
        return saved.source if saved else None
    if source in _DOCUMENT_LABELS:
        if row is None:
            return None
        found = evidence_source(evidence.sentence, context.documents.get(row.application_id, []))
        return found.label if found else None
    if source == INTERVIEW_SOURCE:
        return INTERVIEW_SOURCE if row is not None and _in_interviews(context, row, evidence.sentence) else None
    if source == COMPANY_SOURCE:
        return source if _contains(_company_text(context), evidence.sentence) else None
    if source == POSTING_SOURCE:
        return source if _contains(_posting_text(context), evidence.sentence) else None
    if source == RESULT_SOURCE or (source == SCORE_SOURCE and row is not None):
        actual = (
            "\n".join([stage_result_text(context, row), candidate_summary_text(context, row)])
            if row is not None
            else stage_summary_text(context)
        )
        return source if _contains(actual.replace(":", ""), evidence.sentence.replace(":", "")) else None
    return None


def _canonical_source(source: str) -> str | None:
    compact = "".join(source.split())
    if compact == MEMO_SOURCE:
        return MEMO_SOURCE
    for label in ("자기소개서", "이력서", "포트폴리오", "자격증"):
        if label in compact:
            return label
    if "자소서" in compact:
        return "자기소개서"
    if "면접" in compact:
        return INTERVIEW_SOURCE
    if "제출물" in compact:
        return SUBMISSION_SOURCE
    if "메모" in compact:
        return NOTE_SOURCE
    if "인재상" in compact or "문화" in compact:
        return COMPANY_SOURCE
    for label in (RESULT_SOURCE, SCORE_SOURCE, COMPANY_SOURCE, POSTING_SOURCE):
        if "".join(label.split()) in compact:
            return label
    return None


def memo_evidence(context: ChatContext, row: CandidateRow, evidence: AnswerEvidence) -> InterviewerMemo | None:
    """같은 지원자의 실제 메모에 있는 인용만 반환한다. 메모 내용의 진실성을 인정하는 검사가 아니다."""
    if _canonical_source(evidence.source) != MEMO_SOURCE or not evidence.sentence.strip():
        return None
    return next(
        (
            memo.model_copy(update={"text": evidence.sentence})
            for memo in context.interviewer_memos.get(row.application_id, [])
            if evidence.sentence in memo.text
        ),
        None,
    )


def _company_text(context: ChatContext) -> str:
    """근거를 맞춰 볼 회사 글. 도구가 보여 준 글(인재상 줄의 "제목: 설명")도 넣는다. 모델은 그 줄을 그대로 옮긴다."""
    company = context.company
    talents = " ".join(f"{talent.title} {talent.description}" for talent in company.talents)
    return " ".join([company_text(context), company.name, company.intro, company.culture, talents, *company.benefits])


def _posting_text(context: ChatContext) -> str:
    """근거를 맞춰 볼 공고 글. 도구가 보여 준 글도 넣는다."""
    posting = context.posting
    return " ".join(
        [
            posting_text(context),
            posting.title,
            posting.intro,
            *posting.duties,
            *posting.qualifications,
            *posting.preferred,
            *posting.benefits,
        ]
    )


def _contains(text: str, sentence: str) -> bool:
    needle = "".join(sentence.split())
    return bool(needle) and needle in "".join(text.split())


def _in_interviews(context: ChatContext, row: CandidateRow, sentence: str) -> bool:
    view = context.interviews.get(row.application_id)
    if view is None:
        return False
    questions = [*view.questions, *(question for previous in view.previous for question in previous.questions)]
    text = "".join("".join(f"{question.text}{question.answer}".split()) for question in questions)
    needle = "".join(sentence.split())
    return bool(needle) and needle in text


def _shorten(text: str) -> str:
    trimmed = " ".join(text.split())
    return trimmed if len(trimmed) <= TEXT_LENGTH else trimmed[: TEXT_LENGTH - 1] + "…"
