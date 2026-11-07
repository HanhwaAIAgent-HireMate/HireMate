import json
import sys
from pathlib import Path

import pytest

from eval import document_quality_baseline as baseline
from eval.document_quality_gold import KOREAN_TEXT_CASE, PDF_CASES
from hiremate_ai.agents.analysis.application.normalize import verbatim_document
from hiremate_ai.contract import DocumentSource


def test_saved_model_documents_can_be_rescored_without_a_model_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_sets = {case.name: [DocumentSource(id="s1", page=1, text="가상 자료")] for case in PDF_CASES}
    korean = [
        DocumentSource(id=f"s{i}", page=1, text=text) for i, text in enumerate(KOREAN_TEXT_CASE.reading_order, start=1)
    ]
    documents = {
        case.name: verbatim_document(
            baseline._request(case.name, case.document_type, source_sets[case.name])
        ).model_dump(mode="json", by_alias=True)
        for case in PDF_CASES
    }
    documents[KOREAN_TEXT_CASE.name] = verbatim_document(
        baseline._request(KOREAN_TEXT_CASE.name, KOREAN_TEXT_CASE.document_type, korean)
    ).model_dump(mode="json", by_alias=True)
    path = tmp_path / "documents.json"
    path.write_text(json.dumps(documents, ensure_ascii=False))
    monkeypatch.setattr(baseline, "_sources", lambda _path: source_sets)
    monkeypatch.setattr(sys, "argv", ["document_quality_baseline", "parser.log", "--documents", str(path)])

    baseline.main()

    results = json.loads(capsys.readouterr().out)
    assert set(results) == {case.name for case in PDF_CASES} | {KOREAN_TEXT_CASE.name}
    assert all(result["required_checks_pass"] is True for result in results.values())


def test_one_saved_case_can_be_rescored_without_requiring_other_cases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = next(case for case in PDF_CASES if case.name == "portfolio")
    sources = [DocumentSource(id="s1", page=1, text="가상 포트폴리오")]
    document = verbatim_document(baseline._request(case.name, case.document_type, sources))
    path = tmp_path / "document.json"
    path.write_text(json.dumps({case.name: document.model_dump(mode="json", by_alias=True)}, ensure_ascii=False))
    monkeypatch.setattr(baseline, "_sources", lambda _path: {case.name: sources})
    monkeypatch.setattr(
        sys, "argv", ["document_quality_baseline", "parser.log", "--documents", str(path), "--case", case.name]
    )

    baseline.main()

    results = json.loads(capsys.readouterr().out)
    assert list(results) == [case.name]
    assert results[case.name]["required_checks_pass"] is True
