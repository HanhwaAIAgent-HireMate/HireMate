from dataclasses import replace

import pytest
from application_context import TODAY, YUMIN_API, verdict

from hiremate_ai.agents.analysis.application.extract import locate
from hiremate_ai.agents.analysis.application.judge import (
    CriteriaJudgement,
    Evidence,
    RequirementPart,
    apply_verification,
    baseless_number,
    judge_criteria,
    recheck_criterion,
)
from hiremate_ai.agents.analysis.application.review import ClaimReview
from hiremate_ai.agents.analysis.application.types import (
    Actor,
    Criterion,
    CriterionResult,
    EvaluationRules,
    Fact,
)
from hiremate_ai.contract import (
    ApplicantDetail,
    CriterionCategory,
    CriterionType,
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
