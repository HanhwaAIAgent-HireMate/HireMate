"""카드의 '눈여겨볼 점': 검토를 통과한 본인 경험을 같은 일끼리 묶어 핵심 기여 1~2개로 쓴다.

경험 목록은 서류 문장 하나에 하나씩 뽑혀서, 같은 프로젝트의 구현 · 운영 · 성과가 따로 나열되고 성과 수치가 빠지곤 했다.
모델은 묶음의 제목과 한 문장만 쓰고, 근거는 경험 번호로 고른다. 코드는 없는 번호 · 본인이 아닌 경험을 근거로 쓴 묶음과
근거에 없는 숫자를 쓴 묶음을 뺀다. 묶음이 하나도 남지 않으면 예전처럼 경험 문장을 그대로 쓴다(present.notable_facts).
"""

import re
from collections.abc import Sequence

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.judge import baseless_number, paragraphs
from hiremate_ai.agents.analysis.application.types import Actor, Fact, Note
from hiremate_ai.contract import ApplicantDocument
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

HIGHLIGHT_LIMIT = 2
HIGHLIGHT_SYSTEM = f"""지원자 서류에서 뽑은 본인 경험 목록을 HR이 눈여겨볼 핵심 기여 1~2개로 묶는다.
- 같은 프로젝트 · 같은 서비스의 경험(구현, 운영, 개선, 성과)은 하나로 묶는다. 서로 다른 일만 따로 둔다.
  같은 프로젝트의 기술 작업을 두 묶음으로 나누지 않는다. 다른 팀 · 사람과 기준을 맞추거나 조율한 경험은 기술 작업과
  같은 프로젝트여도 따로 한 묶음으로 둔다. 회사 업무와 개인 프로젝트처럼 다른 프로젝트 · 환경의 일은 주제가 같아도
  한 묶음으로 합치지 않는다.
- 성과 수치가 있는 경험은 그 수치를 만든 일과 같은 묶음에 넣는다. 수치에는 측정 조건(예: 모의 장애, 테스트 환경,
  동일 부하)과 누가 만든 방법인지(예: 본인이 마련한 절차)를 원문대로 함께 쓴다. 실제 운영 성과처럼 읽히게 쓰지 않는다.
- title은 무엇을 했는지 20자 안팎의 명사구다. 예: '정산 배치 개발 · 성능 개선', '물류팀과 출고 기준 조율'.
- detail은 본인이 한 일을 50자 안팎의 한 문장으로 쓴다. 수치는 넣지 않는다. 예: '배치 코드를 작성하고 쿼리를 나눠 처리'.
- metric은 그 묶음의 정량 지표다. 원문 숫자 그대로, 측정 조건과 함께 짧게 쓴다. 예: '처리 시간 40분 → 12분',
  '모의 장애 복구 시간 30분 → 10분'. 성과 수치가 있으면 꼭 쓰고, 없으면 비운다.
- sources는 묶은 경험 번호다 (예: F1, F3). 목록에 없는 번호를 지어내지 않는다. 묶음마다 [본인] 경험이 하나는 있어야
  한다. [불분명] 경험은 같은 일의 [본인] 경험과 묶을 때만 쓴다 (예: 주어 없이 적힌 그 일의 성과 수치).
- 경험 목록에 없는 사실을 더하지 않는다. 팀 성과를 본인 성과로 바꿔 쓰지 않는다. '제가' 같은 1인칭을 쓰지 않고
  '본인이 마련한 절차'처럼 쓴다.

{UNTRUSTED_RULE}"""


class _Highlight(BaseModel):
    title: str
    detail: str
    metric: str = ""
    sources: list[str] = Field(default=[], description="묶은 경험 번호 (F1, F3)")


class _Highlights(BaseModel):
    items: list[_Highlight]


async def highlight(llm: LlmClient, facts: Sequence[Fact], documents: Sequence[ApplicantDocument] = ()) -> list[Note]:
    """본인 경험이 둘 이상일 때만 모델에 묻는다. 하나뿐이면 묶을 것이 없다.
    주어 없이 적힌 성과 문장('응답 시간이 줄었다')은 본인 여부가 불분명으로 뽑혀서, 불분명한 경험도 본인 경험과 묶을
    후보로 넘긴다. 팀 경험은 넘기지 않는다.
    """
    numbered = [
        (number, fact)
        for number, fact in enumerate(facts, start=1)
        if fact.actor in (Actor.SELF, Actor.UNCLEAR) and fact.supported
    ]
    if sum(fact.actor == Actor.SELF for _, fact in numbered) < 2:
        return []
    listing = "\n".join(
        f"F{number}. [{_ACTOR[fact.actor]}] {fact.statement} (근거: {_quote(fact)})" for number, fact in numbered
    )
    answer = await ask(llm, _Highlights, system=HIGHLIGHT_SYSTEM, user=data_block("facts", listing))
    return check_highlights(dict(numbered), answer.items, documents)


def check_highlights(
    facts: dict[int, Fact], items: Sequence[_Highlight], documents: Sequence[ApplicantDocument] = ()
) -> list[Note]:
    """근거 번호가 넘긴 경험을 가리키고 본인 경험이 있으며, 내용 · 지표의 숫자가 모두 근거에 있는 묶음만 남긴다.

    지표에서 빠진 원문의 단서(괄호 속 측정 조건 · 다른 효과)는 다시 붙이고, 근거 문단이 공동 작업이라고 적었는데 본인
    역할이 없으면 내용에 공동 작업을 밝힌다 (팀 성과가 본인 성과처럼 보이지 않게).
    """
    notes: list[Note] = []
    for item in items:
        chosen = [facts[number] for number in _numbers(item.sources) if number in facts]
        title, detail, metric = (" ".join(text.split()) for text in (item.title, item.detail, item.metric))
        # 기준값 없는 수치('300% 개선')는 성과로 보이지 않는다 (확인할 점에 주의 표시로 따로 보인다)
        if baseless_number(metric):
            metric = ""
        if not any(fact.actor == Actor.SELF for fact in chosen) or not title or not detail:
            continue
        grounds = _compact(" ".join(f"{fact.statement} {_quote(fact)}" for fact in chosen))
        if any(number not in grounds for number in re.findall(r"\d+(?:\.\d+)?", f"{detail} {metric}")):
            continue
        metric = _with_conditions(metric, chosen)
        team, role, own = _team(chosen, documents, f"{title} {detail}")
        if team and role:
            detail = f"{detail.rstrip('. ')} ({team} 프로젝트 · {role})"
        elif team and own:
            detail = f"{detail.rstrip('. ')} ({team} 프로젝트)"
        elif team:
            detail = f"{detail.rstrip('. ')} ({team} 공동 작업, {TEAM_ROLE_CHECK})"
        # 묶은 경험이 나온 서류를 모두 출처로 남긴다 (성과 수치가 다른 서류에 있을 수 있다)
        labels = dict.fromkeys(quote.document.label for fact in chosen for quote in fact.quotes)
        source = ", ".join(labels) or "제출 서류"
        text = f"{title} — {detail.rstrip('. ')}" + (f". {metric}" if metric else "")
        notes.append(Note(text=text, source=source, title=title, detail=detail, metric=metric))
    return notes[:HIGHLIGHT_LIMIT]


_ACTOR = {Actor.SELF: "본인", Actor.UNCLEAR: "불분명"}
TEAM_ROLE_CHECK = "본인 역할 확인 필요"
# 측정 조건 · 다른 효과를 밝힌 괄호 단서
_CONDITION = re.compile(r"\(([^()]*(?:포함|섞|영향|기준|환경|테스트|로컬|모의|당시|측정|부하|가정)[^()]*)\)")
# 공동 작업 표현: '3명이 함께', '팀원 4명과', '인원: 3명', '공동 개발'
_TEAM = re.compile(
    r"(\d+)\s*명(?:이|과|의|으로)?\s*(?:함께|같이|공동|팀)|팀원\s*(\d+)\s*명|인원\s*[:：]?\s*[^\d/|\n]{0,10}?(\d+)\s*명"
    r"|공동\s*(?:으로|작업|개발|구축)"
)
# 본인 역할을 밝힌 이력서 표의 칸: '역할: 설계 · 구현 리드', '본인 참여율 약 60%'
_ROLE = re.compile(r"역할\s*[:：]\s*([^|\n()]{2,30}?)\s*(?:\(|\||인원|$)")
_SHARE = re.compile(r"본인\s*참여율\s*약?\s*\d+\s*%")
# 이력서 · 포트폴리오의 프로젝트 줄 ('역할:' · '인원' 이 있는 줄)과, 같은 프로젝트로 볼 겹치는 낱말 수.
# PDF는 프로젝트 이름이 바로 위 줄에 있어 위 두 줄까지 함께 본다
_PROJECT_LINE = re.compile(r"역할\s*[:：]|인원\s*[:：]?\s*[^\d/|\n]{0,10}?\d+\s*명")
PROJECT_ABOVE = 2
PROJECT_BODY = 6
PROJECT_OVERLAP = 2
# 본인 행동을 1인칭으로 밝힌 표현: '제가 ~했습니다', '본인이 담당', '~을 맡아'
_OWN_ACTION = re.compile(r"제가|본인이|저는|담당(?:했|하며|하여|하고)|맡(?:았|아|은)")


def _with_conditions(metric: str, chosen: Sequence[Fact]) -> str:
    """지표가 나온 원문 문장의 괄호 단서가 지표에 없으면 붙인다 (예: '38초 → 21초' + '(보상 개편 효과 포함)')."""
    if not metric:
        return metric
    numbers = re.findall(r"\d+(?:\.\d+)?", metric)
    for fact in chosen:
        for quote in fact.quotes:
            sentence = " ".join(quote.sentence.split())
            if not numbers or not all(number in sentence for number in numbers):
                continue
            missing = [group for group in _CONDITION.findall(sentence) if _compact(group) not in _compact(metric)]
            if missing:
                return f"{metric} ({'; '.join(missing)})"
    return metric


def _team(chosen: Sequence[Fact], documents: Sequence[ApplicantDocument], topic: str) -> tuple[str, str, bool]:
    """2명 이상의 공동 작업이면 ('3명' 또는 '팀', 적힌 본인 역할, 본인 행동을 1인칭으로 밝혔는지).
    공동 작업이 아니면 ('', '', False)다.

    근거 문단과, 이력서 프로젝트 줄('역할:' · '인원:'이 있는 줄) 가운데 같은 프로젝트를 가리키는 줄을 본다.
    """
    quotes = [quote for fact in chosen for quote in fact.quotes]
    if not quotes or not documents:
        return "", "", False
    words = _words(f"{topic} {' '.join(fact.statement for fact in chosen)}")
    # 같은 프로젝트의 줄(이름 + 역할 · 인원)과 그 아래 설명 몇 줄. 찾으면 그 줄만 본다 (한 문단에 다른 프로젝트의
    # 인원 · 역할이 함께 있을 수 있다). 못 찾으면 근거 문단을 본다
    lines: list[str] = []
    bodies: list[str] = []
    for document in documents:
        rows = document.text.splitlines()
        for index, row in enumerate(rows):
            window = " ".join(rows[max(0, index - PROJECT_ABOVE) : index + 1])
            if _PROJECT_LINE.search(row) and len(words & _words(window)) >= PROJECT_OVERLAP:
                lines.append(window)
                bodies.append(" ".join(rows[index + 1 : index + 1 + PROJECT_BODY]))
    context = " / ".join(lines) if lines else paragraphs(quotes, documents, limit=None)
    found = _TEAM.search(context)
    if not found:
        return "", "", False
    size = next((group for group in found.groups() if group), None)
    if size is not None and int(size) < 2:
        return "", "", False
    found_role = _ROLE.search(context)
    share = _SHARE.search(context)
    role = (
        f"본인 역할: {' '.join(found_role.group(1).split())}"
        if found_role
        else (" ".join(share.group(0).split()) if share else "")
    )
    own = any(_OWN_ACTION.search(text) for text in [*(quote.sentence for quote in quotes), *bodies])
    return (f"{size}명" if size else "팀"), role, own


def _words(text: str) -> set[str]:
    return set(re.findall(r"[가-힣A-Za-z]{2,}", text))


def _numbers(sources: Sequence[str]) -> list[int]:
    return [int(match.group(1)) for source in sources if (match := re.fullmatch(r"\s*F(\d+)\s*", source.upper()))]


def _quote(fact: Fact) -> str:
    return fact.quotes[0].sentence if fact.quotes else ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
