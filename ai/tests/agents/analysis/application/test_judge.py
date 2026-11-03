from dataclasses import replace

import pytest
from application_context import TODAY, YUMIN_API, verdict

from hiremate_ai.agents.analysis.application.extract import locate
from hiremate_ai.agents.analysis.application.judge import (
    CriteriaJudgement,
    Evidence,
    judge_criteria,
    recheck_criterion,
)
from hiremate_ai.agents.analysis.application.types import (
    Actor,
    Criterion,
    CriterionResult,
    EvaluationRules,
    Fact,
)
from hiremate_ai.contract import ApplicantDetail, CriterionCategory, CriterionType, Verdict
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
