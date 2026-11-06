from dataclasses import replace
from uuid import uuid4

import pytest
from application_context import TODAY, YUMIN_API, verdict

from hiremate_ai.agents.analysis.application.extract import locate
from hiremate_ai.agents.analysis.application.judge import (
    RESULT_SEARCH,
    CriteriaJudgement,
    Evidence,
    RequirementPart,
    apply_found_results,
    apply_verification,
    baseless_number,
    judge_criteria,
    recheck_criterion,
    result_search_claims,
    verification_claims,
)
from hiremate_ai.agents.analysis.application.review import ClaimReview
from hiremate_ai.agents.analysis.application.types import (
    Actor,
    Criterion,
    CriterionResult,
    EvaluationRules,
    Fact,
    Quote,
)
from hiremate_ai.contract import (
    ApplicantDetail,
    ApplicantDocument,
    CriterionCategory,
    CriterionType,
    DocumentType,
    Verdict,
)
from hiremate_ai.llm.fake import FakeLlm


@pytest.fixture
def criterion() -> Criterion:
    return Criterion(
        criterion_id="Q-01",
        category=CriterionCategory.QUALIFICATION,
        text="Java API 개발 경험",
        important=False,
        criterion_type=CriterionType.SINGLE,
        evaluation_rules=EvaluationRules(met="직접 구현한 근거가 있다", unmet="구현 근거가 없다"),
    )


@pytest.fixture
def evidence(sample_applicants: dict[str, ApplicantDetail]) -> Evidence:
    applicant = sample_applicants["정유민"]
    return Evidence(applicant.documents, [], [], None, TODAY)


@pytest.mark.parametrize("returned_id", ["Q-01", " Q-01 ", "[Q-01]", "  [ Q-01 ]  "])
async def test_display_brackets_match_the_requested_criterion(
    criterion: Criterion,
    evidence: Evidence,
    returned_id: str,
) -> None:
    llm = FakeLlm(CriteriaJudgement(verdicts=[verdict(returned_id, "MET", YUMIN_API)]))
    [result] = await judge_criteria(llm, [criterion], evidence, 8000)
    assert result.criterion_id == "Q-01"
    assert result.verdict == Verdict.MET
    assert result.quotes and result.quotes[0].sentence in evidence.documents[0].text


@pytest.mark.parametrize("returned_id", ["Q-1", "[Q-99]", "[[Q-01]]", "Q-01 extra", "[P-01]"])
async def test_unknown_or_ambiguous_id_is_not_guessed(
    criterion: Criterion,
    evidence: Evidence,
    returned_id: str,
) -> None:
    llm = FakeLlm(CriteriaJudgement(verdicts=[verdict(returned_id, "MET", YUMIN_API)]))
    [result] = await judge_criteria(llm, [criterion], evidence, 8000)
    assert result.verdict == Verdict.UNKNOWN
    assert "모델 응답에 이 항목이 없어" in result.reason


@pytest.mark.parametrize("reverse", [True, False])
async def test_conflicting_duplicate_cannot_be_overwritten(
    criterion: Criterion,
    evidence: Evidence,
    reverse: bool,
) -> None:
    answers = [verdict("[Q-01]", "MET", YUMIN_API), verdict("Q-01", "NOT_MET")]
    if reverse:
        answers.reverse()
    answers.append(verdict("[ Q-01 ]", "MET", YUMIN_API))
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=answers)), [criterion], evidence, 8000)
    assert result.verdict == Verdict.UNKNOWN
    assert "서로 달라" in result.reason


async def test_identical_duplicate_is_safe(criterion: Criterion, evidence: Evidence) -> None:
    answer = verdict("Q-01", "MET", YUMIN_API)
    wrapped = answer.model_copy(update={"criterion_id": "[Q-01]"})
    [result] = await judge_criteria(
        FakeLlm(CriteriaJudgement(verdicts=[answer, wrapped])),
        [criterion],
        evidence,
        8000,
    )
    assert result.verdict == Verdict.MET


@pytest.mark.parametrize("invalid_evidence", ["", "Redis로 분산 락을 구현해 결제 중복을 막았습니다."])
async def test_matching_id_does_not_bypass_evidence_checks(
    criterion: Criterion,
    evidence: Evidence,
    invalid_evidence: str,
) -> None:
    answer = verdict("[Q-01]", "MET", *([invalid_evidence] if invalid_evidence else []))
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], evidence, 8000)
    assert result.verdict == Verdict.UNKNOWN
    assert "근거 문장" in result.reason


async def test_matching_id_does_not_turn_team_work_into_personal_work(
    criterion: Criterion,
    evidence: Evidence,
) -> None:
    answer = verdict("[Q-01]", "MET", YUMIN_API, role="TEAM")
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], evidence, 8000)
    assert result.verdict == Verdict.UNKNOWN
    assert "본인이 직접" in result.reason


async def test_recheck_uses_the_same_id_rules(criterion: Criterion, evidence: Evidence) -> None:
    previous = CriterionResult(
        criterion_id="Q-01",
        category=criterion.category,
        text=criterion.text,
        important=False,
        criterion_type=criterion.criterion_type,
        verdict=Verdict.UNKNOWN,
        reason="본인 역할 확인",
    )
    result = await recheck_criterion(
        FakeLlm(CriteriaJudgement(verdicts=[verdict("[ Q-01 ]", "MET", YUMIN_API)])),
        criterion,
        previous,
        evidence,
        1,
    )
    assert result is not None and result.verdict == Verdict.MET and result.recheck_count == 1


async def test_recheck_does_not_pick_the_first_conflicting_answer(criterion: Criterion, evidence: Evidence) -> None:
    previous = CriterionResult(
        criterion_id="Q-01",
        category=criterion.category,
        text=criterion.text,
        important=False,
        criterion_type=criterion.criterion_type,
        verdict=Verdict.UNKNOWN,
        reason="본인 역할 확인",
    )
    result = await recheck_criterion(
        FakeLlm(CriteriaJudgement(verdicts=[verdict("Q-01", "MET", YUMIN_API), verdict("[Q-01]", "NOT_MET")])),
        criterion,
        previous,
        evidence,
        1,
    )
    assert result is not None and result.verdict == Verdict.UNKNOWN and "서로 달라" in result.reason


YUMIN_LATENCY = "하루 120만 건 승인 트랜잭션을 처리하는 승인 서버의 응답 시간을 180ms에서 90ms로 줄였습니다."


@pytest.mark.parametrize(
    ("metric", "kept"),
    [
        ("응답 시간을 180ms에서 90ms로 줄였습니다", "응답 시간을 180ms에서 90ms로 줄였습니다"),
        # 숫자가 없거나 원문에 없는 지표는 남기지 않는다 (화면에서 상이 아니라 중이다)
        ("응답 시간을 크게 줄였습니다", ""),
        ("응답 시간을 50ms로 줄였습니다", ""),
    ],
)
async def test_metric_is_kept_only_when_it_is_in_the_documents(
    criterion: Criterion, evidence: Evidence, metric: str, kept: str
) -> None:
    answer = verdict("Q-01", "MET", YUMIN_LATENCY).model_copy(update={"metric": metric})
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], evidence, 8000)
    assert result.verdict == Verdict.MET
    assert result.metric == kept


async def test_condition_items_carry_no_metric(criterion: Criterion, evidence: Evidence) -> None:
    condition = criterion.model_copy(update={"criterion_type": CriterionType.CONDITION})
    answer = verdict("Q-01", "MET", YUMIN_LATENCY).model_copy(update={"metric": "하루 120만 건"})
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [condition], evidence, 8000)
    assert result.metric == ""


def _self_fact(evidence: Evidence, sentence: str, actor: Actor = Actor.SELF) -> Fact:
    quote = locate(sentence, list(evidence.documents))
    assert quote is not None
    return Fact(kind="EXPERIENCE", statement="Java API를 직접 개발했다.", actor=actor, quotes=[quote])


@pytest.mark.parametrize(("fact_actor", "expected"), [(Actor.SELF, Verdict.MET), (Actor.TEAM, Verdict.UNKNOWN)])
async def test_unclear_role_follows_the_fact_extracted_from_the_same_sentence(
    criterion: Criterion,
    evidence: Evidence,
    fact_actor: Actor,
    expected: Verdict,
) -> None:
    with_fact = replace(evidence, facts=[_self_fact(evidence, YUMIN_API, fact_actor)])
    answer = verdict("Q-01", "MET", YUMIN_API, role="UNCLEAR")
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], with_fact, 8000)
    assert result.verdict == expected


async def test_team_answer_is_not_overridden_by_a_self_fact(criterion: Criterion, evidence: Evidence) -> None:
    with_fact = replace(evidence, facts=[_self_fact(evidence, YUMIN_API)])
    answer = verdict("Q-01", "MET", YUMIN_API, role="TEAM")
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], with_fact, 8000)
    assert result.verdict == Verdict.UNKNOWN


async def test_own_action_sentence_comes_before_other_quotes(criterion: Criterion, evidence: Evidence) -> None:
    # 모델이 다른 문장을 먼저 옮겨도, 본인 경험(SELF)으로 뽑힌 문장을 화면에 먼저 보인다
    with_fact = replace(evidence, facts=[_self_fact(evidence, YUMIN_LATENCY)])
    answer = verdict("Q-01", "MET", YUMIN_API, YUMIN_LATENCY)
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], with_fact, 8000)
    assert [quote.sentence for quote in result.quotes][0] in YUMIN_LATENCY


async def test_metric_joined_from_two_sentences_keeps_only_the_original_phrase(
    criterion: Criterion, evidence: Evidence
) -> None:
    # 여러 구절을 이어 붙인 지표는 원문에 없는 문장이라 그대로 쓰지 않고, 원문에 있는 첫 구절만 남긴다
    joined = "하루 120만 건 처리 2배; 응답 시간을 180ms에서 90ms로 줄였습니다; 하루 120만 건"
    answer = verdict("Q-01", "MET", YUMIN_LATENCY).model_copy(update={"metric": joined})
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], evidence, 8000)
    assert result.metric == "응답 시간을 180ms에서 90ms로 줄였습니다"


async def test_undecided_criterion_is_kept_apart_from_the_applicant(criterion: Criterion, evidence: Evidence) -> None:
    # 기준이 규모를 정하지 않아 판정이 갈리는 점은 지원자 확인할 점이 아니라 평가 설정 검토로 남긴다
    note = "기준에 '대규모'의 규모가 정해져 있지 않음"
    answer = verdict("Q-01", "UNKNOWN", YUMIN_LATENCY).model_copy(update={"setting_note": note, "unknown_parts": []})
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], evidence, 8000)
    assert result.verdict == Verdict.UNKNOWN
    assert result.setting_note == note


@pytest.mark.parametrize(
    ("criterion_type", "found_second", "expected"),
    [
        # 나열한 것을 모두 요구하므로, 한 부분이라도 확인되지 않으면 충족이 아니다
        (CriterionType.SINGLE, False, Verdict.NOT_MET),
        (CriterionType.COMPOSITE, False, Verdict.PARTIAL),
        (CriterionType.SINGLE, True, Verdict.MET),
    ],
)
async def test_every_required_part_must_be_found(
    criterion: Criterion, evidence: Evidence, criterion_type: CriterionType, found_second: bool, expected: Verdict
) -> None:
    listed = criterion.model_copy(update={"text": "A, B 등 활용 경험", "criterion_type": criterion_type})
    parts = [RequirementPart(part="A", found=True), RequirementPart(part="B", found=found_second)]
    answer = verdict("Q-01", "MET", YUMIN_API).model_copy(update={"parts": parts})
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [listed], evidence, 8000)
    assert result.verdict == expected
    if expected != Verdict.MET:
        assert (result.satisfied_parts, result.unsatisfied_parts) == (["A"], ["B"])


@pytest.mark.parametrize(
    ("text", "baseless"),
    [
        ("검색 API 응답 속도 300% 개선", True),
        ("쿼리 최적화로 성능 5배 향상", True),
        ("'뷰티픽'에서 검색 API 응답 속도를 300% 개선했고, 성능을 5배 향상", True),  # 장소 '에서'는 기준이 아니다
        ("p95 640ms → 48ms (92% 단축)", False),
        ("응답 시간을 180ms에서 90ms로 줄였습니다", False),
        ("장애 0건", False),
        ("전년 대비 매출 20% 증가", False),
    ],
)
def test_numbers_without_a_baseline_are_not_metrics(text: str, baseless: bool) -> None:
    assert baseless_number(text) is baseless


@pytest.mark.parametrize(
    ("cited", "actor", "picked"),
    [
        (YUMIN_LATENCY, Actor.SELF, True),  # 근거로 고른 문장에 전후 수치가 있으면 후보로 고른다
        (YUMIN_LATENCY, Actor.TEAM, False),  # 팀 단위로 뽑힌 문장은 본인 성과가 아니다
        (YUMIN_API, Actor.SELF, False),  # 근거로 고르지 않은 문장의 수치는 항목과 관계없을 수 있어 붙이지 않는다
    ],
)
async def test_metric_is_picked_only_from_the_cited_sentences_when_left_empty(
    criterion: Criterion, evidence: Evidence, cited: str, actor: Actor, picked: bool
) -> None:
    with_fact = replace(evidence, facts=[_self_fact(evidence, YUMIN_LATENCY, actor)])
    answer = verdict("Q-01", "MET", cited)
    [result] = await judge_criteria(FakeLlm(CriteriaJudgement(verdicts=[answer])), [criterion], with_fact, 8000)
    assert ("180ms에서 90ms" in result.metric) is picked


def test_metric_that_fails_verification_is_dropped(criterion: Criterion) -> None:
    result = CriterionResult(
        criterion_id="Q-01",
        category=CriterionCategory.QUALIFICATION,
        text=criterion.text,
        important=False,
        criterion_type=CriterionType.SINGLE,
        verdict=Verdict.MET,
        reason="구현",
        metric="평균 대기 38초에서 21초로 줄었다",
    )
    reviews = {
        "Q-01": ClaimReview(id="Q-01", verdict="SUPPORTED"),
        "Q-01#metric": ClaimReview(id="Q-01#metric", verdict="OVERSTATED", reason="다른 효과가 섞였다고 밝힘"),
    }
    [checked] = apply_verification([result], reviews)
    assert (checked.verdict, checked.metric) == (Verdict.MET, "")


# 직무와 무관하게 쓰이는지 매장 운영 서류로 확인한다
STORE = ApplicantDocument(
    type=DocumentType.PORTFOLIO,
    file_id=uuid4(),
    file_name="",
    size=1,
    text="발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다. 재고 대장을 바코드로 바꿨습니다.\n"
    "바꾼 뒤에는 12분이면 끝났습니다.\n매장 직원은 8명입니다.",
)


def met(criterion: Criterion, metric: str = "") -> CriterionResult:
    return CriterionResult(
        criterion_id="Q-01",
        category=CriterionCategory.QUALIFICATION,
        text=criterion.text,
        important=False,
        criterion_type=CriterionType.SINGLE,
        verdict=Verdict.MET,
        reason="재고 대장 개선",
        metric=metric,
        quotes=[Quote(document=DocumentType.PORTFOLIO, sentence="재고 대장을 바코드로 바꿨습니다.")],
    )


@pytest.mark.parametrize(
    ("found", "metric"),
    [
        # 화살표 없이 줄글로, 전후 값이 두 문장에 나뉘어 있어도 지표가 된다
        (
            ["발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다.", "바꾼 뒤에는 12분이면 끝났습니다."],
            "발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다. … 바꾼 뒤에는 12분이면 끝났습니다.",
        ),
        (["재고 맞추는 시간이 40분에서 12분으로 줄었습니다."], ""),  # 원문에 없는 문장은 쓰지 않는다
        (["매장 직원은 8명입니다."], ""),  # 숫자가 하나뿐이면 전후 값이 아니다
    ],
)
def test_result_found_by_verification_becomes_the_metric(criterion: Criterion, found: list[str], metric: str) -> None:
    review = ClaimReview(id="Q-01", verdict="SUPPORTED", result_quotes=found)

    [checked] = apply_verification([met(criterion)], {"Q-01": review}, [STORE])

    assert checked.metric == metric
    assert len(checked.quotes) == (3 if metric else 1)  # 찾은 문장은 근거에도 더한다


def test_only_items_without_a_metric_ask_for_the_result(criterion: Criterion) -> None:
    without, with_metric = (
        met(criterion),
        met(criterion, metric="40분에서 12분").model_copy(update={"criterion_id": "Q-02"}),
    )

    claims = {claim.id: claim for claim in verification_claims([without, with_metric], [STORE])}

    assert RESULT_SEARCH in claims["Q-01"].claim and RESULT_SEARCH not in claims["Q-02"].claim
    # 결과가 다른 줄에만 있어도 찾을 수 있게 맥락을 넉넉히 준다
    assert "12분이면 끝났습니다" in claims["Q-01"].context


def test_overstated_composite_keeps_a_card_summary(criterion: Criterion) -> None:
    # 검증이 충족을 부분 충족으로 낮춰도 카드 요약이 비지 않는다
    result = CriterionResult(
        criterion_id="Q-01",
        category=CriterionCategory.QUALIFICATION,
        text=criterion.text,
        important=False,
        criterion_type=CriterionType.COMPOSITE,
        verdict=Verdict.MET,
        reason="구현과 운영",
        brief="구현 · 운영 확인",
    )
    review = ClaimReview(id="Q-01", verdict="OVERSTATED", reason="운영 기록 없음", brief="구현은 확인, 운영은 미확인")

    [checked] = apply_verification([result], {"Q-01": review})

    assert (checked.verdict, checked.brief) == (Verdict.PARTIAL, "구현은 확인, 운영은 미확인")


def test_percentile_label_is_not_a_value(criterion: Criterion) -> None:
    # 'p95'의 95는 값이 아니어서, 뒤 값 하나만 있는 문장은 전후 수치가 아니다
    document = STORE.model_copy(update={"text": f"{STORE.text}\n조회 p95는 48ms 수준으로 안정됐습니다."})
    review = ClaimReview(id="Q-01", verdict="SUPPORTED", result_quotes=["조회 p95는 48ms 수준으로 안정됐습니다."])

    [checked] = apply_verification([met(criterion)], {"Q-01": review}, [document])

    assert checked.metric == ""


def test_result_from_several_own_actions_carries_the_condition(criterion: Criterion) -> None:
    # 본인이 여러 조치를 함께 해서 낸 결과도 지표로 쓰고, 함께 적용한 조치를 붙여 담당자가 보게 한다
    found = ["발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다.", "바꾼 뒤에는 12분이면 끝났습니다."]
    review = ClaimReview(id="Q-01", verdict="SUPPORTED", result_quotes=found, result_note="바코드 + 진열 순서 변경")

    [checked] = apply_verification([met(criterion)], {"Q-01": review}, [STORE])

    assert checked.metric.endswith("(바코드 + 진열 순서 변경)")


def test_missing_result_is_searched_once_more(criterion: Criterion) -> None:
    # 첫 검증에서 수치를 못 찾은 항목만 다시 묻고, 다시 찾은 수치를 지표로 쓴다 (판정은 그대로)
    without, with_metric = (
        met(criterion),
        met(criterion, metric="40분에서 12분").model_copy(update={"criterion_id": "Q-02"}),
    )
    claims = result_search_claims([without, with_metric], [STORE])
    assert [claim.id for claim in claims] == ["Q-01#result"]

    found = ["발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다.", "바꾼 뒤에는 12분이면 끝났습니다."]
    review = ClaimReview(id="Q-01#result", verdict="UNSUPPORTED", result_quotes=found)
    [checked, kept] = apply_found_results([without, with_metric], {"Q-01#result": review}, [STORE])

    assert checked.verdict == Verdict.MET and "12분" in checked.metric
    assert kept == with_metric


@pytest.mark.parametrize(
    ("summary", "shown"),
    [
        ("재고 맞추기 40분 → 12분", "재고 맞추기 40분 → 12분"),  # 숫자가 원문에 모두 있으면 짧은 요약을 보인다
        ("재고 맞추기 45분 → 12분", None),  # 원문에 없는 숫자가 있으면 원문 문장을 그대로 쓴다
    ],
)
def test_found_result_is_shown_as_a_short_summary(criterion: Criterion, summary: str, shown: str | None) -> None:
    found = ["발주 마감 전에 재고를 맞추는 일에 매일 40분이 걸렸습니다.", "바꾼 뒤에는 12분이면 끝났습니다."]
    review = ClaimReview(id="Q-01", verdict="SUPPORTED", result_quotes=found, result_summary=summary)

    [checked] = apply_verification([met(criterion)], {"Q-01": review}, [STORE])

    assert checked.metric == (shown or " … ".join(found))
    assert len(checked.quotes) == 3  # 원문 문장은 근거로 남는다
