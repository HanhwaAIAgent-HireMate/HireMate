import httpx2
from openai import APIConnectionError

from hiremate_ai.agents.generation.report.check import sentence_problems
from hiremate_ai.agents.generation.report.explain import (
    CareerCount,
    CriterionCount,
    DistributionFacts,
    _Charts,
    _Draft,
    explain_distribution,
    facts_text,
    highlights,
)
from hiremate_ai.llm.chat import LlmOutputError
from hiremate_ai.llm.fake import FakeLlm, LlmCall

FACTS = DistributionFacts.model_validate(
    {
        "total": 300,
        "analyzed": 300,
        "aboveLine": 97,
        "target": 60,
        "passed": 0,
        "required": {"met": 97, "unmet": 16, "unknown": 187},
        "criteria": [
            {
                "criterionId": "Q-01",
                "text": "Java 또는 Kotlin 기반 서버 개발 경력 3년 이상",
                "required": True,
                "met": 97,
                "partial": 2,
                "notMet": 6,
                "unknown": 195,
            }
        ],
        "groups": [{"label": "선발 경계", "reason": "목표 60명째와 충족 개수가 같아요", "size": 17}],
        "careers": [{"label": "신입", "all": 99, "aboveLine": 34}],
        "counts": [{"value": 5, "count": 35}, {"value": 4, "count": 17}],
        "cut": {"value": 4, "from": 57, "to": 73, "inside": 4},
        # backend가 보내지만 해설에는 쓰지 않는 칸은 무시한다
        "stageId": "s",
        "deepSize": 5,
    }
)


def test_facts_give_the_model_ready_made_ratios_without_people() -> None:
    text = facts_text(FACTS)
    assert "필수 조건을 모두 충족한 사람 97명 (전체의 32%)" in text
    assert "확인 필요 비율 65%" in text
    assert "다시 볼 지원자 '선발 경계' 17명" in text
    assert "필수 조건 충족자의 항목 충족 수별 인원: 5개 35명, 4개 17명" in text
    assert "57~73번째가 같은 개수(목표 안 4명)" in text


async def test_explain_keeps_only_sentences_that_pass_the_report_checks() -> None:
    def answer(call: LlmCall) -> _Draft:
        assert '<data kind="distribution">' in call.user  # 자료는 블록으로 감싸 넣는다
        return _Draft(
            lines=[
                "Java · Kotlin 경력은 확인 필요 비율이 65%라 서류만으로 거르기 어려워요.",
                "A-0001이 가장 우수해요.",
                "선 위가 목표보다 41명 많아요.",
                "목표보다 많은 선 위 37명 중 경계 그룹 17명을 먼저 봐요.",
            ],
            charts=_Charts(
                funnel="선 위가 목표보다 37명 많아 담당자가 더 골라내야 해요.",
                required="확인 필요가 65%라 서류만으로 판단하기 어려운 사람이 많아요.",
                counts="충족 4개인 17명 사이에서 목표가 갈려요.",
                criteria="경계 그룹에서 가장 우수한 사람부터 보세요.",
                careers="",
            ),
        )

    # 걸린 차트 문장이 있어 한 번 다시 쓰게 하고, 다시 써도 걸리면 그 차트는 뺀다
    note = await explain_distribution(FACTS, FakeLlm(answer, answer))

    assert note.lines == [
        "Java · Kotlin 경력은 확인 필요 비율이 65%라 서류만으로 거르기 어려워요.",
        "목표보다 많은 선 위 37명 중 경계 그룹 17명을 먼저 봐요.",
    ]
    # 차트 해석도 같은 검사를 거친다: 순위 표현(가장 우수)과 빈 문장은 빠진다
    assert note.charts == {
        "funnel": "선 위가 목표보다 37명 많아 담당자가 더 골라내야 해요.",
        "required": "확인 필요가 65%라 서류만으로 판단하기 어려운 사람이 많아요.",
        "counts": "충족 4개인 17명 사이에서 목표가 갈려요.",
    }


async def test_explain_returns_nothing_when_the_model_breaks_format() -> None:
    def broken(call: LlmCall) -> _Draft:
        raise LlmOutputError("형식 오류")

    note = await explain_distribution(FACTS, FakeLlm(broken))
    assert note.lines == []


async def test_explain_returns_nothing_when_the_model_server_fails() -> None:
    def down(call: LlmCall) -> _Draft:
        raise APIConnectionError(request=httpx2.Request("POST", "http://model.test"))

    note = await explain_distribution(FACTS, FakeLlm(down))
    assert note.lines == []


def test_highlights_name_what_stands_out_in_each_chart() -> None:
    points = highlights(FACTS)
    assert points["funnel"] == ["필수 조건 충족 97명이 서류 통과 목표 60명보다 37명 많아요"]
    assert points["counts"][0] == "필수 조건 충족자 중 항목 5개를 충족한 사람이 35명으로 가장 많아요"
    assert "Q-01 Java 또는 Kotlin 기반 서버 개발 경력 3년 이상 68%" in points["criteria"][0]
    assert points["careers"] == ["필수 조건 충족 비율이 가장 낮은 경력: 신입 34%(99명 중 34명)"]
    # 코드가 고른 사실은 모델이 받는 자료에도 그대로 들어간다
    text = facts_text(FACTS)
    assert all(point in text for chart in points.values() for point in chart)


async def test_chart_sentence_without_a_number_is_rewritten() -> None:
    vague = _Charts(
        funnel="필수 조건 충족자가 목표보다 많아 처리 현황을 확인해 보세요.",
        required="확인 필요가 65%예요.",
        counts="충족 5개가 35명으로 가장 많아요.",
        criteria="Java · Kotlin 경력은 충족이 아닌 비율이 68%예요.",
        careers="신입은 필수 조건 충족이 34%예요.",
    )
    fixed = vague.model_copy(update={"funnel": "필수 조건 충족 97명이 목표 60명보다 37명 많아요."})
    llm = FakeLlm(
        _Draft(lines=["목표보다 37명 많아 동점인 지원자를 먼저 봐요."], charts=vague), _Draft(lines=[], charts=fixed)
    )

    note = await explain_distribution(FACTS, llm)

    assert note.charts["funnel"] == "필수 조건 충족 97명이 목표 60명보다 37명 많아요."
    assert note.lines == ["목표보다 37명 많아 동점인 지원자를 먼저 봐요."]
    # 다시 쓸 때는 걸린 차트만 알려 준다
    assert "charts.funnel에 숫자가 없다" in llm.calls[1].user
    assert "charts.required" not in llm.calls[1].user


def test_highlights_skip_tiny_career_bands_and_trivial_unsure_rates() -> None:
    facts = FACTS.model_copy(
        update={
            "careers": [
                CareerCount(label="신입", all=1, above_line=0),
                CareerCount(label="3~4년", all=9, above_line=7),
                CareerCount(label="5~6년", all=15, above_line=15),
            ],
            "criteria": [
                CriterionCount(criterion_id="Q-01", text="경력", required=True, met=26, partial=0, not_met=3, unknown=1)
            ],
        }
    )
    points = highlights(facts)
    # 1명뿐인 신입(0%)은 고르지 않고, 인원을 함께 적는다
    assert points["careers"] == [
        "필수 조건 충족 비율이 가장 낮은 경력: 3~4년 78%(9명 중 7명), 가장 높은 경력: 5~6년 100%(15명 중 15명)"
    ]
    # 확인 필요 3%는 모든 항목에 한 명씩인 경우라 알리지 않는다
    assert not any("확인 필요 비율" in point for point in points["criteria"])


def test_hanja_in_a_sentence_is_a_problem() -> None:
    assert any("한자" in p for p in sentence_problems("lines[0]", "확인이 필요한項目도 있어요.", set()))
    assert any("한자" in p for p in sentence_problems("lines[0]", "필수 조건を 못 채웠어요.", set()))


def test_plain_ending_and_wrong_copula_are_problems() -> None:
    assert any("해요체" in p for p in sentence_problems("summary", "경력 5년 이상이 많았다.", set()))
    assert any("틀린 말" in p for p in sentence_problems("summary", "충족 비율은 50% 이하여요.", {"50"}))
    assert any("틀린 말" in p for p in sentence_problems("summary", "합격은 11명여요.", {"11"}))
    # 맞는 해요체 움직씨, 근거 키워드처럼 분석 글을 옮긴 칸은 문제로 보지 않는다
    assert sentence_problems("summary", "경력이 길수록 충족 비율이 높아 보여요.", set()) == []
    assert sentence_problems("items[0]", "리뷰 규칙을 주도했다", set(), plain=False) == []
