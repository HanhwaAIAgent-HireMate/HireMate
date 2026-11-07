import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from hiremate_ai.agents.generation.posting.poster_image import generate_local_banner
from hiremate_ai.config import settings
from hiremate_ai.llm.client import release_local_poster_model


async def test_unconfigured_local_image_does_not_start_process(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "poster_local_python", "")
    assert await generate_local_banner("photo") is None


async def test_only_local_ollama_weights_are_released(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url == "http://host.docker.internal:11434/api/generate"
        assert json.loads(request.content) == {"model": "gemma4:e4b", "keep_alive": 0}
        return httpx.Response(200, json={"done": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(settings, "llm_base_url", "http://host.docker.internal:11434/v1")
    monkeypatch.setattr(settings, "llm_model", "gemma4:e4b")
    assert await release_local_poster_model()
    monkeypatch.setattr(settings, "llm_base_url", "https://api.openai.com/v1")
    assert not await release_local_poster_model()
    assert len(requests) == 1


async def test_local_image_is_cached_and_concurrent_requests_share_one_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(settings, "poster_local_python", "/local/python")
    monkeypatch.setattr(settings, "poster_local_model_path", str(tmp_path / "model"))
    monkeypatch.setattr(settings, "poster_local_image_cache", str(tmp_path / "images"))

    class Process:
        returncode: int | None = None

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            request = json.loads(data)
            assert request["model"] == str(tmp_path / "model")
            assert "api_key" not in request
            await asyncio.sleep(0.01)
            await asyncio.to_thread(Path(request["output"]).write_bytes, b"\xff\xd8image\xff\xd9")
            self.returncode = 0
            return b"", b""

    async def spawn(*args: str, **kwargs: Any) -> Process:
        calls.append(args)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    first, second = await asyncio.gather(generate_local_banner("photo"), generate_local_banner("photo"))
    assert first and first == second
    assert len(calls) == 1
    assert calls[0][0] == "/local/python"
    assert await generate_local_banner("illustration")
    assert len(calls) == 2


async def test_timeout_kills_local_process_without_calling_image_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "poster_local_python", "/local/python")
    monkeypatch.setattr(settings, "poster_local_model_path", str(tmp_path))
    monkeypatch.setattr(settings, "poster_local_image_cache", str(tmp_path))
    monkeypatch.setattr(settings, "poster_local_image_timeout", 0.01)

    class Process:
        returncode: int | None = None
        killed = False

        async def communicate(self, data: bytes) -> tuple[bytes, bytes]:
            await asyncio.sleep(10)
            return b"", b""

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        async def wait(self) -> int:
            return -9

    process = Process()

    async def spawn(*args: str, **kwargs: Any) -> Process:
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    assert await generate_local_banner("photo") is None
    assert process.killed
