"""🎤 1차 인사 질문 (10/30): 이직자 → 이직 계기, 신입 → 어려움 극복 → 스스로 배운 경험 → 강점 · 보완점.

면접관이 인사 · 실무 2명이라 1차에도 인사가 기록할 질문을 1개 넣는다.
최종면접 자리(원칙 · 협업 · 설득 · 지원 이유)와 겹치지 않는 주제만 쓰고, 우선순위는 모든 회사 · 직무에 같다.
"""

from typing import Any, cast

import pytest

from hiremate_ai.agents.generation.interview.agent import (
    _HARDSHIP,
    CULTURE,
    HR_MOVE_UNKNOWN,
    HR_QUOTE_LIMIT,
    HR_STRENGTH,
    LEADERSHIP,
    VALUES,
    State,
    _final_slot_checked,
    _first_hr_question,
    _hr_quote,
    _technical,
)
from hiremate_ai.contract import ApplicantDetail, DocumentType

HARDSHIP = "출시 일정이 2주 밀려 위기였지만, 팀원들과 매일 범위를 다시 정해 일정을 맞췄습니다."
GROWTH = "부족한 SQL 실력을 채우려고 퇴근 후 스터디를 꾸려 매주 문제를 풀었습니다."
TECH_HARDSHIP = "서버 장애로 API 응답이 지연되어 캐시와 쿼리를 바꿔 복구했습니다."


def make_state(
    applicant: ApplicantDetail, sentences: list[str], *, years: int | None = None, company: str | None = None
) -> State:
    """인사 질문 고르기에 필요한 칸만 채운 상태. 문장은 자기소개서에 넣어 출처(자기소개서)도 찾게 한다."""
    info = applicant.info.model_copy(update={"career_years": years, "last_company": company})
    documents = [
        document.model_copy(update={"text": " ".join(sentences)})
        if document.type == DocumentType.COVER_LETTER
        else document
        for document in applicant.documents
    ]
    person = applicant.model_copy(update={"info": info, "documents": documents})
    numbered = {f"S{index}": sentence for index, sentence in enumerate(sentences, 1)}
    return cast(State, {"applicant": person, "sentences": numbered})


@pytest.fixture
def newcomer(sample_applicants: dict[str, ApplicantDetail]) -> ApplicantDetail:
    return sample_applicants["이도윤"]


def test_career_applicant_is_always_asked_why_they_move(newcomer: ApplicantDetail) -> None:
    # 어려움 문장이 있어도 경력 1년 이상이면 이직 계기가 먼저다 (서류만으로 알 수 없는 내용)
    found = _first_hr_question(make_state(newcomer, [HARDSHIP], years=3, company="페이랩"), [])
    assert found is not None
    text, reason = found
    assert text == "페이랩에서 근무하시다가 새로운 회사를 찾게 된 계기를 말해 주세요."
    assert "이직 계기" in reason and "경력 3년" in reason and "부정적인 이유를 전제하지 않습니다" in reason


def test_career_without_company_name_uses_neutral_wording(newcomer: ApplicantDetail) -> None:
    # 회사 이름이 없거나 너무 길면(서류 분석이 잘못 뽑은 값) 이름 없이 묻는다
    assert _first_hr_question(make_state(newcomer, [], years=2), [])[0] == HR_MOVE_UNKNOWN  # type: ignore[index]
    long_name = make_state(newcomer, [], years=2, company="가" * 31)
    assert _first_hr_question(long_name, [])[0] == HR_MOVE_UNKNOWN  # type: ignore[index]


@pytest.mark.parametrize("years", [None, 0])
def test_newcomer_or_unknown_career_is_not_asked_why_they_move(newcomer: ApplicantDetail, years: int | None) -> None:
    # 신입(0)이나 경력을 모르는 지원자(None)에게 이직을 전제하지 않는다
    found = _first_hr_question(make_state(newcomer, [], years=years), [])
    assert found is not None and "새로운 회사" not in found[0]


def test_hardship_comes_before_growth(newcomer: ApplicantDetail) -> None:
    # 성장 문장이 앞에 있어도 어려움 극복이 우선순위가 높다
    found = _first_hr_question(make_state(newcomer, [GROWTH, HARDSHIP]), [])
    assert found is not None
    text, reason = found
    assert text.startswith("'출시 일정이 2주 밀려 위기였지만, 팀원들과 매일 범위를 다시 정해 일정을 맞췄습니다'라고")
    assert "이겨 냈고" in text
    assert "어려움 극복" in reason and "출처: 자기소개서" in reason


def test_growth_asks_how_they_learned_not_the_technique(newcomer: ApplicantDetail) -> None:
    found = _first_hr_question(make_state(newcomer, [GROWTH]), [])
    assert found is not None
    text, reason = found
    assert "스터디" in text and "어떤 방법으로 배웠고" in text
    assert "배우는 방법과 실제 적용 과정" in reason


def test_technical_hardship_is_left_to_the_practical_interviewer(newcomer: ApplicantDetail) -> None:
    # 장애 복구처럼 기술 내용이 중심인 어려움은 인사 질문 재료로 쓰지 않는다 → 다음 후보(기본 질문)
    found = _first_hr_question(make_state(newcomer, [TECH_HARDSHIP]), [])
    assert found is not None and found[0] == HR_STRENGTH


def test_no_material_falls_back_to_strength_question(newcomer: ApplicantDetail) -> None:
    found = _first_hr_question(make_state(newcomer, ["Spring Boot로 결제 API를 만들었습니다."]), [])
    assert found is not None
    text, reason = found
    assert text == HR_STRENGTH and "기본 질문" in reason


def test_sentence_already_quoted_by_another_question_is_not_reused(newcomer: ApplicantDetail) -> None:
    # 실무 질문이 같은 문장을 이미 인용했으면 인사 질문은 다음 후보로 넘어간다
    quoted = f"'{HARDSHIP.rstrip('.')}'라고 적어 주셨는데, 본인이 맡은 역할을 말해 주세요."
    found = _first_hr_question(make_state(newcomer, [HARDSHIP, GROWTH]), [quoted])
    assert found is not None and "스터디" in found[0]


def test_future_plan_is_not_used_as_past_hardship(newcomer: ApplicantDetail) -> None:
    plan = "입사 후에는 어려움이 있어도 끝까지 해내는 개발자가 되겠습니다."
    assert _first_hr_question(make_state(newcomer, [plan]), [])[0] == HR_STRENGTH  # type: ignore[index]


def test_quote_starts_at_the_topic_clause_and_never_uses_ellipsis() -> None:
    lead = "대학 시절 여러 동아리 활동을 하며 다양한 사람과 협업하는 경험을 쌓았고"
    sentence = f"{lead}, 축제 준비 중 예산 승인이 밀려 행사가 무산될 위기였지만, 학과에 직접 설명해 승인을 받았습니다."
    quote = _hr_quote(sentence, _HARDSHIP)
    assert quote is not None and quote.startswith("축제 준비 중")  # 주제 낱말('밀려')이 든 절부터
    assert len(quote) <= HR_QUOTE_LIMIT and "…" not in quote
    # 주제 낱말이 든 절 하나만으로도 길이를 넘으면 쓰지 않는다
    assert _hr_quote("실패" + "가" * HR_QUOTE_LIMIT, _HARDSHIP) is None


def test_technical_counts_distinct_technical_words() -> None:
    assert _technical("멱등성과 트랜잭션 처리가 중요하다고 배운 경험에서, 구현이나 검증 과정에서 지킨 원칙")
    assert _technical("Kafka와 Redis로 처리했습니다")
    assert not _technical("결제는 한 번의 실수가 고객의 돈과 신뢰에 바로 닿는 일이라고 생각합니다.")
    assert not _technical("API 하나만 언급한 문장")  # 낱말 하나만으로는 기술 문장으로 보지 않는다


@pytest.mark.parametrize("key", [VALUES, LEADERSHIP])
def test_values_and_leadership_slots_reject_technical_questions(key: str) -> None:
    # 10/30 Luna 결과: 인성 자리가 기술 문장을 재료로 '구현 · 검증에서 지킨 원칙'을 물었다
    text = "멱등성과 트랜잭션 처리를 구현할 때 중요하게 지키려 한 원칙과 그 이유를 말해 주세요."
    state = cast(State, cast(dict[str, Any], {"company": None}))
    checked, problem = _final_slot_checked(state, key, text, [])
    assert checked is None and problem is not None and "기술 내용" in problem


def test_culture_slot_still_allows_development_teamwork_words() -> None:
    # 조직 적응은 '코드 리뷰 규칙'처럼 개발 협업 방식이 자연스럽게 나와 기술 검사를 하지 않는다
    text = "팀의 코드 리뷰 규칙에 맞춰 본인의 일하는 방식을 바꾼 경험이 있다면, 무엇을 바꿨는지 말해 주세요."
    state = cast(State, cast(dict[str, Any], {"company": None}))
    checked, _ = _final_slot_checked(state, CULTURE, text, [])
    assert checked is not None
