"""이미지 API를 호출하지 않고 로컬 GPU 프로세스로 배너를 만든다."""

import asyncio
import base64
import hashlib
import json
import logging
from pathlib import Path

from hiremate_ai.config import settings
from hiremate_ai.llm.client import release_local_poster_model

logger = logging.getLogger(__name__)
_image_lock = asyncio.Lock()


def _read_banner(path: Path) -> str | None:
    if not path.is_file() or not 4 <= path.stat().st_size <= 93000:
        return None
    data = path.read_bytes()
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        return None
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


async def generate_local_banner(prompt: str) -> str | None:
    if not settings.poster_local_model_path or not settings.poster_local_python:
        return None
    payload = {
        "model": str(await asyncio.to_thread(Path(settings.poster_local_model_path).resolve)),
        "prompt": prompt,
        "width": 1024,
        "height": 640,
        "steps": 9,
        "seed": 42,
        "version": 1,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    cache = await asyncio.to_thread(Path(settings.poster_local_image_cache).resolve)
    output = cache / f"{digest}.jpg"
    runner = Path(__file__).with_name("poster_local_image.py")
    process: asyncio.subprocess.Process | None = None
    try:
        # 메모리 부족을 피하고, 같은 배너의 중복 생성을 막는다. 대기 시간도 제한에 포함한다.
        async with asyncio.timeout(settings.poster_local_image_timeout), _image_lock:
            cached = await asyncio.to_thread(_read_banner, output)
            if cached:
                return cached
            if settings.poster_local_release_ollama and not await release_local_poster_model():
                logger.warning("로컬 언어 모델의 GPU 메모리를 확보하지 못했습니다.")
                return None
            await asyncio.to_thread(cache.mkdir, parents=True, exist_ok=True)
            payload["output"] = str(output)
            with output.with_suffix(".log").open("wb") as log:
                process = await asyncio.create_subprocess_exec(
                    settings.poster_local_python,
                    "-I",
                    str(runner),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=log,
                    stderr=asyncio.subprocess.STDOUT,
                )
                await process.communicate(json.dumps(payload).encode())
            if process.returncode != 0:
                logger.warning("로컬 포스터 이미지 생성 실패 (exit=%s)", process.returncode)
                return None
            return await asyncio.to_thread(_read_banner, output)
    except (OSError, TimeoutError):
        logger.warning("로컬 포스터 이미지 생성 실행 실패 또는 시간 초과")
        return None
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
