"""평가 결과 분석. 모델이 평가 자료에서 강점 · 약점과 근거를 뽑고, 코드가 근거를 원문과 대조한다.

점수 · 등급은 모델에게 보여 주지 않고 바꾸지도 않는다. 점수가 빈 영역처럼 코드가 아는 사실만 코드가 적는다.
"""

from contextlib import suppress

from hiremate_ai.agents.analysis.assessment.checks import (
    RESULT_SOURCE,
    Material,
    checked_item,
    materials_of,
    score_checks,
)
from hiremate_ai.agents.analysis.assessment.types import (
    AssessmentAnalysis,
    AssessmentDraft,
    AssessmentInput,
    FindingDraft,
)
from hiremate_ai.db.profile import ItemCategory, ProfileStatus
from hiremate_ai.db.profile_store import NewItem
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

AGENT = "assessment"
MAX_RETRIES = 2
"""검사를 통과하지 못한 항목만 다시 쓰게 하는 횟수 (v8 근거 원문 대조)."""

NO_MATERIAL = "평가 제출물 본문이 없어 강점 · 약점을 확인하지 못했어요"

SYSTEM = f"""채용 담당자가 볼 평가 전형 자료에서 지원자의 강점과 약점을 뽑는다.
- 자료에 적힌 내용만으로 쓴다. 자료에 없는 경험, 숫자, 평가를 지어내지 않는다.
- 항목마다 evidence에 자료 원문 한 문장을 글자 그대로 옮기고, source에는 그 자료의 label을 그대로 적는다.
- 약점은 부족해 보이는 점이나 담당자가 더 확인할 점이다. 근거가 약하면 항목을 만들지 않는다.
- 합격, 불합격, 순위, 채용 추천처럼 결정을 말하지 않는다. 결정은 담당자가 한다.
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 쓰지 않는다.
- content는 존댓말(~어요)로 짧게 쓴다.

{UNTRUSTED_RULE}"""


async def analyze_assessment(data: AssessmentInput, llm: LlmClient) -> AssessmentAnalysis:
    """지원자 한 명의 평가 자료를 분석해 프로필에 넣을 항목을 돌려준다. 저장하지 않고 채용 상태를 바꾸지 않는다.

    통과하지 못한 항목만 이유를 붙여 MAX_RETRIES번까지 다시 쓰게 하고, 그래도 남은 항목은 버린다.
    """
    items = score_checks(data)
    materials = materials_of(data)
    if not materials:
        no_material = NewItem(category=ItemCategory.CHECK, content=NO_MATERIAL, source=RESULT_SOURCE)
        return AssessmentAnalysis(status=ProfileStatus.CHECK, items=[*items, no_material], dropped=0)

    user = _user_prompt(data, materials)
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
            checked = checked_item(finding, materials)
            if isinstance(checked, str):
                failed.append((finding, checked))
            else:
                items.append(checked)
        if not failed:
            break
        prompt = _retry_prompt(user, failed)
    status = ProfileStatus.DONE if answered else ProfileStatus.FAILED
    return AssessmentAnalysis(status=status, items=_dedupe(items), dropped=len(failed))


async def _draft(llm: LlmClient, user: str) -> AssessmentDraft | None:
    with suppress(LlmOutputError):
        return await llm.structured(AssessmentDraft, agent=AGENT, system=SYSTEM, user=user)
    return None


def _user_prompt(data: AssessmentInput, materials: list[Material]) -> str:
    blocks = "\n\n".join(data_block("assessment", material.text, label=material.label) for material in materials)
    return f"전형: {data.stage_name}\n\n평가 자료:\n\n{blocks}"


def _retry_prompt(user: str, failed: list[tuple[FindingDraft, str]]) -> str:
    rejected = "\n".join(f"- {finding.model_dump_json()}\n  문제: {reason}" for finding, reason in failed)
    return (
        f"{user}\n\n앞서 쓴 항목 중 아래 항목이 검사를 통과하지 못했다:\n{rejected}\n"
        "이 항목들만 문제를 고쳐 다시 쓴다. 고칠 수 없는 항목은 빼고, 통과한 항목은 다시 쓰지 않는다."
    )


def _dedupe(items: list[NewItem]) -> list[NewItem]:
    return list({(item.category, item.content, item.evidence): item for item in items}.values())
