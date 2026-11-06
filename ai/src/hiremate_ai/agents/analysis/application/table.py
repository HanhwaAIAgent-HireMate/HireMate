"""표 보기 부분: 열 이름(평가 기준 · 인재상의 짧은 키워드), 회사 글에서 뽑은 인재상 요소, 지원자별 인재상 판정을 만든다.

자격요건 · 우대사항 칸은 지원 접수 때 저장한 항목별 판정을 그대로 쓴다 (여기서 다시 판정하지 않는다).
인재상은 접수 분석에 없으므로, 저장된 분석의 경험(Fact)과 자기소개서 요약만 읽고 판정한다. 코드가 하는 것:
- 키워드: 개수가 다르거나 너무 긴 답은 쓰지 않고 문장을 잘라 만든다. 같은 문장 묶음은 프로세스 안에서 한 번만 묻는다.
- 인재상 요소: 회사 소개 · 조직 문화 글에 실제로 있는 문장을 근거로 든 요소만 남긴다. 같은 글은 한 번만 묻는다.
- 판정: 모델이 인재상의 행동 확인 · 일부 확인 기준으로 수준을 정하고 근거 번호를 고른다. 고른 근거가 목록에 없거나
  검토를 통과하지 못한 경험이면 확인 필요, 근거가 팀 경험뿐이면 확인 필요, 본인 경험 없이 행동 확인이면 일부 확인이다.
  결과는 저장된 분석 · 인재상이 같으면 다시 쓴다 (analysis_artifacts, kind=talent_fit).
"""

import asyncio
import re

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.present import AGENT_NAME
from hiremate_ai.agents.analysis.application.types import Actor, ApplicationReview
from hiremate_ai.contract import CompanyFactors, Talent, TalentFit, TalentFitItem, TalentLevel
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block
from hiremate_ai.llm.recipe import analysis_recipe, fingerprint

MAX_LABEL = 16
# 영문 · 숫자 바로 뒤에 붙은 조사. 'Spring Boot로' → 'Spring Boot'
_PARTICLE = re.compile(r"(?<=[A-Za-z0-9])(으로|로|를|을|의|에서|와|과|는|은|이|가)$")
# 잘린 끝에 남으면 뜻이 끊기는 말. 'Java 또는' → 'Java'
_DANGLING = {"또는", "및", "등", "와", "과", "·", "기반", "등으로"}
MAX_EVIDENCE = 24
# 열 이름 끝에서 떼어도 뜻이 남는 말. '인성을 중요시한다' → '인성'
_ENDINGS = re.compile(
    r"\s*(을|를|이|가|은|는)?\s*(중요시|중시|최우선으로|우선)\s*(한다|합니다|하는|함)?\.?$"
    r"|\s*(경험|경력)?\s*(보유자?|우대|있는 분|있으신 분|이 있는 분|자)\.?$"
)

LABELS_SYSTEM = f"""채용 표의 열 이름을 만든다. 문장마다 그 문장이 보는 능력 · 가치를 짧은 명사구 키워드로 쓴다.
- {MAX_LABEL}자 이내. 조사 · 어미 · '중요시한다' · '우대' 같은 말은 뺀다.
- 기술 · 도메인 이름은 원문 표기를 그대로 둔다. 기간 조건은 숫자를 남긴다.
- 문장과 같은 순서, 같은 개수로 답한다. 서로 다른 문장에 같은 키워드를 쓰지 않는다.
예: '인성을 중요시한다' → '인성', '인성' → '인성', 'Java 또는 Kotlin 기반 서버 개발 경력 3년 이상' → 'Java/Kotlin 3년',
'Spring Boot로 REST API를 개발 · 운영한 경험' → 'Spring Boot API', '대용량 트래픽 처리 경험' → '대용량 트래픽 처리',
'고객 신뢰를 최우선으로' → '고객 신뢰'"""

TALENT_SYSTEM = f"""지원자 서류에서 뽑은 경험 목록만 보고 회사 인재상마다 그 행동이 서류에서 확인되는지 판정한다.
인재상 설명에 '행동 확인:' · '일부 확인:' 기준이 있으면 그 기준을 그대로 따른다. 없으면 설명이 말하는 행동을
기준으로, 그 행동을 끝까지 했으면 행동 확인, 앞부분만 했으면 일부 확인으로 본다.
- HIGH(행동 확인): 본인이 직접 한 경험이 행동 확인 기준을 모두 채운다. 근거는 F 번호여야 한다.
- MID(일부 확인): 본인이 직접 한 경험이 일부 확인 기준에 해당한다. 기준의 앞부분은 했지만 뒷부분은 서류에 없다.
- LOW(미확인): 기준에 해당하는 행동이 서류에 없다. 다짐 · 자기 평가만 있거나 팀 성과만 있어도 LOW다.
  본인이 했는지 분명하지 않은 경험은 많아야 MID다.
- 경험마다 원문 문장이 붙어 있다. 진술에 빠진 결과 · 영향이 원문에 적혀 있으면 그것까지 본다 (예: 원문에 '그 뒤로
  문제가 사라졌다'가 있으면 결과를 확인한 것이다).
- 인재상마다 경험 목록 전체를 검토한다. 기준에 맞는 경험이 여럿이면 기준을 가장 많이 채우는 경험으로 판정한다.
  처음 찾은 약한 경험만 보고 끝내지 않는다.
- 기준에 없는 행동을 더 요구하지 않는다 (예: 기준이 '안내나 피해를 줄이는 조치'면 둘 중 하나로 충분하다).
  원문에 없는 행동을 지어내지도 않는다.
- 업무를 했다는 사실만으로 인재상을 보여 준다고 보지 않는다. 기준이 말하는 행동(예: 합의, 영향 파악, 접근 바꾸기)이
  경험에 직접 드러나야 한다. 한 경험을 여러 인재상의 근거로 쓰려면 각 기준의 행동이 그 경험에 모두 드러나야 한다.
- 합의 · 공동 결정처럼 여럿이 함께 낸 결과도, 본인이 정리 · 공유 · 제안 같은 행동으로 참여했으면 본인 행동으로 본다.
  기준에 '주도' · '혼자'가 없으면 혼자 이끌었는지 따지지 않는다.
- sources는 근거 번호들이다 (예: F3, F5, S1). 기준의 행동이 여러 경험에 나뉘어 있으면(예: 차이 정리 → 공유 →
  공동 결정) 모두 고른다. 본인 행동이 드러난 경험을 하나는 넣는다. LOW에서 근거가 없으면 비운다.
  목록에 없는 번호를 지어내지 않는다.
- reason을 먼저 쓰고 level을 정한다. level은 reason과 맞아야 한다. reason이 기준 행동을 모두 확인했다고 말하면 HIGH,
  앞부분만 확인했다고 말하면 MID, 기준 행동이 없다고 말하면 LOW다.
- evidence는 지원자가 무엇을 했는지 24자 이내로 쓴다. 예: '타 팀 API 명세 조율', '장애 원인 분석 · 재발 방지'.
- reason은 판정 이유 한 문장이다. F · S 같은 근거 번호를 쓰지 않는다. 성별 · 나이 · 출신 같은 개인 특성으로
  판단하지 않는다. 서류에 드러난 행동을 판정할 뿐 사람의 성격 전체를 단정하지 않는다.

{UNTRUSTED_RULE}"""

MAX_FACTORS = 6
FACTORS_SYSTEM = f"""회사 소개 · 조직 문화 글에서 회사가 사람을 뽑을 때 중요하게 여기는 요소
(가치 · 태도 · 일하는 방식)를 고른다.
- title은 {MAX_LABEL}자 이내의 짧은 명사다.
  예: '인성을 중요시합니다' → '인성', '실패를 두려워하지 않고 도전하는 분' → '도전'.
- quote는 그 요소가 나온 원문 문장을 글자 그대로 옮긴다. 글에 없는 요소를 지어내지 않는다.
- 사업 소개 · 복지 · 제품 설명은 요소가 아니다. 최대 {MAX_FACTORS}개, 서로 겹치지 않게 고른다."""

_labels: dict[str, list[str]] = {}
_label_locks: dict[str, asyncio.Lock] = {}
_factors: dict[str, CompanyFactors] = {}
_factor_locks: dict[str, asyncio.Lock] = {}


class _Labels(BaseModel):
    labels: list[str]


class _Factor(BaseModel):
    title: str
    quote: str


class _Factors(BaseModel):
    items: list[_Factor]


class _Judgment(BaseModel):
    """reason을 level보다 먼저 두어 모델이 이유를 쓴 뒤 수준을 정하게 한다 (이유와 수준이 어긋나지 않게)."""

    number: int = Field(description="인재상 번호 (1부터)")
    sources: list[str] = Field(default=[], description="근거 번호들 (F3, S1)")
    evidence: str = ""
    reason: str
    level: TalentLevel


class _Judgments(BaseModel):
    items: list[_Judgment]


async def feature_labels(llm: LlmClient, texts: list[str]) -> list[str]:
    """texts와 같은 순서의 짧은 키워드. 모델 답이 맞지 않으면 그 문장만 잘라 쓴다."""
    if not texts:
        return []
    key = fingerprint(texts)
    if key in _labels:
        return _labels[key]
    async with _label_locks.setdefault(key, asyncio.Lock()):
        if key in _labels:
            return _labels[key]
        numbered = "\n".join(f"{index}. {text}" for index, text in enumerate(texts, start=1))
        answer = await ask(llm, _Labels, system=LABELS_SYSTEM, user=numbered)
        labels = check_labels(texts, answer.labels)
        _labels[key] = labels
        return labels


async def company_factors(llm: LlmClient, text: str) -> CompanyFactors:
    """회사 소개 · 조직 문화 글에서 뽑은 인재상 요소. 글이 비었으면 묻지 않는다."""
    if not text.strip():
        return CompanyFactors(items=[])
    key = fingerprint([text])
    if key in _factors:
        return _factors[key]
    async with _factor_locks.setdefault(key, asyncio.Lock()):
        if key in _factors:
            return _factors[key]
        answer = await ask(llm, _Factors, system=FACTORS_SYSTEM, user=text)
        factors = check_factors(text, [(item.title, item.quote) for item in answer.items])
        _factors[key] = factors
        return factors


def check_factors(text: str, proposed: list[tuple[str, str]]) -> CompanyFactors:
    """원문에 없는 문장을 든 요소는 버린다. 이름이 비었거나 길면 문장을 잘라 만들고, 겹치는 이름은 하나만 둔다."""
    source = " ".join(text.split())
    items: list[Talent] = []
    for title, quote in proposed:
        quote = " ".join(quote.split()).strip()
        if not quote or quote not in source:
            continue
        title = " ".join(title.split())
        if not title or len(title) > MAX_LABEL:
            title = short_label(quote)
        if title in {item.title for item in items}:
            continue
        items.append(Talent(title=title, description=quote))
    return CompanyFactors(items=items[:MAX_FACTORS])


def check_labels(texts: list[str], labels: list[str]) -> list[str]:
    """개수가 다르면 전부, 비었거나 길거나 겹치는 키워드는 그것만 문장을 잘라 만든다."""
    proposed = labels if len(labels) == len(texts) else [""] * len(texts)
    result: list[str] = []
    for text, label in zip(texts, proposed, strict=True):
        label = " ".join(label.split())
        if not label or len(label) > MAX_LABEL or label in result:
            label = short_label(text)
        while label in result:
            label = f"{label}·"
        result.append(label)
    return result


def short_label(text: str) -> str:
    """모델 없이 만드는 키워드. 끝말을 떼고 단어 경계에서 MAX_LABEL자로 자른다."""
    words = _ENDINGS.sub("", " ".join(text.split())) or text.strip()
    if len(words) <= MAX_LABEL:
        return words
    kept: list[str] = []
    for word in words.split(" "):
        if len(" ".join([*kept, word])) > MAX_LABEL:
            break
        kept.append(word)
    while kept and kept[-1] in _DANGLING:
        kept.pop()
    if kept:
        kept[-1] = _PARTICLE.sub("", kept[-1])
    return " ".join(kept) or words[:MAX_LABEL]


async def judge_talents(llm: LlmClient, review: ApplicationReview | None, talents: list[Talent]) -> TalentFit:
    """저장된 분석으로 인재상을 판정한다. 분석이 없거나 서류를 읽지 못했으면 모두 확인 필요다."""
    if review is None or not review.readable or not (review.facts or review.sections):
        return TalentFit(
            items=[_unknown(talent, "서류 분석 결과가 없어 판단하지 못했어요.") for talent in talents],
            agent=AGENT_NAME,
            stub=False,
        )
    if not talents:
        return TalentFit(items=[], agent=AGENT_NAME, stub=False)
    answer = await ask(llm, _Judgments, system=TALENT_SYSTEM, user=_prompt(review, talents))
    return TalentFit(items=check_talents(review, talents, answer.items), agent=AGENT_NAME, stub=False)


def check_talents(review: ApplicationReview, talents: list[Talent], judgments: list[_Judgment]) -> list[TalentFitItem]:
    """모델 판정을 근거와 맞춰 본다. 빠진 인재상과 근거가 맞지 않는 판정은 확인 필요다."""
    by_number = {judgment.number: judgment for judgment in judgments}
    items: list[TalentFitItem] = []
    for number, talent in enumerate(talents, start=1):
        judgment = by_number.get(number)
        if judgment is None:
            items.append(_unknown(talent, "관련 근거를 찾지 못했어요."))
            continue
        found = [source for number in judgment.sources if (source := _source(review, number.strip().upper()))]
        if judgment.level in (TalentLevel.LOW, TalentLevel.UNKNOWN) and not found:
            # 경험이 확인되지 않으면 하다
            reason = judgment.reason.strip() or "서류에서 관련 경험이 확인되지 않아요."
            items.append(
                TalentFitItem(title=talent.title, level=TalentLevel.LOW, evidence="", reason=reason, quote=None)
            )
            continue
        if not found:
            items.append(_unknown(talent, "판정의 근거를 서류에서 확인하지 못했어요."))
            continue
        actors = {actor for _, _, actor in found}
        # 화면 근거는 본인 경험을 먼저 보인다
        statement, quote, _ = next((source for source in found if source[2] is Actor.SELF), found[0])
        level = TalentLevel.LOW if judgment.level is TalentLevel.UNKNOWN else judgment.level
        reason = judgment.reason.strip()
        # 모델이 인정했는데 고른 근거가 팀 경험뿐이면 확인 필요다. 본인 행동이 없다는 판정(미확인)이 아니라, 고른 근거로
        # 본인 행동을 확인하지 못한 것이다. 본인 경험이 없으면 행동 확인이 아니라 일부 확인까지다.
        # 코드가 수준을 바꾸면 이유도 바꿔 판정과 설명이 어긋나지 않게 한다
        if level is not TalentLevel.LOW and actors == {Actor.TEAM}:
            items.append(_unknown(talent, "고른 근거가 팀 단위로만 적혀 있어 본인 행동을 확인하지 못했어요."))
            continue
        elif level is TalentLevel.HIGH and Actor.SELF not in actors:
            level, reason = TalentLevel.MID, f"{reason} 본인이 했는지 분명하지 않아 일부 확인으로 봤어요."
        evidence = " ".join(judgment.evidence.split()) or statement
        items.append(
            TalentFitItem(
                title=talent.title,
                level=level,
                evidence=_clip(evidence, MAX_EVIDENCE),
                reason=reason,
                quote=quote,
            )
        )
    return items


def talent_recipe(llm: LlmClient) -> str | None:
    recipe = analysis_recipe(llm)
    if recipe is None:
        return None
    return fingerprint(
        {
            "version": "talent-fit-7",
            "llm": recipe,
            "system": TALENT_SYSTEM,
            "schema": _Judgments.model_json_schema(),
        }
    )


def talent_source(review: ApplicationReview, talents: list[Talent]) -> str:
    """다시 쓸 수 있는지 가르는 입력 지문. 저장된 분석이나 인재상이 바뀌면 다시 판정한다."""
    return fingerprint({"review": review.input_hash, "talents": [talent.model_dump(mode="json") for talent in talents]})


def _prompt(review: ApplicationReview, talents: list[Talent]) -> str:
    lines = ["[인재상]"]
    lines += [
        f"{number}. {talent.title}" + (f" - {talent.description}" if talent.description.strip() else "")
        for number, talent in enumerate(talents, start=1)
    ]
    # 진술은 한 문장으로 줄어 결과 · 영향이 빠지기도 해서 원문 문장을 함께 준다.
    # 원문은 지원자 자료라 data 블록으로 감싼다
    experiences = [
        f"F{number}. [{_ACTOR[fact.actor]}] {fact.statement}"
        + (f" (원문: {' / '.join(quote.sentence for quote in fact.quotes)})" if fact.quotes else "")
        for number, fact in enumerate(review.facts, start=1)
        if fact.supported
    ]
    lines.append("\n[경험] (본인: 직접 함 · 팀: 팀 성과 · 불분명)\n" + data_block("facts", "\n".join(experiences)))
    if review.sections:
        summaries = [
            f"S{number}. {section.title}: {section.summary}" for number, section in enumerate(review.sections, start=1)
        ]
        lines.append("\n[자기소개서 요약]\n" + data_block("sections", "\n".join(summaries)))
    return "\n".join(lines)


_ACTOR = {Actor.SELF: "본인", Actor.TEAM: "팀", Actor.UNCLEAR: "불분명"}


def _source(review: ApplicationReview, source: str) -> tuple[str, str | None, Actor] | None:
    """근거 번호를 경험 · 요약으로 바꾼다. 없는 번호이거나 검토를 통과하지 못한 경험이면 None이다."""
    match = re.fullmatch(r"([FS])(\d+)", source)
    if match is None:
        return None
    index = int(match.group(2)) - 1
    if match.group(1) == "F":
        if not 0 <= index < len(review.facts) or not review.facts[index].supported:
            return None
        fact = review.facts[index]
        return fact.statement, fact.quotes[0].sentence if fact.quotes else None, fact.actor
    if not 0 <= index < len(review.sections):
        return None
    section = review.sections[index]
    return section.summary, section.quotes[0].sentence if section.quotes else None, Actor.UNCLEAR


def _unknown(talent: Talent, reason: str) -> TalentFitItem:
    return TalentFitItem(title=talent.title, level=TalentLevel.UNKNOWN, evidence="", reason=reason, quote=None)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
