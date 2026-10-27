from uuid import uuid4

import pytest
from root_context import extra_row, make_context, save_sample_profiles, sessions_of
from sqlalchemy.ext.asyncio import AsyncSession

from hiremate_ai.agents.root.answer import AnswerEvidence, AnswerItem, _invalid_message, readable, verify_items
from hiremate_ai.agents.root.toolkit import AgentEvidence, profile_toolkit, scope_of
from hiremate_ai.agents.root.types import (
    ChatContext,
    InterviewQuestion,
    InterviewView,
    PreviousInterview,
    QuestionSource,
)
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, InterviewerMemo, PostingContent, StageType
from hiremate_ai.db.profile import ItemAgent, ItemCategory
from hiremate_ai.db.profile_store import NewItem, save_profile

type Applicants = dict[str, ApplicantDetail]
BATCH = "MySQL 정산 테이블을 파티셔닝해 월말 정산 배치 시간을 40% 줄였습니다."
RETRO = "장애가 나면 원인을 혼자 감추지 않고 회고에서 팀과 공유합니다."
ASSESSMENT_NOTE = "장애 원인을 로그로 좁혀 가는 과정을 팀원에게 차근차근 설명했어요."


def test_interviewer_memo_is_always_check_and_never_another_candidates_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    application_id = context.candidates[0].application_id
    text = "태도가 좋지만 본인 작업 범위는 확인하지 못함"
    memo = InterviewerMemo(stage_id=context.stage_id, stage_name=context.stage_name, text=text)
    context = context.model_copy(update={"interviewer_memos": {application_id: [memo]}})
    items, sources, _ = verify_items([item(text, source="면접관메모")], context)
    assert items[0].status == "CHECK"
    assert sources == ["면접관메모"]
    _, wrong_sources, _ = verify_items([item(text, source="면접관메모", candidate="C2")], context)
    assert wrong_sources == []


PARTITION_ANSWER = "파티셔닝 기준을 월 단위로 정했습니다."


def context_for(
    applicants: Applicants,
    company: CompanyProfile,
    posting: PostingContent,
    *,
    stage_type: StageType = StageType.DOCUMENT,
) -> ChatContext:
    return make_context(applicants, company, posting, message="근거를 확인해줘", stage_type=stage_type)


def item(sentence: str, *, source: str = "이력서", candidate: str | None = "C1", status: str = "OK") -> AnswerItem:
    return AnswerItem(
        candidate=candidate,
        label="강점",
        text="확인한 내용",
        status="OK" if status == "OK" else "CHECK",
        evidence=[AnswerEvidence(sentence=sentence, source=source)] if sentence else [],
    )


def test_document_evidence_is_checked_against_the_real_document(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    actual = sample_applicants["정유민"].documents[1].text
    sentence = actual.splitlines()[0]

    items, sources, agents = verify_items(
        [item(BATCH), item("증권사에서 10년 일했습니다."), item(sentence, source="이력서")], context
    )

    assert [entry.status for entry in items] == ["OK", "CHECK", "OK"]
    assert sources == ["이력서", "자기소개서"]
    assert agents == []


def test_candidate_ok_needs_evidence_but_honest_check_does_not(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    items, sources, _ = verify_items([item(""), item("", status="CHECK")], context)

    assert [entry.status for entry in items] == ["CHECK", "CHECK"]
    assert sources == []


def test_unknown_candidate_is_not_assigned_to_another_person(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    items, _, _ = verify_items([item(BATCH, candidate="C42")], context)

    assert items == []


def test_evidence_without_a_candidate_is_unverified(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    items, sources, _ = verify_items([item(BATCH, candidate=None)], context)

    assert items[0].application_id is None
    assert items[0].status == "CHECK"
    assert sources == []


def test_profile_evidence_names_its_analysis_agent(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    recorded = {application_id: [AgentEvidence(sentence=ASSESSMENT_NOTE, source="평가 메모", agent="assessment")]}

    items, sources, agents = verify_items([item(ASSESSMENT_NOTE, source="평가 메모")], context, recorded=recorded)

    assert items[0].status == "OK"
    assert sources == ["평가 메모"]
    assert agents == ["Assessment Agent"]


def test_assessment_evidence_without_a_profile_is_unverified(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    items, sources, agents = verify_items([item(ASSESSMENT_NOTE, source="평가 메모")], context)

    assert items[0].status == "CHECK"
    assert sources == [] and agents == []


@pytest.mark.parametrize("verification", ["CONFLICT", "UNCONFIRMED"])
def test_doubtful_profile_evidence_is_not_confirmed_even_if_the_quote_exists(
    verification: str, sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    recorded = {
        context.candidates[0].application_id: [
            AgentEvidence(sentence=BATCH, source="이력서", agent="application", verification=verification)
        ]
    }

    items, sources, agents = verify_items([item(BATCH)], context, recorded=recorded)

    assert items[0].status == "CHECK"
    assert sources == ["이력서"] and agents == ["Application Agent"]


def test_conflict_from_another_source_does_not_invalidate_document_evidence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    recorded = {
        context.candidates[0].application_id: [
            AgentEvidence(sentence=BATCH, source="면접 기록", agent="interview", verification="CONFLICT")
        ]
    }

    items, _, _ = verify_items([item(BATCH)], context, recorded=recorded)

    assert items[0].status == "OK"


def interview_question(text: str) -> InterviewQuestion:
    return InterviewQuestion(
        question_id=uuid4(), text="설계 판단을 설명해 주세요.", source=QuestionSource.AI, answer=text
    )


def test_interview_evidence_uses_current_and_previous_records(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, stage_type=StageType.INTERVIEW)
    application_id = context.candidates[0].application_id
    view = InterviewView(
        application_id=application_id,
        schedule=None,
        questions=[interview_question(PARTITION_ANSWER)],
        previous=[
            PreviousInterview(
                stage_id=uuid4(),
                stage_name="이전 면접",
                schedule=None,
                questions=[interview_question("작게 나눠 배포했습니다.")],
            )
        ],
    )
    context = context.model_copy(update={"interviews": {application_id: view}})

    items, sources, _ = verify_items(
        [
            item(PARTITION_ANSWER, source="면접 기록"),
            item("작게 나눠 배포했습니다.", source="면접 기록"),
            item("샤딩을 도입했습니다.", source="면접 기록"),
        ],
        context,
    )

    assert [entry.status for entry in items] == ["OK", "OK", "CHECK"]
    assert sources == ["면접 기록"]


def test_score_evidence_must_match_backend_values(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting, stage_type=StageType.ASSESSMENT)
    context = context.model_copy(
        update={"candidates": [context.candidates[0].model_copy(update={"score": 82}), *context.candidates[1:]]}
    )

    items, sources, agents = verify_items(
        [item("평가 점수: 82점", source="평가 결과"), item("평가 점수: 100점", source="평가 결과")], context
    )

    assert [entry.status for entry in items] == ["OK", "CHECK"]
    assert sources == ["평가 결과"] and agents == []


def test_company_and_posting_evidence_is_checked_without_request_keywords(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    talent = sample_company.talents[0]
    raw = [
        item(f"{talent.title}: {talent.description}", source="인재상"),
        item(sample_posting.qualifications[0], source="공고"),
        item("가장 큰 결제 회사입니다", source="회사 소개"),
    ]

    items, sources, _ = verify_items(raw, context)

    assert [entry.status for entry in items] == ["OK", "OK", "CHECK"]
    assert sources == ["회사 소개", "공고"]


def test_sources_are_listed_only_once(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)

    _, sources, _ = verify_items([item(BATCH), item(BATCH)], context)

    assert sources == ["이력서"]


def test_readable_handles_candidate_numbers_and_model_leftovers(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="확인", extra_rows=[extra_row("지원자1")]
    )

    assert readable("C9 지원자1의 강점", context) == "지원자1의 강점"
    assert readable("responseC1의 강점", context) == "정유민의 강점"
    assert readable("<think>번호로 부른다</think>C2 김하늘은 은행 경력이에요.", context) == "김하늘은 은행 경력이에요."
    assert readable("EC2 운영 경험", context) == "EC2 운영 경험"


@pytest.mark.parametrize("message", ["정리했어요. (C1)}},", "상세 근거는 items를 참고하세요.", ""])
def test_invalid_message_rejects_internal_output(message: str) -> None:
    assert _invalid_message(message)


def test_technical_method_name_is_not_internal_output() -> None:
    assert not _invalid_message("dict.items() 경험을 확인해 주세요.")


async def test_profile_lookup_preserves_application_evidence(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    await save_sample_profiles(db_session, sample_company, sample_applicants)
    context = context_for(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    toolkit = profile_toolkit(sessions_of(db_session))
    recorded = await toolkit.evidence(scope_of(context), [application_id])

    items, sources, agents = verify_items([item("한빛카드 결제플랫폼팀 2022.03 ~ 현재")], context, recorded=recorded)

    assert items[0].status == "OK"
    assert sources == ["이력서"] and agents == ["Application Agent"]


async def test_assessment_profile_keeps_the_saved_evidence_and_agent(
    db_session: AsyncSession,
    sample_applicants: Applicants,
    sample_company: CompanyProfile,
    sample_posting: PostingContent,
) -> None:
    context = context_for(sample_applicants, sample_company, sample_posting)
    application_id = context.candidates[0].application_id
    await save_profile(
        db_session,
        company_id=sample_company.company_id,
        recruitment_id=context.recruitment_id,
        application_id=application_id,
        agent=ItemAgent.ASSESSMENT,
        items=[
            NewItem(
                category=ItemCategory.STRENGTH,
                content="원인 분석을 설명한다",
                evidence=ASSESSMENT_NOTE,
                source="평가 메모",
            )
        ],
        stage_id=uuid4(),
    )
    toolkit = profile_toolkit(sessions_of(db_session))
    recorded = await toolkit.evidence(scope_of(context), [application_id])

    items, sources, agents = verify_items([item(ASSESSMENT_NOTE, source="평가 메모")], context, recorded=recorded)

    assert items[0].status == "OK"
    assert sources == ["평가 메모"] and agents == ["Assessment Agent"]
