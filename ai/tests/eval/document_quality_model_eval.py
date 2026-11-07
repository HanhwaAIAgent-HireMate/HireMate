"""Evaluate a configured model using only the fictional PDF fixtures.

Provide the backend fixture parser log and a local settings file. The settings
file is read in place; credentials, prompts and model output are not printed.
This opt-in evaluation calls the configured provider and may incur charges.
LangSmith tracing is explicitly disabled for this process.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from langsmith import tracing_context
from pydantic import ValidationError

import hiremate_ai.agents.analysis.application.normalize as normalize_module
import hiremate_ai.llm.client as client_module
from eval.document_quality_baseline import _request, _sources
from eval.document_quality_gold import KOREAN_TEXT_CASE, PDF_CASES
from eval.document_quality_positions import PositionLayout, materialize
from eval.document_quality_score import evaluate
from hiremate_ai.config import Settings
from hiremate_ai.contract import DocumentSource, NormalizedDocument
from hiremate_ai.llm.call_log import CallRecord
from hiremate_ai.llm.chat import LlmFailureReason, LlmOutputError, model_call_budget
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block


class MemoryLog:
    def __init__(self) -> None:
        self.records: list[CallRecord] = []

    async def record(self, record: CallRecord) -> None:
        self.records.append(record)


def _validation_category(error: ValueError, *, positions: bool) -> str:
    position_categories = {
        "Duplicate source IDs",
        "Invalid source range",
        "Empty source range",
        "Ambiguous URL boundary",
        "Source ranges overlap, omit, or change reading order",
        "Section title and children required",
        "Paragraph text and role required",
        "Visual text and kind required",
        "List items required",
        "Table headers and rows required",
    }
    if positions and str(error) in position_categories:
        return str(error)
    return normalize_module._safe_validation_message(error)


async def _evaluate(
    log_path: Path,
    settings_path: Path,
    *,
    positions: bool = False,
    documents: dict[str, NormalizedDocument] | None = None,
    cases: set[str] | None = None,
) -> dict[str, object]:
    available = [*PDF_CASES, KOREAN_TEXT_CASE]
    if cases is not None and (not cases or not cases.issubset({case.name for case in available})):
        raise ValueError("Unknown or empty fixture selection")
    configured = Settings(_env_file=settings_path, langsmith_tracing=False)
    client_module.settings = configured
    normalize_module.settings = configured
    log = MemoryLog()
    llm = client_module.build_llm(log, timeout=60)
    source_sets = _sources(log_path)
    source_sets[KOREAN_TEXT_CASE.name] = [
        DocumentSource(id=f"s{i}", page=1, text=text) for i, text in enumerate(KOREAN_TEXT_CASE.reading_order, start=1)
    ]
    results = {}
    with tracing_context(enabled=False):
        for case in available:
            if cases is not None and case.name not in cases:
                continue
            sources = source_sets[case.name]
            request = _request(case.name, case.document_type, sources)
            start_record = len(log.records)
            started = time.perf_counter()
            error_kind = None
            validation_category = None
            validation_errors = []
            try:
                async with asyncio.timeout(150):
                    if positions:
                        source_data = "\n".join(
                            data_block("document_source", source.text, id=source.id, length=str(len(source.text)))
                            for source in sources
                        )
                        system = (
                            "원문을 재작성하지 말고 JSON 블록에 해당하는 원문의 위치만 지정한다. "
                            "각 span은 source ID와 0부터 시작하는 문자 인덱스 start, 끝을 제외하는 end다. "
                            "원문의 공백을 제외한 모든 문자를 빠짐없이 한 번씩 원문 순서대로 포함한다. "
                            "section의 text는 제목, blocks는 하위 블록이다. paragraph의 text와 role을 지정한다. "
                            "list는 items, table은 caption, headers, rows의 각 항목을 span 배열로 지정한다. "
                            "reference는 possible_visual만 허용하고 text는 원문 설명이다. 코드는 paragraph로 둔다. "
                            "텍스트가 없는 선택 필드는 null로 둔다. " + UNTRUSTED_RULE
                        )
                        with model_call_budget(configured.llm_agent_max_calls):
                            for attempt in range(2):
                                proposal = await llm.structured(
                                    PositionLayout, agent="eval.document_positions", system=system, user=source_data
                                )
                                try:
                                    document = materialize(proposal, request)
                                    break
                                except ValueError:
                                    if attempt == 1:
                                        raise
                                    source_data += (
                                        "\n이전 위치가 유효하지 않았다. 모든 범위를 원문 순서로 다시 확인한다."
                                    )
                    else:
                        document = await normalize_module.normalize_document(llm, request)
                outcome = "structured"
            except ValueError as error:
                outcome = "verbatim_fallback"
                error_kind = type(error).__name__
                validation_category = _validation_category(error, positions=positions)
                if isinstance(error, ValidationError):
                    validation_errors = [
                        {"location": list(item["loc"]), "type": item["type"]}
                        for item in error.errors(include_input=False, include_context=False, include_url=False)
                    ]
                document = normalize_module.verbatim_document(request)
            except LlmOutputError as error:
                error_kind = type(error).__name__
                validation_category = error.reason.value
                if error.reason == LlmFailureReason.FORMAT:
                    outcome = "verbatim_fallback"
                    document = normalize_module.verbatim_document(request)
                else:
                    outcome = "model_or_timeout_error"
                    document = None
            except Exception as error:
                outcome = "model_or_timeout_error"
                error_kind = type(error).__name__
                document = None
            records = log.records[start_record:]
            if documents is not None and document is not None:
                documents[case.name] = document
            results[case.name] = {
                "outcome": outcome,
                "error_kind": error_kind,
                "validation_category": validation_category,
                "validation_errors": validation_errors,
                "elapsed_seconds": round(time.perf_counter() - started, 2),
                "model_call_records": len(records),
                "call_statuses": [record.status for record in records],
                "input_tokens": sum(record.input_tokens or 0 for record in records),
                "output_tokens": sum(record.output_tokens or 0 for record in records),
                "metrics": evaluate(case, sources, document) if document is not None else None,
            }
    return {
        "approach": "positions" if positions else "rewrite",
        "model": configured.llm_model,
        "structured_output": configured.llm_structured_output,
        "temperature": configured.llm_temperature,
        "reasoning_effort": configured.llm_reasoning_effort,
        "langsmith_tracing": False,
        "call_timeout_seconds": 60,
        "document_timeout_seconds": 150,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parser_log", type=Path)
    parser.add_argument("settings_file", type=Path)
    parser.add_argument("--positions", action="store_true", help="Evaluate the experimental source-position approach")
    parser.add_argument("--documents-output", type=Path, help="Save validated fictional results for later rescoring")
    parser.add_argument("--case", action="append", choices=[case.name for case in [*PDF_CASES, KOREAN_TEXT_CASE]])
    args = parser.parse_args()
    documents: dict[str, NormalizedDocument] = {}
    result = asyncio.run(
        _evaluate(
            args.parser_log,
            args.settings_file,
            positions=args.positions,
            documents=documents,
            cases=set(args.case) if args.case else None,
        )
    )
    if args.documents_output is not None:
        args.documents_output.write_text(
            json.dumps(
                {name: value.model_dump(mode="json", by_alias=True) for name, value in documents.items()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
