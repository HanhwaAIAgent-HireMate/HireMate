"""면접관이 그대로 읽을 수 없는 모호한 비교·원칙 질문을 차단한다."""

import re

from hiremate_ai.contract import InterviewerRole


def clarity_problem(text: str) -> str | None:
    """자료에 비교 대상이 있어도 질문 문장에 이름이 없으면 면접관이 읽을 수 없다."""
    explicit_pair = bool(re.search(r"\S+\s*때와\s+.{1,35}?\s*때\s*중", text)) or any(
        not re.search(r"때|개발할|개발 시|적용하는", match.group())
        for match in re.finditer(r"\S{2,}(?:와|과)\s+.{1,35}?(?:중|비교|차이)", text)
    )
    if re.search(r"두\s*가지\s*(?:방법|방식|원칙|접근)|구체적인\s*원칙의\s*차이", text) and not explicit_pair:
        return "두 가지 방법이나 원칙 대신 비교 대상의 이름을 직접 써야 함"
    if "어느 쪽" in text and not explicit_pair:
        return "어느 쪽인지 판단할 비교 대상이 구체적으로 제시되지 않음"
    if re.search(r"(?:두\s*가지|두|양쪽|각각의)\s*(?:방법|방식|원칙|접근|선택지)|어느\s*쪽", text) and not re.search(
        r"(?:와|과|대비|대신|vs\.?|대\s+)\s*\S+|[AB]\s*안", text, re.IGNORECASE
    ):
        return "비교할 두 대상의 구체적인 이름이 질문에 없음"
    if re.search(
        r"(?:적용하는|적용한|따르는)\s*(?:구체적인\s*)?원칙(?:은|의|을)|원칙의\s*차이", text
    ) and not re.search(r"조건|상황|장애|실패|제약|예산|지연|충돌|일정", text):
        return "추상적인 원칙 대신 구체적인 상황과 판단 조건을 질문해야 함"
    return None


def checked_role(text: str, proposed: InterviewerRole) -> InterviewerRole:
    """명백한 기술 수행과 인사 주제의 잘못된 담당만 보정한다. 혼합·기타 주제는 모델 분류를 유지한다."""
    practical = bool(re.search(r"기술\s*스택|각\s*기술|코드|알고리즘|쿼리|인덱스|전환율|캠페인\s*성과", text))
    people = bool(re.search(r"협업|갈등|소통|피드백|가치관|신념|지원.*이유|이직.*계기|업무\s*태도", text))
    if practical and not people:
        return InterviewerRole.PRACTICAL
    if people and not practical:
        return InterviewerRole.HR
    return proposed
