"""평가 기준이 없는 공고 문장의 판정 기준 초안.

평가 기준이 저장되지 않은 공고 문장은 원래 '서류에서 ○○을 확인할 수 있다'는 공고 문장 그대로 충족 · 미충족만 판정했다.
그러면 무엇을 보면 충족인지 정의가 없어 해석이 실행마다 갈렸다(추상적인 '이해' 항목, 'A/B 구축' 같은 복합 항목).
그래서 그런 문장마다 모델이 판정 기준 초안(유형 · 충족 · 부분 충족 · 미충족)을 한 번 쓰고, 같은 공고의 지원자는 모두
같은 초안으로 판정한다. 초안은 채용마다 저장해 두고(분석 산출물), 담당자가 기준을 정하면 그 기준을 쓴다.
초안을 만들지 못하면 공고 문장 그대로 판정한다 (분석을 실패로 만들지 않는다).
"""

import logging
from collections.abc import Sequence
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.types import Criterion, EvaluationRules, Note
from hiremate_ai.contract import CriterionType, PostingContent
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.llm.recipe import analysis_recipe, fingerprint

log = logging.getLogger(__name__)

DRAFT_VERSION = "rubric-draft-6"
# 초안이 고른 해석을 담당자 확인으로 붙이는 알림 문구 (화면이 이 문구로 해석 확인 카드를 만든다)
CONFIRM_MARK = " 담당자 확인: "
DRAFT_SYSTEM = f"""너는 채용 공고의 자격요건 · 우대사항 문장마다 서류 판정 기준 초안을 쓴다. 지원자를 판정하지 않는다.
- criterion_type: SINGLE(한 가지 능력 · 경험), COMPOSITE(여러 부분을 함께 요구한다: 나열, 'A와 B', 'A/B'),
  CONDITION(경력 기간 · 자격증 · 학위처럼 있고 없음이 분명한 조건) 가운데 하나다.
- met는 충족으로 볼 서류 근거, unmet은 미충족으로 볼 서류 기록(하지 않았다고 적힘)이다. partial은 COMPOSITE일 때만
  일부만 한 경우를 쓰고, 그 밖에는 비운다. 모두 지원자 본인이 한 일을 기준으로 한 문장씩 쓴다.
- partial은 어느 부분이 확인되면 부분 충족인지 분명히 쓴다. 어느 부분이든 일부만 하면 부분 충족이면
  '요구한 것 가운데 일부만 본인이 했다'처럼 쓰고, 한쪽만 인정하면 'A는 했지만 B는 드러나지 않는다'처럼 쓴다.
- 공고 문장에 없는 조건(기간, 규모 수치, 특정 도구)을 더하지 않는다.
- 쉼표 · 빗금(/) · '와/과' · '및'으로 묶은 나열은 '또는' · '혹은' · '중 하나'가 없으면 적힌 것을 모두 요구한다.
  나열 끝에 '등'이 붙으면 적힌 것은 예시라서 그 가운데 하나만 해도 충족으로 쓴다 (SINGLE, 예: 'A, B 등 활용 경험'
  → A나 B 가운데 하나를 본인이 활용했다).
- 가운뎃점(·)은 기호만으로 정하지 않고 문맥으로 본다. 같은 종류의 기술 · 도구 · 수행 단계를 묶었으면 모두 요구하고
  (예: '설계·구현·운영 경험'), '중 하나'가 붙었으면 하나만 요구한다. 분야 · 도메인을 묶은 표기(예: '유통·커머스
  도메인')는 어느 한 분야의 경험을 충족으로 쓰고, 한 분야만으로 인정할지 confirm에 적는다.
- 분야 · 도메인 경험을 묻는 문장은 그 분야에서 채용 직무의 일(공고 주요 업무와 같은 종류의 일)을 한 경험을 충족
  근거로 쓰고, 그 분야의 다른 직무 경험(현장 근무 등)은 충족 근거가 아니라고 met에 함께 적는다. 이렇게 직무로
  좁혔다는 것도 confirm에 적는다.
- 규모를 나타내는 말(대용량, 대규모 등)이 붙은 경험은 COMPOSITE로 두고 두 부분을 함께 요구한다. ① 규모: 몰리는
  요청 · 늘어난 처리량이 병목 · 지연 · 오류의 원인으로 서류에 드러남 (기준선 수치로 정하지 않는다). ② 해결: 실서비스
  (실제 사용자가 쓰는 운영 환경)에서 본인이 그 병목 · 지연 · 오류를 분석하고 개선함 (개인 · 교육 과정 프로젝트, 부하
  테스트 환경은 아니다). partial은 둘 가운데 하나만 확인된 경우다.
- 이해 · 능력을 묻는 문장은 대상이 여럿이어도 나누지 않고 SINGLE로 두며, 그 이해 · 능력이 드러난 실제 작업(설계,
  구현, 결정과 그 이유)의 예를 met에 쓴다. 서류가 '원칙을 이해했다'고 따로 쓰지 않아도 그 작업이 근거다.
- confirm에는 공고 문장만으로 정할 수 없어 초안이 고른 해석을 담당자가 확정할 수 있게 한 문장으로 쓴다. 해석이
  하나뿐이면 비운다.

{UNTRUSTED_RULE}"""


class _Draft(BaseModel):
    number: int = Field(description="문장 번호 (1부터)")
    criterion_type: Literal["SINGLE", "COMPOSITE", "CONDITION"]
    met: str
    partial: str = ""
    unmet: str
    confirm: str = Field(default="", description="초안이 고른 해석 가운데 담당자가 확정할 점. 없으면 비운다")


class RubricDraft(BaseModel):
    """공고 문장 → 판정 기준 초안. 저장 · 다시 쓰기 단위다."""

    items: list[_Draft]


@runtime_checkable
class RubricDraftStore(Protocol):
    async def find_rubric_draft(
        self, *, company_id: UUID, recruitment_id: UUID, source_hash: str, recipe_hash: str
    ) -> RubricDraft | None: ...

    async def save_rubric_draft(
        self, draft: RubricDraft, *, company_id: UUID, recruitment_id: UUID, source_hash: str, recipe_hash: str
    ) -> None: ...


# 같은 프로세스에서 같은 공고 문장들의 초안을 다시 쓴다 (저장소가 없을 때도 지원자마다 초안이 달라지지 않게)
_drafts: dict[str, RubricDraft] = {}


def fallback_rules(text: str) -> EvaluationRules:
    """평가 기준이 없는 공고 문장을 그대로 판정할 때의 기준. 초안을 만들지 못했을 때도 쓴다."""
    return EvaluationRules(met=f"서류에서 '{text}'을 확인할 수 있다", unmet=f"서류에서 '{text}'이 확인되지 않는다")


def is_fallback(criterion: Criterion) -> bool:
    return criterion.evaluation_rules == fallback_rules(criterion.text)


async def draft_fallback_rules(
    llm: LlmClient,
    criteria: Sequence[Criterion],
    posting: PostingContent,
    *,
    company_id: UUID | None = None,
    recruitment_id: UUID | None = None,
    store: RubricDraftStore | None = None,
    notes: Sequence[Note] = (),
) -> tuple[tuple[Criterion, ...], tuple[Note, ...]]:
    """평가 기준이 없는 문장에만 초안을 붙인다. 그런 문장이 없으면 모델을 부르지 않는다.

    초안이 고른 해석(confirm)은 그 문장의 '평가 기준 없음' 알림 뒤에 담당자 확인으로 붙여 돌려준다.
    """
    targets = [criterion for criterion in criteria if is_fallback(criterion)]
    if not targets:
        return tuple(criteria), tuple(notes)
    texts = [f"{criterion.category.value}: {criterion.text}" for criterion in targets]
    recipe = analysis_recipe(llm)
    source = fingerprint({"texts": texts, "duties": posting.duties})
    recipe_hash = fingerprint({"version": DRAFT_VERSION, "llm": recipe, "system": DRAFT_SYSTEM})
    key = f"{source}:{recipe_hash}"
    draft = _drafts.get(key)
    can_store = store is not None and company_id is not None and recruitment_id is not None and recipe is not None
    if draft is None and can_store:
        assert store is not None and company_id is not None and recruitment_id is not None
        draft = await store.find_rubric_draft(
            company_id=company_id, recruitment_id=recruitment_id, source_hash=source, recipe_hash=recipe_hash
        )
    if draft is None:
        try:
            draft = await _ask_draft(llm, texts, posting)
        except Exception:  # 초안이 없어도 공고 문장 그대로 판정할 수 있다
            log.warning("판정 기준 초안을 만들지 못해 공고 문장 그대로 판정한다", exc_info=True)
            return tuple(criteria), tuple(notes)
        if can_store:
            assert store is not None and company_id is not None and recruitment_id is not None
            await store.save_rubric_draft(
                draft, company_id=company_id, recruitment_id=recruitment_id, source_hash=source, recipe_hash=recipe_hash
            )
    _drafts[key] = draft
    by_number = {item.number: item for item in draft.items}
    drafted = {criterion.criterion_id: by_number.get(number) for number, criterion in enumerate(targets, start=1)}
    applied = tuple(_apply(criterion, drafted.get(criterion.criterion_id)) for criterion in criteria)
    confirms = {
        criterion.text: item.confirm.strip()
        for criterion in targets
        if (item := drafted.get(criterion.criterion_id)) is not None and item.confirm.strip()
    }
    return applied, tuple(_with_confirm(note, confirms) for note in notes)


def _with_confirm(note: Note, confirms: dict[str, str]) -> Note:
    for text, confirm in confirms.items():
        if note.text.startswith(f"'{text}'") and CONFIRM_MARK not in note.text:
            return note.model_copy(update={"text": f"{note.text}{CONFIRM_MARK}{confirm}"})
    return note


async def _ask_draft(llm: LlmClient, texts: list[str], posting: PostingContent) -> RubricDraft:
    listing = "\n".join(f"{number}. {text}" for number, text in enumerate(texts, start=1))
    user = (
        "공고 주요 업무:\n" + data_block("duties", "\n".join(posting.duties) or "(없음)") + "\n\n"
        "판정 기준을 쓸 문장:\n" + data_block("criteria", listing)
    )
    return await ask(llm, RubricDraft, system=DRAFT_SYSTEM, user=user)


def _apply(criterion: Criterion, draft: _Draft | None) -> Criterion:
    if draft is None or not draft.met.strip() or not draft.unmet.strip():
        return criterion
    kind = CriterionType(draft.criterion_type)
    partial = draft.partial.strip() if kind == CriterionType.COMPOSITE else ""
    rules = EvaluationRules(met=draft.met.strip(), partial=partial or None, unmet=draft.unmet.strip())
    return criterion.model_copy(update={"criterion_type": kind, "evaluation_rules": rules})
