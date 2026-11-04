import httpx
import pytest

from hiremate_ai.agents.generation.posting.free_templates import safe_svg, search_free_templates

SAMPLE = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 800"><rect width="600" height="800" fill="#fff"/></svg>'
)


def test_svg_removes_executable_and_external_content() -> None:
    unsafe = b"""<svg xmlns="http://www.w3.org/2000/svg" onload="attack()">
        <script>attack()</script><foreignObject/><image href="http://localhost/private"/>
        <style>@import url(https://attacker.invalid)</style><rect style="fill:url(http://localhost)" fill="url(https://attacker.invalid)"/>
    </svg>"""
    cleaned = safe_svg(unsafe)
    assert "script" not in cleaned
    assert "foreignObject" not in cleaned
    assert "image" not in cleaned
    assert "onload" not in cleaned
    assert "localhost" not in cleaned
    assert "attacker" not in cleaned


@pytest.mark.parametrize("content", [b"<!DOCTYPE svg><svg/>", b'<!ENTITY x "secret">', b"x" * 100001])
def test_svg_rejects_unsafe_documents(content: bytes) -> None:
    with pytest.raises(ValueError):
        safe_svg(content)


async def test_search_uses_only_fixed_free_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = []

    async def send(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        assert "api-key" not in str(request.headers)
        return httpx.Response(200, content=SAMPLE)

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(send), **kwargs))
    result = await search_free_templates("finance bank https://localhost/private")
    assert len(result) == 2
    assert result[0].id == "inkscape-frame"
    assert all(url.startswith("https://inkscape.de/vorlagen/") for url in urls)
    assert all(item.license == "CC0 1.0" for item in result)


async def test_unavailable_provider_does_not_invent_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def send(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(send), **kwargs))
    assert await search_free_templates("finance") == []
