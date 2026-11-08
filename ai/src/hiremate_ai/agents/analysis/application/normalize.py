"""Page-based document normalization under the agreed JSON policy."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

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
    text: str
    pages: list[int]
    items: list["ListItemProposal"] = Field(default_factory=list)


class SectionProposal(PolicyModel):
    type: Literal["section"]
    title: str | None
    pages: list[int]
    blocks: list["BlockProposal"]


class ParagraphProposal(PolicyModel):
    type: Literal["paragraph"]
    pages: list[int]
    text: str


class ListProposal(PolicyModel):
    type: Literal["list"]
    pages: list[int]
    items: list[ListItemProposal]


class TableProposal(PolicyModel):
    type: Literal["table"]
    pages: list[int]
    title: str | None
    headers: list[str]
    rows: list[list[str]]
    reconstruction: Literal["inferred"]


class VisualNoticeProposal(PolicyModel):
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


class LayoutProposal(PolicyModel):
    title: str | None
    blocks: list[BlockProposal]


class CleanedStrings(PolicyModel):
    values: list[str]


SYSTEM = f"""지원자가 제출한 PDF의 페이지별 추출 텍스트와 위치 단서를 공통 JSON으로 정리한다.
요약하거나 평가하지 말고 문장, 숫자, 단위, 날짜, 고유명사, URL과 경험 및 계획의 구분을 최대한 보존한다.
위치는 읽기 순서와 단 구분의 단서이며, 이미지와 폼 객체 수는 실제로 표시된 시각 자료의 수가 아니다.
본문과 표 설명, 출처, 서명은 유지하고 반복 머리글, 장식 머리표와 실제 값 없는 양식은 생략할 수 있다.
한 행에 입력된 항목과 빈 항목이 섞여 있으면 각각 판단한다. 0, 없음, 해당 없음과 http://는 보존한다.
섹션을 중첩할 수 있다. 제목이 없으면 null이다. 블록과 목록 항목의 페이지 번호를 적고 불명확하면 빈 배열을 쓴다.
표의 관계가 불확실하면 억지로 만들지 말고 텍스트로 보존하고 원본 확인을 안내한다. 표는 reconstruction을 inferred로 쓴다.
코드와 수식은 문단에 보존하고 여러 줄 코드 옆에 원본의 들여쓰기와 줄바꿈을 확인하라는 visual_notice를 둔다.
시각 자료는 단서가 있을 때만 안내하고 세부 내용이나 종류를 지어내지 않는다. 위치가 불명확하면 unknown으로 둔다.
표지의 폼 객체만으로는 안내하지 않으며 얼굴 사진과 사진 자리는 안내하지 않는다.
여러 시각 자료의 종류를 구별할 수 없으면 원본 확인을 안내한다. 시각 안내는 사실 주장이 아니며 detection은 suspected다.
같은 줄이나 페이지 경계에 있는 독립 항목은 임의로 합치지 않는다. 반복된 내용을 삭제하지 않는다.
{UNTRUSTED_RULE}"""


async def normalize_document(llm: LlmClient, request: DocumentNormalizationRequest) -> NormalizedDocument:
    if not request.pages or [page.number for page in request.pages] != list(range(1, len(request.pages) + 1)):
        raise ValueError("정제할 페이지 정보가 없거나 순서가 올바르지 않다")
    if any("PAGE_EXTRACTION_FAILED" in page.issues for page in request.pages):
        raise ValueError("페이지 추출에 실패했다")
    if not any(page.text.strip() for page in request.pages):
        raise ValueError("추출된 텍스트가 없다")
    page_count = len(request.pages)
    payload = json.dumps([page.model_dump(mode="json", by_alias=True) for page in request.pages], ensure_ascii=False)
    with model_call_budget(settings.llm_agent_max_calls):
        proposal = await llm.structured(
            LayoutProposal, agent="application.normalize", system=SYSTEM, user=data_block("pdf_pages", payload)
        )
        if not proposal.blocks:
            raise ValueError("정제된 문서에 내용이 없다")
        data = proposal.model_dump(mode="json", by_alias=True)
        _validate_pages(data, page_count)
        strings: list[tuple[Any, Any]] = []
        _collect_strings(data, strings)
        values = [container[key] for container, key in strings]
        if values:
            corrected = await llm.structured(
                CleanedStrings,
                agent="application.normalize.characters",
                system=(
                    "각 문자열의 U+00B7 기호를 문맥에 맞는 연결 표현으로 정리한다. "
                    "순서와 개수를 유지하고 다른 내용은 바꾸지 않는다. " + UNTRUSTED_RULE
                ),
                user=data_block("strings", json.dumps(values, ensure_ascii=False)),
            )
            if len(corrected.values) != len(strings) or any("\u00b7" in value for value in corrected.values):
                raise ValueError("정제 문자열의 형식이 올바르지 않다")
            for (container, key), value in zip(strings, corrected.values, strict=True):
                container[key] = value
    count = [0]
    for block in data["blocks"]:
        _assign_ids(block, count)
    return NormalizedDocument(
        document=DocumentMetadata(
            id=request.document_id,
            type=request.document_type.value.lower(),
            title=data["title"],
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


def _assign_ids(value: dict, counter: list[int]) -> None:
    counter[0] += 1
    value["id"] = f"block-{counter[0]:04d}"
    for child in value.get("blocks", []):
        _assign_ids(child, counter)
    for child in value.get("items", []):
        _assign_ids(child, counter)
