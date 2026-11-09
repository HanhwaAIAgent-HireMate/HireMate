"""Assessment 부분: 자격요건과 우대사항을 같은 판정 체계(MET · PARTIAL · NOT_MET · UNKNOWN)로 판정한다.

모델은 항목마다 업무 관련성 · 본인 역할 · 수행 범위를 확인하고, 사람이 정한 판정 기준 가운데 하나로 판정한다.
점수는 매기지 않는다. 서류 문장을 하나씩 분석해 뽑은 사실(facts, 프로필 근거)을 먼저 보고 판정한다. 코드가 하는 것:
- 출력 검증: 조건형 · 단일형의 부분 충족, 부분 충족인데 충족 · 미충족 부분이 없는 답, 원문에 없는 근거,
  본인 역할이 분명하지 않은 충족은 받지 않고 확인 필요로 돌려 재확인한다. 단, 근거 문장이 사실 추출에서 본인 경험으로
  뽑힌 문장이면 본인 역할로 본다. 모델 응답 누락도 미충족이 아니라 확인 필요다.
- 'N년 이상' 경력 기간: 모델이 고른, 요건의 직무 · 기술에 해당하는 재직 기간만 더해 계산한다 (전체 재직 기간이 아니다).
- 자격증 보유: 인정 자격증 이름으로 찾고 확인 상태(본인 기재 · 증빙 제출)를 남긴다.
- 정량 지표는 여기서 고르지 않는다. 성과 장부(achievements)가 지원자 단위로 정한 성과 · 항목 연결을 검증 뒤에 붙인다.
  화면은 경험과 지표가 함께 있으면 상, 경험만 있으면 중으로 보여 준다.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.career import EMPLOYMENT, month_index
from hiremate_ai.agents.analysis.application.context import fact_lines, readable
from hiremate_ai.agents.analysis.application.extract import locate, quotes_in
from hiremate_ai.agents.analysis.application.review import Claim, ClaimReview
from hiremate_ai.agents.analysis.application.types import (
    VERDICT_LABEL,
    Actor,
    Criterion,
    CriterionResult,
    EvaluationRules,
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
# 서류에 관련 기록이 아예 없는 항목(언급 없음)의 카드 요약
NO_RECORD_BRIEF = "서류에 해당 내용 없음"
QUOTE_HEAD = 20
RELATED_OVERLAP = 3
RELATED_LINES = 6
# "경력 3년 이상" 같은 기간 요건. 기간은 모델이 아니라 코드가 경력표로 확인한다
_CAREER_YEARS = re.compile(r"경력\s*(\d+)\s*년")
_CAREER_SPAN = re.compile(r"(?<=경력)\s*\d+\s*년\s*(이상)?")
_TYPE_LABEL = {
    CriterionType.CONDITION: "조건형",
    CriterionType.SINGLE: "단일 능력 · 경험형",
    CriterionType.COMPOSITE: "복합 경험형",
}

# 항목 판정 규칙. 지원자 종합 판정(assess)이 성과 · 주의 신호 · 직무 경력과 함께 한 번에 묻고, 재판정도 쓴다
JUDGE_RULES = """### 자료
- facts는 서류 문장을 하나씩 분석해 뽑은 경험 목록이다 ([종류 · 본인 여부] 진술 (근거: 원문 문장)). facts를 먼저 보고,
  facts에 없는 내용만 원문에서 찾는다. 둘이 어긋나면 원문을 따른다.
- 항목마다 relevance(한 일이 항목과 관련되는가), role(SELF 본인이 했다 / TEAM 팀 · 조직의 일만 적었다 / UNCLEAR 알 수
  없다), scope(요구한 일을 어디까지 했는가)를 확인하고, 셋을 종합해 판정 기준 가운데 하나로 판정한다.

### 근거의 원칙
- 근거는 본인이 실제로 한 일이다. 회사 · 서비스의 구성 설명, 팀이 한 일, 계획 · 예정 · 학습 중인 일은 본인이 수행한
  근거가 아니다. 같은 문맥에 실제로 만든 결과물이 적혀 있으면 그 문장이 근거다. 배우는 중이라도 그 기술로 실제로 만든
  것(개인 · 교육 과정 프로젝트의 API 등)이 적혀 있으면 그 기술을 사용한 경험이다. 실무인지는 항목이 '실무'를 요구할
  때만 따진다.
- 근거는 항목이 묻는 대상과 행동을 직접 다룬 기록이어야 한다. 낱말이 겹치거나, 결과만 보이거나, 비슷한 일을 했다는
  것으로 미루어 짐작하지 않는다 (아래처럼 그 일에 반드시 들어가는 행동으로 확인하는 것은 짐작이 아니다).
  이미 있는 것을 쓰거나 일부 고친 것은 그것을 만들고 구성한 것과 다르다.
- 이해 · 능력을 묻는 항목은 그 이해 · 능력이 드러난 실제 작업 내용(설계, 구현, 결정과 그 이유)을 근거로 본다.
  항목의 말이 서류에 그대로 없어도 된다.
- 요구한 부분의 낱말이 서류에 없어도, 그 부분 없이는 할 수 없는 일을 본인이 했다고 적혀 있으면 그 부분은 확인된
  것이다 (예: 인덱스를 만들고 쿼리를 고쳤다 → SQL을 작성했다, PR을 올려 리뷰를 받았다 → Git으로 협업했다).
  그 일에 반드시 들어가는 경우만 그렇다. 함께 쓰일 때가 많다거나, 도구 이름을 나열만 했다는 것으로는 확인되지 않는다.
- 한 일의 행동 · 결과 · 조건이 여러 문장이나 문서에 나뉘어 있으면 함께 본다. 다른 프로젝트 · 다른 환경의 일은 한
  경험으로 합치지 않는다. 기준에 맞는 경험이 여럿이면 가장 잘 맞는 경험으로 판정한다.
- 판정 기준에 없는 조건을 더하지 않는다. 자격증만으로 경험 항목을 채웠다고 보지 않는다.

### 기준의 해석
- 판정 기준이 나열을 어떻게 볼지(모두 · 어느 하나) 정했으면 그대로 따른다. 정하지 않았으면 나열(쉼표 · 빗금(/) ·
  '와/과' · '및')은 '또는' · '혹은' · '중 하나'가 없으면 적힌 것을 모두 요구한다 (예: 'A/B 구축'은 A 구축과
  B 구축이 모두 있어야 한다). 나열 끝에 '등'이 붙으면 적힌 것은 예시라서 그 가운데 하나만 해도 충족이다 (예:
  'A, B 등 활용 경험'은 A만 써도 충족이고, 그 결과에 유효한 수치가 있으면 상의 근거가 된다).
  가운뎃점(·)은 기호만으로 정하지 않고 문맥으로 본다 (같은 종류의 기술 · 단계를 묶으면
  모두 요구한다). 일부만 확인되면 복합 경험형은 부분 충족 기준 문장에 해당하는지 보고(아래 '판정'의 PARTIAL),
  그 밖의 유형은 충족이 아니다. 없는 쪽을 서류가 '해 본 적 없다'고 밝혔으면 NOT_MET이다.
- 규모를 나타내는 말(대용량, 대규모 등)이 붙은 경험은 두 부분을 함께 요구한다 (parts도 둘로 나눈다).
  ① 규모: 몰리는 요청 · 늘어난 처리량이 병목 · 지연 · 오류의 원인으로 서류에 적혀 있다. 기준선 수치로 판정하지 않는다.
  ② 해결: 실서비스(실제 사용자가 쓰는 운영 환경)에서 본인이 병목 · 지연 · 오류를 분석하고 개선했다. 개인 · 교육 과정
  프로젝트나 부하 테스트 환경의 개선은 ②가 아니다. 문제의 원인이 규모가 아니면(비효율적인 쿼리 · 설계 등) ②는 확인돼도
  ①은 확인되지 않은 것이다. 규모 수치는 원문대로 brief에 넣어 담당자가 판단하게 한다.
- 항목이 말하는 상황(규모, 장애, 고객 문제 등)에 해당하는지로 먼저 걸러내 끝내지 않는다. 상황이 그것이었는지 애매해도
  본인이 한 행동으로 판정하고, 애매한 점은 brief나 unknown_parts에 남긴다.
- 기준이 정하지 않은 다른 값 때문에 충족 여부가 실제로 갈리면 setting_note에 그 점을 쓰고 UNKNOWN으로 둔다. 지원자에게
  더 물을 것이 없으면 unknown_parts는 비운다. 기준이 넓거나 추상적이라는 이유로는 쓰지 않는다. 그 밖에는 비운다.

### 판정
- 서류를 충족 → 부분 충족 → 미충족 기준 문장 순서로 대조해, 처음 해당하는 판정을 쓴다.
- MET: 충족 기준에 해당하는 근거가 있다.
- PARTIAL: 복합 경험형에서 부분 충족 기준 문장에 해당한다. satisfied_parts와 unsatisfied_parts를 모두 쓴다.
  불확실하다는 뜻으로 쓰지 않고, 부분 충족 기준이 '없음'인 항목에는 쓰지 않는다.
  - 부분 충족 기준 문장에 해당하는 기록이 있으면 PARTIAL이다. 그 기록을 '같은 분야의 다른 일'로 보아 NO_RECORD ·
    NOT_MET으로 쓰지 않는다 (예: 기준이 '테이블 설계는 했지만 설계서는 드러나지 않는다'이고 테이블 설계 기록이 있으면
    PARTIAL).
  - 기준 문장이 어느 부분이 확인되는 경우인지 정했으면(예: 'A는 했지만 B는 드러나지 않는다') 그 경우만 PARTIAL이다.
    반대 경우(B만 확인)는 기준 문장에 '또는 그 반대'가 있을 때만 PARTIAL이고, 없으면 미충족 기준에 해당하면 NOT_MET,
    직접 한 흔적이 없으면 NO_RECORD다. 기준 문장이 '일부만 했다'처럼 넓으면 요구한 부분 가운데 일부만 확인된 경우가
    PARTIAL이다.
- NOT_MET: 미충족 기준에 해당한다고 서류에 적혀 있다 (하지 않았다, 다른 사람이 맡았다 등).
- UNKNOWN: 항목의 일을 직접 한 흔적은 있지만 충족인지 정할 수 없다 (본인 역할 · 범위 · 문서 간 일치, 또는 항목이
  요구하는 도구 · 방식을 썼는지가 적혀 있지 않다). 예: 그 기술을 배우는 과정의 프로젝트에서 그 일을 맡았다고만 적혔다.
  unknown_parts에 확인되지 않은 것을 쓴다. 충족 · 부분 충족 기준 문장에 나온 행동 가운데 하나라도 한 기록이 있으면,
  그 일이 항목이 말하는 상황이었는지나 결과까지 이어졌는지 분명하지 않아도 직접 한 흔적이다.
- NO_RECORD: 항목의 일을 직접 한 흔적이 없다. 같은 분야의 다른 일, 비슷한 일반 업무처럼 직접적이지 않은 흔적만 있어도
  NO_RECORD다. 경험이 없다고 단정하지 않는다.
- NOT_MET · UNKNOWN · NO_RECORD로 두거나 parts의 found를 false로 쓰기 전에, 그 부분을 제출 서류 전체(이력서 ·
  자기소개서 · 포트폴리오)에서 다시 찾는다. 한 문서에 없다는 것으로 확인되지 않았다고 보지 않는다.

### 출력
- criterion_id는 요청의 번호 그대로 쓴다 (예: Q-01). 대괄호는 넣지 않는다.
- parts에는 항목 문장이 요구하는 것을 나눠 쓰고, 부분마다 서류에서 본인이 한 것으로 확인됐는지 found로 쓴다.
  나열이면 하나씩 나눈다 (예: 'A/B 구축' → A 구축, B 구축). 어느 하나만 있어도 되는 것('A 또는 B', 'A, B 등')은 한
  부분으로 쓴다 (예: 'A, B 등 활용 경험' → 'A 또는 B 활용'). 판정 기준 문장이 '~하거나' · '중 하나'로 하나만
  요구해도 한 부분이다 (예: 충족 기준 '개발하거나 운영했다' → '개발 또는 운영' 한 부분). 요구가 하나면 하나만 쓴다.
  verdict는 parts와 맞아야 한다.
- MET · PARTIAL이면 evidence에 근거 문장을 원문 글자 그대로 옮긴다. 기준의 부분마다 받치는 문장과 결과 문장을 모두
  옮기고, 본인 행동이 드러난 문장을 먼저 둔다. 옮길 문장이 없으면 그 판정을 쓰지 않는다.
  UNKNOWN · NO_RECORD여도 판단에 쓴 흔적 문장이 있으면 evidence에 옮긴다 (담당자가 무엇을 보고 판정했는지 알 수 있게).
- 수치 성과(전후 값)는 성과 장부가 지원자 단위로 한 번 정리해 항목에 연결한다. 판정은 본인이 한 일로만 한다.
  수치의 조건 · 한계(체감치, 팀 공동, 다른 효과 포함 등)가 판정에 영향을 주면 brief에 쓴다.
- brief는 화면 카드에 보일 판정 요약 한 줄이다. 40자 안팎으로, 길이를 맞추려고 수치의 조건 · 한계를 빼지 않는다.
  MET · PARTIAL · NOT_MET은 한 일과 모자란 점을 명사형으로 끝낸다 (예: '○○ 구현은 확인, ○○ 운영은 미확인').
  UNKNOWN은 서류에 있는 흔적과 담당자가 확인할 것을 함께 쓰고 '확인 필요'로 끝낸다 (예: '○○ 프로젝트 API 담당은
  기재, ○○ 사용 여부 확인 필요'). NO_RECORD는 직접적이지 않은 흔적이 있으면 그 흔적과 무엇이 기재되지 않았는지 쓰고
  '서류에 기재되지 않음'으로 끝내고 (예: '○○ 현장 업무는 기재, ○○ 개발은 서류에 기재되지 않음'), 없으면 비운다.
- 경력 기간 항목은 기간을 코드가 계산한다. career_periods에 항목의 직무 · 기술에 맞는 경력표 번호만 고른다. 인턴과
  교육 · 개인 프로젝트는 실무 경력이 아니다. 기간이 모자라도 직무 · 기술이 맞으면 MET로 답한다.
- 자격요건을 NOT_MET으로 판정하면 shortfall에 확인되지 않은 것을 요건의 낱말로 아주 짧게 쓴다 (12자 이내).
- 나이, 성별, 출신 지역, 혼인 여부, 신체 조건은 판단에 쓰지 않는다."""

JUDGE_SYSTEM = f"""너는 지원 서류를 공고의 평가 항목에 대조해 항목마다 판정한다. 점수와 중요도는 다루지 않는다.

## 항목 판정 (verdicts)
{JUDGE_RULES}

{UNTRUSTED_RULE}"""

RECHECK_NOTE = (
    "재확인: 위 항목은 앞 판정이 확인 필요였다 (항목마다 '앞 판정 이유'). 근거 문장의 주변 문맥과 본인 역할, "
    "다른 제출 문서에 보완하거나 어긋나는 근거가 있는지 함께 보고 다시 판정해 줘. "
    "그래도 정할 수 없으면 UNKNOWN으로 둔다."
)


class RequirementPart(BaseModel):
    part: str = Field(description="항목 문장이 요구하는 것 하나")
    found: bool = Field(description="서류에서 본인이 한 것으로 확인됐는가")


class CriterionVerdict(BaseModel):
    criterion_id: str = Field(description="항목 번호 (예: Q-01)")
    parts: list[RequirementPart] = Field(default=[], description="항목 문장을 요구 부분으로 나눠 부분마다 확인한 표")
    relevance: str = ""
    role: Literal["SELF", "TEAM", "UNCLEAR"] = "UNCLEAR"
    scope: str = ""
    verdict: Literal["MET", "PARTIAL", "NOT_MET", "NO_RECORD", "UNKNOWN"]
    reason: str = Field(description="판정 기준에 비춘 이유 한 문장")
    brief: str = Field(default="", description="카드에 보일 판정 요약 한 줄 (40자 안팎)")
    setting_note: str = Field(default="", description="판정 기준이 정하지 않아 판정이 갈리는 점. 없으면 비운다")
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


def judge_answers(
    criteria: Sequence[Criterion], verdicts: Sequence[CriterionVerdict], evidence: Evidence
) -> list[CriterionResult]:
    """모델 판정에 코드 규칙을 적용한다. 자격증 보유 조건은 코드가 판정하고 모델 답은 쓰지 않는다."""
    indexed = _index_verdicts(verdicts, {criterion.criterion_id for criterion in asked_criteria(criteria)})
    return [
        certificate_result(criterion, evidence)
        if criterion.certificates
        else _settle_answer(criterion, indexed, evidence)
        for criterion in criteria
    ]


def asked_criteria(criteria: Sequence[Criterion]) -> list[Criterion]:
    """모델에 묻는 항목. 자격증 보유 조건은 코드가 인정 자격증 이름으로 찾는다."""
    return [criterion for criterion in criteria if not criterion.certificates]


def criteria_listing(criteria: Sequence[Criterion], reasons: dict[str, str] | None = None) -> str:
    """판정 프롬프트의 평가 항목 목록. reasons가 있으면 항목마다 앞 판정 이유를 붙인다 (재판정)."""
    lines = []
    for criterion in criteria:
        line = criterion_listing(criterion)
        if reasons and criterion.criterion_id in reasons:
            line += f"\n  - 앞 판정 이유: {reasons[criterion.criterion_id]}"
        lines.append(line)
    return "# 평가 항목\n" + "\n".join(lines)


async def recheck_criteria(
    llm: LlmClient, criteria: Sequence[Criterion], previous: Sequence[CriterionResult], evidence: Evidence
) -> list[CriterionResult]:
    """확인 필요 항목을 모아 한 번에 다시 판정한다. 제출 문서 전체와 뽑은 사실로 주변 문맥 · 본인 역할과 다른 문서의
    보완 · 상충 근거를 함께 본다. 다시 판정한 항목은 recheck_count를 1 올리고, 그 밖의 항목은 그대로 돌려준다.
    """
    by_id = {criterion.criterion_id: criterion for criterion in criteria}
    targets = [
        result
        for result in previous
        if result.verdict == Verdict.UNKNOWN and result.certificate_status is None and result.criterion_id in by_id
    ]
    usable = readable(evidence.documents)
    if not targets or not usable:
        return list(previous)
    asked = [by_id[result.criterion_id] for result in targets]
    parts = [criteria_listing(asked, {result.criterion_id: result.reason for result in targets})]
    if any(_CAREER_YEARS.search(criterion.text) for criterion in asked):
        parts.append(career_block(evidence.periods))
    parts += [
        "# 제출한 자격증\n" + data_block("certificates", evidence.certificates or "(없음)"),
        "# 서류\n" + documents_block(usable),
        "# facts\n" + data_block("facts", fact_lines(evidence.facts) or "(없음)"),
        "# 요청\n" + RECHECK_NOTE,
    ]
    answer = await ask(llm, CriteriaJudgement, system=JUDGE_SYSTEM, user="\n\n".join(parts))
    again = {
        result.criterion_id: result.model_copy(update={"recheck_count": before.recheck_count + 1})
        for result, before in zip(judge_answers(asked, answer.verdicts, evidence), targets, strict=True)
    }
    return [again.get(result.criterion_id, result) for result in previous]


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


def asks_career_years(criterion: Criterion) -> bool:
    """경력 기간(경력 N년)을 묻는 항목인가. 기간은 코드가 경력표로 센다."""
    return bool(_CAREER_YEARS.search(criterion.text))


def settle(criterion: Criterion, verdict: CriterionVerdict | None, evidence: Evidence) -> CriterionResult:
    """모델 판정에 코드 규칙을 적용한다. 받을 수 없는 답은 미충족이 아니라 확인 필요로 둔다."""
    base = _base(criterion)
    if verdict is None:
        return _unknown(base, "모델 응답에 이 항목이 없어 판정하지 못했어요.")
    # 언급 없음은 미충족의 한 갈래다. 표기 · 거르기 · 리포트는 미충족(하)과 같고, 카드 요약만 따로 쓴다
    no_record = verdict.verdict == "NO_RECORD"
    level = Verdict.NOT_MET if no_record else Verdict(verdict.verdict)
    # 요건을 부분으로 나눠 확인한 표에서 하나라도 확인되지 않았으면 충족이 아니다 (나열은 모두 요구한다).
    # 복합 경험형은 확인된 부분이 있으면 부분 충족, 그 밖의 유형은 미충족이다
    found_parts, missing_parts = _parts(criterion, verdict) if level == Verdict.MET else ([], [])
    if missing_parts:
        composite = criterion.criterion_type == CriterionType.COMPOSITE
        level = Verdict.PARTIAL if composite and found_parts else Verdict.NOT_MET
    quotes = quotes_in(evidence.documents, verdict.evidence)
    # 지표는 여기서 고르지 않는다. 성과 장부(achievements)가 지원자 단위로 정한 연결을 검증 뒤에 붙인다
    role = _role(verdict.role, quotes, evidence.facts)
    result = base.model_copy(
        update={
            "verdict": level,
            "no_record": no_record,
            "setting_note": " ".join(verdict.setting_note.split()),
            "brief": " ".join(verdict.brief.split()) or (NO_RECORD_BRIEF if no_record else ""),
            "reason": verdict.reason,
            "relevance": verdict.relevance,
            "role": role,
            "scope": verdict.scope,
            "satisfied_parts": verdict.satisfied_parts,
            "unsatisfied_parts": verdict.unsatisfied_parts,
            "unknown_parts": verdict.unknown_parts,
            # 하 · 확인 필요도 판단에 쓴 흔적 문장을 남긴다 (담당자가 무엇을 보고 판정했는지 알 수 있게)
            "quotes": _own_first(quotes, evidence.facts),
        }
    )
    if missing_parts:
        missing = " · ".join(missing_parts)
        result = result.model_copy(
            update={
                "satisfied_parts": found_parts,
                "unsatisfied_parts": missing_parts,
                "brief": f"{' · '.join(found_parts)} 확인, {missing} 미확인" if found_parts else "",
                "reason": f"요구한 것 가운데 {missing}은 서류에서 확인되지 않아요.",
            }
        )
    if level == Verdict.PARTIAL and criterion.criterion_type != CriterionType.COMPOSITE:
        return _unknown(result, f"{_TYPE_LABEL[criterion.criterion_type]} 항목인데 부분 충족으로 답해 받지 않았어요.")
    if level == Verdict.PARTIAL and not (result.satisfied_parts and result.unsatisfied_parts):
        return _unknown(result, "부분 충족인데 충족한 부분과 미충족한 부분을 나눠 설명하지 않았어요.")
    if level in (Verdict.MET, Verdict.PARTIAL) and not quotes:
        return _unknown(result, "판정을 받쳐 줄 근거 문장을 원문에서 찾지 못했어요.")
    if level == Verdict.MET and criterion.criterion_type != CriterionType.CONDITION and role != Actor.SELF:
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
        update={
            "verdict": Verdict.NOT_MET,
            "reason": f"인정 자격증({names})이 서류에서 확인되지 않아요.",
            "no_record": True,
            "brief": NO_RECORD_BRIEF,
        }
    )
    if criterion.category == CriterionCategory.QUALIFICATION:
        result = result.model_copy(update={"shortfall": unmet_label(criterion.certificates[0])})
    return result


def verification_claims(
    results: Sequence[CriterionResult],
    documents: Sequence[ApplicantDocument] = (),
    criteria: Sequence[Criterion] = (),
) -> list[Claim]:
    """검증할 판정: 모델이 충족 · 부분 충족으로 본, 인용이 있는 항목. 근거가 판정을 의미상 받쳐 주는지 본다.
    근거 문장이 나온 문단을 맥락으로, 그 판정의 기준 문장을 주장에 함께 넘긴다. 검증이 같은 일의 앞뒤 문장
    (운영 · 성과)을 보고, 기준 문장보다 엄격한 조건을 더하지 않게 한다.
    """
    rules = {criterion.criterion_id: criterion.evaluation_rules for criterion in criteria}
    judged = [
        result
        for result in results
        if result.verdict in (Verdict.MET, Verdict.PARTIAL) and result.quotes and result.certificate_status is None
    ]
    return [
        Claim(
            result.criterion_id,
            f"'{result.text}'을 {VERDICT_LABEL[result.verdict]}했다. 판정 이유: {result.reason}"
            + _rule_text(result, rules),
            result.quotes,
            paragraphs(result.quotes, documents),
        )
        for result in judged
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
                        # 낮춘 판정에 맞는 요약. 검증이 쓰지 않았으면 판정 요약을 지우지 않고 부분 확인임을 알린다
                        "brief": " ".join(review.brief.split()) or "근거가 기준 일부만 받쳐 줌, 나머지 미확인",
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


def _rule_text(result: CriterionResult, rules: dict[str, EvaluationRules]) -> str:
    rule = rules.get(result.criterion_id)
    if rule is None:
        return ""
    text = rule.met if result.verdict == Verdict.MET else rule.partial
    return f" {VERDICT_LABEL[result.verdict]} 기준: {text}" if text else ""


_PARAGRAPH = re.compile(r"\n\s*\n")
PARAGRAPH_CHARS = 600


def paragraphs(
    quotes: Sequence[Quote], documents: Sequence[ApplicantDocument], limit: int | None = PARAGRAPH_CHARS
) -> str:
    """근거 문장이 들어 있는 문단들 (문서 안에서 빈 줄로 나뉜 덩어리). 검증 모델에 줄 때는 문단마다 잘라 쓰고,
    코드가 찾을 때는(limit=None) 자르지 않는다 (PDF는 빈 줄이 없어 문단이 길다)."""
    found: list[str] = []
    for quote in quotes:
        for document in readable(documents):
            if document.type != quote.document:
                continue
            for paragraph in _PARAGRAPH.split(document.text):
                text = " ".join(paragraph.split())
                if _compact(quote.sentence) in _compact(paragraph) and text not in found:
                    found.append(text[:limit] if limit else text)
    return " / ".join(found)


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


def criterion_listing(criterion: Criterion) -> str:
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
                "brief": f"관련 경력 {months // 12}년 {months % 12}개월 (요건 {years}년 이상)",
                "reason": f"요건과 관련된 재직 경력이 {months // 12}년 {months % 12}개월이에요 (요건 {years}년 이상).",
                "shortfall": "신입" if total < 12 else f"경력 {months // 12}년",
                "career_months": months,
                "quotes": [],
            }
        )
    return result.model_copy(update={"career_months": months})


def _employment_months(periods: Sequence[Period], numbers: Sequence[int], today: date) -> int:
    """고른 기간 가운데 재직(EMPLOYMENT) 기간의 합. 겹치는 기간은 한 번만 세고, 시작 달과 끝 달을 모두 센다."""
    current = today.year * 12 + today.month - 1
    spans = []
    for number in numbers:
        period = periods[number - 1]
        begin = month_index(period.start)
        finish = month_index(period.end) if period.end else current
        if period.kind == EMPLOYMENT and begin is not None and finish is not None and finish >= begin:
            spans.append((begin, finish + 1))
    total, reach = 0, -1
    for begin, finish in sorted(spans):
        if finish <= reach:
            continue
        total += finish - max(begin, reach)
        reach = finish
    return total


def career_block(periods: Sequence[Period]) -> str:
    """판정 프롬프트의 번호 붙은 경력표. 모델은 번호로 답한다 (career_periods)."""
    return "# 경력표 (코드가 계산한 개월 수, 번호로 답한다)\n" + data_block("career", numbered_career_table(periods))


def numbered_career_table(periods: Sequence[Period]) -> str:
    if not periods:
        return "(서류에서 찾은 근무 기간이 없음)"
    return "\n".join(
        f"{number}. {period.company} · {period.role or '역할 미기재'} · {period.kind} · "
        f"{period.start} ~ {period.end or '현재'} · {period.months}개월"
        for number, period in enumerate(periods, start=1)
    )


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
    """확인 필요로 둔다. 모델이 다른 판정으로 쓴 요약은 맞지 않으니 모델이 확인 필요로 답했을 때만 남긴다."""
    shortfall = None
    if result.category == CriterionCategory.QUALIFICATION:
        shortfall = label or unknown_label(result.text)
    brief = result.brief if result.verdict == Verdict.UNKNOWN else ""
    return result.model_copy(
        update={
            "verdict": Verdict.UNKNOWN,
            "reason": reason,
            "shortfall": shortfall,
            "metric": "",
            "no_record": False,
            "brief": brief,
        }
    )


def _parts(criterion: Criterion, verdict: CriterionVerdict) -> tuple[list[str], list[str]]:
    """모델이 나눈 요건 부분 가운데 확인된 것과 확인되지 않은 것. 조건형이거나 부분이 하나뿐이면 나누지 않는다.

    충족 기준이 '~하거나' · '또는' · '중 하나'로 하나만 요구하면(either_of), 모델이 그 요구를 여러 부분으로 나눴더라도
    하나가 확인되면 모자란 부분이 없는 것으로 본다 (나열을 모두 요구하는 규칙으로 충족을 낮추지 않는다).
    """
    if criterion.criterion_type == CriterionType.CONDITION or len(verdict.parts) < 2:
        return [], []
    found = [" ".join(item.part.split()) for item in verdict.parts if item.found]
    missing = [" ".join(item.part.split()) for item in verdict.parts if not item.found]
    if found and either_of(criterion):
        return found, []
    return found, missing


# 충족 기준이 하나만 요구한다는 말과, 여럿을 함께 요구한다는 말
_EITHER = re.compile(r"거나|또는|혹은|(?:중|가운데)\s*(?:하나|한\s*가지)|어느\s*하나")
_BOTH = re.compile(r"하고|했고|이고|모두|함께|및|그리고|[와과]\s")


def either_of(criterion: Criterion) -> bool:
    """충족 기준이 여러 행동 가운데 하나만 요구하는가 (예: '개발하거나 운영했다'). 함께 요구하는 말이 섞였으면
    (예: '설계하고 운영하거나 개선했다') 어느 것이 하나만인지 코드가 가를 수 없어 아니라고 본다."""
    met = criterion.evaluation_rules.met
    return bool(_EITHER.search(met)) and not _BOTH.search(met)


def _own_first(quotes: Sequence[Quote], facts: Sequence[Fact]) -> list[Quote]:
    """본인 경험(SELF)으로 뽑힌 문장을 앞에 둔다. 화면은 앞쪽 근거를 먼저 보여 주므로, 회사 구성 · 팀 성과 문장이
    본인 행동보다 먼저 보이지 않게 한다. 같은 묶음 안에서는 모델이 고른 순서를 지킨다.
    """
    own = {_compact(quote.sentence) for fact in facts if fact.actor == Actor.SELF for quote in fact.quotes}
    return sorted(quotes, key=lambda quote: not any(_compact(quote.sentence) in sentence for sentence in own))


def _role(answer: str, quotes: Sequence[Quote], facts: Sequence[Fact]) -> Actor:
    """모델이 본인 역할을 UNCLEAR로 답해도, 근거 문장이 서류 문장 분석에서 본인 경험(SELF)으로 뽑힌 문장이면 본인이다.
    TEAM은 모델이 이 항목을 두고 팀 경험이라고 본 것이라 그대로 둔다.
    """
    if answer != "UNCLEAR":
        return Actor(answer)
    sentences = {_compact(quote.sentence) for quote in quotes}
    own = any(
        fact.actor is Actor.SELF and fact.supported and _compact(quote.sentence) in sentences
        for fact in facts
        for quote in fact.quotes
    )
    return Actor.SELF if own else Actor.UNCLEAR


# 비교 기준이 드러난 표현: 수치 바로 뒤 '에서' · '부터' ('38초에서'), 화살표, '대비', '기준'.
# 장소를 뜻하는 '에서'('뷰티픽'에서 ~ 300% 개선)는 기준이 아니다.
BASELINE = re.compile(r"\d[\d,.]*\s*[^\s\d]{0,6}\s*(?:에서|부터)|→|->|대비|기준")


def baseless_number(text: str) -> bool:
    """기준값 없는 수치인가: 숫자가 모두 %나 배로 크기만 말하고 전후 값 · 비교 기준이 없다 ('300% 개선, 5배 향상')."""
    units = re.findall(r"\d[\d,.]*\s*(%|배)?", text)
    return bool(units) and all(units) and not BASELINE.search(text)


def _line_quote(name: str, document: ApplicantDocument) -> Quote | None:
    for line in document.text.splitlines():
        if _compact(name) in _compact(line):
            return locate(line, [document])
    return None


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()
