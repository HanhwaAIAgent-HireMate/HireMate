"""리포트 문장 속 서류 평가 항목 코드(Q-04)를 항목 이름으로 바꾸기 (QA DE-22 · 23)."""

import pytest

from hiremate_ai.agents.generation.report.repair import _item_name, name_items

NAMES = {"Q-01": "Java 또는 Kotlin", "Q-04": "Git 기반 코드 리뷰", "P-03": "요구사항을 분석"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Q-04는 27명이 충족했어요.", "'Git 기반 코드 리뷰' 항목은 27명이 충족했어요."),
        ("Q-01과 Q-04가 갈렸어요.", "'Java 또는 Kotlin' 항목과 'Git 기반 코드 리뷰' 항목이 갈렸어요."),
        ("P-03은 18명이에요.", "'요구사항을 분석' 항목은 18명이에요."),
        ("P-03로 나뉘어요.", "'요구사항을 분석' 항목으로 나뉘어요."),
        ("Q-04에서 판정이 갈렸어요.", "'Git 기반 코드 리뷰' 항목에서 판정이 갈렸어요."),
        ("Q-04이에요.", "'Git 기반 코드 리뷰' 항목이에요."),
    ],
)
def test_item_codes_become_item_names(text: str, expected: str) -> None:
    assert name_items(text, NAMES) == expected


def test_unknown_codes_and_applicant_numbers_stay() -> None:
    # 모르는 코드와 지원자번호(A-0012)는 그대로 둔다
    assert name_items("Q-09와 A-0012를 봐요.", NAMES) == "Q-09와 A-0012를 봐요."


def test_item_name_is_short_without_code() -> None:
    assert _item_name("Q-04", "Q-04 Git 기반 코드 리뷰와 협업 경험") == "Git 기반 코드 리뷰와 협업"
    assert _item_name("Q-01", "Java 또는 Kotlin 기반 서버 개발 경험") == "Java 또는 Kotlin"
    assert _item_name("Q-05", "MySQL · PostgreSQL 등 RDBMS 경험") == "MySQL"
