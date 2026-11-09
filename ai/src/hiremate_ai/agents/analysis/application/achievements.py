"""지원자 단위 성과 장부: 서류 전체의 수치 성과를 한 번 정리하고, 성과마다 그 결과인 평가 항목을 정한다.

항목마다 따로 지표를 고르면 같은 성과가 항목마다 다르게 다뤄졌다 (한 항목에는 붙고 다른 항목에는 빠짐). 그래서 성과와
항목의 연결을 지원자마다 한 번만 정하고, 판정은 그 연결을 그대로 쓴다. 성과로 받는 것:
- 본인 행동 뒤에 좋아진 측정값이다 (전후 값이 원문 한 문장, 또는 이어진 두 문장에 있다). 나빠진 수치 · 감수한 대가는
  받지 않는다.
- 체감 · 추정치, 다른 사람 · 팀 · 업체 담당의 결과, 본인 조치 밖의 효과가 섞였다고 밝힌 수치는 받지 않는다.
모델이 표시한 값에 코드 검사를 겹치고(숫자가 원문 문장에 있는지, 체감 · 감수 표현), 검증 모델이 성과마다 한 번 더 본다.
화면 지표는 '무엇 전 → 후 (조건)'으로 코드가 만든다 (원문 문장을 통째로 쓰지 않는다).
"""

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.context import readable
from hiremate_ai.agents.analysis.application.extract import quotes_in
from hiremate_ai.agents.analysis.application.judge import paragraphs
from hiremate_ai.agents.analysis.application.review import Claim, ClaimReview
from hiremate_ai.agents.analysis.application.types import Achievement, Criterion, CriterionResult
from hiremate_ai.contract import ApplicantDocument, CriterionType, Verdict
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block, documents_block

LEDGER_SYSTEM = f"""너는 지원 서류 전체에서 수치 성과를 한 번에 정리하고, 성과마다 그 결과인 평가 항목을 정한다.
판정 · 점수는 매기지 않는다.

[성과]
- 지원자 본인의 행동 뒤에 바뀐 결과의 전후 값이다 (처리 · 소요 시간, 오류율, 건수, 정확도 · 재현율, 비용, 사용 비율 등).
  바뀌기 전 값과 바뀐 뒤 값이 모두 원문에 적힌 것만 뽑는다.
- 운영 · 팀 규모, 사용량 · 질의 수, 만든 것의 개수, 기간, 버전, 바꾼 설정값(크기 · 개수 · 주기를 얼마에서 얼마로
  바꿨다는 것은 행동이다)은 성과가 아니라 뽑지 않는다.
- improved: 결과가 좋아졌으면 true다. 줄어야 좋은 값(시간 · 오류 · 비용)이 늘었거나 늘어야 좋은 값(정확도 · 비율)이
  줄었으면 false다. 다른 것을 얻으려고 감수한 악화(예: 정확도를 위해 응답 시간이 늘었다)도 false다.
- estimated: 원문이 체감 · 추정 · 대략적인 값이라고 밝혔으면 true다 (예: '담당자 체감', '약 40분 → 10분 내외').
- owner: 본인이 한 일의 결과면 SELF다. 역할표 · 담당 표기 · 다른 문서에서 그 일을 다른 팀원 · 업체 · TF가
  맡았다고 적혀 있거나, 본인 기여를 나눌 수 없는 팀 · 조직 전체의 성과면 TEAM이다. 알 수 없으면 UNCLEAR다.
- mixed: 본인 조치 밖의 다른 효과(다른 사람이 따로 한 개선, 같은 기간의 다른 개편)가 섞였다고 원문이 밝혔으면 true다.
  본인이 함께 적용한 여러 조치의 결과, 본인이 제안 · 설계한 것을 다른 사람(업체 · 개발팀)이 구현해 생긴 결과는
  mixed가 아니고 owner도 SELF다.
- quotes: 전후 값이 든 원문 문장을 글자 그대로 옮긴다. 한 문장에 함께 있으면 그 문장 하나, 두 문장에 나뉘어
  있으면(예: '매일 40분이 걸렸다.' … '바꾼 뒤에는 12분이면 끝났다.') 두 문장을 옮긴다. 그 밖의 문장은 넣지 않는다.
- what: 무엇이 바뀌었는지 15자 안팎의 명사구다 (예: '검색 정답률', '건당 작성 시간').
- before · after: 원문의 숫자와 단위 그대로다 (예: '64%', '81%', '90분', '35분').
- action: 본인이 한 조치를 짧게 쓴다 (예: '조항 단위 청킹 + 하이브리드 검색').
- action_quotes: 본인이 그 조치를 했다고 적은 원문 문장 1~2개를 글자 그대로 옮긴다. 결과 문장과 다른 문단 · 문서에
  있어도 옮긴다 (검증이 조치와 결과를 함께 보게 한다). 결과 문장에 조치까지 적혀 있으면 비운다.
- condition: 측정 조건이 원문에 있으면 짧게 쓴다 (예: '120문항 기준', '2주 파일럿'). 없으면 비운다.
- 같은 성과가 여러 문서에 나오면 한 번만 쓴다.

[항목 연결]
- criteria에는 그 성과를 낸 본인의 일(조치 · 프로젝트)이 그 항목이 묻는 경험에 해당하면 항목 번호를 넣는다.
  한 성과가 여러 항목의 결과일 수 있다. 항목마다 빠짐없이 따져서 같은 성과는 같은 기준으로 연결한다.
- 예: Python으로 하이브리드 검색을 구현해 정답률이 올랐다 → 검색 품질 개선 항목, Python 개발 항목. 직접 만든
  평가셋으로 그 개선을 측정했다 → 평가 체계 항목에도 연결한다. 직접 만든 LLM 도구를 파일럿 · 현장에 적용해 작성
  시간이 줄었다 → LLM 서비스 개발 · 운영 항목, PoC · 확산 항목에도 연결한다.
- 이해 · 원리를 묻는 항목은 그 원리를 적용한 변경으로 생긴 결과만 연결한다. 도구 · 언어를 묻는 항목은 그 도구 · 언어로
  만든 변경의 결과만 연결하고, 같은 서비스의 다른 개선은 연결하지 않는다.
- 소통 · 협업 항목은 협의 · 조율 행동 자체로 바뀐 결과만 연결한다 (그 서비스 전체의 효과는 연결하지 않는다).
- 해당하는 항목이 없으면 비운다. 목록에 없는 번호를 쓰지 않는다.

{UNTRUSTED_RULE}"""

# 측정하지 않은 값이라고 밝힌 말
_ESTIMATED = re.compile(r"체감|추정|내외|어림|대략")
# 다른 것을 얻으려고 감수한 악화 ('응답 시간이 2.1초에서 2.9초로 늘었지만')
_TRADE_OFF = re.compile(r"(늘었|늘어났|증가했|길어졌|느려졌|떨어졌|낮아졌)[^.]{0,20}지만")
_NUMBER = re.compile(r"\d[\d,.]*")
# 성과 하나의 근거 문장 수 (전후 값이 두 문장에 나뉜 경우까지)
MAX_QUOTES = 2


class _Entry(BaseModel):
    what: str = Field(description="무엇이 바뀌었나 (15자 안팎 명사구)")
    before: str = Field(description="바뀌기 전 값. 원문 숫자 · 단위 그대로")
    after: str = Field(description="바뀐 뒤 값. 원문 숫자 · 단위 그대로")
    quotes: list[str] = Field(default=[], description="전후 값이 든 원문 문장 한두 개 (글자 그대로)")
    action: str = ""
    action_quotes: list[str] = Field(default=[], description="본인 조치를 적은 원문 문장 1~2개 (글자 그대로)")
    condition: str = ""
    owner: Literal["SELF", "TEAM", "UNCLEAR"] = "UNCLEAR"
    improved: bool = True
    estimated: bool = False
    mixed: bool = False
    criteria: list[str] = Field(default=[], description="이 성과가 결과인 평가 항목 번호")


class Ledger(BaseModel):
    results: list[_Entry] = []


def linkable(criterion: Criterion) -> bool:
    """성과를 연결할 수 있는 항목: 경험형(조건형 · 자격증 보유 조건이 아닌) 항목."""
    return criterion.criterion_type != CriterionType.CONDITION and not criterion.certificates


async def collect_achievements(
    llm: LlmClient, documents: Sequence[ApplicantDocument], criteria: Sequence[Criterion]
) -> list[Achievement]:
    """서류 전체를 한 번 보고 성과 장부를 만든다. 연결할 항목이나 읽을 서류가 없으면 모델을 부르지 않는다."""
    targets = [criterion for criterion in criteria if linkable(criterion)]
    usable = readable(documents)
    if not targets or not usable:
        return []
    listing = "\n".join(f"[{criterion.criterion_id}] {criterion.text}" for criterion in targets)
    user = (
        f"{documents_block(usable)}\n\n{data_block('criteria', listing)}\n\n"
        "서류의 수치 성과를 정리하고 성과마다 그 결과인 항목을 골라 줘."
    )
    ledger = await ask(llm, Ledger, system=LEDGER_SYSTEM, user=user)
    return accept(ledger.results, usable, {criterion.criterion_id for criterion in targets})


def accept(entries: Sequence[_Entry], documents: Sequence[ApplicantDocument], allowed: set[str]) -> list[Achievement]:
    """받을 수 있는 성과만 장부에 남긴다. 번호(R1 …)는 남긴 순서대로 매긴다."""
    kept: list[Achievement] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        if entry.owner != "SELF" or not entry.improved or entry.estimated or entry.mixed:
            continue
        found = quotes_in(documents, entry.quotes[:MAX_QUOTES])
        if not found or len(found) < len(entry.quotes[:MAX_QUOTES]):
            continue
        text = " ".join(quote.sentence for quote in found)
        if _ESTIMATED.search(text) or _TRADE_OFF.search(text):
            continue
        before, after, what = _clean(entry.before), _clean(entry.after), _clean(entry.what)
        if not what or not _written(before, text) or not _written(after, text) or before == after:
            continue
        key = (what, before, after)
        if key in seen:
            continue
        seen.add(key)
        kept.append(
            Achievement(
                id=f"R{len(kept) + 1}",
                what=what,
                before=before,
                after=after,
                action=_clean(entry.action),
                action_quotes=[
                    quote for quote in quotes_in(documents, entry.action_quotes[:MAX_QUOTES]) if quote not in found
                ],  # fmt: skip
                condition=_bare(_clean(entry.condition)),
                quotes=found,
                criteria=[criterion for criterion in dict.fromkeys(entry.criteria) if criterion in allowed],
            )
        )
    return kept


def display(achievement: Achievement) -> str:
    """화면 지표: '무엇 전 → 후 (조건)'."""
    shown = f"{achievement.what} {achievement.before} → {achievement.after}"
    return f"{shown} ({achievement.condition})" if achievement.condition else shown


def achievement_claims(achievements: Sequence[Achievement], documents: Sequence[ApplicantDocument] = ()) -> list[Claim]:
    """성과마다 한 번 검증한다 (항목마다가 아니다). 항목과의 연결이 아니라 성과 자체가 받을 수 있는지만 본다.
    결과 문장과 본인 조치 문장, 그 문장들이 나온 문단을 넘겨 조치 · 담당 · 측정 조건을 함께 보게 한다."""
    return [
        Claim(
            achievement.id,
            "다음은 지원자 본인의 행동 뒤에 좋아진 측정값이다 (체감 · 추정치가 아니고, "
            "다른 사람 · 팀 · 업체가 맡은 일의 결과가 아니며, "
            f"본인 조치 밖의 효과가 섞였다고 밝히지 않았다): {display(achievement)}"
            + (f". 본인 조치: {achievement.action}" if achievement.action else ""),
            [*achievement.quotes, *achievement.action_quotes],
            paragraphs([*achievement.quotes, *achievement.action_quotes], documents),
        )
        for achievement in achievements
    ]


def apply_achievement_reviews(
    achievements: Sequence[Achievement], reviews: dict[str, ClaimReview]
) -> list[Achievement]:
    """검증이 받쳐 주지 않는다고 본 성과는 장부에서 뺀다. 검증 답이 없는 성과는 둔다."""
    return [
        achievement
        for achievement in achievements
        if (review := reviews.get(achievement.id)) is None or review.verdict == "SUPPORTED"
    ]


def attach(
    results: Sequence[CriterionResult], achievements: Sequence[Achievement], *, metric: bool = True
) -> list[CriterionResult]:
    """충족 · 부분 충족인 경험형 항목에 장부에서 연결된 성과를 붙인다: 근거에 성과 문장을 더하고, 지표는 첫 성과로 쓴다.

    연결된 성과가 없거나 판정이 충족 · 부분 충족이 아니면 지표를 비운다. metric=False면 근거 문장만 더한다
    (검증 전에 판정 검증이 성과 문장까지 보게 할 때).
    """
    attached = []
    for result in results:
        linked = [achievement for achievement in achievements if result.criterion_id in achievement.criteria]
        usable = (
            result.verdict in (Verdict.MET, Verdict.PARTIAL)
            and result.criterion_type != CriterionType.CONDITION
            and result.certificate_status is None
        )
        if not usable:
            attached.append(result.model_copy(update={"metric": ""}) if metric else result)
            continue
        quotes = list(result.quotes)
        for achievement in linked:
            quotes += [quote for quote in achievement.quotes if quote not in quotes]
        update: dict[str, object] = {"quotes": quotes}
        if metric:
            update["metric"] = display(linked[0]) if linked else ""
        attached.append(result.model_copy(update=update))
    return attached


def _written(value: str, sentence: str) -> bool:
    """값의 숫자가 모두 근거 문장에 있는가 (공백 · 쉼표 차이는 무시)."""
    numbers = _NUMBER.findall(value)
    body = re.sub(r"[\s,]", "", sentence)
    return bool(numbers) and all(re.sub(r",", "", number).rstrip(".") in body for number in numbers)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _bare(text: str) -> str:
    """조건을 괄호 안에 넣을 수 있게, 바깥 괄호를 벗기고 짝이 맞지 않는 괄호는 뺀다."""
    while text.startswith("(") and text.endswith(")") and text.count("(") == text.count(")"):
        text = text[1:-1].strip()
    if text.count("(") != text.count(")"):
        text = text.replace("(", " ").replace(")", " ")
    return _clean(text)
