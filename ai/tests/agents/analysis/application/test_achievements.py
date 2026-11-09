"""지원자 단위 성과 장부: 받을 수 있는 성과만 남기고, 같은 성과를 항목마다 같은 지표로 붙이는지 본다."""

from uuid import uuid4

import pytest

from hiremate_ai.agents.analysis.application.achievements import (
    Entry,
    accept,
    achievement_claims,
    apply_achievement_reviews,
    attach,
    display,
)
from hiremate_ai.agents.analysis.application.review import ClaimReview
from hiremate_ai.agents.analysis.application.types import Criterion, CriterionResult, EvaluationRules
from hiremate_ai.contract import ApplicantDocument, CriterionCategory, CriterionType, DocumentType, Verdict

PORTFOLIO = ApplicantDocument(
    type=DocumentType.PORTFOLIO,
    file_id=uuid4(),
    file_name="포트폴리오.pdf",
    size=1,
    text=(
        "Python으로 하이브리드 검색을 구현해 120문항 기준 정답률을 64%에서 81%로 높였습니다.\n"
        "리랭커 때문에 응답 시간이 2.1초에서 2.9초로 늘었지만, 정확도를 우선해 유지했습니다.\n"
        "하루 취합 시간이 약 40분에서 10분 내외로 줄었습니다(담당자 체감).\n"
        "발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다. 재고 대장을 바코드로 바꿨습니다.\n"
        "바꾼 뒤에는 12분이면 끝났습니다.\n"
        "검색 구조는 팀원 B가 맡았고 정답률은 61%에서 83%로 올랐습니다."
    ),
)
SEARCH = "Python으로 하이브리드 검색을 구현해 120문항 기준 정답률을 64%에서 81%로 높였습니다."


def criterion(criterion_id: str, criterion_type: CriterionType = CriterionType.COMPOSITE) -> Criterion:
    return Criterion(
        criterion_id=criterion_id,
        category=CriterionCategory.PREFERENCE,
        text=f"{criterion_id} 경험",
        important=False,
        criterion_type=criterion_type,
        evaluation_rules=EvaluationRules(met="한 일이 있다", unmet="없다"),
    )


def entry(**update: object) -> Entry:
    base = Entry(
        what="검색 정답률",
        before="64%",
        after="81%",
        quotes=[SEARCH],
        action="하이브리드 검색",
        condition="120문항 기준",
        owner="SELF",
        criteria=["P-01", "P-02"],
    )
    return base.model_copy(update=update)


def result(criterion_id: str, verdict: Verdict = Verdict.MET, **update: object) -> CriterionResult:
    return CriterionResult(
        criterion_id=criterion_id,
        category=CriterionCategory.PREFERENCE,
        text=f"{criterion_id} 경험",
        important=False,
        criterion_type=CriterionType.COMPOSITE,
        verdict=verdict,
        reason="한 일",
    ).model_copy(update=update)


def test_accepted_achievement_is_shown_as_what_before_after_and_condition() -> None:
    [kept] = accept([entry()], [PORTFOLIO], {"P-01", "P-02"})

    assert (kept.id, display(kept)) == ("R1", "검색 정답률 64% → 81% (120문항 기준)")
    assert kept.criteria == ["P-01", "P-02"]


@pytest.mark.parametrize(
    "update",
    [
        # 다른 것을 얻으려고 감수한 악화는 성과가 아니다 (모델이 좋아졌다고 표시해도 코드가 거른다)
        {
            "what": "응답 시간",
            "before": "2.1초",
            "after": "2.9초",
            "quotes": ["리랭커 때문에 응답 시간이 2.1초에서 2.9초로 늘었지만, 정확도를 우선해 유지했습니다."],
        },
        # 체감치는 측정값이 아니다
        {
            "what": "취합 시간",
            "before": "40분",
            "after": "10분",
            "quotes": ["하루 취합 시간이 약 40분에서 10분 내외로 줄었습니다(담당자 체감)."],
        },
        {"improved": False},  # 모델이 나빠진 수치로 본 성과
        {"estimated": True},
        {"owner": "TEAM"},  # 다른 팀원 · 팀 전체의 결과
        {"mixed": True},  # 본인 조치 밖의 효과가 섞였다고 밝힌 수치
        {"after": "89%"},  # 원문 문장에 없는 값
        {"quotes": ["원문에 없는 문장입니다."]},
    ],
)
def test_unacceptable_results_do_not_enter_the_ledger(update: dict[str, object]) -> None:
    assert accept([entry(**update)], [PORTFOLIO], {"P-01"}) == []


def test_before_and_after_split_across_two_sentences_are_accepted() -> None:
    split = entry(
        what="재고 맞추는 시간",
        before="40분",
        after="12분",
        condition="",
        quotes=["발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다.", "바꾼 뒤에는 12분이면 끝났습니다."],
    )

    [kept] = accept([split], [PORTFOLIO], {"P-01"})

    assert display(kept) == "재고 맞추는 시간 40분 → 12분" and len(kept.quotes) == 2


def test_unknown_criteria_and_duplicates_are_dropped_and_parentheses_stay_balanced() -> None:
    kept = accept(
        [entry(criteria=["P-01", "P-99"], condition="VOC 분류 기준 세분화(엑셀 피벗·함수 활용"), entry()],
        [PORTFOLIO],
        {"P-01"},
    )

    assert len(kept) == 1 and kept[0].criteria == ["P-01"]
    assert display(kept[0]).count("(") == display(kept[0]).count(")")


def test_the_same_achievement_gives_every_linked_item_the_same_metric() -> None:
    ledger = accept([entry()], [PORTFOLIO], {"P-01", "P-02"})

    attached = attach([result("P-01"), result("P-02"), result("P-03")], ledger)

    assert [item.metric for item in attached] == ["검색 정답률 64% → 81% (120문항 기준)"] * 2 + [""]
    assert SEARCH in [quote.sentence for quote in attached[0].quotes]  # 성과 문장은 근거에도 더한다


@pytest.mark.parametrize(
    "item",
    [
        result("P-01", Verdict.NOT_MET),
        result("P-01", Verdict.UNKNOWN),
        result("P-01", criterion_type=CriterionType.CONDITION),
    ],
)
def test_unmet_or_condition_items_get_no_metric(item: CriterionResult) -> None:
    ledger = accept([entry()], [PORTFOLIO], {"P-01"})

    [attached] = attach([item.model_copy(update={"metric": "남은 지표"})], ledger)

    assert attached.metric == ""


def test_partial_items_keep_the_metric_and_quotes_only_mode_leaves_it_empty() -> None:
    ledger = accept([entry()], [PORTFOLIO], {"P-01"})

    [partial] = attach([result("P-01", Verdict.PARTIAL)], ledger)
    [quotes_only] = attach([result("P-01")], ledger, metric=False)

    assert partial.metric.startswith("검색 정답률")
    assert quotes_only.metric == "" and quotes_only.quotes


def test_each_achievement_is_verified_once_and_dropped_when_unsupported() -> None:
    ledger = accept([entry(), entry(what="재고 맞추는 시간", before="40분", after="12분", condition="",
                                    quotes=["발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다.",
                                            "바꾼 뒤에는 12분이면 끝났습니다."])],
                    [PORTFOLIO], {"P-01", "P-02"})  # fmt: skip

    claims = achievement_claims(ledger, [PORTFOLIO])
    kept = apply_achievement_reviews(ledger, {"R2": ClaimReview(id="R2", verdict="UNSUPPORTED", reason="팀 성과")})

    assert [claim.id for claim in claims] == ["R1", "R2"]
    assert [achievement.id for achievement in kept] == ["R1"]


def test_verification_sees_the_action_sentence_from_another_paragraph() -> None:
    # 결과 문장과 조치 설명이 다른 문단에 있어도 검증이 둘을 함께 보게 조치 문장을 넘긴다
    document = PORTFOLIO.model_copy(
        update={"text": "## 구조\n문서를 조항 단위로 나누고 하이브리드 검색을 적용했습니다.\n\n## 결과\n" + SEARCH}
    )
    [kept] = accept(
        [entry(action_quotes=["문서를 조항 단위로 나누고 하이브리드 검색을 적용했습니다.", "원문에 없는 문장"])],
        [document],
        {"P-01"},
    )

    [claim] = achievement_claims([kept], [document])

    assert [quote.sentence for quote in claim.quotes][-1] == "문서를 조항 단위로 나누고 하이브리드 검색을 적용했습니다."
    assert "## 구조" in claim.context and "## 결과" in claim.context
