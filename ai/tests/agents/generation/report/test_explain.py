from hiremate_ai.agents.generation.report.explain import (
    DistributionFacts,
    _Charts,
    _Draft,
    explain_distribution,
    facts_text,
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
    assert "선 위(필수 조건 모두 충족) 97명 (전체의 32%)" in text
    assert "확인 필요 비율 65%" in text
    assert "경계 그룹 '선발 경계' 17명" in text
    assert "선 위 지원자의 충족 개수별 인원: 5개 35명, 4개 17명" in text
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

    note = await explain_distribution(FACTS, FakeLlm(answer))

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
