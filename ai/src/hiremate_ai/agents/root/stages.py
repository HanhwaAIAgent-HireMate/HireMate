"""전형 구성과 전형 자료의 상태. 아직 진행하지 않은 전형의 자료를 없는 자료로 말하지 않게 한다.

평가 결과와 면접 기록은 그 전형을 진행해야 생긴다. 첫 서류 전형에서 면접 기록이 없는 것은 부족한 점이 아니다.
"""

import re
from enum import Enum

from hiremate_ai.agents.root.types import ChatContext, ChatStage, StageStatus
from hiremate_ai.contract import StageType

STAGE_LABELS = {StageType.DOCUMENT: "서류", StageType.ASSESSMENT: "평가", StageType.INTERVIEW: "면접"}
STATUS_LABELS = {
    StageStatus.PENDING: "시작 전",
    StageStatus.ACTIVE: "진행 중",
    StageStatus.CONFIRMED: "결과 확정",
    StageStatus.DONE: "종료",
}
NOT_YET = "{label} 자료는 {order}번째 전형 '{name}'에서 생겨요. 아직 진행하지 않은 전형이라 없는 자료가 아니에요."

# 모델이 아직 진행하지 않은 전형의 자료를 부족한 점으로 쓴 문장 ("면접 기록이 없어 확인이 필요해요")
_GAP = r"\S*\s*(?:아직\s*)?(?:없|부족|부재|미입력|확인할\s*수\s*없|확인되지\s*않|확인이\s*안)"
_LATER_GAPS = {
    StageType.ASSESSMENT: re.compile(
        rf"(?<!서류)(?<!서류\s)(?:평가|과제|코딩\s*테스트)\s*(?:기록|결과|점수|자료|제출물){_GAP}"
    ),
    StageType.INTERVIEW: re.compile(
        rf"면접\s*(?:기록|답변|결과|자료|내용){_GAP}|면접(?:을|이)?\s*(?:아직\s*)?(?:진행하지|보지|치르지)\s*않|면접\s*전이"
    ),
}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class StageData(Enum):
    """현재 전형에서 본 한 종류 전형의 자료 상태."""

    NONE = "none"  # 이 채용에 그 종류 전형이 없다
    LATER = "later"  # 뒤 전형에만 있다. 자료가 아직 만들어지지 않았다
    CURRENT = "current"  # 현재 전형이다. 진행 중이면 아직 입력하지 않았을 수 있다
    EARLIER = "earlier"  # 앞 전형에 있다


def stage_data(context: ChatContext, kind: StageType) -> StageData:
    if context.stage_type is kind:
        return StageData.CURRENT
    if kind in context.previous_types:
        return StageData.EARLIER
    return StageData.LATER if next_stage(context, kind) else StageData.NONE


def reached(context: ChatContext, kind: StageType) -> bool:
    """그 종류 전형을 현재 전형이나 앞 전형에서 진행해 자료가 생길 수 있는가."""
    return stage_data(context, kind) in (StageData.CURRENT, StageData.EARLIER)


def next_stage(context: ChatContext, kind: StageType) -> tuple[int, ChatStage] | None:
    """현재 전형 뒤의 첫 그 종류 전형과 그 순서(1부터)."""
    for index, stage in enumerate(context.stages[context.stage_index + 1 :], start=context.stage_index + 2):
        if stage.type is kind:
            return index, stage
    return None


def not_yet(context: ChatContext, kind: StageType) -> str:
    """뒤 전형에서 생길 자료의 안내. 뒤에 그 종류 전형이 없으면 빈 글자다."""
    later = next_stage(context, kind)
    if later is None:
        return ""
    order, stage = later
    return NOT_YET.format(label=STAGE_LABELS[kind], order=order, name=stage.name)


def stage_plan(context: ChatContext) -> str:
    """전형 구성 한 줄. 예: 1. 서류 전형 (서류 · 진행 중, 현재) → 2. 1차 면접 (면접 · 시작 전)"""
    steps = []
    for index, stage in enumerate(context.stages):
        current = ", 현재" if index == context.stage_index else ""
        steps.append(f"{index + 1}. {stage.name} ({STAGE_LABELS[stage.type]} · {STATUS_LABELS[stage.status]}{current})")
    return " → ".join(steps)


def blames_later_stage(context: ChatContext, text: str) -> bool:
    """아직 진행하지 않았거나 이 채용에 없는 전형의 자료를 부족한 점으로 말하는가."""
    return any(pattern.search(text) for kind, pattern in _LATER_GAPS.items() if not reached(context, kind))


def without_later_gaps(context: ChatContext, text: str) -> str:
    """아직 진행하지 않은 전형의 자료를 부족한 점으로 말한 문장을 뺀다. 남는 문장이 없으면 빈 글자다."""
    sentences = _SENTENCE_END.split(text.strip())
    return " ".join(sentence for sentence in sentences if not blames_later_stage(context, sentence))
