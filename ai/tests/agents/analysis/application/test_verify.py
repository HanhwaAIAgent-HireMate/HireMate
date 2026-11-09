"""검증: 주장 검토와 눈여겨볼 점 묶기를 한 번에 받고, 검토에서 떨어진 사실은 묶음에 쓰지 않는지 본다."""

from uuid import uuid4

from hiremate_ai.agents.analysis.application.highlight import Highlight
from hiremate_ai.agents.analysis.application.review import ClaimReview, fact_claims
from hiremate_ai.agents.analysis.application.types import Actor, Fact, Quote
from hiremate_ai.agents.analysis.application.verify import Verification, verify
from hiremate_ai.contract import ApplicantDocument, DocumentType
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.llm.prompt import UNTRUSTED_RULE

BUILD_TEXT = "정산 배치 코드를 작성했습니다."
TUNE_TEXT = "쿼리를 나눠 처리 시간이 40분에서 12분으로 줄었습니다."
LEAD_TEXT = "결제 시스템 전체 설계를 혼자 주도했습니다."
PORTFOLIO = ApplicantDocument(
    type=DocumentType.PORTFOLIO,
    file_id=uuid4(),
    file_name="포트폴리오.pdf",
    size=1,
    text=f"{BUILD_TEXT}\n{TUNE_TEXT}\n{LEAD_TEXT}",
)


def fact(statement: str, sentence: str, actor: Actor = Actor.SELF, kind: str = "EXPERIENCE") -> Fact:
    return Fact(
        kind=kind,
        statement=statement,
        actor=actor,
        quotes=[Quote(document=DocumentType.PORTFOLIO, sentence=sentence)],
    )


TEAM = fact("팀이 정산 시스템을 이관했다", "팀이 정산 시스템을 이관했습니다.", Actor.TEAM)
BUILD = fact("정산 배치를 작성했다", BUILD_TEXT)
TUNE = fact("배치 처리 시간을 줄였다", TUNE_TEXT, kind="ACHIEVEMENT")
LEAD = fact("결제 시스템 설계를 주도했다", LEAD_TEXT, kind="PROJECT")


async def test_rejected_fact_is_dropped_from_the_card_and_from_groups() -> None:
    facts = [TEAM, BUILD, TUNE, LEAD]
    numbers = [3, 4, 2]  # 눈여겨볼 점 후보. 번호는 사실 목록 전체의 위치다
    claims = fact_claims([facts[number - 1] for number in numbers], numbers)
    answer = Verification(
        reviews=[
            ClaimReview(id="F3", verdict="SUPPORTED"),
            ClaimReview(id="F4", verdict="OVERSTATED", reason="혼자 주도했다는 근거가 없다"),
            ClaimReview(id="F2", verdict="SUPPORTED"),
        ],
        highlights=[
            Highlight(title="설계 주도", detail="결제 시스템 설계", sources=["F4"]),
            Highlight(title="정산 배치 개선", detail="배치 작성", metric="40분 → 12분", sources=["F2", "F3"]),
        ],
    )
    llm = FakeLlm(answer)

    checked = await verify(llm, facts, numbers, claims, [PORTFOLIO])

    [call] = llm.calls
    assert UNTRUSTED_RULE in call.system and "[1. 주장 검토] reviews" in call.system
    # 검토할 주장과 묶을 경험이 같은 번호를 쓴다. 팀 경험은 묶을 후보로 넘기지 않는다
    assert "F4. 주장" in call.user and "F4. [본인]" in call.user and "F1. [" not in call.user
    assert [fact.supported for fact in checked.facts] == [True, True, True, False]
    assert [note.title for note in checked.notable] == ["정산 배치 개선"]  # 떨어진 F4로만 묶은 묶음은 뺀다
    assert set(checked.reviews) == {"F2", "F3", "F4"}


async def test_nothing_to_check_makes_no_call() -> None:
    llm = FakeLlm()

    checked = await verify(llm, [BUILD, TEAM], [], [], [PORTFOLIO])

    assert llm.calls == []
    assert checked.notable == [] and checked.facts == [BUILD, TEAM]
