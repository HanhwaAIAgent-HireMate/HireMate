from typing import Any
from uuid import UUID

import pytest

from hiremate_ai.agents.generation.posting.reviser import (
    ANSWER_ONLY_REPLY,
    BLOCKED_REPLY,
    CHECK_FAILED_REPLY,
    CONTENT_STEP,
    DEFAULT_ITEMS,
    FIELD_LABELS,
    LOCKED_REPLY,
    MAX_DRAFT_ITEMS,
    MAX_NCS_UNITS,
    NCS_DETAIL_CHARS,
    NCS_SYSTEM,
    NOTHING_CHANGED_REPLY,
    RETRY_HINT,
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
from hiremate_ai.tools.ncs import ncs_data, unit_by_code

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

    result = await revise_posting(llm, posting(), "", "NCS 기반으로 자격 요건 2개와 우대 사항 1개 써 줘")

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


async def test_revise_shows_performance_criteria_of_a_single_picked_unit_in_full() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=[SERVER]), ncs_draft([]))

    await revise_posting(llm, posting(), "", "자격 요건 새로 써 줘")

    unit = unit_by_code(SERVER)
    assert unit is not None
    write = llm.calls[2].user
    assert all(f"  · {criterion}" in write for element in unit.elements for criterion in element.criteria)
    assert unit.elements[0].knowledge[0] not in write


async def test_revise_keeps_ncs_detail_within_budget_and_spreads_it_over_elements() -> None:
    codes = [unit.code for unit in ncs_data().units][: MAX_NCS_UNITS - 1] + [SERVER]
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=codes), ncs_draft([]))

    await revise_posting(llm, posting(), "", "자격 요건 새로 써 줘")

    write = llm.calls[2].user
    detail = write.split("NCS 능력단위 (")[1].split("\n\nHR 요청")[0]
    assert len(detail) < NCS_DETAIL_CHARS * 1.3
    server = unit_by_code(SERVER)
    assert server is not None
    shown = [element.number for element in server.elements if f"  · {element.criteria[0]}" in write]
    assert shown == [1, 2, 3, 4]


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

    result = await revise_posting(llm, posting(), "", "NCS 기반으로 다시 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.preferred == CONTENT.preferred
    assert result.suggestion.changed_fields == ["qualifications"]


EMPTY_LISTS = CONTENT.model_copy(update={"qualifications": [], "preferred": []})


def items(count: int) -> list[SourcedItem]:
    return [SourcedItem(text=f"서버 프로그램 구현 경험 {number}", sources=[SERVER]) for number in range(1, count + 1)]


@pytest.mark.parametrize(
    ("current", "request_text", "task"),
    [
        (EMPTY_LISTS, "NCS 기반으로 자격 요건과 우대 사항 써 줘", "자격 요건 5개, 우대 사항 5개를 쓴다."),
        (CONTENT, "NCS 기반으로 다시 써 줘", "자격 요건 5개, 우대 사항 5개를 쓴다."),
        (EMPTY_LISTS, "자격 요건 3개, 우대 사항 4개로 써 줘", "자격 요건 3개, 우대 사항 4개를 쓴다."),
        (EMPTY_LISTS, "자격 요건과 우대 사항을 각각 세 개씩 써 줘", "자격 요건 3개, 우대 사항 3개를 쓴다."),
        (EMPTY_LISTS, "자격 요건은 7개로 써 줘", "자격 요건 7개, 우대 사항 5개를 쓴다."),
        (EMPTY_LISTS, "자격 요건 만들어 줘", "자격 요건 5개, 우대 사항 5개를 쓴다."),
        (CONTENT, "자격 요건은 7개로 써 줘", "자격 요건 7개를 쓴다. 우대 사항은 쓰지 않고 빈 목록으로 둔다."),
        (EMPTY_LISTS, "우대 사항만 써 줘", "우대 사항 5개를 쓴다. 자격 요건은 쓰지 않고 빈 목록으로 둔다."),
        (
            EMPTY_LISTS,
            "자격 요건은 그대로 두고 우대 사항 다섯 가지 써 줘",
            "우대 사항 5개를 쓴다. 자격 요건은 쓰지 않고 빈 목록으로 둔다.",
        ),
        (EMPTY_LISTS, "자격 요건 15개 써 줘", f"자격 요건 {MAX_DRAFT_ITEMS}개, 우대 사항 5개를 쓴다."),
    ],
)
async def test_revise_tells_ncs_writer_which_lists_to_write_and_how_many(
    current: PostingContent, request_text: str, task: str
) -> None:
    """말한 목록은 요청대로(개수가 없으면 5개), 말하지 않은 목록은 비어 있을 때만 쓴다."""
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=[SERVER]), ncs_draft([]))

    await revise_posting(llm, posting(content=current), "", request_text)

    assert llm.calls[2].user.endswith(f"HR 요청: {request_text}\n\n지금 할 일: {task}")


async def test_revise_writes_whole_list_with_ncs_even_if_routed_to_content() -> None:
    llm = FakeLlm(
        route("CONTENT"),
        content(preferred=["고용보험 가입 기간 1년 이상인 경우 우대"]),
        NcsPick(ncs_codes=[SERVER]),
        ncs_draft([], items(3)),
    )

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", "우대 사항만 3개 써 줘")

    assert [call.output for call in llm.calls] == [Route, ContentChanges, NcsPick, NcsDraft]
    assert result.suggestion is not None
    assert result.suggestion.content.preferred == [item.text for item in items(3)]


@pytest.mark.parametrize(
    "request_text", ["우대 사항에 AWS 경험 하나 추가해 줘", "우대 사항 두 번째 항목을 고쳐 줘", "근무지 성남"]
)
async def test_revise_keeps_item_edits_as_content(request_text: str) -> None:
    llm = FakeLlm(route("CONTENT"), content(preferred=["금융 도메인 경험", "AWS 경험"]))

    await revise_posting(llm, posting(), "", request_text)

    assert [call.output for call in llm.calls] == [Route, ContentChanges]


async def test_revise_skips_ncs_when_request_keeps_every_list() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"))

    result = await revise_posting(llm, posting(), "", "자격 요건은 그대로 둬")

    assert len(llm.calls) == 1
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_trims_ncs_lists_to_the_planned_count() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=[SERVER]), ncs_draft(items(7), items(6)))

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", "자격 요건과 우대 사항 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == [item.text for item in items(DEFAULT_ITEMS)]
    assert len(result.suggestion.content.preferred) == DEFAULT_ITEMS
    assert "만 썼어요" not in result.reply


async def test_revise_ignores_lists_it_was_not_asked_to_write() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=[SERVER]), ncs_draft(items(5), items(5)))

    result = await revise_posting(llm, posting(content=EMPTY_LISTS), "", "우대 사항만 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == []
    assert result.suggestion.changed_fields == ["preferred"]


async def test_revise_tells_when_ncs_writer_writes_fewer_items() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=[SERVER]), ncs_draft(items(2)))

    result = await revise_posting(llm, posting(), "", "자격 요건 3개 써 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.qualifications == [item.text for item in items(2)]
    assert result.reply == (
        "자격 요건 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요. "
        "자격 요건은 3개 중 2개만 썼어요. 더 필요하면 다시 요청해 주세요. "
        "근거(NCS): 응용SW엔지니어링 · 서버프로그램 구현"
    )


async def test_revise_writes_at_most_the_limit_and_says_so() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=[SERVER]), ncs_draft(items(12)))

    result = await revise_posting(llm, posting(), "", "자격 요건 15개 써 줘")

    assert result.suggestion is not None
    assert len(result.suggestion.content.qualifications) == MAX_DRAFT_ITEMS
    assert f"자격 요건은 {MAX_DRAFT_ITEMS}개까지 써요." in result.reply
    assert "만 썼어요" not in result.reply


async def test_revise_skips_ncs_writer_when_no_known_unit_is_picked() -> None:
    llm = FakeLlm(route("NCS_REQUIREMENTS"), NcsPick(ncs_codes=["없는코드"]))

    result = await revise_posting(llm, posting(), "", "마케팅 자격 요건 써 줘")

    assert len(llm.calls) == 2
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_skips_ncs_when_request_does_not_mention_requirements() -> None:
    llm = FakeLlm(route("CONTENT", "NCS_REQUIREMENTS"), content(intro="결제 플랫폼을 함께 만들 분을 찾아요."))

    result = await revise_posting(llm, posting(), "", "회사 소개를 더 친근하게 바꿔 줘")

    assert [call.output for call in llm.calls] == [Route, ContentChanges]
    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["intro"]


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
