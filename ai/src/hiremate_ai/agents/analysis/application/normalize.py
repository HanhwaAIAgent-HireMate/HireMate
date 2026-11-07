"""Lossless source-local document layout normalization with trusted identities."""

import ast
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from hiremate_ai.config import settings
from hiremate_ai.contract import (
    CODE_NOTICE,
    VISUAL_NOTICE,
    DocumentBlock,
    DocumentListItem,
    DocumentNormalizationRequest,
    DocumentSource,
    NormalizedDocument,
    ParagraphRole,
)
from hiremate_ai.llm.chat import model_call_budget
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.prompt import UNTRUSTED_RULE, data_block

# The request's model budget remains active across every bounded call.
MAX_SOURCE_CHARS = 6000
VERBATIM_PARAGRAPH_CHARS = 300
"""원문 그대로 저장할 때 문단 하나에 묶는 글자 수. 인용할 때 출처가 너무 넓어지지 않게 한다."""


class LayoutBlock(BaseModel):
    """Layout proposal without model-controlled identity or generated notices."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    type: Literal["section", "paragraph", "list", "table", "reference"]
    source_ids: list[str] = Field(alias="sourceIds")
    title: str | None = None
    blocks: list["LayoutBlock"] | None = None
    role: ParagraphRole | None = None
    text: str | None = None
    items: list[DocumentListItem] | None = None
    caption: str | None = None
    headers: list[str | None] | None = None
    rows: list[list[str | None]] | None = None
    kind: Literal["possible_visual", "code_example"] | None = None
    code_text: str | None = Field(default=None, alias="codeText")


class DocumentLayout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocks: list[LayoutBlock]


SYSTEM = f"""지원 문서 원문 조각을 요약 없이 읽는 순서대로 JSON 블록으로 정리한다.
모든 글자와 숫자, 문장 순서를 보존한다. 공백과 줄바꿈만 정리할 수 있다.
sourceIds에는 해당 내용에 실제로 걸친 연속 원문 조각 ID를 순서대로 쓴다. 여러 줄을 합쳐도 출처를 모두 붙인다.
section 출처는 제목의 출처이며 제목이 없으면 빈 배열이다.
목록 marker도 원문 그대로 두고 children은 빈 배열이라도 넣는다.
표는 caption, headers, rows 순서로 읽어 원문과 일치할 때만 만든다.
추측이 필요하면 원문 그대로 paragraph를 쓴다. 짧은 기술 표현과 코드 설명은 본문으로 유지한다.
실제 Python, JavaScript, TypeScript, Java 코드 덩어리만 code_example으로 바꿀 수 있다.
codeText에는 생략할 코드 원문을 그대로 넣고 reference text는 null로 둔다. 코드 앞뒤 설명은 별도 paragraph로 보존한다.
시각 자료는 읽힌 제목과 설명을 text로 전부 남긴다. 없는 내용을 복원하지 않는다.
ID와 안내문은 코드가 부여한다. 각 type의 필드만 출력한다.
{UNTRUSTED_RULE}"""


def _compact(text: str) -> str:
    return re.sub(r"\s", "", text)


def _code_only(text: str) -> bool:
    """Require actual syntax, never merely technical vocabulary or a prose fence."""
    fenced = re.fullmatch(r"\s*```[\w+-]*\s*\n(.*?)\n```\s*", text, re.DOTALL)
    code = fenced[1] if fenced else text
    try:
        program = ast.parse(code)
    except SyntaxError:
        program = None
    if (
        program
        and (fenced or "\n" in code.strip())
        and any(not isinstance(node, ast.Expr) for node in program.body)
        and not any(isinstance(node, ast.AnnAssign) and node.value is None for node in ast.walk(program))
        and not any(
            isinstance(node, ast.Expr) and not isinstance(node.value, (ast.Call, ast.Await, ast.Yield, ast.YieldFrom))
            for node in ast.walk(program)
        )
    ):
        return True
    # Remove actual quoted literals before comments so URLs and comment markers
    # inside strings cannot alter the lexical checks.
    lexical = re.sub(r"'(?:(?:\\.)|[^'\\])*'|\"(?:(?:\\.)|[^\"\\])*\"|`(?:(?:\\.)|[^`\\])*`", "__literal__", code)
    lexical = re.sub(r"/\*.*?\*/", "", lexical, flags=re.DOTALL)
    lexical = re.sub(r"//[^\n]*", "", lexical)
    if "/*" in lexical or "*/" in lexical:
        return False
    lines = [line.strip() for line in lexical.splitlines() if line.strip()]
    keywords = {
        "const",
        "let",
        "var",
        "return",
        "throw",
        "new",
        "class",
        "interface",
        "type",
        "enum",
        "export",
        "default",
        "async",
        "function",
        "public",
        "private",
        "protected",
        "static",
        "abstract",
        "readonly",
        "extends",
        "implements",
        "import",
        "from",
        "as",
        "keyof",
        "typeof",
    }
    brace_depth = 0
    for line in lines:
        if brace_depth <= 0 and re.match(r"^[A-Za-z_$][\w$]*\??\s*:", line):
            return False
        brace_depth += line.count("{") - line.count("}")
        # Ordinary prose has adjacent words without code operators. Do not
        # exempt it just because a preceding line contained a declaration.
        tokens = list(re.finditer(r"[A-Za-z_$][\w$]*", line))
        for left, right in zip(tokens, tokens[1:], strict=False):
            gap = line[left.end() : right.start()]
            if (
                gap.isspace()
                and left[0] not in keywords
                and right[0] not in {"as", "extends", "implements"}
                and not line[right.end() :].lstrip().startswith("(")
            ):
                return False

    # Brace languages need a declaration plus only syntactic statement lines.
    declaration = re.compile(
        r"^(?:(?:export|public|private|static|async|abstract)\s+)*"
        r"(?:(?:const|let|var|type)\s+\w+\s*[:=]|function\s+\w+\s*\("
        r"|(?:class|interface|enum)\s+\w+(?:\s+extends\s+\w+)?\s*[<{])"
        r"|^(?:public|private|protected)\s+\w+[<\w>, ?\[\]]*\s+\w+\s*[({=]"
    )
    syntax = re.compile(r"^[{}()[\];,]+$|^(?:return|throw|import|from)\b.*[;{]$|^[\w.$]+\s*(?:[:=(]).*[;{},]$")
    return (
        bool(lines)
        and any(declaration.match(line) for line in lines)
        and all(declaration.match(line) or syntax.match(line) or _code_line(line) for line in lines)
    )


def _code_line(line: str) -> bool:
    """Recognize continuation syntax around an independently required declaration."""
    if line in {"unknown", "string", "number", "boolean", "void", "any", "never"}:
        return True
    return bool(
        re.fullmatch(
            r"(?:['\"][^'\"]+['\"]|[A-Za-z_$][\w.$]*)(?:\??\s*[:=(<\[|].*|\s*[,;])"
            r"|(?:if|else|for|while|switch|catch)\s*\(.*"
            r"|[})\]>,;|]+(?:\s*=>.*)?",
            line,
        )
    )


def _list_text(items: list[DocumentListItem]) -> str:
    return "\n".join((item.marker or "") + item.text + "\n" + _list_text(item.children) for item in items)


def _segments(proposal: LayoutBlock) -> list[tuple[str, LayoutBlock]]:
    if proposal.type == "section":
        own = [(proposal.title, proposal)] if proposal.title is not None else []
        if proposal.title is None and proposal.source_ids:
            raise ValueError("Untitled section has title provenance")
        return own + [segment for child in proposal.blocks or [] for segment in _segments(child)]
    if proposal.type == "reference" and proposal.kind == "code_example":
        if proposal.text is not None or proposal.code_text is None or not _code_only(proposal.code_text):
            raise ValueError("Code reference requires verified verbatim codeText")
        return [(proposal.code_text, proposal)]
    if proposal.code_text is not None:
        raise ValueError("codeText is only allowed on code references")
    if proposal.type == "list":
        text = _list_text(proposal.items or [])
    elif proposal.type == "table":
        text = (
            (proposal.caption or "")
            + "\n"
            + " ".join(cell or "" for cell in proposal.headers or [])
            + "\n"
            + " ".join(cell or "" for row in proposal.rows or [] for cell in row)
        )
    else:
        text = proposal.text or ""
    return [(text, proposal)]


def _validate_layout(layout: DocumentLayout, sources: list[DocumentSource]) -> None:
    """Reject any changed character or unknown source, then set provenance from position.

    Text matches the sources exactly, so each block's sources follow from where it
    sits. A model that names a neighboring real source does not change the content.
    """
    known = {source.id for source in sources}
    original = "".join(_compact(source.text) for source in sources)
    provenance = [source.id for source in sources for _ in _compact(source.text)]
    cursor = 0
    rendered: list[str] = []
    for proposal in layout.blocks:
        for text, block in _segments(proposal):
            rendered.append(text)
            content = _compact(text)
            if not content:
                raise ValueError("Content blocks require source-backed content")
            end = cursor + len(content)
            if content != original[cursor:end] or not known.issuperset(block.source_ids):
                raise ValueError("Content or per-source provenance changed")
            block.source_ids = list(dict.fromkeys(provenance[cursor:end]))
            cursor = end
    numeric = r"\d+(?:[.,]\d+)*"
    if re.findall(numeric, "\n".join(source.text for source in sources)) != re.findall(numeric, "\n".join(rendered)):
        raise ValueError("Numeric values changed")
    if not layout.blocks or cursor != len(original):
        raise ValueError("Source content was omitted")


def _safe_cut(text: str, limit: int) -> int:
    if len(text) <= limit:
        return len(text)
    end = limit
    # Keep numeric values intact, including decimal/grouping punctuation.
    # ASCII word runs also remain intact where possible. Unsegmented scripts
    # may split at a character boundary without dropping source characters.
    for match in re.finditer(r"\d+(?:[.,]\d+)*|[A-Za-z_]+", text):
        if match.start() < end < match.end():
            end = match.start()
            break
        if match.start() >= end:
            break
    whitespace = [match.end() for match in re.finditer(r"\s+", text[:end])]
    if whitespace and whitespace[-1] >= limit // 2:
        end = whitespace[-1]
    return end


def _batches(sources: list[DocumentSource]) -> list[list[DocumentSource]]:
    batches: list[list[DocumentSource]] = []
    current: list[DocumentSource] = []
    size = 0
    for source in sources:
        remaining = source.text
        while remaining:
            if size == MAX_SOURCE_CHARS or len(current) >= 64:
                batches.append(current)
                current, size = [], 0
            end = _safe_cut(remaining, MAX_SOURCE_CHARS - size)
            if end == 0:
                if not current:
                    raise ValueError("An indivisible source token exceeds the batch limit")
                batches.append(current)
                current, size = [], 0
                continue
            part, remaining = remaining[:end], remaining[end:]
            current.append(DocumentSource(id=source.id, page=source.page, text=part))
            size += len(part)
    if current:
        batches.append(current)
    return batches


def _materialize(proposal: LayoutBlock, counter: list[int]) -> DocumentBlock:
    allowed = {
        "section": {"title"},
        "paragraph": {"role", "text"},
        "list": {"items"},
        "table": {"caption", "headers", "rows"},
        "reference": {"kind", "text"},
    }[proposal.type] | {"type", "sourceIds"}
    supplied = proposal.model_dump(exclude_unset=True, by_alias=True, exclude={"blocks", "code_text"})
    if any(value is not None for key, value in supplied.items() if key not in allowed):
        raise ValueError("Unexpected content fields for block type")
    data = {key: value for key, value in supplied.items() if key in allowed}
    counter[0] += 1
    data["id"] = f"b{counter[0]:06d}"
    if proposal.type == "section":
        if proposal.blocks is None:
            raise ValueError("Section children are required")
        data["blocks"] = [_materialize(child, counter) for child in proposal.blocks]
    if proposal.type == "reference":
        data["notice"] = CODE_NOTICE if proposal.kind == "code_example" else VISUAL_NOTICE
    return TypeAdapter(DocumentBlock).validate_python(data)


async def normalize_document(llm: LlmClient, request: DocumentNormalizationRequest) -> NormalizedDocument:
    """Return a complete validated layout or fail without producing partial output.

    Each bounded ordered source batch is checked in sequence. Exact character
    order, ignoring whitespace, prevents source substitution and invented claims.
    Original source IDs remain unchanged even when a long source needs several calls.
    """
    blocks: list[DocumentBlock] = []
    counter = [0]
    with model_call_budget(settings.llm_agent_max_calls):
        for batch in _batches(request.sources):
            layout = await llm.structured(
                DocumentLayout,
                agent="application.normalize",
                system=SYSTEM,
                user="\n".join(
                    data_block("document_source", source.text, id=source.id, page=str(source.page)) for source in batch
                ),
            )
            _validate_layout(layout, batch)
            blocks.extend(_materialize(block, counter) for block in layout.blocks)
    result = NormalizedDocument(
        document_id=request.document_id,
        revision=request.revision,
        document_type=request.document_type,
        blocks=blocks,
    )
    result.validate_sources(request.sources)
    return result


def _verbatim_blocks(sources: list[DocumentSource]) -> list[LayoutBlock]:
    groups: list[list[DocumentSource]] = []
    for source in sources:
        if not _compact(source.text):
            continue
        last = groups[-1] if groups else None
        size = sum(len(item.text) for item in last) if last else 0
        if last and last[0].page == source.page and size + len(source.text) <= VERBATIM_PARAGRAPH_CHARS:
            last.append(source)
        else:
            groups.append([source])
    return [
        LayoutBlock(
            type="paragraph",
            source_ids=[source.id for source in group],
            role="body",
            text="\n".join(source.text for source in group),
        )
        for group in groups
    ]


def verbatim_document(request: DocumentNormalizationRequest) -> NormalizedDocument:
    """Keep the parser text as body paragraphs when no model layout passed validation.

    No model output is used, so nothing can be invented or dropped. Structure is
    lost, and the same checks as a model layout still apply before it is returned.
    """
    layout = DocumentLayout(blocks=_verbatim_blocks(request.sources))
    _validate_layout(layout, request.sources)
    counter = [0]
    result = NormalizedDocument(
        document_id=request.document_id,
        revision=request.revision,
        document_type=request.document_type,
        blocks=[_materialize(block, counter) for block in layout.blocks],
    )
    result.validate_sources(request.sources)
    return result
