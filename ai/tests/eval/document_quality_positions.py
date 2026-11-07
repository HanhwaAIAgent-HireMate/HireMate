"""Experimental source-position layout, used only with fictional evaluation data."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from hiremate_ai.agents.analysis.application.normalize import (
    DocumentLayout,
    LayoutBlock,
    _materialize,
    _validate_layout,
)
from hiremate_ai.contract import DocumentListItem, DocumentNormalizationRequest, NormalizedDocument, ParagraphRole


class Span(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class PositionBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["section", "paragraph", "list", "table", "reference"]
    text: list[Span] | None = None
    role: ParagraphRole | None = None
    blocks: list["PositionBlock"] | None = None
    items: list[list[Span]] | None = None
    caption: list[Span] | None = None
    headers: list[list[Span]] | None = None
    rows: list[list[list[Span]]] | None = None
    kind: Literal["possible_visual"] | None = None


class PositionLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[PositionBlock]


def materialize(layout: PositionLayout, request: DocumentNormalizationRequest) -> NormalizedDocument:
    """Rebuild text from ranges; every non-whitespace position must be used exactly once in source order."""
    sources = {source.id: source.text for source in request.sources}
    if len(sources) != len(request.sources):
        raise ValueError("Duplicate source IDs")
    expected = [
        (source.id, offset)
        for source in request.sources
        for offset, character in enumerate(source.text)
        if not character.isspace()
    ]
    actual: list[tuple[str, int]] = []

    def read(spans: list[Span] | None) -> tuple[str, list[str]]:
        texts: list[str] = []
        ids: list[str] = []
        previous: Span | None = None
        for span in spans or []:
            if span.source not in sources or span.start >= span.end or span.end > len(sources[span.source]):
                raise ValueError("Invalid source range")
            text = sources[span.source][span.start : span.end]
            if not text.strip():
                raise ValueError("Empty source range")
            actual.extend(
                (span.source, i) for i in range(span.start, span.end) if not sources[span.source][i].isspace()
            )
            if previous is not None:
                if previous.source != span.source and re.search(r"(?:https?://|www\.)\S*$", "".join(texts), re.I):
                    raise ValueError("Ambiguous URL boundary")
                separator = (
                    sources[span.source][previous.end : span.start]
                    if previous.source == span.source and previous.end <= span.start
                    else " "
                )
                texts.append(separator)
            texts.append(text)
            previous = span
            if span.source not in ids:
                ids.append(span.source)
        return "".join(texts), ids

    def block(proposal: PositionBlock) -> LayoutBlock:
        if proposal.type == "section":
            if proposal.text is None or proposal.blocks is None:
                raise ValueError("Section title and children required")
            title, ids = read(proposal.text)
            return LayoutBlock(
                type="section", source_ids=ids, title=title or None, blocks=[block(b) for b in proposal.blocks]
            )
        if proposal.type == "paragraph":
            if proposal.text is None or proposal.role is None:
                raise ValueError("Paragraph text and role required")
            text, ids = read(proposal.text)
            return LayoutBlock(type="paragraph", source_ids=ids, role=proposal.role, text=text)
        if proposal.type == "reference":
            if proposal.text is None or proposal.kind is None:
                raise ValueError("Visual text and kind required")
            text, ids = read(proposal.text)
            return LayoutBlock(type="reference", source_ids=ids, kind=proposal.kind, text=text)
        if proposal.type == "list":
            if proposal.items is None:
                raise ValueError("List items required")
            items: list[DocumentListItem] = []
            ids = []
            for spans in proposal.items:
                text, used = read(spans)
                ids.extend(used)
                items.append(DocumentListItem(marker=None, text=text, children=[]))
            return LayoutBlock(type="list", source_ids=list(dict.fromkeys(ids)), items=items)
        if proposal.headers is None or proposal.rows is None:
            raise ValueError("Table headers and rows required")
        caption, ids = read(proposal.caption)
        headers: list[str] = []
        for spans in proposal.headers:
            text, used = read(spans)
            ids.extend(used)
            headers.append(text)
        rows: list[list[str]] = []
        for row in proposal.rows:
            cells: list[str] = []
            for spans in row:
                text, used = read(spans)
                ids.extend(used)
                cells.append(text)
            rows.append(cells)
        return LayoutBlock(
            type="table", source_ids=list(dict.fromkeys(ids)), caption=caption or None, headers=headers, rows=rows
        )

    blocks = [block(item) for item in layout.blocks]
    if actual != expected:
        raise ValueError("Source ranges overlap, omit, or change reading order")
    _validate_layout(DocumentLayout(blocks=blocks), request.sources)
    counter = [0]
    result = NormalizedDocument(
        document_id=request.document_id,
        revision=request.revision,
        document_type=request.document_type,
        blocks=[_materialize(item, counter) for item in blocks],
    )
    result.validate_sources(request.sources)
    return result
