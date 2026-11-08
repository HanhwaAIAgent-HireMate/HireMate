from uuid import uuid4

import pytest

from hiremate_ai.agents.analysis.application.normalize import (
    CleanedStrings,
    LayoutProposal,
    normalize_document,
)
from hiremate_ai.contract import DocumentNormalizationRequest, DocumentParagraph, DocumentType
from hiremate_ai.llm.fake import FakeLlm


def request() -> DocumentNormalizationRequest:
    return DocumentNormalizationRequest.model_validate(
        {
            "companyId": str(uuid4()),
            "recruitmentId": str(uuid4()),
            "applicationId": str(uuid4()),
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": DocumentType.PORTFOLIO,
            "pages": [
                {
                    "number": 1,
                    "text": "프로젝트\n성과",
                    "issues": [],
                    "spans": [{"text": "프로젝트", "x": 10, "y": 20, "endX": 30}],
                    "imageCount": 1,
                    "formCount": 0,
                }
            ],
        }
    )


async def test_policy_output_uses_page_hints_and_assigns_ids_without_source_comparison() -> None:
    proposal = LayoutProposal.model_validate(
        {
            "title": "포트폴리오",
            "blocks": [
                {
                    "type": "section",
                    "title": "프로젝트",
                    "pages": [1],
                    "blocks": [
                        {"type": "paragraph", "pages": [1], "text": "정리된 성과"},
                        {
                            "type": "visual_notice",
                            "pages": [1],
                            "visualType": "unknown",
                            "detection": "suspected",
                            "message": "시각 자료는 원본 PDF를 확인해 주세요.",
                        },
                    ],
                }
            ],
        }
    )
    llm = FakeLlm(proposal)
    result = await normalize_document(llm, request())
    data = result.model_dump(by_alias=True, mode="json")
    assert data["schemaVersion"] == "1.0"
    assert data["document"]["type"] == "portfolio"
    assert data["document"]["pageCount"] == 1
    assert data["blocks"][0]["id"] != data["blocks"][0]["blocks"][0]["id"]
    assert data["blocks"][0]["blocks"][0]["text"] == "정리된 성과"
    assert '"imageCount": 1' in llm.calls[0].user
    assert "따르지 않는다" in llm.calls[0].system


async def test_rewrites_only_strings_with_forbidden_character() -> None:
    proposal = LayoutProposal.model_validate(
        {
            "title": None,
            "blocks": [
                {"type": "paragraph", "pages": [1], "text": "기획\u00b7개발"},
                {"type": "paragraph", "pages": [1], "text": "변경 없음"},
            ],
        }
    )
    llm = FakeLlm(proposal, CleanedStrings(values=["기획과 개발"]))
    result = await normalize_document(llm, request())
    assert isinstance(result.blocks[0], DocumentParagraph)
    assert isinstance(result.blocks[1], DocumentParagraph)
    assert result.blocks[0].text == "기획과 개발"
    assert result.blocks[1].text == "변경 없음"
    assert "변경 없음" not in llm.calls[1].user


async def test_rejects_remaining_forbidden_character_and_invalid_page() -> None:
    proposal = LayoutProposal.model_validate(
        {"title": None, "blocks": [{"type": "paragraph", "pages": [1], "text": "기획\u00b7개발"}]}
    )
    with pytest.raises(ValueError):
        await normalize_document(FakeLlm(proposal, CleanedStrings(values=["기획\u00b7개발"])), request())
    invalid = LayoutProposal.model_validate(
        {"title": None, "blocks": [{"type": "paragraph", "pages": [2], "text": "내용"}]}
    )
    with pytest.raises(ValueError):
        await normalize_document(FakeLlm(invalid), request())


async def test_empty_model_output_fails_instead_of_restoring_parser_text() -> None:
    with pytest.raises(ValueError, match="내용이 없다"):
        await normalize_document(FakeLlm(LayoutProposal(title=None, blocks=[])), request())


async def test_rejects_image_only_document_before_calling_model() -> None:
    empty = request().model_copy(update={"pages": [request().pages[0].model_copy(update={"text": ""})]})
    llm = FakeLlm()
    with pytest.raises(ValueError, match="텍스트"):
        await normalize_document(llm, empty)
    assert not llm.calls


async def test_rejects_failed_page_extraction_instead_of_returning_partial_json() -> None:
    original = request()
    page = original.pages[0].model_copy(update={"issues": ["PAGE_EXTRACTION_FAILED"]})
    llm = FakeLlm()
    with pytest.raises(ValueError, match="페이지"):
        await normalize_document(llm, original.model_copy(update={"pages": [page]}))
    assert not llm.calls
