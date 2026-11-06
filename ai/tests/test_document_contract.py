from uuid import uuid4

import pytest
from pydantic import ValidationError

from hiremate_ai.contract import DocumentNormalizationRequest, DocumentSource, NormalizedDocument


def document() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "documentId": str(uuid4()),
        "revision": 1,
        "documentType": "RESUME",
        "blocks": [{"id": "b1", "type": "paragraph", "sourceIds": ["s1"], "role": "body", "text": "개발"}],
    }


def test_source_validation() -> None:
    parsed = NormalizedDocument.model_validate(document())
    parsed.validate_sources([DocumentSource(id="s1", page=1, text="개발")])
    with pytest.raises(ValueError):
        parsed.validate_sources([])


@pytest.mark.parametrize("field,value", [("schemaVersion", 2), ("revision", 0), ("documentType", "CERTIFICATE")])
def test_invalid_metadata(field: str, value: object) -> None:
    data = document()
    data[field] = value
    with pytest.raises(ValidationError):
        NormalizedDocument.model_validate(data)


def test_duplicate_block_ids() -> None:
    data = document()
    data["blocks"] = [data["blocks"][0], data["blocks"][0]]  # type: ignore[index]
    with pytest.raises(ValidationError):
        NormalizedDocument.model_validate(data)


def test_request_rejects_duplicate_sources() -> None:
    with pytest.raises(ValidationError):
        DocumentNormalizationRequest(
            company_id=uuid4(),
            recruitment_id=uuid4(),
            application_id=uuid4(),
            document_id=uuid4(),
            revision=1,
            document_type="RESUME",
            sources=[DocumentSource(id="s1", page=None, text="a"), DocumentSource(id="s1", page=None, text="b")],
        )


@pytest.mark.parametrize(
    "block",
    [
        {"type": "unknown"},
        {"type": "paragraph", "role": "unknown", "text": "a"},
        {"type": "section", "title": None, "blocks": []},
        {"type": "reference", "kind": "unknown", "text": None, "notice": "a"},
        {"type": "reference", "kind": "possible_visual", "text": None, "notice": "generated"},
    ],
)
def test_invalid_blocks(block: dict[str, object]) -> None:
    data = document()
    data["blocks"] = [{"id": "b1", "sourceIds": ["s1"], **block}]
    with pytest.raises(ValidationError):
        NormalizedDocument.model_validate(data)
