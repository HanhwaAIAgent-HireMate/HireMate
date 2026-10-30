"""리포트 요청의 판단 규칙. Root는 리포트 내용을 쓰지 않고 대상과 전형만 정해 backend에 넘긴다.

backend가 Report Agent에게 맡겨 만들고 화면이 카드로 연다. 이전 전형 리포트는 backend가 저장된 것을 연다.
"""

import re
from uuid import UUID

from hiremate_ai.agents.root.types import ChatContext

MIN_COMPARED = 2
MAX_COMPARED = 5
"""지원자 비교 리포트의 대상 수. backend도 같은 범위로 다시 확인한다."""

COMPARE_COUNT = (
    f"비교 리포트는 현재 전형 지원자 {MIN_COMPARED}~{MAX_COMPARED}명으로 만들어요. "
    "@이름으로 지정하거나 선택 지원자에 넣어 주세요."
)
COMPARING = "{names} 비교 리포트를 만들고 있어요."
OPENING_STAGE = "{stage} 결과 리포트를 열어요."
NO_PREVIOUS_STAGE = "지금이 첫 전형이라 이전 전형 리포트가 없어요."
UNKNOWN_STAGE = "어느 전형의 리포트인지 알려 주세요. 이 채용의 전형: {names}"
ANSWER_HINT = "리포트, 그래프, 정리 자료를 말하지 않은 비교와 분석은 answer로 답하세요."
REPORT_HINT = (
    "리포트나 그래프를 바라는 요청이에요. report로 내세요. 지원자 비교는 view=compare와 scope, "
    "전형 결과 리포트는 view=stage와 stage예요."
)

_REPORT_NOUN = re.compile(r"리포트|레포트|보고서")
_VISUAL = re.compile(r"그래프|차트|도표|시각화")
"""그림으로 보고 싶다는 말. Chat 답은 글이라 그림은 리포트로만 그린다."""
_REPORT_VERB = re.compile(r"만들|뽑|생성|작성|정리|써|줘|주세요|보여")
_REPORT_CUE = re.compile(r"리포트|레포트|보고서|그래프|차트|도표|시각화|한눈에|한 눈에|정리|자료|문서")
"""리포트를 바란다는 단서. 하나도 없는 '두 사람 비교해줘'는 글로 답할 비교다."""
_PREVIOUS_STAGE = re.compile(r"^(?:이전|지난|직전|앞)\s*(?:단계|전형)?$")
"""전형 이름 대신 쓴 '이전 전형'. 현재 전형 바로 앞 전형이다."""


def asks_report(message: str) -> bool:
    """리포트를 만들어 달라는 요청인가. '리포트'나 그림(그래프 · 차트)과 만들기 · 보기 동사가 같이 있어야 한다.

    '한눈에 정리'처럼 뉘앙스로만 리포트를 바라는 요청은 계획 단계 모델이 판단한다. 여기서는 놓치면 안 되는 말만 잡는다.
    """
    return bool((_REPORT_NOUN.search(message) or _VISUAL.search(message)) and _REPORT_VERB.search(message))


def report_stage(name: str, context: ChatContext) -> UUID | str:
    """리포트를 볼 전형. 전형 이름이나 '이전 전형'(현재 전형 바로 앞 전형)으로 고른다.

    고를 수 없으면 되묻기 문장을 돌려준다.
    """
    if _PREVIOUS_STAGE.match(name.strip()):
        if context.stage_index == 0:
            return NO_PREVIOUS_STAGE
        return context.stages[context.stage_index - 1].id
    matched = [stage for stage in context.stages if name.replace(" ", "") in stage.name.replace(" ", "")]
    if len(matched) != 1:
        return UNKNOWN_STAGE.format(names=", ".join(stage.name for stage in context.stages))
    return matched[0].id


def wants_report(message: str) -> bool:
    """리포트를 바랄 만한 단서가 있는가. 뉘앙스 요청('한눈에 보게 정리해줘')도 단서가 있다."""
    return bool(_REPORT_CUE.search(message))
