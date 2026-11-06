"""주장이 원문 근거로 뒷받침되는지 모델이 한 번에 검토한다 (graph의 verify 노드가 부른다).

생성과 검토의 입력을 나눈다. 검토는 새 사실 · 새 판정을 만들지 않고, 과장이나 근거 없음만 짚는다. 주장은 세 가지다.
- 눈여겨볼 점 후보 사실 (F1, F2 …): 짚은 사실은 카드에서 뺀다 (apply_to_facts).
- 평가 항목의 충족 · 부분 충족 판정 (Q-01, P-01 …): 근거 문장과 그 문단을 맥락으로, 판정 기준 문장에 해당하는지 본다.
  근거가 받쳐 주지 않으면 확인 필요로, 복합 경험형 충족이 과장이면 부분 충족으로 낮춘다 (judge.apply_verification).
  지표가 빈 항목에는 [성과 수치 찾기]가 붙어, 맥락에서 전후 성과 수치 문장(result_quotes)도 찾는다.
- 판정의 정량 지표 (Q-01#metric …): 본인 행동 뒤에 바뀐 결과인지 본다. 아니면 지표만 뺀다.
- 성과 수치 다시 찾기 (Q-01#result …): 첫 검증에서 수치를 찾지 못한 항목만, 결과 수치만 다시 찾는다 (판정은 그대로).
근거 문장이 원문에 있는지는 코드가 인용으로 확인하고, 검토 모델은 의미상 받쳐 주는지만 본다.
판정을 바꾸는 쪽은 낮추는 방향뿐이다 (검토가 판정을 올리지 않는다).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.types import (
    Fact,
    Quote,
)
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

REVIEW_SYSTEM = f"""너는 다른 판정이 원문 근거로 뒷받침되는지 검토한다. 새 판정을 만들지 않는다.

- SUPPORTED: 근거 문장이 주장을 그대로 받쳐 준다.
- OVERSTATED: 근거가 더 약한 주장만 받쳐 준다. 예: 참여를 주도로, 팀 성과를 개인 성과로, 일부를 전부로 본 경우.
- UNSUPPORTED: 근거 문장이 주장과 관계없거나 주장을 받쳐 주지 않는다.
- 주장에 판정 기준이 있으면 근거가 그 기준 문장에 해당하는지로 본다. 기준 문장에 없는 조건(명시적 표현, 혼자 했는지
  같은)을 더하지 않는다. 표현이 달라도 같은 행동이면 해당한다 (예: '원인을 특정했다'는 '원인을 찾았다'에 해당한다).
- 기준의 낱말이 근거에 없어도, 그 부분 없이는 할 수 없는 일을 본인이 했다고 적혀 있으면 그 부분은 받쳐 준 것이다
  (예: 인덱스를 만들고 쿼리를 고쳤다 → SQL을 작성했다, PR을 올려 리뷰를 받았다 → Git으로 협업했다). 그 일에 반드시
  들어가는 경우만 그렇다.
- 수치 주장은 그 수치가 주장에 적힌 항목의 행동 뒤에 바뀐 결과인지 본다. 항목과 관계없는 일의 수치, 바꾼 설정값은
  받쳐 주지 않는다.
- 맥락은 근거 문장이 나온 문단이다. 같은 문단에서 같은 일을 말하는 문장(구현 · 운영 · 그 개선의 성과)은
  함께 근거로 본다.
- 근거 문장과 맥락 밖의 지식으로 보충하지 않는다. SUPPORTED가 아니면 reason에 기준 문장의 어느 부분이 근거와 맥락
  어디에도 없는지, 또는 근거의 어느 문장과 어긋나는지 구체적으로 쓴다. '불충분하다' 같은 막연한 이유로 낮추지 않는다.
  근거 문장 하나에 없는 내용이 같은 맥락 문단에 있으면 SUPPORTED다.
- 주장에 [성과 수치 찾기]가 붙어 있으면, 근거와 맥락에서 그 항목의 본인 행동 뒤에 바뀐 결과 수치를 찾아 result_quotes에
  원문 글자 그대로 옮긴다. 바뀌기 전 값과 바뀐 뒤 값이 모두 있어야 한다. '→' 같은 기호 없이 줄글로 적혀 있어도 되고
  (예: '처리에 40분이 걸렸다' … '12분으로 줄었다'), 두 값이 다른 문장에 나뉘어 있으면 두 문장을 모두 옮긴다.
  결과는 하나만, 가장 잘 맞는 것의 전후 문장만 옮긴다 (많아야 두 문장). 서로 다른 결과를 함께 옮기지 않는다.
  표에서 옮길 때는 숫자만 있는 행이 아니라 무엇의 값인지 드러나는 줄(값 이름이 있는 행)을 옮긴다.
  결과(처리 · 소요 시간, 오류율, 건수 같은 성과)만 옮긴다. 운영 · 팀 규모, 바꾼 설정값, 본인 조치 밖의 다른 효과(다른
  팀 · 회사의 개편 등)가 섞였다고 원문이 밝힌 수치, 다른 프로젝트 · 개인 테스트 환경의 수치는 옮기지 않는다.
  본인이 여러 조치를 함께 해서 낸 결과는 옮기고, result_note에 함께 적용한 조치를 짧게 쓴다 (예: '인덱스 + 캐시
  함께 적용'). result_summary에는 찾은 결과를 '무엇 전 값 → 후 값' 형식으로 30자 안팎으로 요약한다 (예: '좌석 조회
  p95 1.8초 → 290ms'). 숫자는 원문 그대로 쓴다. 항목에 규모를 나타내는 말(대용량, 대규모 등)이 있으면 그 규모
  (몰린 요청 · 늘어난 처리량) 때문에 생긴 문제를 해결한 결과만 옮긴다. 없으면 비운다. 판정 검토는 그대로 한다.
- 수치(지표 주장, [성과 수치 찾기])는 그 항목이 묻는 일 자체를 바꿔서 생긴 결과여야 한다. 항목이 도구 · 언어를
  썼는지, 원칙을 이해하는지, 협업 방식을 묻는다면, 그 도구 · 원칙 · 방식을 적용한 변경으로 생긴 결과만 해당하고
  그 도구로 만든 서비스의 다른 개선은 해당하지 않는다 (예: 캐시를 붙여 응답 시간이 줄었다 → 캐시 활용 항목의 결과다.
  같은 서비스의 쿼리 개선 수치 → 'Java 사용' 항목의 결과가 아니다. 리뷰 방식을 바꾼 뒤 머지 시간이 줄었다 → 'Git 협업'
  항목의 결과다). 만든 것의 개수(테스트 · API 개수 등)는 결과가 아니다.
- OVERSTATED면 brief에 담당자 카드에 보일 한 줄을 쓴다 (40자 안팎, 받쳐 주는 부분과 빠진 부분을 명사형으로:
  '○○은 확인, ○○은 미확인'). 그 밖에는 비운다.

{UNTRUSTED_RULE}"""

type Verdict = Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]


class ClaimReview(BaseModel):
    id: str = Field(description="검토한 주장의 id (예: F4)")
    verdict: Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]
    reason: str = ""
    brief: str = Field(default="", description="OVERSTATED일 때 카드 요약 한 줄. 그 밖에는 비운다")
    result_note: str = Field(default="", description="찾은 결과가 여러 조치를 함께 한 결과면 함께 적용한 조치")
    result_summary: str = Field(
        default="", description="찾은 결과의 짧은 요약 '무엇 전 값 → 후 값' (숫자는 원문 그대로)"
    )
    result_quotes: list[str] = Field(
        default=[], description="[성과 수치 찾기]일 때 전후 값이 든 원문 문장들 (원문 글자 그대로). 없으면 비운다"
    )


class ReviewJudgement(BaseModel):
    reviews: list[ClaimReview]


@dataclass(frozen=True)
class Claim:
    id: str
    claim: str
    quotes: Sequence[Quote]
    context: str = ""  # 근거 문장이 나온 문단. 판정 검증에만 넘긴다


async def review_claims(llm: LlmClient, claims: Sequence[Claim]) -> dict[str, ClaimReview]:
    """주장들을 한 번에 검토한다. 주장이 없으면 모델을 부르지 않는다. 답에서 빠진 주장은 결과에 없다."""
    if not claims:
        return {}
    listing = "\n".join(
        f"{claim.id}. 주장: {claim.claim}\n   근거: "
        + " / ".join(quote.sentence for quote in claim.quotes)
        + (f"\n   맥락: {claim.context}" if claim.context else "")
        for claim in claims
    )
    user = f"{data_block('claims', listing)}\n\n주장마다 근거가 받쳐 주는지 검토해 줘."
    answer = await ask(llm, ReviewJudgement, system=REVIEW_SYSTEM, user=user)
    ids = {claim.id for claim in claims}
    return {review.id: review for review in answer.reviews if review.id in ids}


def fact_claims(facts: Sequence[Fact]) -> list[Claim]:
    return [Claim(f"F{index}", fact.statement, fact.quotes) for index, fact in enumerate(facts, start=1)]


def apply_to_facts(facts: Sequence[Fact], reviews: dict[str, ClaimReview]) -> list[Fact]:
    return [
        fact.model_copy(update={"supported": False})
        if (review := reviews.get(f"F{index}")) and review.verdict != "SUPPORTED"
        else fact
        for index, fact in enumerate(facts, start=1)
    ]
