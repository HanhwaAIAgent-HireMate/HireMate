"""모델이 만든 공고 수정안 검사. 다시 쓰게 할 이유를 찾는다. 원래 공고에 있던 내용은 검사하지 않고 바뀐 칸만 본다.

길이 제한은 backend PostingContentRequest · stages 테이블과 같다. 넘으면 HR이 적용할 때 실패한다.
"""

import re

from hiremate_ai.agents.generation.posting.types import StageDraft
from hiremate_ai.agents.guardrails import blocked_attribute
from hiremate_ai.contract import PostingContent

TEXT_LIMITS = {
    "title": 200,
    "job_category": 100,
    "employment_type": 50,
    "career": 50,
    "location": 100,
    "position": 50,
    "education": 50,
    "work_hours": 100,
    "salary": 100,
    "intro": 5000,
}
ITEM_LIMITS = {"duties": 300, "qualifications": 300, "preferred": 300, "benefits": 100}
MAX_ITEMS = 30
STAGE_NAME_LIMIT = 50

JUDGED_FIELDS = ("qualifications", "preferred")
"""지원자를 거르는 기준이 되는 칸. 차별 조건이 들어가면 안 된다 (규칙 6)."""

# 히라가나 · 가타카나, 한자(확장 A, 통합, 호환). 모델이 한국어 문장에 섞어 쓴다.
# 생김새가 같은 다른 글자가 섞이지 않게 코드 포인트로 적는다
_FOREIGN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]+")
# 금액. 회사가 주지 않은 연봉 · 수당을 지어내는지 본다
_MONEY = re.compile(r"\d[\d,.]*\s*(?:천|만|억)?\s*원")


def blocked_terms(content: PostingContent, changed: list[str]) -> list[str]:
    """바뀐 자격 요건 · 우대 사항에 들어간 차별 조건 낱말."""
    terms = []
    for name in JUDGED_FIELDS:
        if name in changed:
            terms += [term for item in getattr(content, name) if (term := blocked_attribute(item))]
    if "roles" in changed:
        terms += [
            term
            for role in content.roles
            for item in [role.name, role.career, *role.qualifications, *role.preferred]
            if (term := blocked_attribute(item))
        ]
    return list(dict.fromkeys(terms))


def problems(
    content: PostingContent, changed: list[str], stages: list[StageDraft] | None, labels: dict[str, str], source: str
) -> list[str]:
    """작성 규칙을 어긴 곳. 비어 있으면 통과다. source는 모델에게 준 정보로, 금액을 지어냈는지 볼 때 쓴다."""
    found = []
    given = _compact(source)
    if not content.title:
        found.append("채용명이 비어 있다")
    for name in changed:
        if name == "roles":
            names = [role.name.strip() for role in content.roles]
            if len(names) != len(set(names)):
                found.append("직무 이름이 중복된다")
            for role in content.roles:
                for line in [*role.duties, *role.qualifications, *role.preferred]:
                    if len(line) > 300:
                        found.append("직무별 모집 내용이 한 줄 300자를 넘는다")
                    if any(_compact(money) not in given for money in _MONEY.findall(line)):
                        found.append("직무별 모집 내용에 주어진 정보에 없는 금액을 썼다")
            continue
        label = labels[name]
        value = getattr(content, name)
        if value is None or isinstance(value, int):
            continue  # 채용 인원은 숫자로 읽을 때 한도를 본다
        if isinstance(value, str):
            if len(value) > TEXT_LIMITS[name]:
                found.append(f"{label} 칸이 {TEXT_LIMITS[name]}자를 넘는다")
            texts = [value]
        else:
            if len(value) > MAX_ITEMS:
                found.append(f"{label} 항목이 {MAX_ITEMS}개를 넘는다")
            if any(len(item) > ITEM_LIMITS[name] for item in value):
                found.append(f"{label} 항목 하나가 {ITEM_LIMITS[name]}자를 넘는다")
            texts = value
        if foreign := [match for text in texts for match in _FOREIGN.findall(text)]:
            found.append(f"{label}에 한국어가 아닌 문자(한자, 일본어)를 썼다: {', '.join(foreign)}")
        if invented := [money for text in texts for money in _MONEY.findall(text) if _compact(money) not in given]:
            found.append(f"{label}에 주어진 정보에 없는 금액을 썼다: {', '.join(invented)}")
    if stages is not None:
        found += _stage_problems(stages)
    return found


def _stage_problems(stages: list[StageDraft]) -> list[str]:
    found = []
    if not stages:
        found.append("전형이 하나도 없다")
    names = [stage.name for stage in stages]
    if any(not name for name in names):
        found.append("이름이 빈 전형이 있다")
    if any(len(name) > STAGE_NAME_LIMIT for name in names):
        found.append(f"전형 이름이 {STAGE_NAME_LIMIT}자를 넘는다")
    if duplicated := sorted({name for name in names if names.count(name) > 1}):
        found.append(f"같은 이름의 전형이 여러 번 있다: {', '.join(duplicated)}")
    return found


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
