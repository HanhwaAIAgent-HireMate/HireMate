"""정제 문서를 검색할 수 있는 단위로 나눈다."""

import re
from dataclasses import dataclass

from hiremate_ai.agents.guardrails import personal_fact
from hiremate_ai.contract import (
    DocumentBlock,
    DocumentList,
    DocumentListItem,
    DocumentParagraph,
    DocumentSection,
    DocumentTable,
    NormalizedDocument,
)

MAX_CHARS = 1200
_CONTACT = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?\d[\d\s()-]{7,}\d)")
_BOUNDARY = re.compile(r"(?<=[.!?。])\s+|\n+")


@dataclass(frozen=True)
class DocumentChunk:
    text: str
    evidence: str
    block_id: str
    pages: tuple[int, ...]


def document_chunks(document: NormalizedDocument, *, blind: bool, applicant_name: str) -> list[DocumentChunk]:
    """문맥은 임베딩에 넣고 근거와 페이지는 별도로 보존한다."""
    result: list[DocumentChunk] = []

    def safe(text: str) -> bool:
        return bool(text.strip()) and not (
            (applicant_name and applicant_name in text) or _CONTACT.search(text) or personal_fact(text, blind=blind)
        )

    def add(text: str, path: list[str], block_id: str, pages: list[int]) -> None:
        if not safe(text):
            return
        prefix = " > ".join(path)
        max_body = max(100, MAX_CHARS - len(prefix) - 1)
        for part in _split(text, max_body):
            value = f"{prefix}\n{part}" if prefix else part
            result.append(DocumentChunk(value, part, block_id, tuple(pages)))

    def items(values: list[DocumentListItem], path: list[str], parents: list[str]) -> None:
        for item in values:
            if not safe(item.text):
                continue
            add(" > ".join([*parents, item.text]), path, item.id, item.pages)
            items(item.items, path, [*parents, item.text])

    def visit(block: DocumentBlock, path: list[str]) -> None:
        if isinstance(block, DocumentSection):
            # 가리거나 검색할 수 없는 제목도 자식의 검색 문맥에 넣지 않는다.
            next_path = [*path, block.title] if block.title and safe(block.title) else path
            for child in block.blocks:
                visit(child, next_path)
        elif isinstance(block, DocumentParagraph):
            add(block.text, path, block.id, block.pages)
        elif isinstance(block, DocumentList):
            items(block.items, path, [])
        elif isinstance(block, DocumentTable):
            table_path = [*path, block.title] if block.title and safe(block.title) else path
            for row in block.rows:
                if not all(not cell or safe(cell) for cell in row):
                    continue
                if not all(not header or safe(header) for header in block.headers):
                    continue
                text = " | ".join(
                    f"{block.headers[i]}: {cell}" if i < len(block.headers) and block.headers[i] else cell
                    for i, cell in enumerate(row)
                    if cell
                )
                add(text, table_path, block.id, block.pages)

    title = document.document.title
    path = [title] if title and safe(title) else []
    for block in document.blocks:
        visit(block, path)
    return result


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + limit)
        if end < len(text):
            boundaries = list(_BOUNDARY.finditer(text, start, end))
            if boundaries:
                end = boundaries[-1].end()
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
    return parts
