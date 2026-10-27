"""Interview Agent 답변 분석 (FR-28). 면접관이 기록한 답변에서 확인된 점과 아직 확인 안 된 점을 정리한다.

답변 기록(면접관이 쓴 원문)과 AI 해석을 구분한다. 원문은 backend에 그대로 두고, 여기서는 해석만 만든다.
확인된 점에는 답변 속 인용을 붙이고, 답변에 없는 인용은 버린다 (아키텍처 규칙 7).
합격 · 불합격 의견이나 점수는 만들지 않는다 (규칙 1).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

from hiremate_ai.agents.analysis.interview.checks import checked_item, unanswered_checks
from hiremate_ai.agents.analysis.interview.types import (
    FindingDraft,
    InterviewAnalysis,
    InterviewAnalysisInput,
    InterviewDraft,
    InterviewReference,
)
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import NewItem
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

if TYPE_CHECKING:
    from uuid import UUID

    from hiremate_ai.agents.generation.interview.router import InterviewQuestion
    from hiremate_ai.llm.client import LlmClient

AGENT_KEY = "interview"

CONFIRMED = "CONFIRMED"
PARTIAL = "PARTIAL"
NOT_CONFIRMED = "NOT_CONFIRMED"
NO_ANSWER = "NO_ANSWER"

SYSTEM = f"""너는 면접 답변을 정리하는 Interview Agent다.
질문마다 면접관이 기록한 지원자 답변에서 '확인된 점'과 '아직 확인 안 된 점'을 정리한다.

질문마다 하나씩
- no: 질문 번호
- status: "CONFIRMED" | "PARTIAL" | "NOT_CONFIRMED"
  CONFIRMED     = 질문이 확인하려던 것이 답변에 본인 행동 · 판단 · 결과로 구체적으로 나옴
  PARTIAL       = 일부만 나오고 빠진 부분이 있음
  NOT_CONFIRMED = 답변이 질문과 다르거나, 너무 짧거나, 구체적인 내용이 없음
- confirmed: 확인된 점. 각 항목은 point(한 줄 요약)와 quote(답변에서 그대로 옮긴 짧은 구절)
- unconfirmed: 아직 확인 안 된 점. 다음 면접에서 이어서 물을 수 있게 짧은 명사구로 쓴다
  (예: "장애 원인을 찾은 본인의 판단 근거", "개선 결과(수치)")

규칙
- quote는 답변 글자를 그대로 복사한다. 답변에 없는 말을 만들지 않는다.
- 합격 · 불합격 의견, 점수, "우수하다/부족하다" 같은 평가는 쓰지 않는다.
- 나이, 성별, 출신, 혼인 여부, 신체 조건 등 직무와 무관한 내용은 쓰지 않는다.
- {UNTRUSTED_RULE}"""


class _Point(BaseModel):
    point: str
    quote: str


class _Reading(BaseModel):
    no: int
    status: Literal["CONFIRMED", "PARTIAL", "NOT_CONFIRMED"]
    confirmed: list[_Point] = []
    unconfirmed: list[str] = []


class AnswerReading(BaseModel):
    """모델이 돌려줄 형식."""

    results: list[_Reading]


@dataclass(frozen=True)
class Finding:
    """질문 하나의 해석 (라우터가 AnswerFinding으로 바꾼다)."""

    question_id: UUID
    status: str
    confirmed: list[tuple[str, str]] = field(default_factory=list)
    unconfirmed: list[str] = field(default_factory=list)


_SPACES = re.compile(r"[\s\"'“”‘’.,!?·]+")


def _normalize(text: str) -> str:
    return _SPACES.sub("", unicodedata.normalize("NFKC", text))


def user_prompt(answered: Sequence[tuple[int, InterviewQuestion]]) -> str:
    """질문과 답변을 번호와 함께 넣는다. 답변은 면접관이 기록한 자료라 data 블록으로 감싼다."""
    blocks = []
    for no, question in answered:
        blocks.append(f"[{no}] 질문: {question.text}\n" + data_block("interview-answer", question.answer, no=str(no)))
    return "질문마다 답변을 정리한다.\n\n" + "\n\n".join(blocks)


async def analyze_answers(llm: LlmClient, questions: Sequence[InterviewQuestion]) -> list[Finding]:
    """질문 목록의 답변을 분석한다. 답변이 하나도 없으면 모델을 부르지 않는다."""
    answered: list[tuple[int, InterviewQuestion]] = []
    for no, question in enumerate(questions, start=1):
        if question.answer.strip():
            answered.append((no, question))
    readings: dict[int, _Reading] = {}
    if answered:
        reading = await llm.structured(AnswerReading, agent=AGENT_KEY, system=SYSTEM, user=user_prompt(answered))
        for item in reading.results:
            readings.setdefault(item.no, item)
    return [_finding(no, question, readings.get(no)) for no, question in enumerate(questions, start=1)]


def _finding(no: int, question: InterviewQuestion, reading: _Reading | None) -> Finding:
    """모델 해석을 코드로 점검한다.

    - 답변이 없으면 NO_ANSWER
    - 모델이 빠뜨린 질문은 NOT_CONFIRMED + 면접관 확인 필요 (없다고 단정하지 않고 사람에게 넘김)
    - 답변에 없는 인용은 버리고, 인용이 하나도 안 남은 CONFIRMED는 NOT_CONFIRMED로 낮춘다
    """
    if not question.answer.strip():
        return Finding(question.question_id, NO_ANSWER, [], ["면접에서 답변이 기록되지 않은 부분"])
    if reading is None:
        return Finding(question.question_id, NOT_CONFIRMED, [], ["AI가 해석하지 못한 답변 (면접관 확인 필요)"])
    answer = _normalize(question.answer)
    confirmed = []
    for point in reading.confirmed:
        quote = point.quote.strip()
        if quote and _normalize(quote) in answer:
            confirmed.append((point.point.strip(), quote))
    status: str = reading.status
    if status == CONFIRMED and not confirmed:
        status = NOT_CONFIRMED
    unconfirmed = [text.strip() for text in reading.unconfirmed if text.strip()]
    if status != CONFIRMED and not unconfirmed:
        unconfirmed = ["질문이 확인하려던 본인 역할과 결과"]
    return Finding(question.question_id, status, confirmed, unconfirmed)


AGENT = "interview"
MAX_RETRIES = 2
"""검사를 통과하지 못한 항목만 다시 쓰게 하는 횟수 (v8 근거 원문 대조)."""

PROFILE_SYSTEM = f"""채용 담당자가 볼 면접 기록에서, 면접관이 질문마다 기록한 답변을 정리한다.
- CONFIRMED: 질문으로 확인하려던 경험 · 역량을 답변이 구체적으로 뒷받침한 점.
- UNCONFIRMED: 답변이 모호하거나 짧아 아직 확인되지 않은 점.
- CONFLICT: 질문의 전제(서류 · 평가에서 온 내용)나 이전 면접 답변과 어긋나는 점.
- 기록에 적힌 내용만으로 쓴다. 기록에 없는 경험, 숫자, 평가를 지어내지 않는다.
- 항목마다 evidence에 이번 면접 답변 원문 한 문장을 글자 그대로 옮긴다. 질문 글이나 이전 면접 기록은 근거로 쓰지 않는다.
- 앞선 분석 결과는 비교 맥락일 뿐이며, 미확인 내용이나 팀의 결과일 수 있다. 지원자의 확인된 사실로 승격하지 않는다.
- 앞선 분석 결과의 evidence를 이번 면접 답변처럼 인용하지 않는다. 확인과 상충 여부도 이번 답변으로 뒷받침해야 한다.
- 합격, 불합격, 순위, 채용 추천처럼 결정을 말하지 않는다. 결정은 담당자가 한다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- content는 존댓말(~어요)로 짧게 쓴다.

{UNTRUSTED_RULE}"""


async def analyze_interview(
    data: InterviewAnalysisInput, llm: LlmClient, *, references: Sequence[InterviewReference] = ()
) -> InterviewAnalysis:
    """지원자 한 명의 면접 기록을 정리해 프로필에 넣을 항목을 돌려준다. 저장하지 않고 채용 상태를 바꾸지 않는다.

    통과하지 못한 항목만 이유를 붙여 MAX_RETRIES번까지 다시 쓰게 하고, 그래도 남은 항목은 버린다.
    """
    items = unanswered_checks(data)
    if not any(question.answer.strip() for question in data.questions):
        return InterviewAnalysis(status=ProfileStatus.CHECK, items=items, dropped=0)

    user = _user_prompt(data, references)
    prompt = user
    answered = False
    failed: list[tuple[FindingDraft, str]] = []
    for _ in range(1 + MAX_RETRIES):
        try:
            drafts = await _draft(llm, prompt)
        except LlmOutputError as error:
            if error.reason is not LlmFailureReason.BUDGET:
                raise
            return InterviewAnalysis(
                status=ProfileStatus.CHECK, items=_dedupe(items), dropped=len(failed), interrupted=True
            )
        if drafts is None:  # 형식에 맞지 않은 답. 같은 요청으로 다시 묻는다
            continue
        answered = True
        failed = []
        for finding in drafts.findings:
            checked = checked_item(finding, data)
            if isinstance(checked, str):
                failed.append((finding, checked))
            else:
                items.append(checked)
        if not failed:
            break
        prompt = _retry_prompt(user, failed)
    status = ProfileStatus.DONE if answered else ProfileStatus.FAILED
    return InterviewAnalysis(status=status, items=_dedupe(items), dropped=len(failed))


async def _draft(llm: LlmClient, user: str) -> InterviewDraft | None:
    try:
        return await llm.structured(InterviewDraft, agent=AGENT, system=PROFILE_SYSTEM, user=user)
    except LlmOutputError as error:
        if error.reason is not LlmFailureReason.FORMAT:
            raise
        return None


def _user_prompt(data: InterviewAnalysisInput, references: Sequence[InterviewReference]) -> str:
    current = "\n\n".join(
        data_block("interview", f"질문: {question.text}\n답변: {question.answer}", label=f"{data.stage_name} 답변")
        for question in data.questions
        if question.answer.strip()
    )
    prompt = f"전형: {data.stage_name}\n\n이번 면접 기록:\n\n{current}"
    earlier = [
        data_block("interview", f"질문: {question.text}\n답변: {question.answer}", label=f"{previous.stage_name} 답변")
        for previous in data.previous
        for question in previous.questions
        if question.answer.strip()
    ]
    if earlier:
        prompt += "\n\n이전 면접 기록 (비교용, 근거로 쓰지 않는다):\n\n" + "\n\n".join(earlier)
    if references:
        prompt += "\n\n앞선 분석 결과 (비교용, 이번 답변의 근거로 쓰지 않는다):\n\n" + "\n\n".join(
            data_block("specialist-reference", reference.model_dump_json()) for reference in references
        )
    return prompt


def _retry_prompt(user: str, failed: list[tuple[FindingDraft, str]]) -> str:
    rejected = "\n".join(f"- {finding.model_dump_json()}\n  문제: {reason}" for finding, reason in failed)
    return (
        f"{user}\n\n앞서 쓴 항목 중 아래 항목이 검사를 통과하지 못했다:\n{rejected}\n"
        "이 항목들만 문제를 고쳐 다시 쓴다. 고칠 수 없는 항목은 빼고, 통과한 항목은 다시 쓰지 않는다."
    )


def _dedupe(items: list[NewItem]) -> list[NewItem]:
    return list({(item.category, item.content, item.evidence): item for item in items}.values())
