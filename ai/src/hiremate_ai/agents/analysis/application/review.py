"""주장이 원문 근거로 뒷받침되는지 모델이 한 번에 검토한다 (graph의 verify 노드가 부른다).

생성과 검토의 입력을 나눈다. 검토는 새 사실 · 새 판정을 만들지 않고, 과장이나 근거 없음만 짚는다. 주장은 세 가지다.
- 눈여겨볼 점 후보 사실 (F1, F2 …): 짚은 사실은 카드에서 뺀다 (apply_to_facts).
- 평가 항목의 충족 · 부분 충족 판정 (Q-01, P-01 …): 근거 문장과 그 문단을 맥락으로, 판정 기준 문장에 해당하는지 본다.
  근거가 받쳐 주지 않으면 확인 필요로, 복합 경험형 충족이 과장이면 부분 충족으로 낮춘다 (judge.apply_verification).
- 성과 장부의 성과 (R1, R2 …): 지원자 본인의 행동 뒤에 좋아진 측정값인지 성과마다 한 번 본다. 아니면 장부에서 뺀다
  (achievements.apply_achievement_reviews). 항목마다 따로 보지 않아 같은 성과가 항목마다 다르게 다뤄지지 않는다.
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

# 주장 검토 규칙. 검증(verify)이 눈여겨볼 점 묶기와 함께 묻고, Root의 서류 검토(review_claims)도 쓴다
REVIEW_RULES = """- SUPPORTED: 근거 문장이 주장을 그대로 받쳐 준다.
- OVERSTATED: 근거가 더 약한 주장만 받쳐 준다. 예: 참여를 주도로, 팀 성과를 개인 성과로, 일부를 전부로 본 경우.
- UNSUPPORTED: 근거 문장이 주장과 관계없거나 주장을 받쳐 주지 않는다.
- 주장에 판정 기준이 있으면 근거가 그 기준 문장에 해당하는지로 본다. 기준 문장에 없는 조건(명시적 표현, 혼자 했는지
  같은)을 더하지 않는다. 표현이 달라도 같은 행동이면 해당한다 (예: '원인을 특정했다'는 '원인을 찾았다'에 해당한다).
- 기준의 낱말이 근거에 없어도, 그 부분 없이는 할 수 없는 일을 본인이 했다고 적혀 있으면 그 부분은 받쳐 준 것이다
  (예: 인덱스를 만들고 쿼리를 고쳤다 → SQL을 작성했다, PR을 올려 리뷰를 받았다 → Git으로 협업했다). 그 일에 반드시
  들어가는 경우만 그렇다.
- 성과 주장(R1 …)은 그 수치가 지원자 본인의 행동 뒤에 좋아진 측정값인지 본다. 나빠진 수치나 다른 것을 얻으려고
  감수한 악화, 체감 · 추정치, 다른 사람 · 팀 · 업체가 맡은 일의 결과, 본인 조치 밖의 효과가 섞였다고 밝힌 수치,
  운영 · 팀 규모, 바꾼 설정값은 UNSUPPORTED다. 본인이 함께 적용한 여러 조치의 결과는 받쳐 준다.
- 맥락은 근거 문장이 나온 문단이다. 같은 문단에서 같은 일을 말하는 문장(구현 · 운영 · 그 개선의 성과)은
  함께 근거로 본다.
- 근거 문장과 맥락 밖의 지식으로 보충하지 않는다. SUPPORTED가 아니면 reason에 기준 문장의 어느 부분이 근거와 맥락
  어디에도 없는지, 또는 근거의 어느 문장과 어긋나는지 구체적으로 쓴다. '불충분하다' 같은 막연한 이유로 낮추지 않는다.
  근거 문장 하나에 없는 내용이 같은 맥락 문단에 있으면 SUPPORTED다.
- OVERSTATED면 brief에 담당자 카드에 보일 한 줄을 쓴다 (40자 안팎, 받쳐 주는 부분과 빠진 부분을 명사형으로:
  '○○은 확인, ○○은 미확인'). 그 밖에는 비운다."""

REVIEW_SYSTEM = f"""너는 다른 판정이 원문 근거로 뒷받침되는지 검토한다. 새 판정을 만들지 않는다.
주장에 적힌 맥락 C번호는 공통 맥락 목록에서 찾아 함께 본다.

{REVIEW_RULES}

{UNTRUSTED_RULE}"""

type Verdict = Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]


class ClaimReview(BaseModel):
    id: str = Field(description="검토한 주장의 id (예: F4)")
    verdict: Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]
    reason: str = ""
    brief: str = Field(default="", description="OVERSTATED일 때 카드 요약 한 줄. 그 밖에는 비운다")


class ReviewJudgement(BaseModel):
    reviews: list[ClaimReview]


@dataclass(frozen=True)
class Claim:
    id: str
    claim: str
    quotes: Sequence[Quote]
    context: str = ""  # 근거 문장이 나온 문단. 판정 검증에만 넘긴다
    context_parts: tuple[str, ...] = ()  # 여러 주장에 같은 문단이 있으면 한 번만 보낸다


async def review_claims(llm: LlmClient, claims: Sequence[Claim]) -> dict[str, ClaimReview]:
    """주장들을 한 번에 검토한다. 주장이 없으면 모델을 부르지 않는다. 답에서 빠진 주장은 결과에 없다."""
    if not claims:
        return {}
    user = f"{data_block('claims', claim_lines(claims))}\n\n주장마다 근거가 받쳐 주는지 검토해 줘."
    answer = await ask(llm, ReviewJudgement, system=REVIEW_SYSTEM, user=user)
    ids = {claim.id for claim in claims}
    return {review.id: review for review in answer.reviews if review.id in ids}


def claim_lines(claims: Sequence[Claim]) -> str:
    contexts: dict[str, str] = {}
    lines: list[str] = []
    for claim in claims:
        parts = claim.context_parts or ((claim.context,) if claim.context else ())
        refs = []
        for part in parts:
            if part not in contexts:
                contexts[part] = f"C{len(contexts) + 1}"
            refs.append(f"맥락 {contexts[part]}")
        lines.append(
            f"{claim.id}. 주장: {claim.claim}\n   근거: "
            + " / ".join(quote.sentence for quote in claim.quotes)
            + (f"\n   {', '.join(refs)}" if refs else "")
        )
    if contexts:
        lines.append("\n# 공통 맥락\n" + "\n".join(f"{ref}: {text}" for text, ref in contexts.items()))
    return "\n".join(lines)


def fact_claims(facts: Sequence[Fact], numbers: Sequence[int] | None = None) -> list[Claim]:
    """사실 주장 (F1 …). numbers를 주면 그 번호를 쓴다 (사실 목록 전체의 위치로 번호를 맞출 때)."""
    chosen = numbers if numbers is not None else range(1, len(facts) + 1)
    return [Claim(f"F{number}", fact.statement, fact.quotes) for number, fact in zip(chosen, facts, strict=True)]


def apply_to_facts(facts: Sequence[Fact], reviews: dict[str, ClaimReview]) -> list[Fact]:
    return [
        fact.model_copy(update={"supported": False})
        if (review := reviews.get(f"F{index}")) and review.verdict != "SUPPORTED"
        else fact
        for index, fact in enumerate(facts, start=1)
    ]
