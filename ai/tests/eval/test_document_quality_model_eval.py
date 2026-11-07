from pathlib import Path
from typing import Any, cast

import pytest

from eval import document_quality_model_eval as evaluation
from eval.document_quality_gold import PDF_CASES
from eval.document_quality_positions import PositionLayout
from hiremate_ai.agents.analysis.application.normalize import DocumentLayout
from hiremate_ai.contract import DocumentSource, NormalizedDocument
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError
from hiremate_ai.llm.fake import FakeLlm


def test_ambiguous_url_boundary_has_a_safe_specific_category() -> None:
    assert evaluation._validation_category(ValueError("Ambiguous URL boundary"), positions=True) == (
        "Ambiguous URL boundary"
    )


async def test_evaluation_scores_repeated_format_failure_as_raw_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def invalid(_call: object) -> DocumentLayout:
        raise LlmOutputError("형식 오류", reason=LlmFailureReason.FORMAT)

    llm = FakeLlm(*([invalid] * 10))
    monkeypatch.setattr(evaluation.client_module, "build_llm", lambda *_args, **_kwargs: llm)
    monkeypatch.setattr(evaluation.client_module, "settings", evaluation.client_module.settings)
    monkeypatch.setattr(evaluation.normalize_module, "settings", evaluation.normalize_module.settings)
    monkeypatch.setattr(
        evaluation,
        "_sources",
        lambda _path: {case.name: [DocumentSource(id="s1", page=1, text="가상 원문")] for case in PDF_CASES},
    )

    documents: dict[str, NormalizedDocument] = {}
    result = await evaluation._evaluate(tmp_path / "parser.log", tmp_path / "settings.env", documents=documents)
    results = cast(dict[str, dict[str, Any]], result["results"])

    assert all(item["outcome"] == "verbatim_fallback" for item in results.values())
    assert all(item["validation_category"] == "FORMAT" for item in results.values())
    assert set(documents) == set(results)
    assert documents[PDF_CASES[0].name].blocks[0].type == "paragraph"


async def test_position_range_failures_are_reported_without_source_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposal = PositionLayout.model_validate(
        {"blocks": [{"type": "paragraph", "role": "body", "text": [{"source": "missing", "start": 0, "end": 1}]}]}
    )
    monkeypatch.setattr(evaluation.client_module, "build_llm", lambda *_args, **_kwargs: FakeLlm(*([proposal] * 10)))
    monkeypatch.setattr(evaluation.client_module, "settings", evaluation.client_module.settings)
    monkeypatch.setattr(evaluation.normalize_module, "settings", evaluation.normalize_module.settings)
    monkeypatch.setattr(
        evaluation,
        "_sources",
        lambda _path: {case.name: [DocumentSource(id="s1", page=1, text="가상 원문")] for case in PDF_CASES},
    )

    result = await evaluation._evaluate(tmp_path / "parser.log", tmp_path / "settings.env", positions=True)

    results = cast(dict[str, dict[str, Any]], result["results"])
    assert all(item["outcome"] == "verbatim_fallback" for item in results.values())
    assert all(item["validation_category"] == "Invalid source range" for item in results.values())


async def test_selecting_one_fixture_calls_only_for_that_case(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    proposal = DocumentLayout.model_validate(
        {"blocks": [{"type": "paragraph", "sourceIds": ["s1"], "role": "body", "text": "가상 원문"}]}
    )
    llm = FakeLlm(proposal)
    monkeypatch.setattr(evaluation.client_module, "build_llm", lambda *_args, **_kwargs: llm)
    monkeypatch.setattr(evaluation.client_module, "settings", evaluation.client_module.settings)
    monkeypatch.setattr(evaluation.normalize_module, "settings", evaluation.normalize_module.settings)
    monkeypatch.setattr(
        evaluation,
        "_sources",
        lambda _path: {case.name: [DocumentSource(id="s1", page=1, text="가상 원문")] for case in PDF_CASES},
    )
    documents: dict[str, NormalizedDocument] = {}

    result = await evaluation._evaluate(
        tmp_path / "parser.log", tmp_path / "settings.env", documents=documents, cases={"portfolio"}
    )

    results = cast(dict[str, dict[str, Any]], result["results"])
    assert list(results) == ["portfolio"]
    assert list(documents) == ["portfolio"]
    assert len(llm.calls) == 1
