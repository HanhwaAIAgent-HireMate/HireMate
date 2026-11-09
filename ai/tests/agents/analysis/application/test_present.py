from uuid import uuid4

from hiremate_ai.agents.analysis.application.present import to_candidate_analysis, to_profile
from hiremate_ai.agents.analysis.application.types import Actor, ApplicationReview, Fact, Note, Quote
from hiremate_ai.contract import DocumentType
from hiremate_ai.db.profile import ItemCategory, Verification


def fact(statement: str, actor: Actor) -> Fact:
    return Fact(
        kind="EXPERIENCE",
        statement=statement,
        actor=actor,
        quotes=[Quote(document=DocumentType.RESUME, sentence=f"{statement}.")],
    )


def test_team_and_unclear_facts_are_saved_unconfirmed() -> None:
    review = ApplicationReview(
        version="test",
        input_hash="hash",
        application_id=uuid4(),
        readable=True,
        facts=[
            fact("결제 API를 개발했다", Actor.SELF),
            fact("팀이 정산 DB를 이관했다", Actor.TEAM),
            fact("승인 서버 응답 시간을 줄였다", Actor.UNCLEAR),
        ],
    )

    _, items = to_profile(review)

    experiences = {item.content: item.verification for item in items if item.category is ItemCategory.EXPERIENCE}
    assert experiences == {
        "결제 API를 개발했다": None,
        "팀이 정산 DB를 이관했다": Verification.UNCONFIRMED,
        "승인 서버 응답 시간을 줄였다": Verification.UNCONFIRMED,
    }


def test_profile_items_use_plain_style() -> None:
    # 모델이 존댓말로 써도 프로필 항목은 평어(~다)로 저장한다
    review = ApplicationReview(
        version="test",
        input_hash="hash",
        application_id=uuid4(),
        readable=True,
        facts=[fact("결제 API를 개발했습니다", Actor.SELF), fact("배포 자동화를 맡았어요", Actor.SELF)],
    )

    _, items = to_profile(review)

    assert {item.content for item in items if item.category is ItemCategory.EXPERIENCE} == {
        "결제 API를 개발했다",
        "배포 자동화를 맡았다",
    }


def test_stored_company_warning_that_says_there_is_no_mismatch_is_not_displayed() -> None:
    review = ApplicationReview(
        version="test",
        input_hash="hash",
        application_id=uuid4(),
        readable=True,
        checks=[
            Note(
                title="회사명 불일치",
                text="두 곳 모두 케어링크로 일치하며 불일치 없음",
                source="자기소개서",
                warning=True,
            ),
            Note(title="확인 필요", text="역할 확인 필요", source="이력서"),
        ],
    )

    analysis = to_candidate_analysis(review, [])

    assert [item.title for item in analysis.checks] == ["확인 필요"]
