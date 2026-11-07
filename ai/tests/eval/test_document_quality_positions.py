from uuid import UUID

import pytest

from eval.document_quality_positions import PositionLayout, materialize
from hiremate_ai.contract import DocumentNormalizationRequest


def sample() -> DocumentNormalizationRequest:
    fixture_id = UUID(int=1)
    return DocumentNormalizationRequest.model_validate(
        {
            "companyId": fixture_id,
            "recruitmentId": fixture_id,
            "applicationId": fixture_id,
            "documentId": fixture_id,
            "revision": 1,
            "documentType": "RESUME",
            "sources": [
                {"id": "s1", "page": 1, "text": "경력\n같은 내용"},
                {"id": "s2", "page": 2, "text": "같은 내용"},
            ],
        }
    )


def layout(second: dict[str, object]) -> PositionLayout:
    return PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "section",
                    "text": [{"source": "s1", "start": 0, "end": 2}],
                    "blocks": [
                        {
                            "type": "paragraph",
                            "role": "body",
                            "text": [{"source": "s1", "start": 3, "end": 8}, second],
                        }
                    ],
                }
            ]
        }
    )


def test_spans_reconstruct_text_and_provenance_across_pages() -> None:
    document = materialize(layout({"source": "s2", "start": 0, "end": 5}), sample())
    section = document.blocks[0]
    assert section.type == "section"
    assert section.title == "경력"
    paragraph = section.blocks[0]
    assert paragraph.type == "paragraph"
    assert paragraph.text == "같은 내용 같은 내용"
    assert paragraph.source_ids == ["s1", "s2"]


def test_adjacent_spans_do_not_insert_space_into_a_url() -> None:
    original = sample()
    source = original.sources[0].model_copy(update={"text": "https://example.com/profile"})
    request = original.model_copy(update={"sources": [source]})
    proposal = PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "role": "body",
                    "text": [{"source": "s1", "start": 0, "end": 8}, {"source": "s1", "start": 8, "end": 27}],
                }
            ]
        }
    )

    block = materialize(proposal, request).blocks[0]

    assert block.type == "paragraph"
    assert block.text == "https://example.com/profile"


def test_url_crossing_source_lines_is_not_silently_broken() -> None:
    original = sample()
    sources = [
        original.sources[0].model_copy(update={"text": "https://exa"}),
        original.sources[1].model_copy(update={"text": "mple.test"}),
    ]
    request = original.model_copy(update={"sources": sources})
    proposal = PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "role": "body",
                    "text": [{"source": "s1", "start": 0, "end": 11}, {"source": "s2", "start": 0, "end": 9}],
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="Ambiguous URL boundary"):
        materialize(proposal, request)


def test_spans_keep_korean_tracking_and_newlines_when_they_are_ambiguous() -> None:
    original = sample()
    text = "자  기  소  개  서\n지원동기"
    request = original.model_copy(update={"sources": [original.sources[0].model_copy(update={"text": text})]})
    proposal = PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "paragraph",
                    "role": "body",
                    "text": [
                        {"source": "s1", "start": 0, "end": 1},
                        {"source": "s1", "start": 3, "end": len(text)},
                    ],
                }
            ]
        }
    )

    block = materialize(proposal, request).blocks[0]

    assert block.type == "paragraph"
    assert block.text == text
    assert block.source_ids == ["s1"]


def test_section_and_body_cannot_split_a_single_source_word() -> None:
    original = sample()
    request = original.model_copy(update={"sources": [original.sources[0].model_copy(update={"text": "Python"})]})
    proposal = PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "section",
                    "text": [{"source": "s1", "start": 0, "end": 2}],
                    "blocks": [{"type": "paragraph", "role": "body", "text": [{"source": "s1", "start": 2, "end": 6}]}],
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="Source word split"):
        materialize(proposal, request)


@pytest.mark.parametrize(
    "invalid",
    [
        {"source": "s1", "start": 3, "end": 8},
        {"source": "s2", "start": 1, "end": 5},
        {"source": "s2", "start": 0, "end": 6},
        {"source": "other", "start": 0, "end": 5},
    ],
)
def test_spans_reject_duplicates_gaps_and_invalid_ranges(invalid: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        materialize(layout(invalid), sample())


def test_table_cells_are_reconstructed_from_their_own_ranges() -> None:
    original = sample()
    request = original.model_copy(
        update={"sources": [original.sources[0].model_copy(update={"text": "항목 값\n속도 25"})]}
    )
    proposal = PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "table",
                    "headers": [[{"source": "s1", "start": 0, "end": 2}], [{"source": "s1", "start": 3, "end": 4}]],
                    "rows": [[[{"source": "s1", "start": 5, "end": 7}], [{"source": "s1", "start": 8, "end": 10}]]],
                }
            ]
        }
    )

    table = materialize(proposal, request).blocks[0]
    assert table.type == "table"
    assert table.headers == ["항목", "값"]
    assert table.rows == [["속도", "25"]]


def test_table_cells_cannot_split_one_source_number_into_two() -> None:
    original = sample()
    request = original.model_copy(update={"sources": [original.sources[0].model_copy(update={"text": "항목\n25"})]})
    proposal = PositionLayout.model_validate(
        {
            "blocks": [
                {
                    "type": "table",
                    "headers": [[{"source": "s1", "start": 0, "end": 2}]],
                    "rows": [[[{"source": "s1", "start": 3, "end": 4}], [{"source": "s1", "start": 4, "end": 5}]]],
                }
            ]
        }
    )

    with pytest.raises(ValueError, match="Numeric values changed"):
        materialize(proposal, request)
