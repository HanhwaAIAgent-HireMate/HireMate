"""질문 대상 확인: @멘션, 문장 속 이름, 체크한 지원자. 모델이 아니라 코드가 정한다 (기획 §11)."""

from dataclasses import dataclass

from hiremate_ai.agents.root.types import CandidateRow, ChatContext

# 이름을 찾은 자리를 지워 짧은 이름이 긴 이름 안에서 다시 잡히지 않게 한다
_FOUND = "\0"


@dataclass(frozen=True)
class Targets:
    """대상 지원자(후보 순서)와, 멘션 없이 이름만으로는 누구인지 정할 수 없는 이름."""

    rows: list[CandidateRow]
    ambiguous: list[str]


def resolve(context: ChatContext) -> Targets:
    """멘션한 지원자와 문장에 이름이 그대로 있는 지원자. 현재 전형에 없는 id는 버린다 (규칙 4).

    멘션한 지원자와 같은 이름은 멘션한 사람만 쓴다. 그 밖에 같은 이름이 둘 이상이면 고르지 않고 ambiguous에 넣는다.
    """
    by_id = {row.application_id: row for row in context.candidates}
    chosen = {application_id for application_id in context.mentions if application_id in by_id}
    mentioned_names = {by_id[application_id].name for application_id in chosen}

    ambiguous = []
    for name in _names_in(context.message, {row.name for row in context.candidates}):
        if name in mentioned_names:
            continue
        same = [row for row in context.candidates if row.name == name]
        if len(same) > 1:
            ambiguous.append(name)
        else:
            chosen.add(same[0].application_id)
    return Targets(rows=[row for row in context.candidates if row.application_id in chosen], ambiguous=ambiguous)


def checked(context: ChatContext) -> list[CandidateRow]:
    """체크한 지원자. 현재 전형에 없는 id는 버린다."""
    ids = set(context.checked)
    return [row for row in context.candidates if row.application_id in ids]


def _names_in(message: str, names: set[str]) -> list[str]:
    """문장에 있는 이름. 긴 이름부터 찾고 찾은 자리를 지운다."""
    found = []
    rest = message
    for name in sorted(names, key=len, reverse=True):
        if name and name in rest:
            found.append(name)
            rest = rest.replace(name, _FOUND)
    return found
