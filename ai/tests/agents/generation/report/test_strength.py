import pytest

from hiremate_ai.agents.generation.report.bundle import Strength
from hiremate_ai.agents.generation.report.strength import quote_strength


@pytest.mark.parametrize(
    "sentence",
    [
        "조회 응답 시간을 800ms에서 120ms로 줄였습니다",
        "배포 시간을 30% 단축했어요",
        "하루 5만 건의 예약을 처리하는 API를 운영했습니다",
        "팀 PR 리뷰 규칙을 만들고 주 2회 리뷰를 이끌었어요",
        "처리량을 3x 늘렸습니다",
        "피크 시 1,200 TPS를 견디도록 개선했습니다",
    ],
)
def test_sentences_with_measured_results_are_quantified(sentence: str) -> None:
    assert quote_strength(sentence) is Strength.QUANT


@pytest.mark.parametrize(
    "sentence",
    [
        "MySQL 예약 테이블을 설계했습니다",
        "Spring Boot로 REST API를 개발했습니다",
        "2023년에 결제 모듈 리팩터링을 맡았습니다",
        "Java 17과 Kotlin으로 서버를 만들었습니다",
        "3 Microservices 구조를 도입했습니다",
        "팀은 총 3명으로 구성되었으며, 저는 API 설계를 맡았습니다",
    ],
)
def test_sentences_that_only_say_what_was_done_are_claims(sentence: str) -> None:
    assert quote_strength(sentence) is Strength.CLAIM


def test_no_quote_has_no_strength() -> None:
    assert quote_strength(None) is None
    assert quote_strength("") is None
