import pytest
from pydantic import ValidationError
from root_context import STAGE_ID, make_context

from hiremate_ai.agents.root.stages import (
    StageData,
    blames_later_stage,
    not_yet,
    reached,
    stage_data,
    stage_plan,
    without_later_gaps,
)
from hiremate_ai.agents.root.types import ChatContext, StageStatus
from hiremate_ai.contract import ApplicantDetail, CompanyProfile, PostingContent, StageType

type Applicants = dict[str, ApplicantDetail]

GAP = "면접 기록이 없어 실제 역량과 태도를 확인할 수 없어요."


def first_stage(applicants: Applicants, company: CompanyProfile, posting: PostingContent) -> ChatContext:
    """서류 → 과제 평가 → 1차 면접 가운데 첫 서류 전형."""
    return make_context(
        applicants,
        company,
        posting,
        message="질문",
        later_types=(StageType.ASSESSMENT, StageType.INTERVIEW),
    )


def test_stage_data_tells_later_current_earlier_and_none(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    first = first_stage(sample_applicants, sample_company, sample_posting)
    interview = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="질문",
        stage_type=StageType.INTERVIEW,
        previous_types=(StageType.DOCUMENT,),
    )

    assert stage_data(first, StageType.DOCUMENT) is StageData.CURRENT
    assert stage_data(first, StageType.INTERVIEW) is StageData.LATER
    assert stage_data(interview, StageType.DOCUMENT) is StageData.EARLIER
    assert stage_data(interview, StageType.ASSESSMENT) is StageData.NONE
    assert not reached(first, StageType.INTERVIEW)
    assert reached(interview, StageType.DOCUMENT) and reached(interview, StageType.INTERVIEW)


def test_stage_plan_lists_every_stage_in_order(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(sample_applicants, sample_company, sample_posting)

    assert stage_plan(context) == (
        "1. 서류 전형 (서류 · 진행 중, 현재) → 2. 과제 평가 (평가 · 시작 전) → 3. 1차 면접 (면접 · 시작 전)"
    )
    assert context.previous_types == []


def test_not_yet_names_the_later_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(sample_applicants, sample_company, sample_posting)
    only_document = make_context(sample_applicants, sample_company, sample_posting, message="질문")

    assert not_yet(context, StageType.INTERVIEW).startswith("면접 자료는 3번째 전형 '1차 면접'에서 생겨요.")
    assert not_yet(only_document, StageType.INTERVIEW) == ""


def test_previous_types_come_from_stages(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = make_context(
        sample_applicants,
        sample_company,
        sample_posting,
        message="질문",
        stage_type=StageType.INTERVIEW,
        previous_types=(StageType.DOCUMENT, StageType.ASSESSMENT),
        later_types=(StageType.INTERVIEW,),
        stage_status=StageStatus.CONFIRMED,
    )

    assert context.previous_types == [StageType.DOCUMENT, StageType.ASSESSMENT]
    assert context.stage_index == 2
    assert context.stage_status is StageStatus.CONFIRMED


def test_context_without_current_stage_is_rejected(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(sample_applicants, sample_company, sample_posting)
    payload = context.model_dump(mode="json")
    payload["stages"] = [stage for stage in payload["stages"] if stage["id"] != str(STAGE_ID)]

    with pytest.raises(ValidationError, match="현재 전형"):
        ChatContext.model_validate(payload)


@pytest.mark.parametrize(
    "text",
    [
        GAP,
        "확인할 점 면접 답변이 아직 없어 추가 확인이 필요해요",
        "면접을 아직 진행하지 않아 태도는 알 수 없어요.",
        "과제 평가 결과가 없어 실무 역량은 확인되지 않았어요.",
        "평가 점수가 부족해 판단하기 어려워요.",
    ],
)
def test_later_stage_gap_is_blamed_before_that_stage(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent, text: str
) -> None:
    assert blames_later_stage(first_stage(sample_applicants, sample_company, sample_posting), text)


@pytest.mark.parametrize(
    "text",
    [
        "협업 방식은 면접에서 확인할 점이에요.",
        "서류 평가 결과가 없어 다시 분석이 필요해요.",
        "자기소개서에 본인 역할이 드러나지 않아 확인이 필요해요.",
    ],
)
def test_next_step_and_document_gaps_are_not_blamed(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent, text: str
) -> None:
    assert not blames_later_stage(first_stage(sample_applicants, sample_company, sample_posting), text)


def test_gap_of_a_reached_stage_is_kept(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    # 면접 전형에서는 면접 기록이 없다는 말이 실제 상태다
    context = make_context(
        sample_applicants, sample_company, sample_posting, message="질문", stage_type=StageType.INTERVIEW
    )

    assert not blames_later_stage(context, GAP)


def test_without_later_gaps_drops_only_that_sentence(
    sample_applicants: Applicants, sample_company: CompanyProfile, sample_posting: PostingContent
) -> None:
    context = first_stage(sample_applicants, sample_company, sample_posting)

    assert without_later_gaps(context, f"정산 배치 경험이 강점이에요. {GAP}") == "정산 배치 경험이 강점이에요."
    assert without_later_gaps(context, GAP) == ""
