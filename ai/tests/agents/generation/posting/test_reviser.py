from typing import Any
from uuid import UUID

from hiremate_ai.agents.generation.posting.reviser import NOTHING_CHANGED_REPLY, ContentEdit, revise_posting
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


def posting(**overrides: Any) -> PostingDraftContext:
    fields: dict[str, Any] = {
        "recruitment_id": UUID("6f1c2b3a-4d5e-4f60-8a7b-9c0d1e2f3a4b"),
        "status": RecruitmentStatus.DRAFT,
        "content": CONTENT,
        "stages": [StageDraft(name="서류 전형", type=StageType.DOCUMENT)],
        "required_extras": [DocumentType.PORTFOLIO],
    }
    return PostingDraftContext(**{**fields, **overrides})


async def test_revise_applies_only_edited_fields_and_marks_them() -> None:
    llm = FakeLlm(ContentEdit(preferred=["금융 도메인 경험", "결제 · 정산 시스템 운영 경험"]))

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
    llm = FakeLlm(ContentEdit(title=CONTENT.title, duties=["결제 승인 · 정산 API 개발", "정산 배치 개선"]))

    result = await revise_posting(llm, posting(), "", "주요 업무에 정산 배치 개선 넣어 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["duties"]


async def test_revise_lists_changed_fields_in_screen_order() -> None:
    llm = FakeLlm(ContentEdit(preferred=["대용량 트래픽 경험"], employment_type="계약직"))

    result = await revise_posting(llm, posting(), "", "계약직으로 바꾸고 우대 사항도 고쳐 줘")

    assert result.suggestion is not None
    assert result.suggestion.changed_fields == ["employmentType", "preferred"]
    assert result.reply.startswith("고용 형태, 우대 사항 수정안")


async def test_revise_trims_text_and_drops_empty_list_items() -> None:
    llm = FakeLlm(ContentEdit(location="  경기 성남시 ", benefits=[" 유연 근무 ", "", "  ", "식대 지원"]))

    result = await revise_posting(llm, posting(), "", "근무지 성남, 복지에 식대 지원 추가")

    assert result.suggestion is not None
    assert result.suggestion.content.location == "경기 성남시"
    assert result.suggestion.content.benefits == ["유연 근무", "식대 지원"]


async def test_revise_asks_again_when_nothing_changes() -> None:
    llm = FakeLlm(ContentEdit(career=CONTENT.career))

    result = await revise_posting(llm, posting(), "", "음")

    assert result.suggestion is None
    assert result.reply == NOTHING_CHANGED_REPLY


async def test_revise_sends_current_posting_style_and_request_to_model() -> None:
    llm = FakeLlm(ContentEdit())

    await revise_posting(llm, posting(), "짧고 친근하게 쓴다", "우대 사항 다듬어 줘")

    call = llm.calls[0]
    assert call.agent == "posting"
    assert call.output is ContentEdit
    assert "채용명: 결제 플랫폼 백엔드 개발자" in call.user
    assert "우대 사항:\n- 금융 도메인 경험" in call.user
    assert "공고 작성 스타일: 짧고 친근하게 쓴다" in call.user
    assert "HR 요청: 우대 사항 다듬어 줘" in call.user


async def test_revise_marks_empty_fields_and_missing_style_in_prompt() -> None:
    llm = FakeLlm(ContentEdit())
    empty = CONTENT.model_copy(update={"location": "", "benefits": []})

    await revise_posting(llm, posting(content=empty), "  ", "근무지 넣어 줘")

    user = llm.calls[0].user
    assert "근무지: (비어 있음)" in user
    assert "복지:\n(비어 있음)" in user
    assert "공고 작성 스타일: (없음)" in user
