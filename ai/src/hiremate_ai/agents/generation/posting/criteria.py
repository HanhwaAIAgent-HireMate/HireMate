"""서류 평가 기준 초안. 공고 작성 화면의 평가 기준 AI 초안에서 자격 요건 · 우대 사항 한 항목의 유형과 판정 기준을 쓴다.

초안은 HR이 보고 고쳐 저장해야 기준이 된다. 서류 평가 AI는 저장한 기준으로만 판정한다.
항목마다 따로 묻되 앞부분(지금 공고)을 같게 둬서, 여러 항목을 이어서 물을 때 모델이 앞부분을 다시 읽지 않는다.

- 항목 문장에 없는 자격증 이름은 버린다. 모델이 "관련 자격증"을 정보처리기사 같은 이름으로 채우곤 한다 (규칙 7).
- 판정 기준이 비면 공고 문장 그대로 확인하는 기준으로 채운다. 서류 평가 AI가 기준이 없을 때 쓰는 문장과 같다.
- 근거 NCS 능력단위가 있으면 정의와 수행준거를 참고로 보여 준다.
"""

import re

from pydantic import BaseModel, Field

from hiremate_ai.agents.generation.posting.reviser import AGENT
from hiremate_ai.contract import ContractModel, CriterionCategory, CriterionType, PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.tools.ncs import unit_by_code

CATEGORY_LABELS = {CriterionCategory.QUALIFICATION: "자격 요건", CriterionCategory.PREFERENCE: "우대 사항"}
NCS_CRITERIA = 6
"""참고로 보여 줄 수행준거 수. 판정 기준 한 항목에 이 정도면 충분하고, 많으면 작은 모델이 느려진다."""


class CriterionDraft(ContractModel):
    """평가 항목 하나의 초안 (ai.PostingCriteriaAgent.CriterionDraft). partial은 복합 경험형에만 있다."""

    criterion_type: CriterionType
    met: str
    partial: str | None
    unmet: str
    certificates: list[str]


class RuleDraft(BaseModel):
    """모델에게서 받는 답. 모든 필드를 필수(값이 없으면 null)로 둔다. 선택 필드로 두면 작은 모델이 빼먹는다."""

    criterion_type: CriterionType = Field(description="CONDITION, SINGLE, COMPOSITE 중 하나")
    met: str = Field(description="충족 기준 한 문장")
    partial: str | None = Field(description="부분 충족 기준 한 문장. COMPOSITE가 아니면 null")
    unmet: str = Field(description="미충족 기준 한 문장")
    certificates: list[str] = Field(description="항목이 요구하는 자격증 이름. 자격증 조건이 아니면 빈 목록")


CRITERIA_SYSTEM = """너는 채용 공고의 자격 요건 · 우대 사항 한 항목을 서류 평가 기준으로 바꾸는 Posting Agent다.
서류 평가 AI가 이 기준으로 지원 서류를 판정한다. 기준은 초안이고 HR이 고쳐 확정한다.

유형 (criterion_type):
- CONDITION (조건형): 경력 기간 · 자격증 · 학위처럼 사실로 맞다 / 아니다를 보는 항목
- SINGLE (단일 경험형): 한 가지 능력이나 경험이 있다 / 없다로 보는 항목
- COMPOSITE (복합 경험형): "A와 B"처럼 여러 부분이 있어 일부만 있으면 부분 충족인 항목

규칙:
1. 판정 기준은 지원 서류(이력서 · 자기소개서 · 포트폴리오)에서 확인할 수 있는 사실로 한 문장씩 쓴다.
   충족은 "~을 본인이 했다", 미충족은 "~이 서류에서 확인되지 않는다"처럼 쓴다.
2. 항목 문장에 없는 조건(기간, 기술 이름, 수준)을 더하지 않는다.
   경력 기간 조건이면 충족 기준 끝에 "(기간은 경력표로 계산한다)"를 붙인다.
3. partial은 COMPOSITE일 때만 쓰고, 어느 부분만 확인되면 부분 충족인지 적는다. 다른 유형이면 null이다.
4. certificates에는 항목이 자격증 보유를 요구할 때 그 자격증 이름만 적는다. 아니면 빈 목록이다.
5. 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 기준에 넣지 않는다. 한국어로 쓴다."""

CRITERIA_STEP = "지금 할 일: 이 항목의 유형을 고르고 판정 기준을 쓴다."

_SPACES = re.compile(r"\s+")


async def draft_criterion(
    llm: LlmClient, posting: PostingContent, category: CriterionCategory, text: str, ncs_unit_code: str | None
) -> CriterionDraft:
    """공고 항목 하나의 유형과 판정 기준 초안을 쓴다."""
    draft = await llm.structured(
        RuleDraft,
        agent=AGENT,
        system=CRITERIA_SYSTEM,
        user=f"{_context(posting)}\n\n{_item_prompt(category, text, ncs_unit_code)}",
    )
    return _checked(draft, text)


def _checked(draft: RuleDraft, text: str) -> CriterionDraft:
    """비거나 맞지 않는 값을 고친다. 부분 충족 기준이 없는 복합 경험형은 단일 경험형으로 둔다."""
    partial = (draft.partial or "").strip()
    kind = draft.criterion_type
    if kind is CriterionType.COMPOSITE and not partial:
        kind = CriterionType.SINGLE
    return CriterionDraft(
        criterion_type=kind,
        met=draft.met.strip() or f"서류에서 '{text}'을 확인할 수 있다",
        partial=partial if kind is CriterionType.COMPOSITE else None,
        unmet=draft.unmet.strip() or f"서류에서 '{text}'이 확인되지 않는다",
        certificates=_named_certificates(draft.certificates, text),
    )


def _named_certificates(names: list[str], text: str) -> list[str]:
    """항목 문장에 이름이 있는 자격증만, 한 번씩. 공백 차이는 무시한다."""
    compact = _SPACES.sub("", text)
    kept = [name.strip() for name in names if name.strip() and _SPACES.sub("", name) in compact]
    return list(dict.fromkeys(kept))


def _context(posting: PostingContent) -> str:
    """모든 호출의 앞부분. 항목마다 같다."""
    lines = [f"지금 공고: {posting.title} ({posting.job_category}, {posting.career})", "주요 업무:"]
    lines += [f"- {duty}" for duty in posting.duties] or ["(없음)"]
    return "\n".join(lines)


def _item_prompt(category: CriterionCategory, text: str, ncs_unit_code: str | None) -> str:
    lines = [f"판정할 {CATEGORY_LABELS[category]}: {text.strip()}"]
    if ncs_unit_code and (unit := unit_by_code(ncs_unit_code)):
        criteria = [criterion for element in unit.elements for criterion in element.criteria][:NCS_CRITERIA]
        lines.append(f"참고 NCS 능력단위 {unit.name}: {unit.definition}")
        lines += [f"  · {criterion}" for criterion in criteria]
    return "\n".join([*lines, CRITERIA_STEP])
