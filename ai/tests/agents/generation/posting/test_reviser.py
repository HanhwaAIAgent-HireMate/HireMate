from typing import Any
from uuid import UUID

from hiremate_ai.agents.generation.posting.reviser import (
    BLOCKED_REPLY,
    CHECK_FAILED_REPLY,
    LOCKED_REPLY,
    NOTHING_CHANGED_REPLY,
    PostingEdit,
    StageEdit,
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


def stage(draft: StageDraft) -> StageEdit:
    return StageEdit(name=draft.name, type=draft.type)


# 공고 본문


async def test_revise_applies_only_edited_fields_and_marks_them() -> None:
    llm = FakeLlm(PostingEdit(preferred=["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"]))

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
    llm = FakeLlm(PostingEdit(title=CONTENT.title, duties=["결제 승인 · 정산 API 개발", "정산 배치 개선"]))

    result = await revise_posting(llm, posting(), "", "주요 업무에 정산 배치 개선 넣어 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["duties"]


async def test_revise_lists_changed_fields_in_screen_order() -> None:
    llm = FakeLlm(PostingEdit(preferred=["대용량 트래픽 경험"], employment_type="계약직"))

    result = await revise_posting(llm, posting(), "", "계약직으로 바꾸고 우대 사항도 고쳐 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["employmentType", "preferred"]
    assert result.reply.startswith("고용 형태, 우대 사항 수정안")


async def test_revise_trims_text_and_drops_empty_list_items() -> None:
    llm = FakeLlm(PostingEdit(location="  경기 성남시 ", benefits=[" 유연 근무 ", "", "  ", "식대 지원"]))

    result = await revise_posting(llm, posting(), "", "근무지 성남, 복지에 식대 지원 추가")

    assert result.suggestion is not None
    assert result.suggestion.content.location == "경기 성남시"
    assert result.suggestion.content.benefits == ["유연 근무", "식대 지원"]


async def test_revise_without_changes_says_nothing_changed() -> None:
    llm = FakeLlm(PostingEdit(career=CONTENT.career))

    result = await revise_posting(llm, posting(), "", "음")

    assert result.suggestion is None
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_asks_the_models_question_when_nothing_changes() -> None:
    llm = FakeLlm(PostingEdit(question="어느 칸을 고칠까요?"))

    result = await revise_posting(llm, posting(), "", "좀 더 좋게")

    assert result.suggestion is None
    assert result.reply == "어느 칸을 고칠까요?"


# 전형 절차


async def test_revise_changes_stages_in_spoken_order() -> None:
    llm = FakeLlm(PostingEdit(stages=[stage(DOCUMENT), stage(CODING), stage(INTERVIEW)]))

    result = await revise_posting(llm, posting(), "", "서류, 코딩테스트, 1차 면접 순으로 해 줘")

    assert result.suggestion is not None
    assert result.suggestion.stages == [DOCUMENT, CODING, INTERVIEW]
    assert result.suggestion.changed_fields == ["stages"]
    assert result.suggestion.content == CONTENT
    assert result.reply.startswith("전형 절차 수정안")


async def test_revise_ignores_stages_returned_unchanged() -> None:
    llm = FakeLlm(PostingEdit(stages=[stage(DOCUMENT)]))

    result = await revise_posting(llm, posting(), "", "전형은 서류만")

    assert result.suggestion is None
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_asks_back_when_a_stage_type_is_unknown() -> None:
    llm = FakeLlm(PostingEdit(stages=[stage(DOCUMENT), StageEdit(name="PT 발표", type=None)]))

    result = await revise_posting(llm, posting(), "", "서류 다음에 PT 발표 넣어 줘")

    assert result.suggestion is None
    assert result.reply == "'PT 발표' 전형은 서류, 평가, 면접 중 어떤 종류인가요?"
    assert len(llm.calls) == 1


async def test_revise_uses_the_models_question_for_unknown_stage_type() -> None:
    llm = FakeLlm(
        PostingEdit(stages=[StageEdit(name="워크숍", type=None)], question="워크숍은 평가인가요, 면접인가요?")
    )

    result = await revise_posting(llm, posting(), "", "워크숍 전형 넣어 줘")

    assert result.reply == "워크숍은 평가인가요, 면접인가요?"


# 필수 제출 서류


async def test_revise_changes_required_extras_sorted() -> None:
    llm = FakeLlm(PostingEdit(required_extras=["PORTFOLIO", "CERTIFICATE"]))

    result = await revise_posting(llm, posting(), "", "자격증도 필수로 받아 줘")

    assert result.suggestion is not None
    assert result.suggestion.required_extras == [DocumentType.CERTIFICATE, DocumentType.PORTFOLIO]
    assert result.suggestion.changed_fields == ["requiredDocuments"]
    assert result.reply.startswith("필수 제출 서류 수정안")


async def test_revise_can_remove_all_required_extras() -> None:
    llm = FakeLlm(PostingEdit(required_extras=[]))

    result = await revise_posting(llm, posting(), "", "포트폴리오는 필수에서 빼 줘")

    assert result.suggestion is not None
    assert result.suggestion.required_extras == []


async def test_revise_ignores_required_extras_returned_unchanged() -> None:
    llm = FakeLlm(PostingEdit(required_extras=["PORTFOLIO"]))

    result = await revise_posting(llm, posting(), "", "포트폴리오 필수로")

    assert result.suggestion is None


# 게시 후 잠금


async def test_revise_after_publishing_keeps_content_and_drops_process_changes() -> None:
    llm = FakeLlm(PostingEdit(preferred=["대용량 트래픽 경험"], stages=[stage(DOCUMENT), stage(INTERVIEW)]))

    result = await revise_posting(
        llm, posting(status=RecruitmentStatus.PUBLISHED), "", "우대 사항 고치고 1차 면접 추가"
    )

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["preferred"]
    assert result.suggestion.stages is None
    assert result.reply.endswith(LOCKED_REPLY)


async def test_revise_after_publishing_refuses_only_process_changes() -> None:
    llm = FakeLlm(PostingEdit(required_extras=["CERTIFICATE"]))

    result = await revise_posting(llm, posting(status=RecruitmentStatus.IN_PROGRESS), "", "자격증 필수로")

    assert result.suggestion is None
    assert result.reply == LOCKED_REPLY


# 결과 검사


async def test_revise_refuses_discriminatory_preferences_without_retry() -> None:
    llm = FakeLlm(PostingEdit(preferred=["금융 도메인 경험", "20대 여성 우대"]))

    result = await revise_posting(llm, posting(), "", "우대 사항에 20대 여성 넣어 줘")

    assert result.suggestion is None
    assert result.reply == BLOCKED_REPLY
    assert len(llm.calls) == 1


async def test_revise_allows_region_words_outside_judged_fields() -> None:
    llm = FakeLlm(PostingEdit(location="경기 지역 (판교)", benefits=["유연 근무", "자녀 학자금 지원"]))

    result = await revise_posting(llm, posting(), "", "근무 지역 판교, 복지에 자녀 학자금 추가")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["location", "benefits"]


async def test_revise_retries_once_with_reasons_then_succeeds() -> None:
    llm = FakeLlm(
        PostingEdit(benefits=["유연 근무", "연봉 6000만원 보장"]),
        PostingEdit(benefits=["유연 근무", "성과급"]),
    )

    result = await revise_posting(llm, posting(), "", "복지에 성과급 추가해 줘")

    assert result.suggestion is not None
    assert result.suggestion.content.benefits == ["유연 근무", "성과급"]
    assert len(llm.calls) == 2
    assert "복지에 주어진 정보에 없는 금액을 썼다: 6000만원" in llm.calls[1].user
    assert llm.calls[1].user.startswith(llm.calls[0].user)


async def test_revise_gives_up_after_one_retry() -> None:
    long_title = "가" * 201
    llm = FakeLlm(PostingEdit(title=long_title), PostingEdit(title=long_title))

    result = await revise_posting(llm, posting(), "", "채용명 길게")

    assert result.suggestion is None
    assert result.reply == CHECK_FAILED_REPLY
    assert len(llm.calls) == 2


async def test_revise_accepts_money_given_in_request() -> None:
    llm = FakeLlm(PostingEdit(benefits=["유연 근무", "식대 월 20만 원 지원"]))

    result = await revise_posting(llm, posting(), "", "복지에 식대 월 20만원 지원 넣어 줘")

    assert result.suggestion is not None
    assert len(llm.calls) == 1


# 프롬프트


async def test_revise_sends_posting_process_style_and_request_to_model() -> None:
    llm = FakeLlm(PostingEdit())

    await revise_posting(llm, posting(stages=[DOCUMENT, CODING]), "짧고 친근하게 쓴다", "우대 사항 다듬어 줘")

    call = llm.calls[0]
    assert call.agent == "posting"
    assert call.output is PostingEdit
    assert "채용명: 결제 플랫폼 백엔드 개발자" in call.user
    assert "우대 사항:\n- 금융 도메인 경험" in call.user
    assert "전형 절차:\n1. 서류 전형 (서류)\n2. 코딩테스트 (평가)" in call.user
    assert "필수 제출 서류: 이력서, 자기소개서, 포트폴리오" in call.user
    assert "공고 상태: 작성 중" in call.user
    assert "공고 작성 스타일: 짧고 친근하게 쓴다" in call.user
    assert "HR 요청: 우대 사항 다듬어 줘" in call.user


async def test_revise_tells_model_when_process_is_locked() -> None:
    llm = FakeLlm(PostingEdit())

    await revise_posting(llm, posting(status=RecruitmentStatus.PUBLISHED, required_extras=[]), "  ", "근무지 넣어 줘")

    user = llm.calls[0].user
    assert "공고 상태: 공고 게시 중 (게시한 뒤라 전형 절차와 필수 제출 서류는 바꿀 수 없다)" in user
    assert "필수 제출 서류: 이력서, 자기소개서\n" in user
    assert "공고 작성 스타일: (없음)" in user


async def test_revise_marks_empty_fields_in_prompt() -> None:
    llm = FakeLlm(PostingEdit())
    empty = CONTENT.model_copy(update={"location": "", "benefits": []})

    await revise_posting(llm, posting(content=empty), "", "근무지 넣어 줘")

    user = llm.calls[0].user
    assert "근무지: (비어 있음)" in user
    assert "복지:\n(비어 있음)" in user
