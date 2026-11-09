import asyncio
from typing import Literal

import pytest
from application_context import (
    CRITERIA_VERSION,
    PREFERRED,
    TODAY,
    Script,
    make_posting,
    make_rubric,
    scripted,
    verdict,
)

from hiremate_ai.agents.analysis.application.achievements import Ledger, _Entry
from hiremate_ai.agents.analysis.application.extract import (
    ExtractedFact,
    ExtractedFacts,
    ExtractedPeriod,
    ExtractedSection,
    LetterSummary,
)
from hiremate_ai.agents.analysis.application.graph import ReviewInput, run_review
from hiremate_ai.agents.analysis.application.judge import CriteriaJudgement
from hiremate_ai.agents.analysis.application.present import to_analysis, to_candidate_analysis
from hiremate_ai.agents.analysis.application.review import ReviewJudgement
from hiremate_ai.agents.analysis.application.service import match_criteria
from hiremate_ai.agents.analysis.application.types import (
    ApplicationReview,
    CriterionResult,
    EvaluationRules,
    ScreeningRubric,
)
from hiremate_ai.contract import (
    ApplicantDetail,
    CertificateStatus,
    CriterionCategory,
    CriterionType,
    DocumentType,
    PostingContent,
    Verdict,
)
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.llm.prompt import UNTRUSTED_RULE

API = "카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다."
LATENCY = "하루 120만 건 승인 트랜잭션을 처리하는 승인 서버의 응답 시간을 180ms에서 90ms로 줄였습니다."
PARTITION = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
PERIOD = "한빛카드 결제플랫폼팀 2022.03 ~ 현재"
MADE_UP = "결제 시스템 전체 아키텍처 설계를 혼자 주도했습니다."

YUMIN_EXTRACT = ExtractedFacts(
    facts=[
        ExtractedFact(
            kind="ACHIEVEMENT", statement="승인 서버 응답 시간을 절반으로 줄였다", actor="SELF", evidence=[LATENCY]
        )
    ],
    periods=[
        ExtractedPeriod(company="한빛카드", role="결제플랫폼팀", kind="EMPLOYMENT", start="2022-03", evidence=[PERIOD])
    ],
)
YUMIN = {
    "Q-01": verdict("Q-01", "MET", API, periods=[1]),
    "Q-02": verdict("Q-02", "MET", API),
    "Q-03": verdict("Q-03", "MET", PARTITION),
    "Q-04": verdict("Q-04", "NOT_MET", shortfall="Git 근거 없음"),
    "P-01": verdict("P-01", "PARTIAL", API),
}


def context(applicant: ApplicantDetail, posting: PostingContent, rubric: ScreeningRubric | None = None) -> ReviewInput:
    full = make_posting(posting)
    criteria, notes = match_criteria(full, rubric or make_rubric())
    return ReviewInput(
        applicant=applicant,
        posting=full,
        criteria=criteria,
        criteria_version=CRITERIA_VERSION,
        notes=notes,
        input_hash="hash",
        today=TODAY,
    )


async def review_of(
    llm: FakeLlm, applicant: ApplicantDetail, posting: PostingContent, rubric: ScreeningRubric | None = None
) -> ApplicationReview:
    return await run_review(llm, context(applicant, posting, rubric))


def result(review: ApplicationReview, criterion_id: str) -> CriterionResult:
    return next(item for item in review.criteria if item.criterion_id == criterion_id)


def judging(llm: FakeLlm) -> list[str]:
    return [call.user for call in llm.calls if call.output is CriteriaJudgement]


async def test_criteria_are_judged_without_scores(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, verdicts=YUMIN)

    review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)

    # 자격요건: 충족 · 충족 · 충족 · 미충족, 우대사항: 부분 충족 · 미충족 · 미충족 (자격증 없음). 점수는 매기지 않는다
    verdicts = {item.criterion_id: item.verdict for item in review.criteria}
    assert [verdicts[key] for key in ("Q-01", "Q-02", "Q-03", "Q-04")] == [Verdict.MET] * 3 + [Verdict.NOT_MET]
    assert verdicts["P-01"] == Verdict.PARTIAL
    assert review.holds == []
    analysis = to_analysis(review)
    assert analysis.shortfalls == ["Git 근거 없음"]
    assert analysis.criterion_marks == verdicts
    assert result(review, "Q-01").career_months == 56  # 2022.03 ~ 2026.10 (시작 · 끝 달 포함)
    card = to_candidate_analysis(review, sample_applicants["정유민"].documents)
    lines = {line.criterion_id: line for line in card.criteria}
    assert lines["Q-01"].career_years == 4
    assert lines["P-01"].satisfied_parts and lines["P-01"].unsatisfied_parts
    assert card.criteria_version == CRITERIA_VERSION


async def test_unknown_is_rechecked_and_listed_for_checking(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, verdicts={**YUMIN, "P-02": verdict("P-02", "UNKNOWN")})
    llm = scripted(script)

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    unknown = result(review, "P-02")
    assert (unknown.verdict, unknown.recheck_count) == (Verdict.UNKNOWN, 2)
    # 재확인해도 정하지 못한 항목은 확인 필요로 모은다
    assert len(review.holds) == 1 and "P-02" in review.holds[0].text
    assert to_analysis(review).criterion_marks["P-02"] == Verdict.UNKNOWN
    rounds = [user for user in judging(llm) if "재확인" in user]
    assert any("1차 재확인" in user for user in rounds) and any("2차 재확인" in user for user in rounds)
    assert len(rounds) == 2  # 확인 필요인 항목만 다시 묻는다


async def test_recheck_can_settle_the_item(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        verdicts={**YUMIN, "P-01": verdict("P-01", "MET", MADE_UP)},
        rechecks={("P-01", 1): verdict("P-01", "MET", API)},
    )

    review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)

    # 원문에 없는 근거로 충족이라 했으면 받지 않고 확인 필요로 돌려 재확인한다
    item = result(review, "P-01")
    assert (item.verdict, item.recheck_count) == (Verdict.MET, 1)
    assert review.holds == []


async def test_output_checks_reject_partial_and_missing_answers(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    team = verdict("P-01", "MET", API, role="TEAM")
    no_parts = verdict("P-02", "PARTIAL", PARTITION).model_copy(update={"unsatisfied_parts": []})
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        verdicts={**YUMIN, "Q-02": verdict("Q-02", "PARTIAL", API), "P-01": team, "P-02": no_parts},
        omit={"Q-03"},
    )

    review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)

    # 단일형의 부분 충족, 응답 누락(Q-03), 팀 경험의 충족, 나눠 설명하지 않은 부분 충족은 모두 확인 필요다
    for criterion_id in ("Q-02", "Q-03", "P-01", "P-02"):
        assert result(review, criterion_id).verdict == Verdict.UNKNOWN, criterion_id
    assert "부분 충족" in result(review, "Q-02").reason
    assert "응답" in result(review, "Q-03").reason
    assert "Spring 확인 필요" in to_analysis(review).shortfalls


async def test_career_counts_only_periods_of_the_required_job(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    # 기간은 날짜가 근거 문장에 적혀 있어야 받으므로, 두 기간의 날짜가 적힌 줄을 이력서에 더한다
    current, earlier = "한빛카드 결제플랫폼팀 2024.08 ~ 현재", "새솔은행 디지털팀 2019.01 ~ 2022.02"
    yumin = sample_applicants["정유민"]
    applicant = yumin.model_copy(
        update={
            "documents": [
                document.model_copy(update={"text": f"{document.text}\n{current}\n{earlier}"})
                if document.type == DocumentType.RESUME
                else document
                for document in yumin.documents
            ]
        }
    )
    two_jobs = ExtractedFacts(
        periods=[
            ExtractedPeriod(company="한빛카드", kind="EMPLOYMENT", start="2024-08", evidence=[current]),
            ExtractedPeriod(company="새솔은행", kind="EMPLOYMENT", start="2019-01", end="2022-02", evidence=[earlier]),
        ]
    )
    script = Script(
        extract={"결제플랫폼팀": two_jobs}, verdicts={**YUMIN, "Q-01": verdict("Q-01", "MET", API, periods=[1])}
    )

    review = await review_of(scripted(script), applicant, sample_posting)

    # 전체 재직은 5년이 넘지만 요건의 직무에 해당하는 기간은 2024.08 ~ 2026.10 (시작 · 끝 달 포함 2년 3개월)뿐이다
    item = result(review, "Q-01")
    assert (item.verdict, item.shortfall, item.career_months) == (Verdict.NOT_MET, "경력 2년", 27)


async def test_career_years_count_only_periods_of_the_hiring_job(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    # 경력 연수는 공고 직무와 같은 일을 한 재직 기간만 센다. 다른 직무 경력은 빼고 무엇을 뺐는지 알린다
    current, earlier = "한빛카드 결제플랫폼팀 2024.08 ~ 현재", "새솔은행 영업점 2019.01 ~ 2022.02"
    yumin = sample_applicants["정유민"]
    applicant = yumin.model_copy(
        update={
            "documents": [
                document.model_copy(update={"text": f"{document.text}\n{current}\n{earlier}"})
                if document.type == DocumentType.RESUME
                else document
                for document in yumin.documents
            ]
        }
    )
    two_jobs = ExtractedFacts(
        periods=[
            ExtractedPeriod(company="한빛카드", kind="EMPLOYMENT", start="2024-08", evidence=[current]),
            ExtractedPeriod(company="새솔은행", kind="EMPLOYMENT", start="2019-01", end="2022-02", evidence=[earlier]),
        ]
    )
    script = Script(extract={"결제플랫폼팀": two_jobs}, verdicts=YUMIN, jobs={"새솔은행": "NO"})

    review = await review_of(scripted(script), applicant, sample_posting)

    assert review.career_years == 2  # 2024.08 ~ 2026.10 (2년 3개월). 새솔은행 3년 2개월은 세지 않는다
    [note] = [note for note in review.checks if note.title == "경력 계산"]
    assert "새솔은행 38개월" in note.text


async def test_career_requirement_counts_the_same_job_periods_as_career_years(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    # 경력 기간 항목도 화면의 경력 연수와 같은 직무 관련 기간으로 센다. 판정의 경력표에 다른 직무 경력은 없다
    current, earlier = "한빛카드 결제플랫폼팀 2024.08 ~ 현재", "새솔은행 영업점 2019.01 ~ 2022.02"
    yumin = sample_applicants["정유민"]
    applicant = yumin.model_copy(
        update={
            "documents": [
                document.model_copy(update={"text": f"{document.text}\n{current}\n{earlier}"})
                if document.type == DocumentType.RESUME
                else document
                for document in yumin.documents
            ]
        }
    )
    two_jobs = ExtractedFacts(
        periods=[
            ExtractedPeriod(company="한빛카드", kind="EMPLOYMENT", start="2024-08", evidence=[current]),
            ExtractedPeriod(company="새솔은행", kind="EMPLOYMENT", start="2019-01", end="2022-02", evidence=[earlier]),
        ]
    )
    script = Script(
        extract={"결제플랫폼팀": two_jobs},
        verdicts={**YUMIN, "Q-01": verdict("Q-01", "MET", API, periods=[1, 2])},
        jobs={"새솔은행": "NO"},
    )
    llm = scripted(script)

    review = await review_of(llm, applicant, sample_posting)

    item = result(review, "Q-01")
    assert (item.verdict, item.career_months) == (Verdict.NOT_MET, 27)
    assert review.career_years == 2
    judged = [call.user for call in llm.calls if call.output is CriteriaJudgement and "경력표" in call.user]
    assert judged and all("새솔은행" not in user.split("경력표")[1].split("</data>")[0] for user in judged)


async def test_unclear_career_is_not_called_a_newcomer(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(Script(verdicts=YUMIN))  # 근무 기간을 하나도 뽑지 못한 경우

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    item = result(review, "Q-01")
    assert (item.verdict, item.shortfall) == (Verdict.UNKNOWN, "경력 확인 필요")
    assert review.career_years is None
    assert "신입" not in to_analysis(review).shortfalls


async def test_newcomer_with_education_only_is_marked(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    school = ExtractedFacts(
        periods=[
            ExtractedPeriod(
                company="한결대학교",
                kind="EDUCATION",
                start="2022-03",
                end="2026-02",
                evidence=["한결대학교 컴퓨터공학과 졸업 (2026.02)"],
            )
        ]
    )
    script = Script(
        extract={"신입 백엔드": school}, verdicts={"Q-01": verdict("Q-01", "NOT_MET", shortfall="경력 없음")}
    )

    review = await review_of(scripted(script), sample_applicants["이도윤"], sample_posting)

    assert result(review, "Q-01").shortfall == "신입"
    assert review.career_years == 0
    assert result(review, "Q-01").verdict == Verdict.NOT_MET


async def test_certificate_is_checked_by_code_with_status(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(Script())

    review = await review_of(llm, sample_applicants["김하늘"], sample_posting)

    item = result(review, "P-03")
    assert (item.verdict, item.certificate_status) == (Verdict.MET, CertificateStatus.SELF_REPORTED)
    assert "미검증" in item.reason
    assert not any("[P-03]" in user for user in judging(llm))


async def test_verification_lowers_overstated_and_rechecks_unsupported(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        verdicts={**YUMIN, "P-01": verdict("P-01", "MET", API), "Q-02": verdict("Q-02", "MET", API)},
        rechecks={("Q-02", 1): verdict("Q-02", "MET", API)},
        reviews={"P-01": "OVERSTATED", "Q-02": "UNSUPPORTED"},
    )
    llm = scripted(script)

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    assert result(review, "P-01").verdict == Verdict.PARTIAL  # 복합 경험형의 과장된 충족은 부분 충족으로
    assert result(review, "Q-02").recheck_count == 1  # 받쳐 주지 않는 근거는 확인 필요로 돌려 재확인
    review_call = next(call.user for call in llm.calls if call.output is ReviewJudgement)
    assert "P-01. 주장" in review_call and "Q-02. 주장" in review_call and "F1. 주장" in review_call


async def test_prompts_wrap_documents_and_hide_importance(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, verdicts=YUMIN))

    await review_of(llm, sample_applicants["정유민"], sample_posting)

    assert all(UNTRUSTED_RULE in call.system for call in llm.calls)
    calls = judging(llm)
    assert len(calls) == 2  # 자격요건 · 우대사항 영역마다 한 번
    assert all("<data" in user and "중요" not in user and "1.5" not in user for user in calls)
    assert any("(복합 경험형)" in user and "- 부분 충족: 설계의 일부만" in user for user in calls)
    assert any("(단일 능력 · 경험형)" in user and "- 부분 충족: 없음" in user for user in calls)
    assert any("[Q-01] (조건형) Java 또는 Kotlin 기반 서버 개발 경력 (기간은" in user for user in calls)


async def test_no_preferences_judges_only_qualifications(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, verdicts=YUMIN)
    full = make_posting(sample_posting).model_copy(update={"preferred": []})
    criteria, notes = match_criteria(full, make_rubric())
    context_ = ReviewInput(
        applicant=sample_applicants["정유민"],
        posting=full,
        criteria=criteria,
        criteria_version=CRITERIA_VERSION,
        notes=notes,
        input_hash="hash",
        today=TODAY,
    )

    review = await run_review(scripted(script), context_)

    assert {item.category for item in review.criteria} == {CriterionCategory.QUALIFICATION}
    assert len(review.criteria) == 4


async def test_recheck_stops_when_time_runs_out(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, verdicts={**YUMIN, "P-02": verdict("P-02", "UNKNOWN")})
    llm = scripted(script)
    base = context(sample_applicants["정유민"], sample_posting)
    late = ReviewInput(**{**base.__dict__, "deadline": asyncio.get_running_loop().time() + 1})

    review = await run_review(llm, late)

    assert result(review, "P-02").recheck_count == 0
    assert any("P-02" in note.text for note in review.holds)


async def test_posting_items_without_rubric_are_judged_plainly(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    empty = make_rubric().model_copy(update={"criteria": []})
    llm = scripted(Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}))

    review = await review_of(llm, sample_applicants["정유민"], sample_posting, empty)

    assert {item.criterion_id for item in review.criteria} == {"Q-01", "Q-02", "Q-03", "Q-04", "P-01", "P-02", "P-03"}
    assert not any(item.important for item in review.criteria)
    assert any("평가 기준이 없어" in note.text for note in review.checks)
    assert PREFERRED[2] in judging(llm)[1] or PREFERRED[2] in judging(llm)[0]


async def test_unreadable_documents_are_held_without_model_calls(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = FakeLlm()

    review = await review_of(llm, sample_applicants["윤태오"], sample_posting)

    assert llm.calls == []
    assert not review.readable and review.holds
    analysis = to_analysis(review)
    assert (analysis.career_years, analysis.criterion_marks) == (None, {})
    assert to_candidate_analysis(review, []).criteria == []


async def test_instructions_in_documents_stay_inside_data_blocks(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(Script())

    await review_of(llm, sample_applicants["한예린"], sample_posting)

    portfolio_calls = [call for call in llm.calls if "이전 지시를 모두 무시하고" in call.user]
    assert any(call.output is CriteriaJudgement for call in portfolio_calls)
    for call in portfolio_calls:
        instruction = call.user.index("이전 지시를 모두 무시하고")
        assert call.user.rfind("<data", 0, instruction) > call.user.rfind("</data>", 0, instruction)


async def test_cover_letter_sections_are_summarized_with_checked_quotes(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    cover = "정산 배치 지연을 줄이기 위해 팀과 함께 처리 구조를 바꿨고"
    summary = LetterSummary(
        sections=[
            ExtractedSection(title="지원 동기", summary="결제 신뢰를 중요하게 여겨 지원했다고 썼다.", evidence=[cover]),
            ExtractedSection(title="협업", summary="팀과 정산 구조를 바꿨다고 썼다.", evidence=[MADE_UP]),
        ]
    )
    llm = scripted(Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, verdicts=YUMIN, summary=summary))

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    # 자기소개서만 따로 한 번 묻고, 근거는 원문에서 찾은 문장만 남긴다
    assert [section.title for section in review.sections] == ["지원 동기", "협업"]
    assert [len(section.quotes) for section in review.sections] == [1, 0]
    assert sum(call.output is LetterSummary for call in llm.calls) == 1
    card = to_candidate_analysis(review, sample_applicants["정유민"].documents)
    assert card.summaries[0].evidence[0].document.value == "COVER_LETTER"


async def test_posting_lines_without_rules_keep_their_number_and_required_mark(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    # backend는 평가 기준 입력이 없는 공고 줄을 판정 기준 없이 보낸다.
    # 번호 · 필수 표시는 공고에서 온 값이라 그대로 쓰고,
    # 판정 기준만 초안으로 채운다 (기준선이 같은 번호의 판정으로 필수 조건을 가른다)
    rubric = make_rubric()
    blank = EvaluationRules(met="", unmet="")
    rubric = rubric.model_copy(
        update={
            "criteria": [
                criterion.model_copy(update={"evaluation_rules": blank, "important": criterion.criterion_id == "Q-03"})
                if criterion.criterion_id in ("Q-02", "Q-03")
                else criterion
                for criterion in rubric.criteria
            ]
        }
    )
    llm = scripted(Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}))

    review = await review_of(llm, sample_applicants["정유민"], sample_posting, rubric)

    lines = {item.criterion_id: item for item in review.criteria}
    assert lines["Q-03"].important and not lines["Q-02"].important
    assert lines["Q-01"].important  # 판정 기준이 있는 항목은 그대로다
    blank_notes = [note.text for note in review.checks if "평가 기준이 없어" in note.text]
    assert len(blank_notes) == 2


@pytest.mark.parametrize("ledger_review", ["SUPPORTED", "UNSUPPORTED"])
async def test_metrics_come_from_the_applicant_ledger_once(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    ledger_review: Literal["SUPPORTED", "UNSUPPORTED"],
) -> None:
    # 성과는 지원자마다 한 번 정리하고, 연결된 항목에는 같은 지표가 붙는다. 성과 검증에서 떨어지면 어느 항목에도 없다
    linked = ["Q-01", "Q-02", "Q-03", "P-01"]
    entry = _Entry(
        what="승인 응답 시간",
        before="180ms",
        after="90ms",
        quotes=[LATENCY],
        owner="SELF",
        criteria=linked,
    )
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        verdicts=YUMIN,
        ledger=Ledger(results=[entry]),
        reviews={"R1": ledger_review},
    )
    llm = scripted(script)

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    shown = {
        item.criterion_id: item.metric
        for item in review.criteria
        if item.criterion_id in linked
        and item.verdict in (Verdict.MET, Verdict.PARTIAL)
        and item.criterion_type != CriterionType.CONDITION
    }
    assert shown  # 연결된 충족 · 부분 충족 경험형 항목이 있다
    expected = "승인 응답 시간 180ms → 90ms" if ledger_review == "SUPPORTED" else ""
    assert set(shown.values()) == {expected}
    assert all(not item.metric for item in review.criteria if item.criterion_id not in linked)
    assert sum(call.output is Ledger for call in llm.calls) == 1
    review_call = next(call.user for call in llm.calls if call.output is ReviewJudgement)
    assert "R1. 주장" in review_call
