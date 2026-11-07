"""Evaluate synthetic document structure separately from source preservation.

The expectations are deliberately explicit, not inferred from a model output.
This is a small diagnostic sample, not a representative production benchmark.
"""

import re
from typing import Any

from eval.document_quality_gold import ExpectedBlock, QualityCase
from hiremate_ai.contract import DocumentSource, NormalizedDocument


def _compact(value: str) -> str:
    return re.sub(r"\s", "", value)


def _list_text(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        ((item["marker"] + " ") if item.get("marker") else "") + item["text"] + _list_text(item["children"])
        for item in items
    )


def _gaps(text: str) -> list[str]:
    positions = [match.start() for match in re.finditer(r"\S", text)]
    return [text[left + 1 : right] for left, right in zip(positions, positions[1:], strict=False)]


def _text(block: dict[str, Any]) -> str:
    match block["type"]:
        case "section":
            return block.get("title") or ""
        case "paragraph":
            return block["text"]
        case "list":
            return _list_text(block["items"])
        case "table":
            return "\n".join(
                [block.get("caption") or ""]
                + [cell or "" for cell in block["headers"]]
                + [cell or "" for row in block["rows"] for cell in row]
            )
        case "reference":
            return block.get("text") or ""
        case _:
            raise ValueError("Unknown block type")


def _list_fields(items: list[dict[str, Any]]) -> list[str]:
    return [
        field for item in items for field in [item.get("marker") or "", item["text"], *_list_fields(item["children"])]
    ]


def _word_fields(block: dict[str, Any]) -> list[str]:
    if block["type"] in {"paragraph", "section", "reference"}:
        return [_text(block)]
    if block["type"] == "list":
        return _list_fields(block["items"])
    if block["type"] == "table":
        return [block.get("caption") or "", *(cell or "" for cell in block["headers"])] + [
            cell or "" for row in block["rows"] for cell in row
        ]
    return []


def _walk(
    blocks: list[dict[str, Any]], parent: tuple[str | None, ...] = ()
) -> list[tuple[dict[str, Any], tuple[str | None, ...]]]:
    result = []
    for block in blocks:
        result.append((block, parent))
        if block["type"] == "section":
            result.extend(_walk(block["blocks"], (*parent, block.get("title"))))
    return result


def _matches(expected: ExpectedBlock, block: dict[str, Any], parent: tuple[str | None, ...]) -> bool:
    parent_matches = not parent if expected.parent is None else bool(parent) and parent[-1] == expected.parent
    if block["type"] != expected.type or not parent_matches:
        return False
    if expected.type == "section":
        return block.get("title") == expected.value
    if expected.type == "paragraph":
        return block.get("text") == expected.value and block.get("role") == expected.role
    if expected.type == "reference":
        return block.get("kind") == expected.role and (block.get("text") or "") == expected.value
    if expected.type == "list":
        return "|".join(item["text"] for item in block["items"]) == expected.value
    if expected.type == "table":
        rows = [block["headers"], *block["rows"]]
        return ";".join("|".join(cell or "" for cell in row) for row in rows) == expected.value
    return False


def evaluate(case: QualityCase, sources: list[DocumentSource], document: NormalizedDocument) -> dict[str, Any]:
    """Compare with human-authored checks and actual parser sources.

    Code examples are explicitly excluded from source-text equality because the
    public JSON intentionally omits code. None means unverified, not passed.
    """
    blocks = _walk(document.model_dump(mode="json", by_alias=True)["blocks"])
    known_ids = {source.id for source in sources}
    source_chars = "".join(_compact(source.text) for source in sources)
    provenance = [source.id for source in sources for _ in _compact(source.text)]
    output_chars = "".join(_compact(_text(block)) for block, _ in blocks)
    has_code = any(block["type"] == "reference" and block.get("kind") == "code_example" for block, _ in blocks)
    all_ids_known = all(set(block["sourceIds"]).issubset(known_ids) for block, _ in blocks)
    content_matches = bool(source_chars) and source_chars == output_chars if not has_code else None
    numbers = r"\d+(?:[.,]\d+)*"
    source_numbers = re.findall(numbers, "\n".join(source.text for source in sources))
    output_numbers = re.findall(numbers, "\n".join(_text(block) for block, _ in blocks))
    numeric_matches = source_numbers == output_numbers if not has_code else None
    single_space_matches = None
    source_word_matches = None
    if content_matches:
        source_gaps = _gaps("\n".join(source.text for source in sources))
        output_gaps = _gaps("\n".join(_text(block) for block, _ in blocks))
        single_space_matches = all(
            before != " " or bool(after) for before, after in zip(source_gaps, output_gaps, strict=True)
        )
        source_word_matches = True
        offset = 0
        for block, _ in blocks:
            if _compact(_text(block)) and offset and not source_gaps[offset - 1]:
                source_word_matches = False
            field_offset = offset
            for field in _word_fields(block):
                length = len(_compact(field))
                if (
                    length
                    and field_offset > 0
                    and not source_gaps[field_offset - 1]
                    and (
                        (block["type"] == "table" and field_offset > offset)
                        or (source_chars[field_offset - 1].isalnum() and source_chars[field_offset].isalnum())
                    )
                ):
                    source_word_matches = False
                if length > 1:
                    gaps = source_gaps[field_offset : field_offset + length - 1]
                    if any(not before and after for before, after in zip(gaps, _gaps(field), strict=True)):
                        source_word_matches = False
                field_offset += length
            offset += len(_compact(_text(block)))
    position_matches = True
    cursor = 0
    for block, _ in blocks:
        end = cursor + len(_compact(_text(block)))
        expected_ids = list(dict.fromkeys(provenance[cursor:end]))
        if block["sourceIds"] != expected_ids:
            position_matches = False
        cursor = end
    provenance_matches = (
        all_ids_known and position_matches and bool(content_matches)
        if not has_code
        else (None if all_ids_known else False)
    )
    type_matches = document.document_type == case.document_type
    required_checks: bool | None = (
        bool(
            type_matches
            and content_matches
            and numeric_matches
            and single_space_matches
            and source_word_matches
            and provenance_matches
        )
        if not has_code
        else (None if type_matches and all_ids_known else False)
    )

    used: set[int] = set()
    checks = []
    for expected in case.expected_blocks:
        match = next(
            (
                index
                for index, (block, parent) in enumerate(blocks)
                if index not in used and _matches(expected, block, parent)
            ),
            None,
        )
        if match is not None:
            used.add(match)
        checks.append(
            {"type": expected.type, "value": expected.value, "parent": expected.parent, "pass": match is not None}
        )

    cursor = 0
    reading_order_matches = True
    for text in case.reading_order:
        position = output_chars.find(_compact(text), cursor)
        if position < 0:
            reading_order_matches = False
            break
        cursor = position + len(_compact(text))
    return {
        "document_type_matches": type_matches,
        "source_content_matches": content_matches,
        "source_numeric_matches": numeric_matches,
        "single_space_matches": single_space_matches,
        "source_word_matches": source_word_matches,
        "source_provenance_matches": provenance_matches,
        "all_source_ids_known": all_ids_known,
        "required_checks_pass": required_checks,
        "pdf_reading_order_matches": reading_order_matches if case.pages and not has_code else None,
        "structure_passed": sum(check["pass"] for check in checks),
        "structure_total": len(checks),
        "structure_checks": checks,
    }
