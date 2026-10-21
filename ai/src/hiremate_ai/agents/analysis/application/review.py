"""카드의 '눈여겨볼 점'에 보일 사실 문장이 근거 문장으로 뒷받침되는지 모델이 한 번에 본다.

생성과 검토의 입력을 나눈다. 검토는 새 사실을 만들지 않고, 과장이나 근거 없음만 짚는다.
짚은 사실은 카드에서 뺀다. 판정(자격요건 · 우대사항)은 검토하지 않는다. 근거가 있는지는 원문에서 찾은 인용(코드)으로
정한다. 검토 모델은 같은 문장을 두고도 판단이 흔들려 판정에 쓰면 결과가 크게 흔들렸다.
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
- 근거 문장 밖의 지식으로 보충하지 않는다. SUPPORTED가 아니면 reason에 이유를 한 문장으로 쓴다.

{UNTRUSTED_RULE}"""

type Verdict = Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]


class ClaimReview(BaseModel):
    id: str = Field(description="검토한 주장의 id (예: F4)")
    verdict: Literal["SUPPORTED", "OVERSTATED", "UNSUPPORTED"]
    reason: str = ""


class ReviewJudgement(BaseModel):
    reviews: list[ClaimReview]


@dataclass(frozen=True)
class Claim:
    id: str
    claim: str
    quotes: Sequence[Quote]


async def review_claims(llm: LlmClient, claims: Sequence[Claim]) -> dict[str, ClaimReview]:
    """주장들을 한 번에 검토한다. 주장이 없으면 모델을 부르지 않는다. 답에서 빠진 주장은 결과에 없다."""
    if not claims:
        return {}
    listing = "\n".join(
        f"{claim.id}. 주장: {claim.claim}\n   근거: " + " / ".join(quote.sentence for quote in claim.quotes)
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
