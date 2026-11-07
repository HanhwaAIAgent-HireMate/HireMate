"""Checks for the synthetic document quality evaluation, not model behavior."""

from uuid import uuid4

from eval.document_quality_gold import KOREAN_PDF_CASE, KOREAN_TEXT_CASE, DrawText, ExpectedBlock, QualityCase
from eval.document_quality_score import evaluate
from hiremate_ai.contract import DocumentSource, NormalizedDocument


def _case() -> QualityCase:
    return QualityCase(
        name="simple",
        document_type="RESUME",
        pages=[[DrawText(10, 20, "Skills"), DrawText(10, 10, "Python 25%")]],
        reading_order=["Skills", "Python 25%"],
        expected_blocks=[
            ExpectedBlock("section", "Skills"),
            ExpectedBlock("paragraph", "Python 25%", "Skills", "body"),
        ],
    )


def _document(*, value: str = "Python 25%", source: str = "s2") -> NormalizedDocument:
    return NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "section",
                    "title": "Skills",
                    "sourceIds": ["s1"],
                    "blocks": [{"id": "b2", "type": "paragraph", "role": "body", "text": value, "sourceIds": [source]}],
                }
            ],
        }
    )


def test_correct_document_passes_content_structure_and_provenance() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Skills"), DocumentSource(id="s2", page=1, text="Python 25%")]
    result = evaluate(_case(), sources, _document())
    assert result["source_content_matches"] is True
    assert result["source_provenance_matches"] is True
    assert result["pdf_reading_order_matches"] is True
    assert result["structure_passed"] == 2
    assert result["structure_total"] == 2


def test_empty_result_is_not_a_successful_document() -> None:
    document = NormalizedDocument.model_validate(
        {"documentId": str(uuid4()), "revision": 1, "documentType": "RESUME", "blocks": []}
    )

    result = evaluate(_case(), [], document)

    assert result["required_checks_pass"] is False


def test_changed_number_and_wrong_source_are_reported() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Skills"), DocumentSource(id="s2", page=1, text="Python 25%")]
    result = evaluate(_case(), sources, _document(value="Python 52%", source="s1"))
    assert result["source_content_matches"] is False
    assert result["source_provenance_matches"] is False
    assert result["structure_passed"] == 1


def test_expected_top_level_section_does_not_match_a_nested_section() -> None:
    sources = [
        DocumentSource(id="s1", page=1, text="Outer"),
        DocumentSource(id="s2", page=1, text="Skills"),
        DocumentSource(id="s3", page=1, text="Python 25%"),
    ]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "outer",
                    "type": "section",
                    "title": "Outer",
                    "sourceIds": ["s1"],
                    "blocks": [
                        {
                            "id": "nested",
                            "type": "section",
                            "title": "Skills",
                            "sourceIds": ["s2"],
                            "blocks": [
                                {
                                    "id": "body",
                                    "type": "paragraph",
                                    "role": "body",
                                    "text": "Python 25%",
                                    "sourceIds": ["s3"],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["structure_checks"][0]["pass"] is False
    assert result["structure_checks"][1]["pass"] is True
    assert result["structure_passed"] == 1


def test_untitled_parent_is_not_the_document_root() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Skills"), DocumentSource(id="s2", page=1, text="Python 25%")]
    nested = _document().model_dump(mode="json")
    nested["blocks"] = [{"id": "outer", "type": "section", "title": None, "sourceIds": [], "blocks": nested["blocks"]}]

    result = evaluate(_case(), sources, NormalizedDocument.model_validate(nested))

    assert result["structure_checks"][0]["pass"] is False
    assert result["structure_checks"][1]["pass"] is True


def test_korean_spacing_and_line_break_require_exact_human_readable_structure() -> None:
    from hiremate_ai.agents.analysis.application.normalize import verbatim_document
    from hiremate_ai.contract import DocumentNormalizationRequest, DocumentType

    source_text = KOREAN_TEXT_CASE.reading_order
    sources = [DocumentSource(id=f"s{i}", page=1, text=text) for i, text in enumerate(source_text, start=1)]
    request = DocumentNormalizationRequest(
        company_id=uuid4(),
        recruitment_id=uuid4(),
        application_id=uuid4(),
        document_id=uuid4(),
        revision=1,
        document_type=DocumentType.COVER_LETTER,
        sources=sources,
    )
    result = evaluate(KOREAN_TEXT_CASE, sources, verbatim_document(request))
    assert result["source_content_matches"] is True
    assert result["source_provenance_matches"] is True
    assert result["structure_passed"] == 0
    assert result["pdf_reading_order_matches"] is None


def test_numeric_boundaries_cannot_be_hidden_by_whitespace_compaction() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Skills"), DocumentSource(id="s2", page=1, text="Python 2 5%")]
    result = evaluate(_case(), sources, _document())
    assert result["source_content_matches"] is True
    assert result["source_numeric_matches"] is False
    assert result["required_checks_pass"] is False


def test_missing_single_word_space_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Skills"), DocumentSource(id="s2", page=1, text="Python 25%")]
    result = evaluate(_case(), sources, _document(value="Python25%"))

    assert result["source_content_matches"] is True
    assert result["source_numeric_matches"] is True
    assert result["single_space_matches"] is False
    assert result["required_checks_pass"] is False


def test_new_space_inside_source_word_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Skills"), DocumentSource(id="s2", page=1, text="Python 25%")]
    result = evaluate(_case(), sources, _document(value="Py thon 25%"))

    assert result["source_content_matches"] is True
    assert result["single_space_matches"] is True
    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_word_split_across_blocks_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Python")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {"id": "b1", "type": "paragraph", "role": "body", "text": "Py", "sourceIds": ["s1"]},
                {"id": "b2", "type": "paragraph", "role": "body", "text": "thon", "sourceIds": ["s1"]},
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_word_split_across_table_cells_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="Python")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "table",
                    "sourceIds": ["s1"],
                    "caption": None,
                    "headers": ["Py", "thon"],
                    "rows": [],
                }
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_url_split_at_punctuation_across_blocks_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="https://example.test")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {"id": "b1", "type": "paragraph", "role": "body", "text": "https:", "sourceIds": ["s1"]},
                {"id": "b2", "type": "paragraph", "role": "body", "text": "//example.test", "sourceIds": ["s1"]},
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_url_split_at_punctuation_across_table_cells_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="https://example.test")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "table",
                    "sourceIds": ["s1"],
                    "caption": None,
                    "headers": ["https:", "//example.test"],
                    "rows": [],
                }
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_list_marker_does_not_cause_a_false_spacing_failure() -> None:
    sources = [DocumentSource(id="s1", page=1, text="- Python 25%")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "list",
                    "sourceIds": ["s1"],
                    "items": [{"marker": "-", "text": "Python 25%", "children": []}],
                }
            ],
        }
    )
    result = evaluate(_case(), sources, document)

    assert result["single_space_matches"] is True
    assert result["required_checks_pass"] is True


def test_new_space_inside_a_list_item_is_not_a_safe_pass() -> None:
    sources = [DocumentSource(id="s1", page=1, text="- Python 25%")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "list",
                    "sourceIds": ["s1"],
                    "items": [{"marker": "-", "text": "Py thon 25%", "children": []}],
                }
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["source_content_matches"] is True
    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_new_space_inside_visual_reference_is_not_a_safe_pass() -> None:
    from hiremate_ai.contract import VISUAL_NOTICE

    sources = [DocumentSource(id="s1", page=1, text="성능 그래프")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "reference",
                    "sourceIds": ["s1"],
                    "kind": "possible_visual",
                    "text": "성 능 그래프",
                    "notice": VISUAL_NOTICE,
                }
            ],
        }
    )

    result = evaluate(_case(), sources, document)

    assert result["source_content_matches"] is True
    assert result["source_word_matches"] is False
    assert result["required_checks_pass"] is False


def test_table_cells_do_not_merge_distinct_numbers_during_scoring() -> None:
    sources = [DocumentSource(id="s1", page=1, text="값 A B 11 2")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "table",
                    "caption": "값",
                    "headers": ["A", "B"],
                    "rows": [["11", "2"]],
                    "sourceIds": ["s1"],
                }
            ],
        }
    )
    result = evaluate(_case(), sources, document)
    assert result["source_numeric_matches"] is True
    assert result["required_checks_pass"] is True


def test_code_reference_with_unknown_source_fails_instead_of_being_unverified() -> None:
    from hiremate_ai.contract import CODE_NOTICE

    sources = [DocumentSource(id="s1", page=1, text="print(1)")]
    document = NormalizedDocument.model_validate(
        {
            "documentId": str(uuid4()),
            "revision": 1,
            "documentType": "RESUME",
            "blocks": [
                {
                    "id": "b1",
                    "type": "reference",
                    "sourceIds": ["missing"],
                    "kind": "code_example",
                    "text": None,
                    "notice": CODE_NOTICE,
                }
            ],
        }
    )
    result = evaluate(_case(), sources, document)
    assert result["source_content_matches"] is None
    assert result["source_provenance_matches"] is False
    assert result["required_checks_pass"] is False


def test_committed_pdf_fixtures_match_their_generator() -> None:
    from pathlib import Path

    from eval.document_quality_fixtures import _pdf
    from eval.document_quality_gold import CASES

    samples = Path(__file__).resolve().parents[1] / "samples"
    for case in CASES:
        assert (samples / f"document_quality_{case.name}.pdf").read_bytes() == _pdf(case)


def test_korean_pdf_uses_the_same_reviewed_gold_as_the_parser_case() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "samples" / "document_quality_korean.pdf"
    assert path.read_bytes().startswith(b"%PDF-")
    assert KOREAN_PDF_CASE.reading_order == KOREAN_TEXT_CASE.reading_order
    assert KOREAN_PDF_CASE.expected_blocks == KOREAN_TEXT_CASE.expected_blocks
    assert [line.text for line in KOREAN_PDF_CASE.pages[0]] == KOREAN_TEXT_CASE.reading_order
