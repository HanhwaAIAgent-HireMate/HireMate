"""표 보기 부분: 열 이름(평가 기준 · 인재상의 짧은 키워드), 회사 글에서 뽑은 인재상 요소, 지원자별 인재상 판정을 만든다.

자격요건 · 우대사항 칸은 지원 접수 때 저장한 항목별 판정을 그대로 쓴다 (여기서 다시 판정하지 않는다).
인재상은 접수 분석에 없으므로, 저장된 분석의 경험(Fact)과 자기소개서 요약만 읽고 판정한다. 코드가 하는 것:
- 키워드: 개수가 다르거나 너무 긴 답은 쓰지 않고 문장을 잘라 만든다. 같은 문장 묶음은 프로세스 안에서 한 번만 묻는다.
- 인재상 요소: 회사 소개 · 조직 문화 글에 실제로 있는 문장을 근거로 든 요소만 남긴다. 같은 글은 한 번만 묻는다.
- 판정: 고른 근거가 목록에 없거나 검토를 통과하지 못한 경험이면 확인 필요로 돌린다. 본인이 직접 한 경험이 아니면
  '상'을 주지 않는다. 결과는 저장된 분석 · 인재상이 같으면 다시 쓴다 (analysis_artifacts, kind=talent_fit).
"""

import asyncio
import re

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.present import AGENT_NAME
from hiremate_ai.agents.analysis.application.types import Actor, ApplicationReview
from hiremate_ai.contract import CompanyFactors, Talent, TalentFit, TalentFitItem, TalentLevel
from hiremate_ai.llm.client import LlmClient
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

TALENT_SYSTEM = """지원자 서류에서 뽑은 경험 목록만 보고 회사 인재상마다 맞는 정도를 판정한다.
- HIGH(상): 본인이 직접 한 구체 경험이 인재상을 보여 준다. 근거는 F 번호여야 한다.
- MID(중): 관련 경험이 있지만 팀 성과이거나 본인 역할 · 결과가 분명하지 않다.
- LOW(하): 관련 언급은 있지만 구체 경험이 없다 (다짐 · 자기 평가만 있다).
- UNKNOWN(확인 필요): 관련 근거가 없다. 근거가 없다고 LOW를 주지 않는다.
- source는 근거 번호 하나(F3, S1). UNKNOWN이면 비운다. 목록에 없는 번호를 지어내지 않는다.
- evidence는 지원자가 무엇을 했는지 24자 이내로 쓴다. 예: '타 팀 API 명세 조율', '장애 원인 분석 · 재발 방지'.
- reason은 판정 이유 한 문장이다. 성별 · 나이 · 출신 같은 개인 특성으로 판단하지 않는다."""

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
    number: int = Field(description="인재상 번호 (1부터)")
    level: TalentLevel
    source: str = ""
    evidence: str = ""
    reason: str


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
        if judgment is None or judgment.level is TalentLevel.UNKNOWN:
            items.append(_unknown(talent, judgment.reason if judgment else "관련 근거를 찾지 못했어요."))
            continue
        source = _source(review, judgment.source.strip().upper())
        if source is None:
            items.append(_unknown(talent, "판정의 근거를 서류에서 확인하지 못했어요."))
            continue
        statement, quote, actor = source
        level = judgment.level
        # 본인이 직접 한 경험(F)이 아니면 상을 주지 않는다
        if level is TalentLevel.HIGH and actor is not Actor.SELF:
            level = TalentLevel.MID
        evidence = " ".join(judgment.evidence.split()) or statement
        items.append(
            TalentFitItem(
                title=talent.title,
                level=level,
                evidence=_clip(evidence, MAX_EVIDENCE),
                reason=judgment.reason.strip(),
                quote=quote,
            )
        )
    return items


def talent_recipe(llm: LlmClient) -> str | None:
    recipe = analysis_recipe(llm)
    if recipe is None:
        return None
    return fingerprint(
        {"version": "talent-fit-1", "llm": recipe, "system": TALENT_SYSTEM, "schema": _Judgments.model_json_schema()}
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
    lines.append("\n[경험] (본인: 직접 함 · 팀: 팀 성과 · 불분명)")
    lines += [
        f"F{number}. [{_ACTOR[fact.actor]}] {fact.statement}"
        for number, fact in enumerate(review.facts, start=1)
        if fact.supported
    ]
    if review.sections:
        lines.append("\n[자기소개서 요약]")
        lines += [
            f"S{number}. {section.title}: {section.summary}" for number, section in enumerate(review.sections, start=1)
        ]
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
