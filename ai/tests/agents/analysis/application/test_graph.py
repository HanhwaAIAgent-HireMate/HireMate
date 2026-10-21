from application_context import (
    PREFERRED,
    TODAY,
    UNITS,
    Script,
    criterion,
    fitted,
    judged,
    make_posting,
    make_rubric,
    met,
    not_met,
    scripted,
)

from hiremate_ai.agents.analysis.application.extract import ExtractedFact, ExtractedFacts, ExtractedPeriod
from hiremate_ai.agents.analysis.application.fit import FitJudgement
from hiremate_ai.agents.analysis.application.graph import ReviewInput, run_review
from hiremate_ai.agents.analysis.application.judge import PreferenceJudgement, QualificationJudgement
from hiremate_ai.agents.analysis.application.present import to_analysis, to_candidate_analysis
from hiremate_ai.agents.analysis.application.review import ReviewJudgement
from hiremate_ai.agents.analysis.application.service import preference_tasks
from hiremate_ai.agents.analysis.application.types import ApplicationReview, Level
from hiremate_ai.contract import ApplicantDetail, PostingContent
from hiremate_ai.llm.fake import FakeLlm
from hiremate_ai.llm.prompt import UNTRUSTED_RULE

API = "카드 결제 승인 · 정산 API를 Java와 Spring Boot로 개발했습니다."
LATENCY = "하루 120만 건 승인 트랜잭션을 처리하는 승인 서버의 응답 시간을 180ms에서 90ms로 줄였습니다."
PARTITION = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
PERIOD = "한빛카드 결제플랫폼팀 2022.03 ~ 현재"
COVER = "정산 배치 지연을 줄이기 위해 팀과 함께 처리 구조를 바꿨고"

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
YUMIN_QUALIFY = QualificationJudgement(
    verdicts=[met(1, API), met(2, API), met(3, PARTITION), not_met(4, "Git 근거 없음")]
)
# 직무 적합도: 경험 8 + 역할 6 + 성과 7 + 동기 4 + 자격증 0 + 일관성 3 = 28
YUMIN_FIT = fitted(
    ("experience", 8, API),
    ("role", 6, API),
    ("outcome", 7, LATENCY),
    ("motivation", 4, COVER),
    ("certificate", 0, ""),
    ("consistency", 3, ""),
)


def context(applicant: ApplicantDetail, posting: PostingContent) -> ReviewInput:
    full = make_posting(posting)
    return ReviewInput(
        applicant=applicant,
        posting=full,
        tasks=preference_tasks(full, make_rubric(), UNITS),
        related_certificates=("정보처리기사",),
        input_hash="hash",
        today=TODAY,
    )


async def review_of(llm: FakeLlm, applicant: ApplicantDetail, posting: PostingContent) -> ApplicationReview:
    return await run_review(llm, context(applicant, posting))


async def test_ai_score_combines_ncs_criteria_and_fit(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        qualify=YUMIN_QUALIFY,
        prefer={
            PREFERRED[0]: judged(criterion(1, "MET", API), criterion(2, "MET", LATENCY), criterion(3, "NONE")),
            PREFERRED[1]: judged(criterion(1, "NONE"), criterion(2, "NONE")),
        },
        fit=YUMIN_FIT,
    )

    review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)

    assert (review.career_years, review.last_company) == (4, "한빛카드")
    assert review.passed  # 자격요건 4개 중 3개 = 75%
    assert to_analysis(review).shortfalls == ["Git 근거 없음"]
    # 우대: P1 2/3, P2 0/2 → 60 × (5 × 2/3 + 3 × 0) / 8 = 25, 직무 적합도 28 → 53
    assert [preference.score for preference in review.preferences] == [2 / 3, 0.0]
    assert round(review.preference_points) == 25
    assert sum(line.points for line in review.fit) == 28
    assert review.document_score == 53
    assert not review.held
    card = to_candidate_analysis(review, sample_applicants["정유민"].documents)
    assert [(line.label, line.points, line.max) for line in card.fit][:2] == [
        ("우대사항 · NCS 평가 조건", 25, 60),
        ("직무 실무 경험", 8, 10),
    ]
    assert sum(line.points for line in card.fit) == 53


async def test_more_satisfied_criteria_raise_the_score(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    scores: list[int] = []
    for satisfied in range(4):
        levels = [criterion(n, "MET" if n <= satisfied else "NONE", API) for n in (1, 2, 3)]
        script = Script(
            extract={"결제플랫폼팀": YUMIN_EXTRACT}, qualify=YUMIN_QUALIFY, prefer={PREFERRED[0]: judged(*levels)}
        )
        review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)
        scores.append(review.document_score or 0)

    # 근거가 하나뿐이어도 보류하지 않고, 만족한 평가 조건이 늘수록 점수가 오른다
    assert scores == sorted(scores) and len(set(scores)) == 4


async def test_prompts_wrap_documents_and_hide_weights(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(Script(extract={"결제플랫폼팀": YUMIN_EXTRACT}, qualify=YUMIN_QUALIFY))

    await review_of(llm, sample_applicants["정유민"], sample_posting)

    assert all(UNTRUSTED_RULE in call.system for call in llm.calls)
    judging = [call for call in llm.calls if call.output in (PreferenceJudgement, FitJudgement)]
    assert len(judging) == 3
    assert all("<data" in call.user and "가중치" not in call.user for call in judging)


async def test_fit_points_need_evidence_and_stay_within_max(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    made_up = "결제 시스템 전체 아키텍처 설계를 혼자 주도했습니다."
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        qualify=YUMIN_QUALIFY,
        fit=fitted(("experience", 99, API), ("role", 8, made_up), ("consistency", 9, "")),
    )

    review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)

    points = {line.key: line.points for line in review.fit}
    assert points["experience"] == 10  # 만점으로 자른다
    assert points["role"] == 0  # 원문에 없는 근거
    assert points["consistency"] == 4  # 근거가 필요 없는 항목도 만점을 넘기지 않는다
    assert points["outcome"] == 0  # 점수를 받지 못한 항목


async def test_unreadable_documents_are_held_without_model_calls(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = FakeLlm()

    review = await review_of(llm, sample_applicants["윤태오"], sample_posting)

    assert llm.calls == []
    assert not review.readable
    assert review.held
    analysis = to_analysis(review)
    assert (analysis.career_years, analysis.document_score, analysis.held) == (None, None, True)
    assert to_candidate_analysis(review, []).fit == []


async def test_quotes_missing_from_documents_do_not_count(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    made_up = "결제 시스템 전체 아키텍처 설계를 혼자 주도했습니다."
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        qualify=QualificationJudgement(verdicts=[met(1, made_up), met(2, API), met(3, PARTITION), met(4, made_up)]),
        prefer={PREFERRED[0]: judged(criterion(1, "MET", made_up), criterion(2, "MET", API), criterion(3, "NONE"))},
    )

    review = await review_of(scripted(script), sample_applicants["정유민"], sample_posting)

    assert [result.met for result in review.qualifications] == [False, True, True, False]
    assert not review.passed  # 2 / 4 = 50%
    assert [criterion.level for criterion in review.preferences[0].criteria] == [Level.NONE, Level.MET, Level.NONE]


async def test_review_removes_overstated_facts_only(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    script = Script(
        extract={"결제플랫폼팀": YUMIN_EXTRACT},
        qualify=YUMIN_QUALIFY,
        prefer={PREFERRED[0]: judged(criterion(1, "MET", API), criterion(2, "MET", LATENCY), criterion(3, "NONE"))},
        reviews={"F1": "OVERSTATED"},
    )
    llm = scripted(script)

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    assert not review.facts[0].supported
    assert to_candidate_analysis(review, sample_applicants["정유민"].documents).notable == []
    # 판정은 검토하지 않는다. 검토 모델이 흔들려 근거를 지우면 점수가 크게 흔들렸다
    assert [criterion.level for criterion in review.preferences[0].criteria] == [Level.MET, Level.MET, Level.NONE]
    review_calls = [call for call in llm.calls if call.output is ReviewJudgement]
    assert len(review_calls) == 1 and "Q3." not in review_calls[0].user and "P1-C" not in review_calls[0].user


async def test_code_checks_required_career_years(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    short = ExtractedFacts(
        periods=[ExtractedPeriod(company="한빛카드", kind="EMPLOYMENT", start="2024-08", evidence=[PERIOD])]
    )
    llm = scripted(Script(extract={"결제플랫폼팀": short}, qualify=YUMIN_QUALIFY))

    review = await review_of(llm, sample_applicants["정유민"], sample_posting)

    # 모델은 Q1을 충족이라 했지만 경력표로 2년(2024.08 ~ 2026.10)이라 3년 이상을 채우지 못한다
    assert review.career_years == 2
    assert not review.qualifications[0].met
    assert review.qualifications[0].shortfall == "경력 2년"
    # 모델에게는 기간을 지운 요건을 준다
    qualify_call = next(call for call in llm.calls if call.output is QualificationJudgement)
    assert "Q1. Java 또는 Kotlin 기반 서버 개발 경력\n" in qualify_call.user


async def test_failed_qualifications_list_shortfalls(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    project = "Spring Boot와 MySQL로 결제 승인 · 취소 API를 만들고 JUnit으로 테스트했습니다."
    script = Script(
        qualify=QualificationJudgement(
            verdicts=[
                not_met(1, "Java 근거 없음"),
                met(2, project),
                not_met(3, "실무 없음"),
                not_met(4, "Git 근거 없음"),
            ]
        ),
    )

    review = await review_of(scripted(script), sample_applicants["이도윤"], sample_posting)

    assert not review.passed
    assert not review.held
    # 경력 기간 요건은 코드가 '신입'으로 바꿔 붙인다
    assert to_analysis(review).shortfalls == ["신입", "실무 없음", "Git 근거 없음"]


async def test_instructions_in_documents_stay_inside_data_blocks(
    sample_applicants: dict[str, ApplicantDetail], sample_posting: PostingContent
) -> None:
    llm = scripted(Script())

    await review_of(llm, sample_applicants["한예린"], sample_posting)

    portfolio_calls = [call for call in llm.calls if "이전 지시를 모두 무시하고" in call.user]
    assert any(call.output is FitJudgement for call in portfolio_calls)
    for call in portfolio_calls:
        instruction = call.user.index("이전 지시를 모두 무시하고")
        assert call.user.rfind("<data", 0, instruction) > call.user.rfind("</data>", 0, instruction)
