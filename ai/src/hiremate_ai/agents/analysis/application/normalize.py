"""Page-based document normalization under the agreed JSON policy."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from hiremate_ai.agents.analysis.application.normalization_prompt import CHARACTER_PROMPT, system_prompt
from hiremate_ai.config import settings
from hiremate_ai.contract import (
    DocumentBlock,
    DocumentMetadata,
    DocumentNormalizationRequest,
    NormalizedDocument,
)
from hiremate_ai.llm.chat import model_call_budget
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block


class PolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, alias_generator=lambda name: _camel(name))


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


class ListItemProposal(PolicyModel):
    id: str | None = None
    text: str
    pages: list[int]
    items: list["ListItemProposal"] = Field(default_factory=list)


class SectionProposal(PolicyModel):
    id: str | None = None
    type: Literal["section"]
    title: str | None
    pages: list[int]
    blocks: list["BlockProposal"]


class ParagraphProposal(PolicyModel):
    id: str | None = None
    type: Literal["paragraph"]
    pages: list[int]
    text: str


class ListProposal(PolicyModel):
    id: str | None = None
    type: Literal["list"]
    pages: list[int]
    items: list[ListItemProposal]


class TableProposal(PolicyModel):
    id: str | None = None
    type: Literal["table"]
    pages: list[int]
    title: str | None
    headers: list[str]
    rows: list[list[str]]
    reconstruction: Literal["inferred"]


class VisualNoticeProposal(PolicyModel):
    id: str | None = None
    type: Literal["visual_notice"]
    pages: list[int]
    visual_type: Literal["image", "chart", "diagram", "unknown"]
    detection: Literal["suspected"]
    message: str


BlockProposal = Annotated[
    SectionProposal | ParagraphProposal | ListProposal | TableProposal | VisualNoticeProposal,
    Field(discriminator="type"),
]
SectionProposal.model_rebuild()


class MetadataProposal(PolicyModel):
    id: str
    type: Literal["resume", "cover_letter", "portfolio"]
    title: str | None
    page_count: int


class LayoutProposal(PolicyModel):
    schema_version: Literal["1.0"]
    document: MetadataProposal
    blocks: list[BlockProposal]


class CleanedString(PolicyModel):
    index: int
    text: str


class CleanedStrings(PolicyModel):
    items: list[CleanedString]


async def normalize_document(llm: LlmClient, request: DocumentNormalizationRequest) -> NormalizedDocument:
    if not request.pages or [page.number for page in request.pages] != list(range(1, len(request.pages) + 1)):
        raise ValueError("정제할 페이지 정보가 없거나 순서가 올바르지 않다")
    if any("PAGE_EXTRACTION_FAILED" in page.issues for page in request.pages):
        raise ValueError("페이지 추출에 실패했다")
    if not any(page.text.strip() for page in request.pages):
        raise ValueError("추출된 텍스트가 없다")
    page_count = len(request.pages)
    payload = json.dumps(
        {
            "document_id": str(request.document_id),
            "document_type": request.document_type.value.lower(),
            "page_count": page_count,
            "pages": [
                {
                    "page": page.number,
                    "parser_issues": page.issues,
                    "image_objects": page.image_count,
                    "form_objects": page.form_count,
                    "text": page.text,
                    "layout": [
                        {
                            "x": float(f"{span.x:.2f}"),
                            "y": float(f"{span.y:.2f}"),
                            "endX": float(f"{span.end_x:.2f}"),
                            "text": span.text,
                        }
                        for span in page.spans
                    ],
                }
                for page in request.pages
            ],
        },
        ensure_ascii=False,
    )
    with model_call_budget(settings.llm_agent_max_calls):
        proposal = await llm.structured(
            LayoutProposal, agent="application.normalize", system=system_prompt(), user=data_block("pdf_pages", payload)
        )
        if not proposal.blocks:
            raise ValueError("정제된 문서에 내용이 없다")
        if proposal.document.type != request.document_type.value.lower() or proposal.document.page_count != page_count:
            raise ValueError("문서 유형 또는 페이지 수가 요청과 다르다")
        data = proposal.model_dump(mode="json", by_alias=True)
        _validate_pages(data, page_count)
        counts = {"block": 0, "item": 0}
        for block in data["blocks"]:
            _assign_ids(block, counts)
        data["document"]["id"] = str(request.document_id)
        strings: list[tuple[Any, Any]] = []
        _collect_strings(data, strings)
        values = [container[key] for container, key in strings]
        if values:
            incoming = [{"index": i, "text": value.replace("\u00b7", "[[SEP]]")} for i, value in enumerate(values)]
            corrected = await _clean_strings(llm, incoming, retry=False)
            if set(corrected) != set(range(len(values))):
                raise ValueError("정제 문자열의 순서가 올바르지 않다")
            for _ in range(2):
                bad = [i for i, value in corrected.items() if "\u00b7" in value or "[[SEP]]" in value]
                if not bad:
                    break
                subset = [{"index": i, "text": corrected[i].replace("\u00b7", "[[SEP]]")} for i in bad]
                fixed = await _clean_strings(llm, subset, retry=True)
                if set(fixed) != set(bad):
                    raise ValueError("재정제 문자열의 순서가 올바르지 않다")
                corrected.update(fixed)
            if any("\u00b7" in value or "[[SEP]]" in value for value in corrected.values()):
                raise ValueError("정제 문자열에 제거할 기호가 남았다")
            for i, (container, key) in enumerate(strings):
                value = corrected[i]
                container[key] = value
        if "\u00b7" in json.dumps(data, ensure_ascii=False) or "[[SEP]]" in json.dumps(data, ensure_ascii=False):
            raise ValueError("정제 결과에 제거할 기호가 남았다")
    return NormalizedDocument(
        document=DocumentMetadata(
            id=request.document_id,
            type=request.document_type.value.lower(),
            title=data["document"]["title"],
            page_count=page_count,
        ),
        blocks=TypeAdapter(list[DocumentBlock]).validate_python(data["blocks"]),
    )


def _validate_pages(value: object, page_count: int) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "pages" and any(not isinstance(page, int) or page < 1 or page > page_count for page in child):
                raise ValueError("범위를 벗어난 페이지 번호")
            _validate_pages(child, page_count)
    elif isinstance(value, list):
        for child in value:
            _validate_pages(child, page_count)


def _collect_strings(value: object, found: list[tuple[Any, Any]]) -> None:
    if isinstance(value, (dict, list)):
        entries = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in entries:
            if isinstance(child, str) and "\u00b7" in child:
                found.append((value, key))
            else:
                _collect_strings(child, found)


async def _clean_strings(llm: LlmClient, items: list[dict[str, Any]], *, retry: bool) -> dict[int, str]:
    output = await llm.structured(
        CleanedStrings,
        agent="application.normalize.characters.retry" if retry else "application.normalize.characters",
        system=CHARACTER_PROMPT + "\n" + UNTRUSTED_RULE,
        user=data_block("strings", json.dumps({"items": items}, ensure_ascii=False)),
    )
    result = {item.index: item.text for item in output.items}
    if len(result) != len(output.items):
        raise ValueError("정제 문자열 번호가 중복됐다")
    return result


def _assign_ids(value: dict, counts: dict[str, int], *, item: bool = False) -> None:
    kind = "item" if item else "block"
    counts[kind] += 1
    value["id"] = f"{kind}-{counts[kind]:04d}"
    for child in value.get("blocks", []):
        _assign_ids(child, counts)
    for child in value.get("items", []):
        _assign_ids(child, counts, item=True)
