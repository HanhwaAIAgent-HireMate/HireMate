"""검증: 앞 단계가 낸 주장을 원문 근거로 검토하고, 검토를 통과한 본인 경험으로 '눈여겨볼 점'을 묶는다.

판정 · 추출을 낸 호출과 다른 호출로 검토한다 (같은 호출의 자기 검증은 다시 보는 효과가 없다). 눈여겨볼 점은 검토
결과에 기대므로 같은 호출에서 함께 받는다. 사실 번호(F1 …)는 사실 목록 전체의 위치라, 검토한 주장과 묶을 경험이 같은
번호를 쓴다. 검토가 받쳐 주지 않는다고 본 사실은 코드가 묶음의 근거에서 뺀다 (check_highlights).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from hiremate_ai.agents.analysis.application.ask import ask
from hiremate_ai.agents.analysis.application.highlight import (
    HIGHLIGHT_RULES,
    Highlight,
    check_highlights,
    experience_lines,
    experiences,
)
from hiremate_ai.agents.analysis.application.review import REVIEW_RULES, Claim, ClaimReview, claim_lines
from hiremate_ai.agents.analysis.application.types import Fact, Note
from hiremate_ai.contract import ApplicantDocument
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

VERIFY_SYSTEM = f"""너는 다른 단계가 낸 주장을 원문 근거로 검토하고, 검토를 통과한 본인 경험을 묶는다.
새 사실 · 새 판정을 만들지 않는다.

# 입력
- claims: 검토할 주장. 사실(F1 …), 평가 항목 판정(Q-01, P-01 …), 수치 성과(R1 …)가 있고, 주장마다 근거와 맥락이 있다.
- experiences: 묶을 본인 경험 목록. 번호(F1 …)는 claims의 사실 번호와 같다.

# 출력 (이 순서로 쓴다)
1. reviews: claims의 주장마다 검토. 빠짐없이 쓴다.
2. highlights: 눈여겨볼 점 묶음. experiences가 없으면 비운다.

## 1. 주장 검토 (reviews)
{REVIEW_RULES}

## 2. 눈여겨볼 점 (highlights)
- experiences의 본인 경험을 HR이 눈여겨볼 핵심 기여 1~2개로 묶는다.
- 1번에서 SUPPORTED가 아니라고 본 F 주장은 묶음의 근거(sources)로 쓰지 않는다.
{HIGHLIGHT_RULES}

{UNTRUSTED_RULE}"""


class Verification(BaseModel):
    reviews: list[ClaimReview] = Field(default=[], description="주장마다 검토")
    highlights: list[Highlight] = Field(default=[], description="눈여겨볼 점 묶음. 묶을 경험이 없으면 비운다")


@dataclass(frozen=True)
class Verified:
    """검토 결과(주장 id → 검토)와, 검토를 통과한 사실을 반영한 사실 목록 · 눈여겨볼 점."""

    reviews: dict[str, ClaimReview]
    facts: list[Fact]
    notable: list[Note]


async def verify(
    llm: LlmClient,
    facts: Sequence[Fact],
    fact_numbers: Sequence[int],
    claims: Sequence[Claim],
    documents: Sequence[ApplicantDocument],
) -> Verified:
    """주장(사실 · 판정 · 성과)을 검토하고 눈여겨볼 점을 묶는다. 둘 다 없으면 모델을 부르지 않는다.

    fact_numbers는 claims 가운데 사실 주장이 가리키는 사실 번호(facts 안의 위치, 1부터)다. 받쳐 주지 않는다고 본 사실은
    supported를 끈다 (카드에서 빠진다).
    """
    candidates = experiences(facts)
    if not claims and not candidates:
        return Verified({}, list(facts), [])
    parts = [
        "# claims\n" + data_block("claims", claim_lines(claims) or "(없음)"),
        "# experiences\n" + data_block("experiences", experience_lines(candidates) or "(없음)"),
        "# 요청\n주장마다 근거가 받쳐 주는지 검토하고(reviews), 검토를 통과한 본인 경험을 묶어 줘(highlights).",
    ]
    answer = await ask(llm, Verification, system=VERIFY_SYSTEM, user="\n\n".join(parts))
    ids = {claim.id for claim in claims}
    reviews = {review.id: review for review in answer.reviews if review.id in ids}
    checked = list(facts)
    for number in fact_numbers:
        review = reviews.get(f"F{number}")
        if review is not None and review.verdict != "SUPPORTED":
            checked[number - 1] = checked[number - 1].model_copy(update={"supported": False})
    # 묶음의 근거는 검토를 통과한 경험만 (번호는 그대로)
    passed = {number: checked[number - 1] for number, _ in candidates if checked[number - 1].supported}
    notable = check_highlights(passed, answer.highlights, documents) if candidates else []
    return Verified(reviews, checked, notable)
