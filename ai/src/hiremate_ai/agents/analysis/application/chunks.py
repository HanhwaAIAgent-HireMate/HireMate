"""Lossless normalized-document chunks with original block and source provenance."""

from dataclasses import dataclass, replace
from uuid import UUID

from hiremate_ai.contract import (
    DocumentBlock,
    DocumentList,
    DocumentListItem,
    DocumentParagraph,
    DocumentReference,
    DocumentSection,
    DocumentTable,
    NormalizedDocument,
)


@dataclass(frozen=True)
class DocumentChunk:
    document_id: UUID
    revision: int
    block_ids: list[str]
    section_path: list[str]
    source_ids: list[str]
    text: str
    prefix: str = ""

    @property
    def embedding_text(self) -> str:
        context = " > ".join(self.section_path)
        return f"{context}\n{self.text}" if context and self.text != self.section_path[-1] else self.text


def embedding_chunks(document: NormalizedDocument) -> list[DocumentChunk]:
    """Bound UTF-8 bytes below 512 byte-fallback tokens, including title context.

    Short context and table labels repeat on every part. Oversized context is
    split without dropping it; every part retains the full structured path.
    """
    result: list[DocumentChunk] = []
    for chunk in chunk_document(document):
        formatted = chunk.embedding_text
        body = chunk.text[len(chunk.prefix) :]
        prefix = formatted[: len(formatted) - len(body)] if body else formatted
        if len(prefix.encode("utf-8")) > 250:
            prefix, body = "", formatted
        capacity = 500 - len(prefix.encode("utf-8"))
        for part in _byte_parts(body, capacity):
            result.append(replace(chunk, text=prefix + part))
    return result


def _byte_parts(value: str, capacity: int) -> list[str]:
    parts: list[str] = []
    start = size = 0
    for index, character in enumerate(value):
        width = len(character.encode("utf-8"))
        if size + width > capacity:
            parts.append(value[start:index])
            start, size = index, 0
        size += width
    if start < len(value):
        parts.append(value[start:])
    return parts


def chunk_document(document: NormalizedDocument, *, max_chars: int = 1800) -> list[DocumentChunk]:
    """Split text without summarizing. Reject unbounded table labels explicitly."""
    if max_chars < 32:
        raise ValueError("Chunk size must be at least 32")
    chunks: list[DocumentChunk] = []

    def emit(block: DocumentBlock, text: str, path: list[str], sources: list[str], prefix: str = "") -> None:
        capacity = max_chars - len(prefix)
        if capacity < 1:
            raise ValueError("Table header or list marker exceeds chunk size")
        for start in range(0, len(text), capacity):
            chunks.append(
                DocumentChunk(
                    document.document_id,
                    document.revision,
                    [block.id],
                    path,
                    list(dict.fromkeys(sources + block.source_ids)),
                    prefix + text[start : start + capacity],
                    prefix,
                )
            )

    def items(
        block: DocumentList, values: list[DocumentListItem], path: list[str], sources: list[str], depth: int
    ) -> None:
        for item in values:
            prefix = "  " * depth + ((item.marker + " ") if item.marker else "")
            emit(block, item.text, path, sources, prefix)
            items(block, item.children, path, sources, depth + 1)

    def visit(blocks: list[DocumentBlock], path: list[str], sources: list[str]) -> None:
        for block in blocks:
            if isinstance(block, DocumentSection):
                next_path = path + ([block.title] if block.title is not None else [])
                if block.title is not None:
                    emit(block, block.title, next_path, sources)
                visit(block.blocks, next_path, list(dict.fromkeys(sources + block.source_ids)))
            elif isinstance(block, DocumentParagraph):
                if block.role in {"body", "caption"}:
                    emit(block, block.text, path, sources)
            elif isinstance(block, DocumentReference):
                if block.text:
                    emit(block, block.text, path, sources)
            elif isinstance(block, DocumentList):
                items(block, block.items, path, sources, 0)
            elif isinstance(block, DocumentTable):
                if block.caption:
                    emit(block, block.caption, path, sources)
                for header in block.headers:
                    if header:
                        emit(block, header, path, sources)
                for row_number, row in enumerate(block.rows, 1):
                    for column, cell in enumerate(row, 1):
                        header = block.headers[column - 1] if column <= len(block.headers) else None
                        prefix = f"행 {row_number} 열 {column} {header or ''}: "
                        if len(prefix) >= max_chars:
                            raise ValueError("Table header exceeds chunk size")
                        if cell is not None:
                            emit(block, cell, path, sources, prefix)

    visit(document.blocks, [], [])
    return chunks
