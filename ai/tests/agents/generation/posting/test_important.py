from hiremate_ai.agents.generation.posting.important import (
    IMPORTANT_SYSTEM,
    ImportantAdvice,
    ImportantItem,
    ImportantPicks,
    Pick,
    recommend_important,
)
from hiremate_ai.agents.generation.posting.reviser import SourcedItem
from hiremate_ai.contract import PostingContent
from hiremate_ai.llm.fake import FakeLlm

API = "결제 승인 · 정산 API 개발"
TRANSACTIONS = "대용량 트랜잭션 처리 구조 개선"
CONTENT = PostingContent(
    title="결제 플랫폼 백엔드 개발자",
    job_category="백엔드 개발",
    employment_type="정규직",
    career="경력 3년 이상",
    location="서울 중구",
    intro="카드 결제와 정산을 처리하는 플랫폼을 함께 만들 백엔드 개발자를 찾습니다.",
    duties=[API, TRANSACTIONS],
    qualifications=[],
    preferred=[],
    benefits=["유연 근무"],
)
SERVER = "2001020211_23v6"
"""서버프로그램 구현 (현장 조사 점수 2.18)"""
DB_TUNING = "2001020408_19v4"
"""DB엔지니어링 · 데이터베이스 성능확보 (조사 없음)"""
QUALIFICATIONS = [
    SourcedItem(text="서버 프로그램 구현 능력", sources=[SERVER]),
    SourcedItem(text="DB 성능 분석 능력", sources=[DB_TUNING]),
    SourcedItem(text="협업 능력", sources=[]),
]
PREFERRED = [
    SourcedItem(text="결제 도메인 경험", sources=[]),
    SourcedItem(text="대용량 트랜잭션 튜닝 경험", sources=[DB_TUNING]),
    SourcedItem(text="오픈소스 기여 경험", sources=[]),
]
LISTS = {"qualifications": QUALIFICATIONS, "preferred": PREFERRED}


def picks(*pairs: tuple[int, int]) -> ImportantPicks:
    return ImportantPicks(picks=[Pick(item=item, duty=duty) for item, duty in pairs])


async def test_recommends_items_with_the_duty_line_from_the_posting() -> None:
    llm = FakeLlm(picks((1, 1), (2, 2)), picks((2, 2)))

    advice = await recommend_important(llm, CONTENT, LISTS)

    assert advice == ImportantAdvice(
        qualifications=[ImportantItem(index=0, duty=API), ImportantItem(index=1, duty=TRANSACTIONS)],
        preferred=[ImportantItem(index=1, duty=TRANSACTIONS)],
    )


async def test_drops_picks_with_wrong_numbers() -> None:
    """없는 항목이나 없는 주요 업무 번호는 근거가 없어 버린다 (규칙 7)."""
    llm = FakeLlm(picks((4, 1), (1, 3), (0, 1), (3, 2)), picks())

    advice = await recommend_important(llm, CONTENT, LISTS)

    assert advice.qualifications == [ImportantItem(index=2, duty=TRANSACTIONS)]
    assert advice.preferred == []


async def test_keeps_each_item_once_and_at_most_two() -> None:
    items = [SourcedItem(text=f"항목 {number}", sources=[]) for number in range(5)]
    llm = FakeLlm(picks((1, 1), (1, 2), (2, 1), (3, 1)))

    advice = await recommend_important(llm, CONTENT, {"qualifications": items})

    assert [item.index for item in advice.qualifications] == [0, 1]
    assert advice.qualifications[0].duty == API


async def test_recommends_fewer_items_than_the_list_has() -> None:
    """두 항목 목록은 하나까지, 한 항목 목록은 묻지 않는다. 전부 '중요'면 표시하지 않은 것과 같다."""
    two = [SourcedItem(text="가", sources=[]), SourcedItem(text="나", sources=[])]
    llm = FakeLlm(picks((1, 1), (2, 1)))

    advice = await recommend_important(llm, CONTENT, {"qualifications": two, "preferred": two[:1]})

    assert len(llm.calls) == 1
    assert "최대 1개" in llm.calls[0].user
    assert advice == ImportantAdvice(qualifications=[ImportantItem(index=0, duty=API)], preferred=[])


async def test_does_not_ask_without_duties() -> None:
    """근거로 댈 주요 업무가 없으면 묻지 않는다. 응답 없는 FakeLlm이 불리면 테스트가 실패한다."""
    advice = await recommend_important(FakeLlm(), CONTENT.model_copy(update={"duties": []}), LISTS)

    assert advice == ImportantAdvice(qualifications=[], preferred=[])


async def test_prompt_numbers_duties_and_items_and_shows_survey_scores() -> None:
    llm = FakeLlm(picks(), picks())

    await recommend_important(llm, CONTENT, LISTS)

    first, second = (call.user for call in llm.calls)
    header = "지금 공고: 결제 플랫폼 백엔드 개발자 (백엔드 개발, 경력 3년 이상)"
    shared = f"{header}\n주요 업무:\n[업무 1] {API}\n[업무 2] {TRANSACTIONS}"
    assert first.startswith(f"{shared}\n\n자격 요건 목록:\n")
    assert second.startswith(f"{shared}\n\n우대 사항 목록:\n")
    assert "[항목 1] 서버 프로그램 구현 능력 (NCS: 서버프로그램 구현 · 현장 조사 점수 2.18)" in first
    assert "[항목 2] DB 성능 분석 능력 (NCS: 데이터베이스 성능확보)\n" in first
    assert "[항목 3] 협업 능력\n" in first
    assert first.endswith("최대 2개 picks에 고른다. 항목 번호는 item, 주요 업무 번호는 duty에 적는다.")
    assert all(call.system == IMPORTANT_SYSTEM and call.agent == "posting" for call in llm.calls)
