"""🎤 꼬리질문 제안. 면접관이 [꼬리질문 받기]를 눌렀을 때만 모델을 한 번 부른다 (토큰은 버튼을 누를 때만 쓴다).

흐름
  처음 질문부터 지금 질문까지의 질문과 답(chain)을 읽는다
    → 답이 질문에 충분히 답했으면 needed=False (화면: "추가로 확인할 점이 없어요")
    → 아니면 서로 다른 확인 포인트를 가진 꼬리질문 2개를 제안한다
  면접관이 하나를 고르거나 직접 쓰면 backend가 원래 질문 아래에 저장한다. 이 모듈은 저장하지 않는다.

모델이 쓴 질문은 코드가 검사한다 (agent.py의 질문 검사와 같은 원칙)
  - 차별 조건(나이, 성별, 출신 지역, 혼인 여부, 신체 조건 등)이 들어간 질문과 확인 포인트는 버린다 (규칙 6)
  - 점수 · 합격 판단을 드러내는 질문, 너무 긴 질문, 빈 질문은 버린다
  - 앞 질문들, [다시 제안] 전에 보여 준 제안(avoid), 서로 비슷한 질문은 버린다
  확인할 점이 있다면서 쓸 수 있는 질문이 하나도 남지 않으면 버린 이유를 알려 주고 한 번만 다시 쓰게 한다.
  다시 써도 남지 않으면 꾸며내지 않고 확인할 점이 없다고 돌려준다.

면접 답변은 지원자의 말이라 <data> 블록으로 감싸고 system에 UNTRUSTED_RULE을 넣는다 (규칙 5).
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from pydantic import BaseModel, Field

from hiremate_ai.agents.generation.interview.types import FollowUpsRequest, FollowUpSuggestion, InterviewFollowUps
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import InterviewerRole
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

AGENT_KEY = "interview"

MAX_SUGGESTIONS = 2
MAX_TEXT = 150  # 면접관이 바로 읽어 물을 수 있는 한 문장
MAX_CHECK = 80
SIMILAR = 0.8  # 이 비율 이상 겹치면 같은 질문으로 본다

# 점수 · 합격 판단 같은 내부 판단을 지원자에게 묻거나 드러내는 질문은 쓰지 않는다
_INTERNAL = re.compile(r"점수|합격|불합격|탈락|평가 결과|등급")

SYSTEM = f"""너는 면접관을 돕는 면접 보조다. 면접관이 지원자의 답을 듣고 바로 이어서 물을 꼬리질문을 제안한다.

판단
- current 질문의 답을 읽고, 질문 의도에 비해 비어 있거나 모호한 부분을 찾는다.
  예: 구체적인 사례, 본인이 직접 한 일과 팀이 한 일의 구분, 판단 근거, 결과와 확인 방법, 배운 점.
- 답이 질문에 구체적으로 충분히 답했으면 needed=false, suggestions=[] 로 답한다. 억지로 질문을 만들지 않는다.
- 확인할 점이 있으면 needed=true 로 두고 서로 다른 확인 포인트를 가진 꼬리질문을 정확히 2개 쓴다.

꼬리질문
- 지원자가 방금 한 답의 낱말을 이어받아 한 문장, {MAX_TEXT}자 이내, 존댓말로 쓴다.
- check 에는 이 질문으로 무엇을 확인하려는지(답에서 무엇이 비었는지) {MAX_CHECK}자 이내 한 문장으로 쓴다.
- earlier 질문에서 이미 답한 내용과 avoid 목록의 질문은 다시 묻지 않는다.
- 담당이 HR(인사)이면 동기 · 협업 · 조직 적응 · 가치관 관점으로 묻는다.
- 담당이 PRACTICAL(실무)이면 직무 경험 · 문제 해결 관점으로 묻는다.
- 나이, 성별, 출신 지역, 혼인 여부, 가족, 신체 조건처럼 직무와 무관한 개인 사항은 묻지 않는다.
- 점수나 합격 여부 같은 평가 판단을 말하지 않는다. 답에 없는 사실을 있다고 단정하지 않는다.
- {UNTRUSTED_RULE}"""

_ROLE_LABEL = {InterviewerRole.HR: "HR(인사)", InterviewerRole.PRACTICAL: "PRACTICAL(실무)"}


class _Suggestion(BaseModel):
    text: str = Field(description="꼬리질문 한 문장")
    check: str = Field(description="이 질문으로 확인할 점 (답에서 비어 있거나 모호한 부분)")


class FollowUpDraft(BaseModel):
    """모델이 쓰는 꼬리질문 제안. 코드가 검사한 뒤 InterviewFollowUps로 돌려준다."""

    needed: bool = Field(description="꼬리질문으로 더 확인할 점이 있으면 true, 답이 충분하면 false")
    suggestions: list[_Suggestion] = Field(
        default_factory=list, description="needed=true 일 때 서로 다른 확인 포인트의 꼬리질문 2개"
    )


async def suggest_follow_ups(llm: LlmClient, request: FollowUpsRequest) -> InterviewFollowUps:
    """처음 질문부터 지금 질문까지의 질문과 답을 보고 꼬리질문을 최대 2개 제안한다."""
    user = _prompt(request)
    draft = await llm.structured(FollowUpDraft, agent=AGENT_KEY, system=SYSTEM, user=user)
    if not draft.needed:
        return InterviewFollowUps(needed=False)
    kept, rejected = _check(draft, request)
    if not kept:
        # 확인할 점이 있다는데 쓸 수 있는 질문이 없다: 버린 이유를 알려 주고 한 번만 다시 쓰게 한다
        retry = user + "\n\n" + data_block("rejected", "\n".join(rejected) or "(쓸 수 있는 질문이 없음)")
        retry += "\n위 질문은 쓸 수 없었다. 이유를 피해 새 꼬리질문 2개를 다시 써라."
        draft = await llm.structured(FollowUpDraft, agent=AGENT_KEY, system=SYSTEM, user=retry)
        if not draft.needed:
            return InterviewFollowUps(needed=False)
        kept, _ = _check(draft, request)
    if not kept:
        return InterviewFollowUps(needed=False)
    return InterviewFollowUps(needed=True, suggestions=kept)


def _prompt(request: FollowUpsRequest) -> str:
    """공고(직무)와 질문 사슬. 앞 질문은 earlier, 꼬리질문을 받을 질문은 current로 둔다."""
    posting = request.posting
    job = [f"공고: {posting.title}"]
    if posting.duties:
        job.append("주요 업무: " + " / ".join(posting.duties))
    if posting.qualifications:
        job.append("자격 요건: " + " / ".join(posting.qualifications))
    *earlier, current = request.chain
    lines = [data_block("job", "\n".join(job))]
    for turn in earlier:
        lines.append(data_block("earlier", f"질문: {turn.text}\n답변: {turn.answer.strip() or '(답 없음)'}"))
    role = _ROLE_LABEL.get(current.interviewer_role or InterviewerRole.PRACTICAL, "PRACTICAL(실무)")
    purpose = f"\n질문 의도: {current.reason.strip()}" if current.reason and current.reason.strip() else ""
    lines.append(
        data_block("current", f"질문: {current.text}{purpose}\n답변: {current.answer.strip()}", interviewer=role)
    )
    lines.append(data_block("avoid", "\n".join(request.avoid) or "(없음)"))
    return "\n".join(lines)


def _check(draft: FollowUpDraft, request: FollowUpsRequest) -> tuple[list[FollowUpSuggestion], list[str]]:
    """쓸 수 있는 제안과 버린 제안(이유 포함). 앞 질문 · avoid · 서로 비슷한 질문은 버린다."""
    seen = [turn.text for turn in request.chain] + list(request.avoid)
    kept: list[FollowUpSuggestion] = []
    rejected: list[str] = []
    for suggestion in draft.suggestions:
        text = " ".join(suggestion.text.split())
        check = " ".join(suggestion.check.split())
        reason = _problem(text, check, seen)
        if reason:
            rejected.append(f"{text} → {reason}")
            continue
        seen.append(text)
        kept.append(FollowUpSuggestion(text=text, check=check))
        if len(kept) == MAX_SUGGESTIONS:
            break
    return kept, rejected


def _problem(text: str, check: str, seen: list[str]) -> str | None:
    """쓸 수 없는 이유. 쓸 수 있으면 None."""
    if not text or not check:
        return "질문이나 확인 포인트가 비어 있음"
    if blocked_attribute(text) or blocked_attribute(check):
        return "직무와 무관한 개인 사항을 물음"
    if _INTERNAL.search(text):
        return "평가 판단을 드러냄"
    if len(text) > MAX_TEXT:
        return f"{MAX_TEXT}자를 넘음"
    if any(_similar(text, other) for other in seen):
        return "앞 질문이나 앞서 보여 준 제안과 같음"
    return None


def _similar(left: str, right: str) -> bool:
    a, b = _normalize(left), _normalize(right)
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def _normalize(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", unicodedata.normalize("NFKC", text)).lower()
