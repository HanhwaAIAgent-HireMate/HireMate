"""검증한 CC0 제공처의 SVG만 가져온다. API 키나 유료 다운로드를 사용하지 않는다."""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from hiremate_ai.agents.generation.posting.poster import FreePosterTemplate

SVG = "http://www.w3.org/2000/svg"
MAX_BYTES = 100000
ALLOWED = {
    "svg",
    "g",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "path",
    "text",
    "tspan",
    "defs",
    "linearGradient",
    "radialGradient",
    "stop",
    "clipPath",
    "title",
    "desc",
}


@dataclass(frozen=True)
class FreeSource:
    id: str
    name: str
    filename: str
    keywords: str


SOURCES = (
    FreeSource(
        "inkscape-frame",
        "이중 프레임형",
        "vorlage-einladung-a6.svg",
        "금융 은행 신뢰 금융권 finance bank trust frame corporate business",
    ),
    FreeSource(
        "inkscape-a4", "A4 세로 기본 양식", "vorlage-a4-hoch.svg", "세로 채용 공고 poster portrait recruitment minimal"
    ),
    FreeSource("inkscape-a5", "A5 가로 기본 양식", "vorlage-a5-quer.svg", "가로 안내 flyer landscape notice"),
)


def safe_svg(value: bytes) -> str:
    """실행 요소·외부 링크·스타일시트를 제거한 작은 SVG만 클라이언트에 전달한다."""
    if len(value) > MAX_BYTES or b"<!DOCTYPE" in value.upper() or b"<!ENTITY" in value.upper():
        raise ValueError("Unsupported SVG")
    root = ET.fromstring(value)
    if root.tag != f"{{{SVG}}}svg":
        raise ValueError("Expected SVG")
    elements = list(root.iter())
    if len(elements) > 1000:
        raise ValueError("SVG has too many elements")
    for parent in elements:
        for child in list(parent):
            if child.tag.rsplit("}", 1)[-1] not in ALLOWED:
                parent.remove(child)
        for key, item in list(parent.attrib.items()):
            local = key.rsplit("}", 1)[-1].lower()
            if (
                local.startswith("on")
                or local in {"href", "style", "src"}
                or ("url(" in item.lower() and not re.fullmatch(r"url\(#[\w-]+\)", item))
            ):
                del parent.attrib[key]
    ET.register_namespace("", SVG)
    return ET.tostring(root, encoding="unicode")


async def search_free_templates(query: str, selected_id: str | None = None) -> list[FreePosterTemplate]:
    """검색어는 모델이 정한 명시적 검색 조건이다. 검색 범위는 이 무료 제공처의 세 양식이다."""
    words = set(query.lower().split())
    ranked = sorted(SOURCES, key=lambda source: -len(words & set(source.keywords.split())))[:2]
    if selected_id:
        ranked = [source for source in SOURCES if source.id == selected_id]
    found = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        for source in ranked:
            try:
                # URL은 사용자나 모델이 지정하지 못한다. 검증한 고정 제공처만 읽는다.
                url = f"https://inkscape.de/vorlagen/{source.filename}"
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise ValueError("SVG too large")
                found.append(
                    FreePosterTemplate(
                        id=source.id,
                        name=source.name,
                        source_url="https://inkscape.de/vorlagen/",
                        license="CC0 1.0",
                        svg=safe_svg(bytes(data)),
                    )
                )
            except (httpx.HTTPError, ValueError, ET.ParseError):
                continue
    return found
