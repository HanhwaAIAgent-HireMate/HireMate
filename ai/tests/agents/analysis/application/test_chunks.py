from uuid import uuid4

import pytest

from hiremate_ai.agents.analysis.application.chunks import chunk_document
from hiremate_ai.contract import DocumentTable, NormalizedDocument


def test_chunks_preserve_long_text_and_exclude_notices() -> None:
    text = "긴 원문 " * 800
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "s",
                    "type": "section",
                    "title": "경력",
                    "sourceIds": ["s1"],
                    "blocks": [
                        {"id": "p", "type": "paragraph", "role": "body", "text": text, "sourceIds": ["s2"]},
                        {"id": "f", "type": "paragraph", "role": "page_footer", "text": "제외", "sourceIds": ["s3"]},
                    ],
                }
            ],
        }
    )
    chunks = chunk_document(document, max_chars=200)
    assert "".join(c.text for c in chunks if c.block_ids == ["p"]) == text
    assert all(len(c.text) <= 200 and c.section_path == ["경력"] for c in chunks)
    assert all("제외" not in c.text for c in chunks)
    assert chunks[-1].source_ids == ["s1", "s2"]


def test_tables_repeat_headers_and_reject_oversized_header() -> None:
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "t",
                    "type": "table",
                    "caption": None,
                    "headers": ["업무"],
                    "rows": [["가" * 500]],
                    "sourceIds": ["s"],
                }
            ],
        }
    )
    chunks = chunk_document(document, max_chars=100)
    chunks = [c for c in chunks if c.text != "업무"]
    assert all(c.text.startswith("행 1 열 1 업무: ") and len(c.text) <= 100 for c in chunks)
    assert "".join(c.text.split(": ", 1)[1] for c in chunks) == "가" * 500
    table = document.blocks[0]
    assert isinstance(table, DocumentTable)
    document = document.model_copy(update={"blocks": [table.model_copy(update={"headers": ["헤더" * 100]})]})
    with pytest.raises(ValueError, match="header"):
        chunk_document(document, max_chars=100)


def test_nested_lists_references_and_long_headings_preserve_original_text() -> None:
    title = "긴 제목" * 200
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 7,
            "documentType": "PORTFOLIO",
            "blocks": [
                {
                    "id": "s",
                    "type": "section",
                    "title": title,
                    "sourceIds": ["s1"],
                    "blocks": [
                        {
                            "id": "l",
                            "type": "list",
                            "sourceIds": ["s2"],
                            "items": [
                                {
                                    "marker": "1.",
                                    "text": "부모",
                                    "children": [{"marker": "a)", "text": "자식", "children": []}],
                                }
                            ],
                        },
                        {
                            "id": "r",
                            "type": "reference",
                            "kind": "code_example",
                            "text": "원문 코드 설명",
                            "notice": "코드 예시가 포함되어 있습니다. 원본 PDF를 확인해 주세요.",
                            "sourceIds": ["s3"],
                        },
                        *[
                            {"id": role, "type": "paragraph", "role": role, "text": "제외", "sourceIds": ["s4"]}
                            for role in ["page_header", "page_footer", "form_instruction", "unassigned"]
                        ],
                    ],
                },
            ],
        }
    )
    chunks = chunk_document(document, max_chars=100)
    assert "".join(chunk.text for chunk in chunks if chunk.block_ids == ["s"]) == title
    assert [chunk.text for chunk in chunks if chunk.block_ids == ["l"]] == ["1. 부모", "  a) 자식"]
    assert chunks[-1].text == "원문 코드 설명"
    assert all("원본 PDF" not in chunk.text and "제외" not in chunk.text for chunk in chunks)
    assert all(chunk.document_id == document.document_id and chunk.revision == 7 for chunk in chunks)
