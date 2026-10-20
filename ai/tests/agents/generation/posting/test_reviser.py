from typing import Any
from uuid import UUID

from hiremate_ai.agents.generation.posting.ncs import ncs_data
from hiremate_ai.agents.generation.posting.reviser import (
    BLOCKED_REPLY,
    CHECK_FAILED_REPLY,
    CONTENT_STEP,
    FIELD_LABELS,
    LOCKED_REPLY,
    MAX_NCS_UNITS,
    NCS_SYSTEM,
    NOTHING_CHANGED_REPLY,
    ROUTE_STEP,
    SYSTEM,
    ContentChanges,
    ExtrasPlan,
    FieldChange,
    NcsDraft,
    NcsPick,
    Route,
    SourcedItem,
    StageEdit,
    StagePlan,
    revise_posting,
)
from hiremate_ai.agents.generation.posting.types import PostingDraftContext, RecruitmentStatus, StageDraft
from hiremate_ai.contract import DocumentType, PostingContent, StageType
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
SERVER = "2001020211_23v6"
"""응용SW엔지니어링 · 서버프로그램 구현"""
SQL = "2001020414_19v4"
"""DB엔지니어링 · SQL응용"""
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


def route(*targets: Any, question: str | None = None) -> Route:
    return Route(targets=list(targets), question=question)


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
    assert second.user.endswith(CONTENT_STEP)
    assert first.user.removesuffix(ROUTE_STEP) == second.user.removesuffix(CONTENT_STEP)


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


async def test_revise_tidies_text_bullets_and_number_spacing() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(
            location="  경기 성남시 ",
            career="경력 5 년 이상",
            benefits=["- 유연 근무", "", "  ", "2. 식대 지원", "• 연 1 회 건강검진"],
        ),
    )

    result = await revise_posting(llm, posting(), "", "근무지 성남, 경력 5년, 복지 추가")

    assert result.suggestion is not None
    assert result.suggestion.content.location == "경기 성남시"
    assert result.suggestion.content.career == "경력 5년 이상"
    assert result.suggestion.content.benefits == ["유연 근무", "식대 지원", "연 1회 건강검진"]


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
    assert result.reply == "'워크숍'의 종류를 알려 주세요. 서류, 평가, 면접 중 어떤 전형인가요?"


async def test_revise_asks_back_for_ambiguous_new_stage_even_if_model_guessed() -> None:
    llm = FakeLlm(route("STAGES"), plan(DOCUMENT, StageDraft(name="PT 발표", type=StageType.ASSESSMENT)))

    result = await revise_posting(llm, posting(), "", "서류 다음에 PT 발표 넣어 줘")

    assert result.suggestion is None
    assert result.reply == "'PT 발표'의 종류를 알려 주세요. 서류, 평가, 면접 중 어떤 전형인가요?"


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
    assert llm.calls[2].user.endswith(CONTENT_STEP)


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


# NCS 근거


def ncs_draft(qualifications: list[SourcedItem], preferred: list[SourcedItem] | None = None) -> NcsDraft:
    return NcsDraft(qualifications=qualifications, preferred=preferred or [])


async def test_revise_writes_requirements_from_picked_ncs_units_and_cites_them() -> None:
    llm = FakeLlm(
        route("NCS_REQUIREMENTS"),
        NcsPick(ncs_codes=[SERVER, SQL, "없는코드"]),
        ncs_draft(
            [
                SourcedItem(text="서버 프로그램과 배치 프로그램 구현 경험", sources=[SERVER]),
                SourcedItem(text="Java · Spring Boot 기반 서버 개발 경력 3년 이상", sources=[]),
            ],
            [SourcedItem(text="SQL로 응용 기능에 맞는 데이터 처리 경험", sources=[SQL, "보여주지않은코드"])],
        ),
    )

    result = await revise_posting(llm, posting(), "", "NCS 기반으로 자격 요건과 우대 사항 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == [
        "서버 프로그램과 배치 프로그램 구현 경험",
        "Java · Spring Boot 기반 서버 개발 경력 3년 이상",
    ]
    assert result.suggestion.content.preferred == ["SQL로 응용 기능에 맞는 데이터 처리 경험"]
    assert result.suggestion.changed_fields == ["qualifications", "preferred"]
    assert result.reply == (
        "자격 요건, 우대 사항 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요. "
        "근거(NCS): 응용SW엔지니어링 · 서버프로그램 구현, DB엔지니어링 · SQL응용"
    )


async def test_revise_accepts_ncs_codes_with_a_wrong_version() -> None:
    llm = FakeLlm(
        route("NCS_REQUIREMENTS"),
        NcsPick(ncs_codes=["2001020211_23v5"]),
        ncs_draft([SourcedItem(text="서버 프로그램 구현 경험", sources=["2001020211_19v1"])]),
    )

    result = await revise_posting(llm, posting(), "", "자격 요건 새로 써 줘")

    assert result.reply.endswith("근거(NCS): 응용SW엔지니어링 · 서버프로그램 구현")
    assert SERVER in llm.calls[2].user


async def test_revise_shows_only_picked_units_with_definitions_to_ncs_writer() -> None:
    llm = FakeLlm(
        route("NCS_REQUIREMENTS"),
        NcsPick(ncs_codes=[SERVER]),
        ncs_draft([SourcedItem(text="서버 프로그램 구현 경험", sources=[SERVER])]),
    )

    await revise_posting(llm, posting(), "", "자격 요건 새로 써 줘")

    pick, write = llm.calls[1], llm.calls[2]
    assert f"{SERVER} 서버프로그램 구현 (수준 5)" in pick.user
    assert "서버프로그램 구현이란" not in pick.user
    assert write.system == NCS_SYSTEM
    assert write.output is NcsDraft
    assert f"- {SERVER} 서버프로그램 구현 (수준 5): 서버프로그램 구현이란" in write.user
    assert SQL not in write.user
    assert "지금 우대 사항:\n- 금융 도메인 경험" in write.user
    assert "HR 요청: 자격 요건 새로 써 줘" in write.user


async def test_revise_lists_ncs_units_only_in_the_pick_step() -> None:
    llm = FakeLlm(route("CONTENT"), content(location="경기 성남시"))

    await revise_posting(llm, posting(), "", "근무지 성남")

    assert all(SERVER not in call.user for call in llm.calls)


async def test_revise_keeps_current_list_when_ncs_writer_leaves_it_empty() -> None:
    llm = FakeLlm(
        route("NCS_REQUIREMENTS"),
        NcsPick(ncs_codes=[SERVER]),
        ncs_draft([SourcedItem(text="서버 프로그램 구현 경험", sources=[SERVER])]),
    )

    result = await revise_posting(llm, posting(), "", "자격 요건만 NCS로 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.preferred == CONTENT.preferred
    assert result.suggestion.changed_fields == ["qualifications"]


async def test_revise_skips_ncs_writer_when_no_known_unit_is_picked() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=["없는코드"]))

    result = await revise_posting(llm, posting(), "", "마케팅 자격 요건 써 줘")

    assert len(llm.calls) == 2
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_limits_units_shown_to_ncs_writer() -> None:
    codes = [unit.code for unit in ncs_data().units][: MAX_NCS_UNITS + 3]
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=codes), ncs_draft([]))

    await revise_posting(llm, posting(), "", "자격 요건 새로 써 줘")

    shown = [code for code in codes if code in llm.calls[2].user]
    assert shown == codes[:MAX_NCS_UNITS]


async def test_revise_combines_content_changes_with_ncs_lists() -> None:
    llm = FakeLlm(
        route("CONTENT", "NCS_REQUIREMENTS"),
        content(location="경기 성남시", qualifications=["덮어써질 항목"]),
        NcsPick(ncs_codes=[SERVER]),
        ncs_draft([SourcedItem(text="서버 프로그램 구현 경험", sources=[SERVER])]),
    )

    result = await revise_posting(llm, posting(), "", "근무지 성남으로 하고 자격 요건은 NCS로 새로 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.location == "경기 성남시"
    assert result.suggestion.content.qualifications == ["서버 프로그램 구현 경험"]
    assert result.suggestion.changed_fields == ["location", "qualifications"]


async def test_revise_checks_ncs_written_lists_too() -> None:
    llm = FakeLlm(
        route("NCS_REQUIREMENTS"),
        NcsPick(ncs_codes=[SERVER]),
        ncs_draft([SourcedItem(text="30세 이하 서버 개발자", sources=[SERVER])]),
    )

    result = await revise_posting(llm, posting(), "", "자격 요건 써 줘")

    assert result.reply == BLOCKED_REPLY


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
