"""Assessment 부분: 자격요건과 우대사항을 같은 판정 체계(MET · PARTIAL · NOT_MET · UNKNOWN)로 판정한다.

모델은 항목마다 업무 관련성 · 본인 역할 · 수행 범위를 확인하고, 사람이 정한 판정 기준 가운데 하나로 판정한다.
점수는 프롬프트에 넣지 않는다 (score.py가 계산한다). 코드가 하는 것:
- 출력 검증: 조건형 · 단일형의 부분 충족, 부분 충족인데 충족 · 미충족 부분이 없는 답, 원문에 없는 근거,
  본인 역할이 분명하지 않은 충족은 받지 않고 확인 필요로 돌려 재확인한다. 모델 응답 누락도 미충족이 아니라 확인 필요다.
- 'N년 이상' 경력 기간: 모델이 고른, 요건의 직무 · 기술에 해당하는 재직 기간만 더해 계산한다 (전체 재직 기간이 아니다).
- 자격증 보유: 인정 자격증 이름으로 찾고 확인 상태(본인 기재 · 증빙 제출)를 남긴다.
"""

import asyncio
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.career import EMPLOYMENT, month_index
from hiremate_ai.agents.analysis.application.context import evidence_text, readable, related, terms
from hiremate_ai.agents.analysis.application.extract import locate, quotes_in
from hiremate_ai.agents.analysis.application.review import Claim, ClaimReview
from hiremate_ai.agents.analysis.application.types import (
    VERDICT_LABEL,
    Actor,
    Criterion,
    CriterionResult,
    Fact,
    Period,
    Quote,
)
from hiremate_ai.contract import (
    ApplicantDocument,
    CertificateStatus,
    CriterionCategory,
    CriterionType,
    DocumentType,
    Verdict,
)
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block, documents_block

SHORTFALL_LENGTH = 12
# "경력 3년 이상" 같은 기간 요건. 기간은 모델이 아니라 코드가 경력표로 확인한다
_CAREER_YEARS = re.compile(r"경력\s*(\d+)\s*년")
_CAREER_SPAN = re.compile(r"(?<=경력)\s*\d+\s*년\s*(이상)?")
_TYPE_LABEL = {
    CriterionType.CONDITION: "조건형",
    CriterionType.SINGLE: "단일 능력 · 경험형",
    CriterionType.COMPOSITE: "복합 경험형",
}

JUDGE_SYSTEM = f"""너는 지원 서류를 공고의 평가 항목에 대조해 항목마다 판정한다. 점수와 중요도는 다루지 않는다.

- 항목마다 먼저 relevance(업무 관련성: 실제로 한 일이 이 항목과 관련되는가), role(본인 역할: SELF 본인이 했다 /
  TEAM 팀 · 조직의 경험만 적었다 / UNCLEAR 알 수 없다), scope(수행 범위: 요구한 일을 어디까지 했는가)를 확인한다.
  셋에 따로 점수를 매기지 않고, 항목의 판정 기준 가운데 하나로 판정(verdict)한다.
- criterion_id는 요청의 번호 그대로 쓴다. 예: Q-01. 목록 표시용 대괄호는 값에 넣지 않는다.
- MET: 충족 기준에 해당한다는 근거가 있다.
- PARTIAL: 복합 경험형 항목에서 일부 수행이 확인됐다. satisfied_parts와 unsatisfied_parts를 모두 쓴다.
  불확실하다는 뜻으로 쓰지 않는다. 부분 충족 기준이 '없음'인 항목에는 쓰지 않는다.
- NOT_MET: 미충족 기준에 해당한다. 서류에 관련 기록이 없을 때도 NOT_MET이지만, 이유는 '서류에서 확인되지 않음'처럼
  쓰고 경험이 없다고 단정하지 않는다.
- UNKNOWN: 관련 기록은 있지만 본인 역할이 불분명하거나, 문서끼리 어긋나거나, 근거가 모자라 기준에 대 볼 수 없다.
  unknown_parts에 확인되지 않은 것을 쓴다.
- MET · PARTIAL이면 근거 문장(evidence)을 원문 글자 그대로 옮긴다. 옮길 문장이 없으면 그 판정을 쓰지 않는다.
- 항목의 '등'과 나열은 예시다. 같은 종류면 해당한다 (MySQL · PostgreSQL 등 RDBMS라면 Oracle도 RDBMS다).
- 경력 기간 항목은 기간을 코드가 경력표로 계산한다. career_periods에 그 항목의 직무 · 기술에 해당하는 경력표 번호만
  고른다. 인턴, 교육 · 개인 프로젝트는 실무 경력이 아니다. 기간이 모자라도 직무 · 기술이 맞으면 MET로 답한다.
- 자격증만으로 경험 항목을 채웠다고 보지 않는다. 판정 기준에 없는 조건을 더하지 않는다.
- 자격요건을 NOT_MET으로 판정하면 shortfall에 확인되지 않은 것을 요건의 낱말로 아주 짧게 쓴다 (12자 이내).
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 판단에 쓰지 않는다.

{UNTRUSTED_RULE}"""

RECHECK_NOTES = {
    1: "1차 재확인: 앞 판정은 확인 필요였다. 이유: {reason}\n근거 문장의 주변 문맥과 본인 역할을 다시 보고 판정해 줘.",
    2: "2차 재확인: 앞 판정은 확인 필요였다. 이유: {reason}\n"
    "다른 제출 문서에 보완하거나 어긋나는 근거가 있는지 보고 판정해 줘. 그래도 정할 수 없으면 UNKNOWN으로 둔다.",
}


class CriterionVerdict(BaseModel):
    criterion_id: str = Field(description="항목 번호 (예: Q-01)")
    relevance: str = ""
    role: Literal["SELF", "TEAM", "UNCLEAR"] = "UNCLEAR"
    scope: str = ""
    verdict: Literal["MET", "PARTIAL", "NOT_MET", "UNKNOWN"]
    reason: str = Field(description="판정 기준에 비춘 이유 한 문장")
    satisfied_parts: list[str] = []
    unsatisfied_parts: list[str] = []
    unknown_parts: list[str] = []
    evidence: list[str] = Field(default=[], description="근거 문장. 원문 글자 그대로")
    career_periods: list[int] = Field(default=[], description="경력 기간 항목이면 해당하는 경력표 번호")
    shortfall: str = Field(default="", description="자격요건 NOT_MET이면 이름 옆에 붙일 아주 짧은 표시")


class CriteriaJudgement(BaseModel):
    verdicts: list[CriterionVerdict]


@dataclass(frozen=True)
class Evidence:
    """판정에 쓰는 지원자 자료 한 묶음."""

    documents: Sequence[ApplicantDocument]
    facts: Sequence[Fact]
    periods: Sequence[Period]
    certificates: str | None
    today: date


async def judge_criteria(
    llm: LlmClient, criteria: Sequence[Criterion], evidence: Evidence, full_text_chars: int
) -> list[CriterionResult]:
    """항목을 판정한다. 자격증 보유 조건은 코드가, 나머지는 영역(자격요건 · 우대사항)마다 한 번씩 모델이 본다."""
    by_code = {c.criterion_id: certificate_result(c, evidence) for c in criteria if c.certificates}
    asked = [criterion for criterion in criteria if not criterion.certificates]
    groups = [group for category in CriterionCategory if (group := [c for c in asked if c.category == category])]
    answers = await asyncio.gather(
        *(
            _ask(
                llm, group, evidence, evidence_text(evidence.documents, evidence.facts, _words(group), full_text_chars)
            )
            for group in groups
        )
    )
    verdicts: dict[str, CriterionVerdict | None] = {}
    for group, answer in zip(groups, answers, strict=True):
        verdicts.update(_index_verdicts(answer.verdicts, {criterion.criterion_id for criterion in group}))
    return [
        by_code.get(criterion.criterion_id) or _settle_answer(criterion, verdicts, evidence) for criterion in criteria
    ]


async def recheck_criterion(
    llm: LlmClient, criterion: Criterion, previous: CriterionResult, evidence: Evidence, round_no: int
) -> CriterionResult | None:
    """확인 필요 항목 하나를 다시 판정한다.

    1차는 근거 · 관련 문장이 나온 문서의 원문 전체로 주변 문맥 · 본인 역할을, 2차는 제출 문서 전체로 다른 문서의
    보완 · 상충 근거를 본다. 2차 자료가 1차와 같으면 같은 질문이라 묻지 않는다(None).
    """
    usable = readable(evidence.documents)
    near = _near_documents(criterion, previous, usable)
    if round_no == 1:
        documents = near
    elif {document.type for document in near} == {document.type for document in usable}:
        return None
    else:
        documents = usable
    facts = "\n".join(f"- [{fact.actor.value}] {fact.statement}" for fact in evidence.facts)
    parts = [
        documents_block(documents),
        data_block("facts", facts or "(없음)"),
        RECHECK_NOTES[round_no].format(reason=previous.reason),
    ]
    answer = await _ask(llm, [criterion], evidence, "\n\n".join(parts))
    verdicts = _index_verdicts(answer.verdicts, {criterion.criterion_id})
    return _settle_answer(criterion, verdicts, evidence).model_copy(
        update={"recheck_count": previous.recheck_count + 1}
    )


def _index_verdicts(verdicts: Sequence[CriterionVerdict], allowed: set[str]) -> dict[str, CriterionVerdict | None]:
    """표시용 괄호·공백만 정리해 요청한 번호와 대조한다. 의미나 번호 자릿수는 추측하지 않는다."""
    indexed: dict[str, CriterionVerdict | None] = {}
    for verdict in verdicts:
        key = verdict.criterion_id.strip()
        bracketed = re.fullmatch(r"\[\s*([^\[\]]+?)\s*\]", key)
        if bracketed:
            key = bracketed.group(1).strip()
        if key not in allowed:
            continue
        canonical = verdict.model_copy(update={"criterion_id": key})
        if key not in indexed:
            indexed[key] = canonical
        elif indexed[key] != canonical:
            indexed[key] = None  # 뒤에 같은 번호가 또 와도 충돌을 덮어쓰지 않는다.
    return indexed


def _settle_answer(
    criterion: Criterion, verdicts: dict[str, CriterionVerdict | None], evidence: Evidence
) -> CriterionResult:
    if criterion.criterion_id in verdicts and verdicts[criterion.criterion_id] is None:
        return _unknown(_base(criterion), "같은 항목 번호의 모델 판정이 서로 달라 확인이 필요해요.")
    return settle(criterion, verdicts.get(criterion.criterion_id), evidence)


def settle(criterion: Criterion, verdict: CriterionVerdict | None, evidence: Evidence) -> CriterionResult:
    """모델 판정에 코드 규칙을 적용한다. 받을 수 없는 답은 미충족이 아니라 확인 필요로 둔다."""
    base = _base(criterion)
    if verdict is None:
        return _unknown(base, "모델 응답에 이 항목이 없어 판정하지 못했어요.")
    level = Verdict(verdict.verdict)
    quotes = quotes_in(evidence.documents, verdict.evidence)
    result = base.model_copy(
        update={
            "verdict": level,
            "reason": verdict.reason,
            "relevance": verdict.relevance,
            "role": Actor(verdict.role),
            "scope": verdict.scope,
            "satisfied_parts": verdict.satisfied_parts,
            "unsatisfied_parts": verdict.unsatisfied_parts,
            "unknown_parts": verdict.unknown_parts,
            "quotes": quotes if level != Verdict.NOT_MET else [],
        }
    )
    if level == Verdict.PARTIAL and criterion.criterion_type != CriterionType.COMPOSITE:
        return _unknown(result, f"{_TYPE_LABEL[criterion.criterion_type]} 항목인데 부분 충족으로 답해 받지 않았어요.")
    if level == Verdict.PARTIAL and not (verdict.satisfied_parts and verdict.unsatisfied_parts):
        return _unknown(result, "부분 충족인데 충족한 부분과 미충족한 부분을 나눠 설명하지 않았어요.")
    if level in (Verdict.MET, Verdict.PARTIAL) and not quotes:
        return _unknown(result, "판정을 받쳐 줄 근거 문장을 원문에서 찾지 못했어요.")
    if level == Verdict.MET and criterion.criterion_type != CriterionType.CONDITION and verdict.role != "SELF":
        return _unknown(result, f"본인이 직접 했는지 분명하지 않아요. {verdict.reason}")
    required = _CAREER_YEARS.search(criterion.text)
    if required:
        return _career(result, verdict, int(required.group(1)), evidence)
    if level == Verdict.NOT_MET and criterion.category == CriterionCategory.QUALIFICATION:
        return result.model_copy(update={"shortfall": unmet_label(criterion.text, verdict.shortfall)})
    if level == Verdict.UNKNOWN:
        return _unknown(result, verdict.reason)
    return result


def certificate_result(criterion: Criterion, evidence: Evidence) -> CriterionResult:
    """자격증 보유 조건. 인정 자격증이 자격증 사본(증빙 문서)에 있으면 증빙 제출, 자격증 칸이나 다른 서류에만 있으면
    본인 기재다. 발급기관 확인은 서류 단계에서 하지 않는다. 어디에도 없으면 미충족이다.
    """
    base = _base(criterion)
    usable = readable(evidence.documents)
    for name in criterion.certificates:
        for document in usable:
            if document.type == DocumentType.CERTIFICATE and _compact(name) in _compact(document.text):
                quote = _line_quote(name, document)
                return base.model_copy(
                    update={
                        "verdict": Verdict.MET,
                        "reason": f"제출한 자격증 사본에 '{name}'이 있어요 (증빙 제출, 발급기관 확인 전).",
                        "quotes": [quote] if quote else [],
                        "certificate_status": CertificateStatus.EVIDENCE_SUBMITTED,
                    }
                )
    for name in criterion.certificates:
        if evidence.certificates and _compact(name) in _compact(evidence.certificates):
            return base.model_copy(
                update={
                    "verdict": Verdict.MET,
                    "reason": f"자격증 칸에 '{name}'을 적었어요 (본인 기재, 미검증).",
                    "certificate_status": CertificateStatus.SELF_REPORTED,
                }
            )
        for document in usable:
            if (quote := _line_quote(name, document)) is not None:
                return base.model_copy(
                    update={
                        "verdict": Verdict.MET,
                        "reason": f"{document.type.label}에 '{name}'을 적었어요 (본인 기재, 미검증).",
                        "quotes": [quote],
                        "certificate_status": CertificateStatus.SELF_REPORTED,
                    }
                )
    names = ", ".join(criterion.certificates)
    result = base.model_copy(
        update={"verdict": Verdict.NOT_MET, "reason": f"인정 자격증({names})이 서류에서 확인되지 않아요."}
    )
    if criterion.category == CriterionCategory.QUALIFICATION:
        result = result.model_copy(update={"shortfall": unmet_label(criterion.certificates[0])})
    return result


def verification_claims(results: Sequence[CriterionResult]) -> list[Claim]:
    """검증할 판정: 모델이 충족 · 부분 충족으로 본, 인용이 있는 항목. 근거가 판정을 의미상 받쳐 주는지 본다."""
    return [
        Claim(
            result.criterion_id,
            f"'{result.text}'을 {VERDICT_LABEL[result.verdict]}했다. 판정 이유: {result.reason}",
            result.quotes,
        )
        for result in results
        if result.verdict in (Verdict.MET, Verdict.PARTIAL) and result.quotes and result.certificate_status is None
    ]


def apply_verification(results: Sequence[CriterionResult], reviews: dict[str, ClaimReview]) -> list[CriterionResult]:
    """근거가 판정을 받쳐 주지 않으면 확인 필요로, 복합 경험형의 충족이 과장이면 부분 충족으로 낮춘다."""
    checked = []
    for result in results:
        review = reviews.get(result.criterion_id)
        if review is None or review.verdict == "SUPPORTED":
            checked.append(result)
        elif (
            review.verdict == "OVERSTATED"
            and result.verdict == Verdict.MET
            and result.criterion_type == CriterionType.COMPOSITE
        ):
            checked.append(
                result.model_copy(
                    update={
                        "verdict": Verdict.PARTIAL,
                        "satisfied_parts": result.satisfied_parts or [result.scope or result.reason],
                        "unsatisfied_parts": [review.reason or "근거가 충족 기준 전부를 받쳐 주지 않아요."],
                        "reason": f"검증에서 근거가 충족 기준 일부만 받쳐 준다고 봤어요. {review.reason}".strip(),
                    }
                )
            )
        else:
            reason = f"검증에서 근거가 판정을 받쳐 주지 않는다고 봤어요. {review.reason}".strip()
            checked.append(_unknown(result, reason))
    return checked


def short_label(text: str) -> str:
    """이름 옆 ✕ 표시. 12자를 넘으면 '근거 없음' 꼬리를 떼고, 그래도 길면 낱말 단위로 자른다."""
    label = " ".join(text.split())
    if len(label) > SHORTFALL_LENGTH:
        label = re.sub(r"\s*(근거\s*)?없음$", "", label)
    while len(label) > SHORTFALL_LENGTH and " " in label:
        label = label.rsplit(" ", 1)[0]
    return label[:SHORTFALL_LENGTH] or "근거 없음"


def unknown_label(text: str) -> str:
    """확인 필요인 자격요건의 짧은 표시 (예: Git 확인 필요)."""
    return _labelled(text, "확인 필요")


def unmet_label(text: str, shortfall: str = "") -> str:
    """미충족 자격요건의 짧은 표시. 모델이 비워 두면 항목 첫 낱말로 만든다 (예: JUnit 근거 없음)."""
    return short_label(shortfall) if shortfall.strip() else _labelled(text, "근거 없음")


def _labelled(text: str, tail: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#./]*|[가-힣]{2,}", _CAREER_SPAN.sub("", text))
    head = words[0] if words else ""
    return f"{head} {tail}" if head and len(head) <= 6 else tail


async def _ask(llm: LlmClient, group: Sequence[Criterion], evidence: Evidence, material: str) -> CriteriaJudgement:
    parts = ["평가 항목:\n" + "\n".join(_listing(criterion) for criterion in group)]
    if any(_CAREER_YEARS.search(criterion.text) for criterion in group):
        parts.append("경력표 (코드가 계산한 개월 수):\n" + data_block("career", _career_table(evidence.periods)))
    parts.append("제출한 자격증:\n" + data_block("certificates", evidence.certificates or "(없음)"))
    parts.append("서류:\n" + material)
    parts.append("항목마다 판정해 줘.")
    return await ask(llm, CriteriaJudgement, system=JUDGE_SYSTEM, user="\n\n".join(parts))


def _listing(criterion: Criterion) -> str:
    rules = criterion.evaluation_rules
    text = _CAREER_SPAN.sub("", criterion.text).strip()
    span = " (기간은 코드가 경력표로 확인한다)" if _CAREER_YEARS.search(criterion.text) else ""
    partial = rules.partial if criterion.criterion_type == CriterionType.COMPOSITE and rules.partial else "없음"
    return "\n".join(
        [
            f"[{criterion.criterion_id}] ({_TYPE_LABEL[criterion.criterion_type]}) {text}{span}",
            f"  - 충족: {rules.met}",
            f"  - 부분 충족: {partial}",
            f"  - 미충족: {rules.unmet}",
        ]
    )


def _words(group: Sequence[Criterion]) -> list[str]:
    return terms([text for c in group for text in (c.text, c.evaluation_rules.met, c.evaluation_rules.partial or "")])


def _career(result: CriterionResult, verdict: CriterionVerdict, years: int, evidence: Evidence) -> CriterionResult:
    """경력 기간 조건. 모델이 고른 직무 · 기술 관련 재직 기간만 더한다.

    근무 기간을 하나도 찾지 못했거나 어느 기간이 해당하는지 모르면 신입이 아니라 경력 확인 필요다.
    """
    if not evidence.periods:
        return _unknown(result, "서류에서 근무 기간을 찾지 못해 경력을 확인하지 못했어요.", "경력 확인 필요")
    total = _employment_months(evidence.periods, range(1, len(evidence.periods) + 1), evidence.today)
    if result.verdict == Verdict.NOT_MET:
        # 직무 · 기술이 맞지 않는 경력이다. 전체 재직 기간으로 채우지 않는다
        label = "신입" if total < 12 else _labelled(result.text, "경력 없음")
        return result.model_copy(update={"shortfall": label, "career_months": 0})
    if result.verdict != Verdict.MET:
        return _unknown(result, result.reason or "경력을 확인하지 못했어요.", "경력 확인 필요")
    chosen = [number for number in verdict.career_periods if 1 <= number <= len(evidence.periods)]
    if not chosen:
        return _unknown(result, "요건의 직무 · 기술에 해당하는 재직 기간을 고르지 못했어요.", "경력 확인 필요")
    months = _employment_months(evidence.periods, chosen, evidence.today)
    if months < years * 12:
        return result.model_copy(
            update={
                "verdict": Verdict.NOT_MET,
                "reason": f"요건과 관련된 재직 경력이 {months // 12}년 {months % 12}개월이에요 (요건 {years}년 이상).",
                "shortfall": "신입" if total < 12 else f"경력 {months // 12}년",
                "career_months": months,
                "quotes": [],
            }
        )
    return result.model_copy(update={"career_months": months})


def _employment_months(periods: Sequence[Period], numbers: Sequence[int], today: date) -> int:
    """고른 기간 가운데 재직(EMPLOYMENT) 기간의 합. 겹치는 기간은 한 번만 센다."""
    current = today.year * 12 + today.month - 1
    spans = []
    for number in numbers:
        period = periods[number - 1]
        begin = month_index(period.start)
        finish = month_index(period.end) if period.end else current
        if period.kind == EMPLOYMENT and begin is not None and finish is not None and finish >= begin:
            spans.append((begin, finish))
    total, reach = 0, -1
    for begin, finish in sorted(spans):
        if finish <= reach:
            continue
        total += finish - max(begin, reach)
        reach = finish
    return total


def _career_table(periods: Sequence[Period]) -> str:
    if not periods:
        return "(서류에서 찾은 근무 기간이 없음)"
    return "\n".join(
        f"{number}. {period.company} · {period.role or '역할 미기재'} · {period.kind} · "
        f"{period.start} ~ {period.end or '현재'} · {period.months}개월"
        for number, period in enumerate(periods, start=1)
    )


def _near_documents(
    criterion: Criterion, previous: CriterionResult, documents: Sequence[ApplicantDocument]
) -> list[ApplicantDocument]:
    """근거나 관련 문장이 나온 문서. 없으면 이력서(또는 첫 문서)."""
    words = terms([criterion.text, criterion.evaluation_rules.met])
    types = {quote.document for quote in previous.quotes} | {quote.document for quote in related(documents, words)}
    near = [document for document in documents if document.type in types]
    if near:
        return near
    resume = [document for document in documents if document.type == DocumentType.RESUME]
    return resume or list(documents[:1])


def _base(criterion: Criterion) -> CriterionResult:
    return CriterionResult(
        criterion_id=criterion.criterion_id,
        category=criterion.category,
        text=criterion.text,
        important=criterion.important,
        criterion_type=criterion.criterion_type,
        verdict=Verdict.UNKNOWN,
        reason="",
    )


def _unknown(result: CriterionResult, reason: str, label: str | None = None) -> CriterionResult:
    shortfall = None
    if result.category == CriterionCategory.QUALIFICATION:
        shortfall = label or unknown_label(result.text)
    return result.model_copy(update={"verdict": Verdict.UNKNOWN, "reason": reason, "shortfall": shortfall})


def _line_quote(name: str, document: ApplicantDocument) -> Quote | None:
    for line in document.text.splitlines():
        if _compact(name) in _compact(line):
            return locate(line, [document])
    return None


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()
