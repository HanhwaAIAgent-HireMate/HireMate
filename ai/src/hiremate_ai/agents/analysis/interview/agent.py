"""면접 답변 분석. 모델이 질문별 답변에서 확인된 점 · 확인되지 않은 점 · 어긋나는 점과 근거를 뽑고,
코드가 근거를 답변 원문과 대조한다.

답변을 기록하지 않은 질문처럼 코드가 아는 사실만 코드가 적는다. 이전 면접 기록은 비교할 맥락으로만 보여 준다.
"""

from contextlib import suppress

from hiremate_ai.agents.analysis.interview.checks import checked_item, unanswered_checks
from hiremate_ai.agents.analysis.interview.types import (
    FindingDraft,
    InterviewAnalysis,
    InterviewAnalysisInput,
    InterviewDraft,
)
from hiremate_ai.db.profile import ProfileStatus
from hiremate_ai.db.profile_store import NewItem
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

AGENT = "interview"
MAX_RETRIES = 2
"""검사를 통과하지 못한 항목만 다시 쓰게 하는 횟수 (v8 근거 원문 대조)."""

SYSTEM = f"""채용 담당자가 볼 면접 기록에서, 면접관이 질문마다 기록한 답변을 정리한다.
- CONFIRMED: 질문으로 확인하려던 경험 · 역량을 답변이 구체적으로 뒷받침한 점.
- UNCONFIRMED: 답변이 모호하거나 짧아 아직 확인되지 않은 점.
- CONFLICT: 질문의 전제(서류 · 평가에서 온 내용)나 이전 면접 답변과 어긋나는 점.
- 기록에 적힌 내용만으로 쓴다. 기록에 없는 경험, 숫자, 평가를 지어내지 않는다.
- 항목마다 evidence에 이번 면접 답변 원문 한 문장을 글자 그대로 옮긴다. 질문 글이나 이전 면접 기록은 근거로 쓰지 않는다.
- 합격, 불합격, 순위, 채용 추천처럼 결정을 말하지 않는다. 결정은 담당자가 한다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- content는 존댓말(~어요)로 짧게 쓴다.

{UNTRUSTED_RULE}"""


async def analyze_interview(data: InterviewAnalysisInput, llm: LlmClient) -> InterviewAnalysis:
    """지원자 한 명의 면접 기록을 정리해 프로필에 넣을 항목을 돌려준다. 저장하지 않고 채용 상태를 바꾸지 않는다.

    통과하지 못한 항목만 이유를 붙여 MAX_RETRIES번까지 다시 쓰게 하고, 그래도 남은 항목은 버린다.
    """
    items = unanswered_checks(data)
    if not any(question.answer.strip() for question in data.questions):
        return InterviewAnalysis(status=ProfileStatus.CHECK, items=items, dropped=0)

    user = _user_prompt(data)
    prompt = user
    answered = False
    failed: list[tuple[FindingDraft, str]] = []
    for _ in range(1 + MAX_RETRIES):
        drafts = await _draft(llm, prompt)
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
    with suppress(LlmOutputError):
        return await llm.structured(InterviewDraft, agent=AGENT, system=SYSTEM, user=user)
    return None


def _user_prompt(data: InterviewAnalysisInput) -> str:
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
    return prompt


def _retry_prompt(user: str, failed: list[tuple[FindingDraft, str]]) -> str:
    rejected = "\n".join(f"- {finding.model_dump_json()}\n  문제: {reason}" for finding, reason in failed)
    return (
        f"{user}\n\n앞서 쓴 항목 중 아래 항목이 검사를 통과하지 못했다:\n{rejected}\n"
        "이 항목들만 문제를 고쳐 다시 쓴다. 고칠 수 없는 항목은 빼고, 통과한 항목은 다시 쓰지 않는다."
    )


def _dedupe(items: list[NewItem]) -> list[NewItem]:
    return list({(item.category, item.content, item.evidence): item for item in items}.values())
