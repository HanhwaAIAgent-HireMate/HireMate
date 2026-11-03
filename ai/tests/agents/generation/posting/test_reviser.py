from typing import Any
from uuid import UUID

import pytest
from ncs_context import UNIT, FakeNcs, task
from pydantic import BaseModel

from hiremate_ai.agents.generation.posting.ncs import (
    NCS_HEADER,
    NCS_NOT_FOUND,
    NCS_SOURCES_DROPPED,
    NCS_UNAVAILABLE,
    SOURCES_STEP,
    LineCitation,
    NcsQuery,
    NcsUse,
    SupportReview,
    SupportVerdict,
)
from hiremate_ai.agents.generation.posting.reviser import (
    ANSWER_ONLY_REPLY,
    BLIND_LINE,
    BLIND_REPLY,
    BLOCKED_REPLY,
    CHECK_FAILED_REPLY,
    CHECKING_STEP,
    CONTENT_STEP,
    FIELD_LABELS,
    FOCUS_MISSING_REPLY,
    LINE_STEP,
    LINE_UNCHANGED_REPLY,
    LOCKED_REPLY,
    MULTILINE_LINE,
    NCS_STEP,
    NOTHING_CHANGED_REPLY,
    RETRY_HINT,
    REWRITING_STEP,
    ROUTE_STEP,
    SOURCES_CHECK_STEP,
    SYSTEM,
    UNCHANGED_LINE,
    WRITING_STEP,
    CitedContentChanges,
    ContentChanges,
    ExtrasPlan,
    FieldChange,
    IntroEdit,
    LineEdit,
    RoleChanges,
    Route,
    StageEdit,
    StagePlan,
    revise_posting,
)
from hiremate_ai.agents.generation.posting.types import (
    PostingDraftContext,
    PostingFocus,
    RecruitmentStatus,
    StageDraft,
)
from hiremate_ai.config import settings
from hiremate_ai.contract import DocumentType, PostingContent, PostingRole, StageType
from hiremate_ai.llm.fake import FakeLlm

CONTENT = PostingContent(
    title="결제 플랫폼 백엔드 개발자",
    job_category="백엔드 개발",
    employment_type="정규직",
    career="경력 3년 이상",
    location="서울 중구",
    intro="카드 결제와 정산을 처리하는 플랫폼을 함께 만들 백엔드 개발자를 찾습니다.",
    duties=["결제 승인 · 정산 API 개발"],
    qualifications=["Java · Spring Boot 기반 서버 개발 경력 3년 이상"],
    preferred=["금융 도메인 경험"],
    benefits=["유연 근무"],
)
DOCUMENT = StageDraft(name="서류 전형", type=StageType.DOCUMENT)
CODING = StageDraft(name="코딩테스트", type=StageType.ASSESSMENT)
INTERVIEW = StageDraft(name="1차 면접", type=StageType.INTERVIEW)


def posting(**overrides: Any) -> PostingDraftContext:
    fields: dict[str, Any] = {
        "recruitment_id": UUID("6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b"),
        "status": RecruitmentStatus.DRAFT,
        "content": CONTENT,
        "stages": [DOCUMENT],
        "required_extras": [DocumentType.PORTFOLIO],
    }
    return PostingDraftContext(**{**fields, **overrides})


def route(*targets: Any, question: str | None = None, writes_posting: bool = False, ncs: NcsUse = "SKIP") -> Route:
    return Route(targets=list(targets), question=question, writes_posting=writes_posting, ncs=ncs)


async def test_multiple_roles_are_separate_proposals_and_keep_common_data() -> None:
    roles = [
        PostingRole(
            name=name, career="신입", duties=["기초 업무 수행"], qualifications=["직무 기초 지식"], preferred=[]
        )
        for name in ["백엔드", "인사", "생산관리"]
    ]
    llm = FakeLlm(route("ROLES", writes_posting=True), RoleChanges(roles=roles))
    result = await revise_posting(llm, posting(), "", "신입 백엔드, 인사, 생산관리 세 직무 모집 표로 만들어줘")
    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["roles"]
    assert result.suggestion.content.roles == roles
    assert result.suggestion.content.benefits == CONTENT.benefits
    assert result.suggestion.stages is None


async def test_stage_reordering_preserves_existing_icons() -> None:
    stages = [
        StageDraft(name="서류", type=StageType.DOCUMENT, icon="FILE_TEXT"),
        StageDraft(name="실무면접", type=StageType.INTERVIEW, icon="CHAIR"),
    ]
    llm = FakeLlm(
        route("STAGES"),
        StagePlan(
            stages=[
                StageEdit(name="실무면접", type=StageType.INTERVIEW),
                StageEdit(name="서류", type=StageType.DOCUMENT),
            ]
        ),
    )
    result = await revise_posting(llm, posting(stages=stages), "", "전형을 실무면접, 서류 순서로 바꿔줘")
    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["stages"]
    assert result.suggestion.stages == [stages[1], stages[0]]


def content(**fields: str | list[str]) -> ContentChanges:
    """본문 칸 이름(title, preferred 등)으로 바꿀 값을 받아 모델 답을 만든다."""
    return ContentChanges(
        changes=[
            FieldChange.model_validate(
                {
                    "field": FIELD_LABELS[name],
                    "text": value if isinstance(value, str) else None,
                    "items": None if isinstance(value, str) else value,
                }
            )
            for name, value in fields.items()
        ]
    )


def plan(*stages: StageDraft | StageEdit) -> StagePlan:
    return StagePlan(stages=[StageEdit(name=stage.name, type=stage.type) for stage in stages])


def extras(*names: Any) -> ExtrasPlan:
    return ExtrasPlan(required_extras=list(names))


# 대상 고르기


async def test_revise_without_targets_says_nothing_changed() -> None:
    llm = FakeLlm(route())

    result = await revise_posting(llm, posting(), "", "음")

    assert result.suggestion is None
    assert result.reply == NOTHING_CHANGED_REPLY
    assert len(llm.calls) == 1


async def test_revise_without_targets_asks_the_models_question() -> None:
    llm = FakeLlm(route(question="어느 칸을 고칠까요?"))

    result = await revise_posting(llm, posting(), "", "좀 더 좋게")

    assert result.reply == "어느 칸을 고칠까요?"


async def test_every_call_shares_system_and_context_and_ends_with_its_step() -> None:
    llm = FakeLlm(route("CONTENT"), content(location="경기 성남시"))

    await revise_posting(llm, posting(), "", "근무지 성남")

    first, second = llm.calls
    assert first.system == second.system == SYSTEM
    assert first.output is Route
    assert second.output is ContentChanges
    assert first.user.endswith(ROUTE_STEP)
    assert second.user.endswith(CONTENT_STEP + "\n이번에 반영할 HR 요청: 근무지 성남")
    assert first.user.removesuffix(ROUTE_STEP) == second.user.removesuffix(
        CONTENT_STEP + "\n이번에 반영할 HR 요청: 근무지 성남"
    )


# 공고 본문


async def test_revise_applies_only_edited_fields_and_marks_them() -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"]))

    result = await revise_posting(llm, posting(), "", "우대 사항에 결제 · 정산 경험 추가해 줘")

    assert result.suggestion is not None
    assert result.suggestion.content == CONTENT.model_copy(
        update={"preferred": ["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"]}
    )
    assert result.suggestion.changed_fields == ["preferred"]
    assert result.suggestion.stages is None
    assert result.suggestion.required_extras is None
    assert result.reply == "우대 사항 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요."


async def test_revise_does_not_mark_fields_the_model_returned_unchanged() -> None:
    llm = FakeLlm(
        route("CONTENT"), content(title=CONTENT.title, duties=["결제 승인 · 정산 API 개발", "정산 배치 개선"])
    )

    result = await revise_posting(llm, posting(), "", "주요 업무에 정산 배치 개선 넣어 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["duties"]


async def test_revise_ignores_empty_values_instead_of_clearing_fields() -> None:
    llm = FakeLlm(route("CONTENT"), content(job_category="", career=" ", benefits=[], location="경기 성남시"))

    result = await revise_posting(llm, posting(), "", "근무지 성남")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["location"]


async def test_revise_lists_changed_fields_in_screen_order() -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["대용량 트래픽 경험"], employment_type="계약직"))

    result = await revise_posting(llm, posting(), "", "계약직으로 바꾸고 우대 사항도 고쳐 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["employmentType", "preferred"]
    assert result.reply.startswith("고용 형태, 우대 사항 수정안")


async def test_revise_keeps_employment_type_outside_the_four_choices() -> None:
    llm = FakeLlm(route("CONTENT"), content(employment_type="프리랜서"))

    result = await revise_posting(llm, posting(), "", "프리랜서로 바꿔 줘")

    assert result.suggestion is None or "employmentType" not in result.suggestion.changed_fields


@pytest.mark.parametrize(
    ("written", "expected"),
    [("5년 이상", "경력 5년 이상"), ("경력무관", "경력 무관"), ("신입", "신입"), ("3~5년", None)],
)
async def test_revise_keeps_career_to_the_set_shapes(written: str, expected: str | None) -> None:
    # 연차가 바뀌면 자격 요건에 남은 이전 연차(경력 3년 이상)를 고치게 한 번 더 묻는다
    fixed = content(career=written, qualifications=["Java · Spring Boot 기반 서버 개발 경력 5년 이상"])
    llm = FakeLlm(route("CONTENT"), content(career=written), fixed)

    result = await revise_posting(llm, posting(), "", f"경력을 {written}으로 바꿔 줘")

    if expected is None:
        assert result.suggestion is None or "career" not in result.suggestion.changed_fields
    else:
        assert result.suggestion is not None
        assert result.suggestion.content.career == expected


async def test_revise_tidies_text_bullets_and_number_spacing() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(
            location="  경기 성남시 ",
            career="경력 5 년 이상",
            qualifications=["Java · Spring Boot 기반 서버 개발 경력 5년 이상"],
            benefits=["- 유연 근무", "", "  ", "2. 식대 지원", "• 연 1 회 건강검진"],
        ),
    )

    result = await revise_posting(llm, posting(), "", "근무지 성남, 경력 5년, 복지 추가")

    assert result.suggestion is not None
    assert result.suggestion.content.location == "경기 성남시"
    assert result.suggestion.content.career == "경력 5년 이상"
    assert result.suggestion.content.benefits == ["유연 근무", "식대 지원", "연 1회 건강검진"]


async def test_career_change_retries_when_related_requirement_still_has_old_condition() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(career="경력 5년 이상"),
        content(career="경력 5년 이상", qualifications=["Java · Spring Boot 기반 서버 개발 경력 5년 이상"]),
    )
    result = await revise_posting(llm, posting(), "", "경력 5년 이상으로 바꿔줘")
    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["career", "qualifications"]
    assert "이전 경력 조건이 남아 있다" in llm.calls[2].user
    assert result.suggestion.content.duties == CONTENT.duties


async def test_career_conflict_is_not_returned_as_an_applicable_suggestion() -> None:
    llm = FakeLlm(route("CONTENT"), content(career="경력 5년 이상"), content(career="경력 5년 이상"))
    result = await revise_posting(llm, posting(), "", "경력 5년 이상으로 바꿔줘")
    assert result.suggestion is None
    assert result.reply == CHECK_FAILED_REPLY


async def test_revise_attaches_particles_after_english_words() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(
            qualifications=[
                "Java 와 Spring Boot 를 활용한 서버 개발 경험",
                "AWS 에서 서비스를 운영한 경험",
                "Java 17 이상, Kafka 로그 수집 경험",
                "REST API 기반 설계 능력",
            ]
        ),
    )

    result = await revise_posting(llm, posting(), "", "자격 요건 항목을 고쳐 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == [
        "Java와 Spring Boot를 활용한 서버 개발 경험",
        "AWS에서 서비스를 운영한 경험",
        "Java 17 이상, Kafka 로그 수집 경험",
        "REST API 기반 설계 능력",
    ]


async def test_revise_says_nothing_changed_when_content_step_changes_nothing() -> None:
    llm = FakeLlm(route("CONTENT"), content(career=CONTENT.career))

    result = await revise_posting(llm, posting(), "", "경력 그대로")

    assert result.suggestion is None
    assert result.reply == NOTHING_CHANGED_REPLY


# 전형 절차


async def test_revise_changes_stages_in_spoken_order() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT, CODING, StageEdit(name="1 차 면접", type=StageType.INTERVIEW)))

    result = await revise_posting(llm, posting(), "", "서류, 코딩테스트, 1차 면접 순으로 해 줘")

    assert result.suggestion is not None
    assert result.suggestion.stages == [DOCUMENT, CODING, INTERVIEW]
    assert result.suggestion.changed_fields == ["stages"]
    assert result.suggestion.content == CONTENT
    assert result.reply.startswith("전형 절차 수정안")
    assert llm.calls[1].output is StagePlan


async def test_revise_ignores_stages_returned_unchanged() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT))

    result = await revise_posting(llm, posting(), "", "전형은 서류만")

    assert result.suggestion is None
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_asks_back_when_model_leaves_a_stage_type_unknown() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT, StageEdit(name="워크숍", type=None)))

    result = await revise_posting(llm, posting(), "", "워크숍 전형 넣어 줘")

    assert result.suggestion is None
    assert result.reply.startswith("'워크숍'의 종류를 알 수 없어요.")
    assert result.reply.endswith(RETRY_HINT)


async def test_revise_asks_back_for_ambiguous_new_stage_even_if_model_guessed() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT, StageDraft(name="PT 발표", type=StageType.ASSESSMENT)))

    result = await revise_posting(llm, posting(), "", "서류 다음에 PT 발표 넣어 줘")

    assert result.suggestion is None
    assert result.reply.startswith("'PT 발표'의 종류를 알 수 없어요.")


async def test_revise_accepts_ambiguous_stage_when_retried_with_its_type() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT, StageDraft(name="PT 발표 전형", type=StageType.ASSESSMENT)))

    result = await revise_posting(llm, posting(), "", "서류 다음에 PT 발표 전형을 평가로 넣어 줘")

    assert result.suggestion is not None
    assert result.suggestion.stages == [DOCUMENT, StageDraft(name="PT 발표 전형", type=StageType.ASSESSMENT)]


async def test_revise_explains_how_to_answer_when_only_a_type_word_comes() -> None:
    for answer in ("평가", "면접 전형이요", "서류입니다."):
        llm = FakeLlm()

        result = await revise_posting(llm, posting(), "", answer)

        assert result.suggestion is None
        assert result.reply == ANSWER_ONLY_REPLY
        assert llm.calls == []


async def test_revise_accepts_ambiguous_stage_when_request_names_its_type() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT, StageDraft(name="PT 발표", type=StageType.INTERVIEW)))

    result = await revise_posting(llm, posting(), "", "서류 다음에 PT 발표를 면접 전형으로 넣어 줘")

    assert result.suggestion is not None
    assert result.suggestion.stages == [DOCUMENT, StageDraft(name="PT 발표", type=StageType.INTERVIEW)]


async def test_revise_does_not_ask_about_ambiguous_stage_already_in_posting() -> None:
    pt = StageDraft(name="PT 발표", type=StageType.INTERVIEW)
    llm = FakeLlm(route("STAGES"), plan(pt, DOCUMENT))

    result = await revise_posting(llm, posting(stages=[DOCUMENT, pt]), "", "PT 발표를 맨 앞으로 옮겨 줘")

    assert result.suggestion is not None
    assert result.suggestion.stages == [pt, DOCUMENT]


# 필수 제출 서류


async def test_revise_adds_only_extras_named_in_request() -> None:
    llm = FakeLlm(route("REQUIRED_EXTRAS"), extras("PORTFOLIO", "CERTIFICATE"))

    result = await revise_posting(llm, posting(required_extras=[]), "", "포트폴리오도 필수로 받아 줘")

    assert result.suggestion is not None
    assert result.suggestion.required_extras == [DocumentType.PORTFOLIO]
    assert result.suggestion.changed_fields == ["requiredDocuments"]
    assert result.reply.startswith("필수 제출 서류 수정안")


async def test_revise_removes_extras_named_in_request() -> None:
    llm = FakeLlm(route("REQUIRED_EXTRAS"), extras())

    result = await revise_posting(llm, posting(), "", "포트폴리오는 필수에서 빼 줘")

    assert result.suggestion is not None
    assert result.suggestion.required_extras == []


async def test_revise_keeps_extras_not_named_in_request() -> None:
    llm = FakeLlm(route("REQUIRED_EXTRAS"), extras("CERTIFICATE"))

    result = await revise_posting(llm, posting(), "", "자격증도 필수로")

    assert result.suggestion is not None
    assert result.suggestion.required_extras == [DocumentType.CERTIFICATE, DocumentType.PORTFOLIO]


# 게시 후 잠금


async def test_revise_after_publishing_skips_process_steps_and_keeps_content() -> None:
    llm = FakeLlm(route("CONTENT", "STAGES"), content(preferred=["대용량 트래픽 경험"]))

    result = await revise_posting(
        llm, posting(status=RecruitmentStatus.PUBLISHED), "", "우대 사항 고치고 1차 면접 추가"
    )

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["preferred"]
    assert result.reply.endswith(LOCKED_REPLY)
    assert [call.output for call in llm.calls] == [Route, ContentChanges]


async def test_revise_after_publishing_refuses_only_process_changes_without_more_calls() -> None:
    llm = FakeLlm(route("REQUIRED_EXTRAS"))

    result = await revise_posting(llm, posting(status=RecruitmentStatus.IN_PROGRESS), "", "자격증 필수로")

    assert result.suggestion is None
    assert result.reply == LOCKED_REPLY
    assert len(llm.calls) == 1


# 차별 조건과 결과 검사


async def test_revise_refuses_discriminatory_request_without_calling_model() -> None:
    llm = FakeLlm()

    result = await revise_posting(llm, posting(), "", "우대 사항에 20대 여성 우대 넣어 줘")

    assert result.reply == BLOCKED_REPLY
    assert llm.calls == []


async def test_revise_refuses_discriminatory_output_without_retry() -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["금융 도메인 경험", "30세 이하 지원자"]))

    result = await revise_posting(llm, posting(), "", "우대 사항 다듬어 줘")

    assert result.suggestion is None
    assert result.reply == BLOCKED_REPLY
    assert len(llm.calls) == 2


async def test_revise_allows_region_and_children_words_in_other_requests() -> None:
    llm = FakeLlm(route("CONTENT"), content(location="경기 지역 (판교)", benefits=["유연 근무", "자녀 학자금 지원"]))

    result = await revise_posting(llm, posting(), "", "근무 지역 판교, 복지에 자녀 학자금 추가")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["location", "benefits"]


async def test_revise_retries_the_writing_steps_once_with_reasons() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(benefits=["유연 근무", "연봉 6000만원 보장"]),
        content(benefits=["유연 근무", "성과급"]),
    )

    result = await revise_posting(llm, posting(), "", "복지에 성과급 추가해 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.benefits == ["유연 근무", "성과급"]
    assert len(llm.calls) == 3
    assert "복지에 주어진 정보에 없는 금액을 썼다: 6000만원" in llm.calls[2].user
    assert llm.calls[2].user.endswith(CONTENT_STEP + "\n이번에 반영할 HR 요청: 복지에 성과급 추가해 줘")


async def test_revise_gives_up_after_one_retry() -> None:
    long_title = "가" * 201
    llm = FakeLlm(route("CONTENT"), content(title=long_title), content(title=long_title))

    result = await revise_posting(llm, posting(), "", "채용명 길게")

    assert result.suggestion is None
    assert result.reply == CHECK_FAILED_REPLY
    assert len(llm.calls) == 3


async def test_revise_accepts_money_given_in_request() -> None:
    llm = FakeLlm(route("CONTENT"), content(benefits=["유연 근무", "식대 월 20만 원 지원"]))

    result = await revise_posting(llm, posting(), "", "복지에 식대 월 20만원 지원 넣어 줘")

    assert result.suggestion is not None
    assert len(llm.calls) == 2


# 자격 요건 · 우대 사항 쓰기


EMPTY_LISTS = CONTENT.model_copy(update={"qualifications": [], "preferred": []})


async def test_revise_writes_whole_lists_as_content() -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["대용량 트래픽 처리 경험", "결제 도메인 경험", "AWS 운영 경험"]))

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", "우대 사항만 3개 써 줘")

    assert [call.output for call in llm.calls] == [Route, ContentChanges]
    assert result.suggestion is not None
    assert result.suggestion.content.preferred == ["대용량 트래픽 처리 경험", "결제 도메인 경험", "AWS 운영 경험"]


@pytest.mark.parametrize(
    "request_text", ["우대 사항에 AWS 경험 하나 추가해 줘", "우대 사항 두 번째 항목을 고쳐 줘", "근무지 성남"]
)
async def test_revise_keeps_item_edits_as_content(request_text: str) -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["금융 도메인 경험", "AWS 경험"]))

    await revise_posting(llm, posting(), "", request_text)

    assert [call.output for call in llm.calls] == [Route, ContentChanges]


# 공고 전체 쓰기와 회사 정보


BROAD = "백엔드 개발자 경력 3년 이상 5명 채용하려고 해."


async def test_revise_fills_empty_lists_when_asked_to_write_the_whole_posting() -> None:
    llm = FakeLlm(
        route("CONTENT", writes_posting=True),
        content(duties=["결제 API 개발"], qualifications=["서버 개발 경험"], preferred=["결제 도메인 경험"]),
    )

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", BROAD)

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["salary", "duties", "qualifications", "preferred"]
    step = llm.calls[1].user
    assert "자격 요건, 우대 사항 칸이 비어 있다" in step
    assert "회사가 정하지 않은 필수 자격증 · 경력 연수" in step
    assert len(llm.calls) == 2


async def test_revise_names_only_the_empty_list_for_a_whole_posting_request() -> None:
    llm = FakeLlm(route("CONTENT", writes_posting=True), content(preferred=["결제 도메인 경험"]))
    only_preferred_empty = CONTENT.model_copy(update={"preferred": []})

    result = await revise_posting(llm, posting(content=only_preferred_empty), "", BROAD)

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == CONTENT.qualifications
    assert "공고 전체 작성 요청이다. 우대 사항 칸이 비어 있다." in llm.calls[1].user


async def test_revise_adds_content_step_for_a_whole_posting_with_empty_lists() -> None:
    llm = FakeLlm(
        route(writes_posting=True), content(qualifications=["서버 개발 경험"], preferred=["결제 도메인 경험"])
    )

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", BROAD)

    assert [call.output for call in llm.calls] == [Route, ContentChanges]
    assert result.suggestion is not None


async def test_revise_does_not_rewrite_filled_lists_for_a_whole_posting_request() -> None:
    llm = FakeLlm(route("CONTENT", writes_posting=True), content(career="경력 3년 이상"))

    result = await revise_posting(llm, posting(), "", BROAD)

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == CONTENT.qualifications
    assert result.suggestion.changed_fields == ["salary"]
    assert len(llm.calls) == 2


async def test_revise_fills_only_the_salary_and_lists_fields_left_for_hr() -> None:
    """누구를 어떻게 뽑을지는 회사만 알아 비워 두고, 급여만 거짓이 되지 않는 문구로 채운다."""
    blank = CONTENT.model_copy(update={"employment_type": "", "career": ""})
    llm = FakeLlm(route("CONTENT", writes_posting=True), content(title="결제 플랫폼 백엔드 개발자 채용"))

    result = await revise_posting(llm, posting(content=blank), "", "백엔드 개발자 공고 작성해 줘")

    assert result.suggestion is not None
    filled = result.suggestion.content
    assert (filled.employment_type, filled.career, filled.education, filled.work_hours) == ("", "", "", "")
    assert filled.salary == "회사 내규에 따름"
    assert "급여 칸은 기본 문구로 채웠어요. 회사에 맞게 확인해 주세요." in result.reply
    # 안내는 한 줄에 하나씩 보인다
    lines = result.reply.split("\n")
    assert "급여 칸은 기본 문구로 채웠어요. 회사에 맞게 확인해 주세요." in lines
    assert "고용 형태, 경력 구분, 채용 인원, 학력, 근무 요일 · 시간 칸은 정해 주세요." in lines


async def test_revise_keeps_the_salary_hr_wrote_for_a_whole_posting_request() -> None:
    written = CONTENT.model_copy(update={"salary": "연봉 4,000만 원 이상"})
    llm = FakeLlm(route("CONTENT", writes_posting=True), content(title="결제 플랫폼 백엔드 개발자 채용"))

    result = await revise_posting(llm, posting(content=written), "", "백엔드 개발자 공고 작성해 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.salary == "연봉 4,000만 원 이상"
    assert "기본 문구" not in result.reply


async def test_revise_writes_one_job_as_the_posting_body_even_if_routed_to_roles() -> None:
    one_role = PostingRole(name="백엔드 개발자", career="", duties=["API 개발"], qualifications=[], preferred=[])
    llm = FakeLlm(
        route("CONTENT", "ROLES", writes_posting=True),
        RoleChanges(roles=[one_role]),
        content(
            title="백엔드 개발자 채용",
            duties=["결제 API 개발"],
            qualifications=["서버 개발 경험"],
            preferred=["결제 도메인 경험"],
        ),
    )

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", "백엔드 개발자 채용 공고 작성해줘")

    assert result.suggestion is not None
    assert result.suggestion.content.roles == []
    assert "roles" not in result.suggestion.changed_fields
    assert {"qualifications", "preferred", "salary"} <= set(result.suggestion.changed_fields)


async def test_revise_keeps_blank_fields_when_hr_asks_to_change_some_fields() -> None:
    llm = FakeLlm(route("CONTENT"), content(title="결제 플랫폼 백엔드 개발자 채용"))

    result = await revise_posting(llm, posting(), "", "채용명 바꿔 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["title"]
    assert result.suggestion.content.education == ""


async def test_revise_ignores_stages_the_request_did_not_mention() -> None:
    llm = FakeLlm(route("CONTENT", "STAGES"), content(career="신입"))

    result = await revise_posting(llm, posting(), "", "신입 3명 채용하려고 해")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["career"]
    assert len(llm.calls) == 2


async def test_revise_drops_company_facts_the_request_did_not_give() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(
            benefits=["유연 근무", "점심 식대 지원"],
            intro="하루 수백만 건의 결제를 처리하는 회사입니다.",
            salary="연봉 협의",
            work_hours="주 5일 09:00~18:00",
            headcount="5",
            career="경력 3년 이상",
        ),
    )

    result = await revise_posting(llm, posting(), "", BROAD)

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["headcount"]
    assert result.suggestion.content.headcount == 5
    assert result.suggestion.content.benefits == CONTENT.benefits


async def test_revise_does_not_invent_career_or_employment_type() -> None:
    blank = CONTENT.model_copy(update={"career": "", "employment_type": ""})
    llm = FakeLlm(route("CONTENT"), content(title="백엔드 개발자", career="경력 3년 이상", employment_type="정규직"))

    result = await revise_posting(llm, posting(content=blank), "", "백엔드 개발자 채용 공고 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["title"]
    assert result.suggestion.content.career == ""
    assert result.suggestion.content.employment_type == ""


@pytest.mark.parametrize(
    ("request_text", "changed"),
    [
        ("신입 정규직으로 바꿔 줘", ["employmentType", "career"]),
        ("경력 무관, 계약직으로 해 줘", ["employmentType", "career"]),
        ("5년 차 이상 인턴으로 뽑을게", ["employmentType", "career"]),
    ],
)
async def test_revise_changes_career_and_employment_type_the_request_names(
    request_text: str, changed: list[str]
) -> None:
    llm = FakeLlm(route("CONTENT"), content(career="신입", employment_type="계약직"))

    result = await revise_posting(llm, posting(), "", request_text)

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == changed


async def test_revise_changes_company_facts_the_request_names() -> None:
    llm = FakeLlm(route("CONTENT"), content(salary="회사 내규에 따름", position="사원~대리", education="학력 무관"))

    result = await revise_posting(
        llm, posting(), "", "급여는 회사 내규에 따름, 직급은 사원~대리, 학력 무관으로 넣어 줘"
    )

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["position", "education", "salary"]


@pytest.mark.parametrize(("text", "count"), [("3", 3), ("3명", 3), ("세 명", 3), ("0", None), ("많이", None)])
async def test_revise_reads_headcount_as_a_number(text: str, count: int | None) -> None:
    llm = FakeLlm(route("CONTENT"), content(headcount=text))

    result = await revise_posting(llm, posting(), "", "채용 인원 바꿔 줘")

    assert (result.suggestion.content.headcount if result.suggestion else None) == count


async def test_context_shows_recruitment_conditions() -> None:
    llm = FakeLlm(route())
    conditions = CONTENT.model_copy(update={"headcount": 2, "education": "학력 무관"})

    await revise_posting(llm, posting(content=conditions), "", "음")

    user = llm.calls[0].user
    assert (
        "채용 인원: 2명\n직급: (비어 있음)\n학력: 학력 무관\n근무 요일 · 시간: (비어 있음)\n급여: (비어 있음)" in user
    )


# 고른 줄


def focus(field: Any, index: int | None = None) -> PostingFocus:
    return PostingFocus(field=field, index=index)


def rewrite(text: str | None) -> LineEdit:
    return LineEdit(action="REWRITE", text=text)


TWO_PREFERRED = CONTENT.model_copy(update={"preferred": ["금융 도메인 경험", "대용량 트래픽 처리 경험"]})


async def test_revise_line_changes_only_the_picked_line_in_one_call() -> None:
    llm = FakeLlm(rewrite("카드 결제 · 정산 시스템 개발 경험"))

    result = await revise_posting(
        llm, posting(content=TWO_PREFERRED), "", "결제 쪽으로 구체적으로", focus("preferred", 0)
    )

    assert result.suggestion is not None
    assert result.suggestion.content == TWO_PREFERRED.model_copy(
        update={"preferred": ["카드 결제 · 정산 시스템 개발 경험", "대용량 트래픽 처리 경험"]}
    )
    assert result.suggestion.changed_fields == ["preferred"]
    assert result.suggestion.stages is None
    assert result.reply == "우대 사항 1번 줄 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요."
    (call,) = llm.calls
    assert call.output is LineEdit
    assert call.system == SYSTEM
    assert "HR 요청: 결제 쪽으로 구체적으로" in call.user
    assert call.user.endswith(
        '지금 할 일: HR이 고른 우대 사항 1번 줄("금융 도메인 경험")을 다룬다. '
        "먼저 HR 요청이 이 줄을 지우라는 것인지 본다. 지우라는 요청이면 action을 DELETE로, text를 null로 둔다. "
        "아니면 action을 REWRITE로 두고 이 줄만 요청대로 고친 한 줄을 text에 쓴다. 칸 이름이나 다른 줄은 쓰지 않는다."
    )


async def test_revise_line_removes_the_line_when_model_chooses_delete() -> None:
    llm = FakeLlm(LineEdit(action="DELETE", text=None))

    result = await revise_posting(llm, posting(content=TWO_PREFERRED), "", "이 줄 지워 줘", focus("preferred", 1))

    assert result.suggestion is not None
    assert result.suggestion.content.preferred == ["금융 도메인 경험"]
    assert result.reply == "우대 사항 2번 줄을 지운 수정안을 만들었어요. 확인하고 적용해 주세요."


async def test_revise_line_tidies_bullets_and_spacing() -> None:
    llm = FakeLlm(rewrite("- 연 1 회 워크숍"))

    result = await revise_posting(llm, posting(), "", "워크숍으로 바꿔 줘", focus("benefits", 0))

    assert result.suggestion is not None
    assert result.suggestion.content.benefits == ["연 1회 워크숍"]


async def test_revise_line_retries_when_model_writes_the_list_in_one_line() -> None:
    llm = FakeLlm(rewrite("복지:\n- 유연 근무"), rewrite("식대 지원"))

    result = await revise_posting(llm, posting(), "", "식대 지원으로 바꿔 줘", focus("benefits", 0))

    assert result.suggestion is not None
    assert result.suggestion.content.benefits == ["식대 지원"]
    assert MULTILINE_LINE in llm.calls[1].user


async def test_revise_line_rewrites_intro_as_a_whole() -> None:
    llm = FakeLlm(IntroEdit(text="카드 결제와 정산 플랫폼을 운영하는 회사입니다."))

    result = await revise_posting(llm, posting(), "", "더 짧게", focus("intro"))

    assert result.suggestion is not None
    assert result.suggestion.content.intro == "카드 결제와 정산 플랫폼을 운영하는 회사입니다."
    assert result.suggestion.changed_fields == ["intro"]
    assert result.reply == "회사 소개 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요."
    assert llm.calls[0].output is IntroEdit
    assert llm.calls[0].user.endswith(
        f'지금 할 일: HR이 고른 회사 소개("{CONTENT.intro}")만 요청대로 고쳐 text에 쓴다. 다른 칸은 쓰지 않는다.'
    )


async def test_revise_line_asks_again_when_model_returns_the_line_unchanged() -> None:
    llm = FakeLlm(IntroEdit(text=CONTENT.intro), IntroEdit(text="결제 플랫폼 회사입니다."))

    result = await revise_posting(llm, posting(), "", "더 짧게", focus("intro"))

    assert result.suggestion is not None
    assert result.suggestion.content.intro == "결제 플랫폼 회사입니다."
    assert UNCHANGED_LINE in llm.calls[1].user


async def test_revise_line_does_not_clear_intro() -> None:
    llm = FakeLlm(IntroEdit(text=" "), IntroEdit(text=""))

    result = await revise_posting(llm, posting(), "", "지워 줘", focus("intro"))

    assert result.suggestion is None
    assert result.reply == LINE_UNCHANGED_REPLY


async def test_revise_line_says_nothing_changed_when_line_stays_the_same_twice() -> None:
    llm = FakeLlm(rewrite("금융 도메인 경험"), rewrite("금융 도메인 경험"))

    result = await revise_posting(llm, posting(), "", "괜찮은지 봐 줘", focus("preferred", 0))

    assert result.suggestion is None
    assert result.reply == LINE_UNCHANGED_REPLY
    assert len(llm.calls) == 2


@pytest.mark.parametrize("picked", [focus("preferred", 1), focus("preferred", -1), focus("duties")])
async def test_revise_line_reports_a_line_not_in_posting_without_calling_model(picked: PostingFocus) -> None:
    llm = FakeLlm()

    result = await revise_posting(llm, posting(), "", "고쳐 줘", picked)

    assert result.reply == FOCUS_MISSING_REPLY
    assert llm.calls == []


async def test_revise_line_refuses_discriminatory_request_on_requirements_without_calling_model() -> None:
    llm = FakeLlm()

    result = await revise_posting(llm, posting(), "", "20대 여성으로 바꿔 줘", focus("qualifications", 0))

    assert result.reply == BLOCKED_REPLY
    assert llm.calls == []


async def test_revise_line_refuses_discriminatory_output_without_retry() -> None:
    llm = FakeLlm(rewrite("30세 이하 지원자"))

    result = await revise_posting(llm, posting(), "", "다듬어 줘", focus("preferred", 0))

    assert result.suggestion is None
    assert result.reply == BLOCKED_REPLY
    assert len(llm.calls) == 1


async def test_revise_line_retries_once_with_reasons() -> None:
    llm = FakeLlm(rewrite("연봉 6000만원 보장"), rewrite("성과급"))

    result = await revise_posting(llm, posting(), "", "성과급으로 바꿔 줘", focus("benefits", 0))

    assert result.suggestion is not None
    assert result.suggestion.content.benefits == ["성과급"]
    assert len(llm.calls) == 2
    assert "복지에 주어진 정보에 없는 금액을 썼다: 6000만원" in llm.calls[1].user


# 프롬프트


async def test_context_has_posting_process_style_and_request() -> None:
    llm = FakeLlm(route())

    await revise_posting(llm, posting(stages=[DOCUMENT, CODING]), "짧고 친근하게 쓴다", "우대 사항 다듬어 줘")

    user = llm.calls[0].user
    assert "채용명: 결제 플랫폼 백엔드 개발자" in user
    assert "우대 사항:\n- 금융 도메인 경험" in user
    assert "전형 절차:\n1. 서류 전형 (서류)\n2. 코딩테스트 (평가)" in user
    assert "필수 제출 서류: 이력서, 자기소개서, 포트폴리오" in user
    assert "공고 상태: 작성 중" in user
    assert "공고 작성 스타일: 짧고 친근하게 쓴다" in user
    assert "HR 요청: 우대 사항 다듬어 줘" in user


async def test_context_tells_model_when_process_is_locked_and_marks_empty_fields() -> None:
    llm = FakeLlm(route())
    empty = CONTENT.model_copy(update={"location": "", "benefits": []})

    await revise_posting(
        llm, posting(status=RecruitmentStatus.PUBLISHED, required_extras=[], content=empty), "  ", "근무지 넣어 줘"
    )

    user = llm.calls[0].user
    assert "공고 상태: 공고 게시 중 (게시한 뒤라 전형 절차와 필수 제출 서류는 바꿀 수 없다)" in user
    assert "필수 제출 서류: 이력서, 자기소개서\n" in user
    assert "근무지: (비어 있음)" in user
    assert "복지:\n(비어 있음)" in user
    assert "공고 작성 스타일: (없음)" in user


# NCS 참고

NCS_QUERY = NcsQuery(tasks=["서버 프로그램을 구현 한다"], units=[UNIT])
NEW_DUTY = "주문 · 결제 서버 프로그램 구현"
NCS_LINE = '주요 업무 2번 ← 응용SW엔지니어링 › 서버프로그램 구현 › 서버 프로그램 구현하기: "서버 프로그램을 구현 한다"'
MADE = "주요 업무 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요."


class Malformed(BaseModel):
    """모델이 형식에 맞지 않는 답을 냈을 때. FakeLlm이 다른 형식을 받으면 예외를 낸다."""


def cited(duty: str = NEW_DUTY, *, cite: bool = True, **fields: str | list[str]) -> CitedContentChanges:
    citations = [LineCitation(field="주요 업무", line=duty, sources=["S1"])] if cite else []
    changes = content(duties=[*CONTENT.duties, duty], **fields).changes
    return CitedContentChanges(changes=changes, citations=citations)


def review(*verdicts: str) -> SupportReview:
    return SupportReview(
        verdicts=[SupportVerdict.model_validate({"index": i, "verdict": v}) for i, v in enumerate(verdicts)]
    )


async def test_skip_makes_no_ncs_calls() -> None:
    ncs = FakeNcs()
    llm = FakeLlm(route("CONTENT"), content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "주요 업무에 주문 결제 서버 구현 추가해 줘", ncs=ncs)

    assert [call.output for call in llm.calls] == [Route, ContentChanges]
    assert ncs.searches == []
    assert result.reply == MADE


async def test_requested_call_order_and_reply() -> None:
    ncs = FakeNcs()
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, cited(), review("supports"))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 추가해 줘", ncs=ncs)

    assert [call.output for call in llm.calls] == [Route, NcsQuery, CitedContentChanges, SupportReview]
    assert ncs.searches == [("NCS 참고해서 주요 업무 추가해 줘", NCS_QUERY.tasks, [UNIT])]
    assert "[S1] 응용SW엔지니어링" in llm.calls[2].user
    assert SOURCES_STEP in llm.calls[2].user
    assert llm.calls[2].system == SYSTEM
    assert result.reply == f"{MADE}\n\n{NCS_HEADER}\n{NCS_LINE}"
    assert result.suggestion is not None
    assert result.suggestion.content.duties == [*CONTENT.duties, NEW_DUTY]
    assert "NCS" not in result.suggestion.content.model_dump_json()


async def test_helpful_without_results_has_no_notice() -> None:
    llm = FakeLlm(route("CONTENT", ncs="HELPFUL"), NCS_QUERY, content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "주요 업무 추천해 줘", ncs=FakeNcs(found=[]))

    assert [call.output for call in llm.calls] == [Route, NcsQuery, ContentChanges]
    assert result.reply == MADE


async def test_requested_without_results_notices() -> None:
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 써 줘", ncs=FakeNcs(found=[]))

    assert result.reply == f"{MADE}\n{NCS_NOT_FOUND}"


async def test_empty_ncs_table_skips_query_call() -> None:
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 써 줘", ncs=FakeNcs(unit_list=[]))

    assert [call.output for call in llm.calls] == [Route, ContentChanges]
    assert result.suggestion is not None
    assert result.reply == f"{MADE}\n{NCS_NOT_FOUND}"


async def test_embed_failure_keeps_revision() -> None:
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 써 줘", ncs=FakeNcs(unavailable=True))

    assert result.suggestion is not None
    assert result.reply == f"{MADE}\n{NCS_UNAVAILABLE}"


async def test_query_call_failure_keeps_revision() -> None:
    llm = FakeLlm(route("CONTENT", ncs="HELPFUL"), Malformed(), content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "주요 업무 추천해 줘", ncs=FakeNcs())

    assert result.suggestion is not None
    assert result.reply == MADE


async def test_retry_uses_last_attempt_citations() -> None:
    llm = FakeLlm(
        route("CONTENT", ncs="REQUESTED"),
        NCS_QUERY,
        cited("첫 번째 업무", title="가" * 201),
        cited(NEW_DUTY),
        review("supports"),
    )

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 추가해 줘", ncs=FakeNcs())

    assert llm.calls[3].output is CitedContentChanges
    assert SOURCES_STEP in llm.calls[3].user
    assert result.reply.endswith(NCS_LINE)
    assert "첫 번째 업무" not in result.reply


async def test_unrelated_source_removed_with_notice() -> None:
    llm = FakeLlm(route("CONTENT", ncs="HELPFUL"), NCS_QUERY, cited(), review("unrelated"))

    result = await revise_posting(llm, posting(), "", "주요 업무 추천해 줘", ncs=FakeNcs())

    assert result.reply == f"{MADE}\n{NCS_SOURCES_DROPPED}"


async def test_requested_with_every_source_removed_says_not_found_once() -> None:
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, cited(), review("unrelated"))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 추가해 줘", ncs=FakeNcs())

    assert result.reply == f"{MADE}\n{NCS_NOT_FOUND}"


async def test_requested_without_citations_says_not_found() -> None:
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, cited(cite=False))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 추가해 줘", ncs=FakeNcs())

    assert [call.output for call in llm.calls] == [Route, NcsQuery, CitedContentChanges]
    assert result.reply == f"{MADE}\n{NCS_NOT_FOUND}"


async def test_no_suggestion_reply_has_no_ncs_text() -> None:
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, cited(title="가" * 201), cited(title="가" * 201))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 채용명 길게", ncs=FakeNcs())

    assert result.reply == CHECK_FAILED_REPLY


async def test_focus_line_request_never_uses_ncs() -> None:
    ncs = FakeNcs()
    llm = FakeLlm(rewrite("카드 결제 · 정산 시스템 개발 경험"))

    await revise_posting(
        llm, posting(content=TWO_PREFERRED), "", "NCS 참고해서 고쳐 줘", focus("preferred", 0), ncs=ncs
    )

    assert [call.output for call in llm.calls] == [LineEdit]
    assert ncs.searches == []


async def test_roles_request_never_uses_ncs() -> None:
    ncs = FakeNcs()
    roles = [
        PostingRole(name=name, career="신입", duties=["기초 업무 수행"], qualifications=[], preferred=[])
        for name in ["백엔드", "인사"]
    ]
    llm = FakeLlm(route("ROLES", writes_posting=True, ncs="HELPFUL"), RoleChanges(roles=roles))

    result = await revise_posting(llm, posting(), "", "신입 백엔드, 인사 두 직무 표로 만들어 줘", ncs=ncs)

    assert result.suggestion is not None
    assert ncs.searches == []


async def test_each_posting_line_shows_one_source() -> None:
    sentences = ["서버 프로그램을 구현 한다", "서버 프로그램을 테스트 한다"]
    two = CitedContentChanges(
        changes=content(duties=[*CONTENT.duties, NEW_DUTY]).changes,
        citations=[LineCitation(field="주요 업무", line=NEW_DUTY, sources=["S1", "S2"])],
    )
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, two, review("supports", "supports"))

    result = await revise_posting(
        llm, posting(), "", "NCS 참고해서 주요 업무 추가해 줘", ncs=FakeNcs(found=[task(sentences=sentences)])
    )

    assert result.reply == f"{MADE}\n\n{NCS_HEADER}\n{NCS_LINE}"


@pytest.mark.parametrize(("use", "reply"), [("HELPFUL", MADE), ("REQUESTED", f"{MADE}\n{NCS_UNAVAILABLE}")])
async def test_ncs_db_failure_keeps_revision(use: NcsUse, reply: str) -> None:
    llm = FakeLlm(route("CONTENT", ncs=use), content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "주요 업무 추천해 줘", ncs=FakeNcs(units_unavailable=True))

    assert result.suggestion is not None
    assert result.reply == reply


async def test_slow_ncs_step_gives_up_and_keeps_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ncs_reference_timeout_seconds", 0.05)
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, content(duties=[*CONTENT.duties, NEW_DUTY]))

    result = await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 써 줘", ncs=FakeNcs(delay=5))

    assert result.suggestion is not None
    assert result.reply == f"{MADE}\n{NCS_UNAVAILABLE}"


# 처리 단계


class Steps:
    """revise_posting이 낸 단계 (문구, 깊이)."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, int]] = []

    def __call__(self, text: str, depth: int = 0) -> None:
        self.seen.append((text, depth))


async def test_plain_request_reports_checking_and_writing() -> None:
    steps = Steps()
    llm = FakeLlm(route("CONTENT"), content(location="경기 성남시"))

    await revise_posting(llm, posting(), "", "근무지 성남", report=steps)

    assert steps.seen == [(CHECKING_STEP, 0), (WRITING_STEP, 0)]


async def test_ncs_request_reports_search_and_source_check() -> None:
    steps = Steps()
    llm = FakeLlm(route("CONTENT", ncs="REQUESTED"), NCS_QUERY, cited(), review("supports"))

    await revise_posting(llm, posting(), "", "NCS 참고해서 주요 업무 추가해 줘", ncs=FakeNcs(), report=steps)

    assert steps.seen == [(CHECKING_STEP, 0), (NCS_STEP, 0), (WRITING_STEP, 0), (SOURCES_CHECK_STEP, 0)]


async def test_rewrite_after_check_failure_is_a_sub_step() -> None:
    steps = Steps()
    long_title = "가" * 201
    llm = FakeLlm(route("CONTENT"), content(title=long_title), content(title="결제 백엔드 개발자"))

    await revise_posting(llm, posting(), "", "채용명 바꿔 줘", report=steps)

    assert steps.seen == [(CHECKING_STEP, 0), (WRITING_STEP, 0), (REWRITING_STEP, 1)]


async def test_line_request_reports_one_step() -> None:
    steps = Steps()
    llm = FakeLlm(rewrite("카드 결제 · 정산 시스템 개발 경험"))

    await revise_posting(llm, posting(content=TWO_PREFERRED), "", "구체적으로", focus("preferred", 0), report=steps)

    assert steps.seen == [(LINE_STEP, 0)]


async def test_blocked_request_reports_nothing() -> None:
    steps = Steps()

    await revise_posting(FakeLlm(), posting(), "", "남성만 우대한다고 써 줘", report=steps)

    assert steps.seen == []


# 블라인드 채용


async def test_blind_posting_refuses_education_conditions_in_the_request() -> None:
    llm = FakeLlm()

    result = await revise_posting(
        llm, posting(content=CONTENT.model_copy(update={"blind": True})), "", "우대 사항에 석사 이상 우대 넣어 줘"
    )

    assert result.reply == BLIND_REPLY
    assert llm.calls == []


async def test_non_blind_posting_still_allows_education_conditions() -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["석사 이상 우대"]))

    result = await revise_posting(llm, posting(), "", "우대 사항에 석사 이상 우대 넣어 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.preferred == ["석사 이상 우대"]


async def test_blind_posting_drops_school_conditions_the_model_writes() -> None:
    llm = FakeLlm(route("CONTENT"), content(qualifications=["4년제 대학교 졸업자"]))

    result = await revise_posting(
        llm, posting(content=CONTENT.model_copy(update={"blind": True})), "", "자격 요건 한 줄 고쳐 줘"
    )

    assert result.reply == BLIND_REPLY
    assert result.suggestion is None


async def test_blind_posting_never_fills_education_and_tells_the_model() -> None:
    llm = FakeLlm(route("CONTENT", writes_posting=True), content(education="학력 무관", title="백엔드 개발자 채용"))

    result = await revise_posting(
        llm, posting(content=CONTENT.model_copy(update={"blind": True})), "", "백엔드 개발자 공고 작성해 줘"
    )

    assert result.suggestion is not None
    assert result.suggestion.content.education == ""
    assert "education" not in result.suggestion.changed_fields
    assert "학력" not in result.reply  # 학력 칸은 정해 달라고 하지 않는다
    assert BLIND_LINE in llm.calls[0].user
