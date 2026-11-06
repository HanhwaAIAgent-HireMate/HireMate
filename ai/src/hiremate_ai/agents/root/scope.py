"""대상 범위. 계획 단계의 모델은 범위를 말로 정하고(멘션, 체크, 이름 등), 실제 지원자 목록은 코드가 펼친다.

이름은 전형 지원자 이름과 정확히 맞춘다. 없거나 동명이인이면 비슷한 사람으로 대신하지 않고 되묻는다.
탭은 T번호로 가리키고, 여러 탭이면 그 탭 모두에 선택된 지원자(교집합)로 펼친다.
"""

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hiremate_ai.agents.root.toolkit import resolve_ref
from hiremate_ai.agents.root.types import CandidateRow, ChatContext, ChatTab

type Source = Literal["mentions", "checked", "selected", "result", "subject", "all"]

NO_MENTIONS = "멘션한 지원자가 없어요. @로 지원자를 골라 다시 말씀해 주세요."
NO_CHECKED = "체크한 지원자가 없어요. 목록에서 체크한 뒤 다시 말씀해 주세요."
NO_SELECTED = "선택 지원자가 없어요."
NO_RESULT = "앞에서 찾은 지원자가 없어요. 찾을 조건을 말씀해 주세요."
NO_SUBJECT = "앞에서 다룬 지원자가 없어요. @로 지원자를 골라 다시 말씀해 주세요."
NOT_FOUND = "현재 전형에서 {names} 님을 찾을 수 없어요."
HOMONYM = "{name} 님이 {count}명이에요({who}). @로 한 명을 골라 주세요."
UNKNOWN_PICK = "가리킨 지원자를 확인하지 못했어요. @로 지원자를 골라 다시 말씀해 주세요."
UNKNOWN_TAB = "가리킨 탭을 확인하지 못했어요. 탭 이름으로 다시 말씀해 주세요."
EMPTY_TAB = "{name} 탭에 선택 지원자가 없어요."
NO_COMMON = "{names} 탭에 공통으로 선택된 지원자가 없어요."


class Scope(BaseModel):
    """요청이 말한 대상 범위. 비우면 범위를 말하지 않은 것이다."""

    model_config = ConfigDict(extra="forbid")

    sources: list[Source] = Field(
        default=[],
        description=(
            "멘션은 mentions, 체크한 사람은 checked, 선택 지원자는 selected, 앞 결과('그중')는 result, "
            "생략된 주어가 직전 대상이면 subject, 전형 전체는 all"
        ),
    )
    names: list[str] = Field(default=[], description="요청 본문에 이름으로 가리킨 지원자")
    picks: list[str] = Field(
        default=[], description="'두 번째 사람'처럼 순서로 가리킨 지원자의 C번호. 화면 요약에 나온 번호만"
    )
    tabs: list[str] = Field(
        default=[],
        description=(
            "탭의 선택 지원자를 가리키면 그 탭의 T번호. 화면 요약의 [탭]에 나온 번호만. "
            "두 개 이상이면 그 탭 모두에 공통으로 선택된 지원자다. "
            "'3개 탭'처럼 수만 말하면 현재 탭을 뺀, 선택 지원자가 있는 탭에서 고른다. "
            "그런 탭이 정확히 그 수면 되묻지 않고 모두 쓰고, 더 많을 때만 clarify로 묻는다"
        ),
    )

    @property
    def empty(self) -> bool:
        return not (self.sources or self.names or self.picks or self.tabs)


def expand_scope(
    scope: Scope, context: ChatContext, result: Sequence[str] | None, subject: Sequence[str]
) -> list[CandidateRow] | str:
    """sources 순서, names, picks 순으로 펼치고 중복은 처음 것만 남긴다. 펼칠 수 없으면 되묻기 문장을 돌려준다."""
    by_id = {row.application_id: row for row in context.candidates}
    rows: dict[UUID, CandidateRow] = {}

    def take(ids: Sequence[UUID]) -> None:
        for application_id in ids:
            if (row := by_id.get(application_id)) is not None:
                rows.setdefault(application_id, row)

    for source in scope.sources:
        match source:
            case "mentions":
                if not context.mentions:
                    return NO_MENTIONS
                take(context.mentions)
            case "checked":
                if not context.checked:
                    return NO_CHECKED
                take(context.checked)
            case "selected":
                selected = [row.application_id for row in context.candidates if row.selected]
                if not selected:
                    return NO_SELECTED
                take(selected)
            case "result":
                if not result:
                    return NO_RESULT
                take([UUID(application_id) for application_id in result])
            case "subject":
                if not subject:
                    return NO_SUBJECT
                take([UUID(application_id) for application_id in subject])
            case "all":
                take(list(by_id))
    missing: list[str] = []
    for name in scope.names:
        same = [row for row in context.candidates if row.name == name.strip().lstrip("@")]
        if len(same) > 1:
            return HOMONYM.format(name=same[0].name, count=len(same), who=", ".join(_who(row) for row in same))
        if not same:
            missing.append(name)
            continue
        take([same[0].application_id])
    if missing:
        return NOT_FOUND.format(names=", ".join(missing))
    for ref in scope.picks:
        row = resolve_ref(context, ref)
        if row is None:
            return UNKNOWN_PICK
        take([row.application_id])
    if scope.tabs:
        common = common_selection(context, scope.tabs)
        if isinstance(common, str):
            return common
        take(common)
    return list(rows.values())


def tab_ref(index: int) -> str:
    """화면 요약에서 탭을 가리키는 번호. 탭 순서로 T1부터 매긴다."""
    return f"T{index + 1}"


def resolve_tab(context: ChatContext, ref: str) -> ChatTab | None:
    """탭 번호(T2, t2, 2)를 탭으로 바꾼다. 없는 번호면 None."""
    value = ref.strip().upper().removeprefix("T")
    if not value.isdigit():
        return None
    index = int(value)
    return context.tabs[index - 1] if 1 <= index <= len(context.tabs) else None


def common_selection(context: ChatContext, refs: Sequence[str]) -> list[UUID] | str:
    """가리킨 탭 모두에 선택된 지원자. 첫 탭의 선택 순서를 따르고 현재 전형 지원자만 남긴다."""
    tabs: list[ChatTab] = []
    for ref in refs:
        tab = resolve_tab(context, ref)
        if tab is None:
            return UNKNOWN_TAB
        if tab not in tabs:
            tabs.append(tab)
    known = {row.application_id for row in context.candidates}
    for tab in tabs:
        if not any(application_id in known for application_id in tab.application_ids):
            return EMPTY_TAB.format(name=tab.name)
    rest = [set(tab.application_ids) for tab in tabs[1:]]
    common = [
        application_id
        for application_id in tabs[0].application_ids
        if application_id in known and all(application_id in other for other in rest)
    ]
    if not common:
        return NO_COMMON.format(names=", ".join(tab.name for tab in tabs))
    return common


def _who(row: CandidateRow) -> str:
    career = (
        "경력 알 수 없음"
        if row.career_years is None
        else "신입"
        if row.career_years == 0
        else f"경력 {row.career_years}년"
    )
    return f"{career} · {row.last_company}" if row.last_company else career
