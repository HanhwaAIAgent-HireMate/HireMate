"""Score parser and raw-fallback results from the synthetic PDF fixtures.

Input is the synthetic-source output from DocumentQualityFixturesTests. No
actual applicant documents or model credentials are needed.
"""

import argparse
import json
import re
from pathlib import Path
from uuid import UUID

from eval.document_quality_gold import KOREAN_TEXT_CASE, PDF_CASES
from eval.document_quality_score import evaluate
from hiremate_ai.agents.analysis.application.normalize import verbatim_document
from hiremate_ai.contract import DocumentNormalizationRequest, DocumentSource, NormalizedDocument


def _request(name: str, document_type: str, sources: list[DocumentSource]) -> DocumentNormalizationRequest:
    fixture_id = UUID("00000000-0000-0000-0000-000000000001")
    return DocumentNormalizationRequest.model_validate(
        {
            "companyId": fixture_id,
            "recruitmentId": fixture_id,
            "applicationId": fixture_id,
            "documentId": fixture_id,
            "revision": 1,
            "documentType": document_type,
            "sources": sources,
        }
    )


def _sources(log: Path) -> dict[str, list[DocumentSource]]:
    result: dict[str, list[DocumentSource]] = {}
    for line in log.read_text().splitlines():
        match = re.search(r"DOCUMENT_QUALITY_SOURCE (\w+) (\[.*\])$", line)
        if match:
            result[match[1]] = [DocumentSource.model_validate(item) for item in json.loads(match[2])]
    expected = {case.name for case in PDF_CASES}
    if set(result) != expected:
        raise ValueError(f"Expected fixture source sets {sorted(expected)}, got {sorted(result)}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parser_log", type=Path, help="Gradle test output containing synthetic parser sources")
    parser.add_argument("--documents", type=Path, help="Optional JSON mapping fixture names to normalized documents")
    parser.add_argument("--case", action="append", choices=[case.name for case in [*PDF_CASES, KOREAN_TEXT_CASE]])
    args = parser.parse_args()
    selected = set(args.case) if args.case else None
    source_sets = _sources(args.parser_log)
    if args.documents:
        output_documents = json.loads(args.documents.read_text())
        pdf_names = {case.name for case in PDF_CASES}
        if selected is not None and set(output_documents) != selected:
            raise ValueError("The candidate file must contain exactly the selected fixture names")
        if selected is None and (
            not pdf_names.issubset(output_documents) or set(output_documents) - pdf_names - {KOREAN_TEXT_CASE.name}
        ):
            raise ValueError(
                "The candidate file must contain all PDF fixture names and may include the Korean text case"
            )
    else:
        output_documents = None

    results = {}
    for case in PDF_CASES:
        if selected is not None and case.name not in selected:
            continue
        sources = source_sets[case.name]
        document = (
            NormalizedDocument.model_validate(output_documents[case.name])
            if output_documents is not None
            else verbatim_document(_request(case.name, case.document_type, sources))
        )
        results[case.name] = evaluate(case, sources, document)
    korean_sources = [
        DocumentSource(id=f"s{i}", page=1, text=text) for i, text in enumerate(KOREAN_TEXT_CASE.reading_order, start=1)
    ]
    if (selected is None or KOREAN_TEXT_CASE.name in selected) and (
        output_documents is None or KOREAN_TEXT_CASE.name in output_documents
    ):
        korean_document = (
            verbatim_document(_request(KOREAN_TEXT_CASE.name, "COVER_LETTER", korean_sources))
            if output_documents is None
            else NormalizedDocument.model_validate(output_documents[KOREAN_TEXT_CASE.name])
        )
        results[KOREAN_TEXT_CASE.name] = evaluate(KOREAN_TEXT_CASE, korean_sources, korean_document)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
