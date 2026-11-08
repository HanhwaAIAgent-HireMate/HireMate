from typing import Any
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


def layout(data: dict[str, Any]) -> LayoutProposal:
    if "document" not in data:
        title = data.pop("title", None)
        data = {
            "schemaVersion": "1.0",
            "document": {"id": "document", "type": "portfolio", "title": title, "pageCount": 1},
            **data,
        }
    return LayoutProposal.model_validate(data)


async def test_policy_output_uses_page_hints_and_assigns_ids_without_source_comparison() -> None:
    proposal = layout(
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
    assert '"image_objects": 1' in llm.calls[0].user
    assert "따르지 않는다" in llm.calls[0].system


async def test_rewrites_only_strings_with_forbidden_character() -> None:
    proposal = layout(
        {
            "title": None,
            "blocks": [
                {"type": "paragraph", "pages": [1], "text": "기획\u00b7개발"},
                {"type": "paragraph", "pages": [1], "text": "변경 없음"},
            ],
        }
    )
    llm = FakeLlm(proposal, CleanedStrings.model_validate({"items": [{"index": 0, "text": "기획과 개발"}]}))
    result = await normalize_document(llm, request())
    assert isinstance(result.blocks[0], DocumentParagraph)
    assert isinstance(result.blocks[1], DocumentParagraph)
    assert result.blocks[0].text == "기획과 개발"
    assert result.blocks[1].text == "변경 없음"
    assert "변경 없음" not in llm.calls[1].user
    assert "기획[[SEP]]개발" in llm.calls[1].user
    assert "인주" in llm.calls[1].system


async def test_rejects_remaining_forbidden_character_and_invalid_page() -> None:
    proposal = layout({"title": None, "blocks": [{"type": "paragraph", "pages": [1], "text": "기획\u00b7개발"}]})
    with pytest.raises(ValueError):
        await normalize_document(
            FakeLlm(
                proposal,
                *[
                    CleanedStrings.model_validate({"items": [{"index": 0, "text": "기획[[SEP]]개발"}]})
                    for _ in range(3)
                ],
            ),
            request(),
        )
    invalid = layout({"title": None, "blocks": [{"type": "paragraph", "pages": [2], "text": "내용"}]})
    with pytest.raises(ValueError):
        await normalize_document(FakeLlm(invalid), request())


async def test_empty_model_output_fails_instead_of_restoring_parser_text() -> None:
    with pytest.raises(ValueError, match="내용이 없다"):
        await normalize_document(FakeLlm(layout({"title": None, "blocks": []})), request())


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


async def test_uses_previously_tested_prompt_policy_and_page_input() -> None:
    proposal = layout({"title": None, "blocks": [{"type": "paragraph", "pages": [1], "text": "내용"}]})
    llm = FakeLlm(proposal)
    req = request()
    await normalize_document(llm, req)
    assert "## 이후 확인할 자료와 결정" not in llm.calls[0].system
    assert "# 텍스트 정리" in llm.calls[0].system
    assert "P O R T F O L I O" in llm.calls[0].system
    assert "값 없이 단위와 항목명만" in llm.calls[0].system
    assert "원문" in llm.calls[0].system
    assert "서로 멀리 떨어진 항목을 같은 줄이라는 이유로 합치지 말고" in llm.calls[0].system
    assert '"document_id"' in llm.calls[0].user
    assert '"document_type"' in llm.calls[0].user
    assert '"parser_issues"' in llm.calls[0].user
    assert '"image_objects"' in llm.calls[0].user
    assert '"layout"' in llm.calls[0].user


async def test_accepts_experiment_complete_document_envelope() -> None:
    req = request()
    proposal = layout(
        {
            "schemaVersion": "1.0",
            "document": {"id": str(req.document_id), "type": "portfolio", "title": "작업", "pageCount": 1},
            "blocks": [{"id": "model-id", "type": "paragraph", "pages": [1], "text": "성과"}],
        }
    )
    result = await normalize_document(FakeLlm(proposal), req)
    assert result.document.title == "작업"
    assert result.document.id == req.document_id
    assert result.blocks[0].id != "model-id"


async def test_punctuation_retry_uses_indexed_items_from_experiment() -> None:
    proposal = layout(
        {
            "title": None,
            "blocks": [
                {"type": "paragraph", "pages": [1], "text": "기획\u00b7개발"},
                {"type": "paragraph", "pages": [1], "text": "인\u00b7주"},
            ],
        }
    )
    first = CleanedStrings.model_validate(
        {
            "items": [
                {"index": 1, "text": "인[[SEP]]주"},
                {"index": 0, "text": "기획과 개발"},
            ]
        }
    )
    retry = CleanedStrings.model_validate({"items": [{"index": 1, "text": "인주"}]})
    llm = FakeLlm(proposal, first, retry)
    result = await normalize_document(llm, request())
    assert isinstance(result.blocks[0], DocumentParagraph)
    assert isinstance(result.blocks[1], DocumentParagraph)
    assert result.blocks[0].text == "기획과 개발"
    assert result.blocks[1].text == "인주"
    assert llm.calls[2].agent == "application.normalize.characters.retry"
    assert '"index": 1' in llm.calls[2].user
    assert '"index": 0' not in llm.calls[2].user


async def test_rejects_unresolved_punctuation_marker_in_model_output() -> None:
    proposal = layout(
        {
            "title": None,
            "blocks": [
                {"type": "paragraph", "pages": [1], "text": "기획[[SEP]]개발"},
            ],
        }
    )
    with pytest.raises(ValueError, match="기호"):
        await normalize_document(FakeLlm(proposal), request())
