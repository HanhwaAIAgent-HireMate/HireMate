"""로컬 참고 색인을 검증해 생성 모델에 제공한다. URL은 자동으로 열지 않는다."""

import base64
import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from hiremate_ai.config import settings

logger = logging.getLogger(__name__)


class PosterReference(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    role: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1, max_length=250)
    designAdaptation: str = Field(min_length=1, max_length=600)
    postingUrl: str = Field(max_length=2000)


class PosterReferences(BaseModel):
    references: list[PosterReference] = Field(max_length=80)


def load_poster_references() -> list[PosterReference]:
    if not settings.poster_references_path:
        return []
    try:
        path = Path(settings.poster_references_path)
        if path.stat().st_size > 1_000_000:
            raise ValueError("Poster reference index exceeds limit")
        index = PosterReferences.model_validate(json.loads(path.read_text(encoding="utf-8-sig")))
        ids = [item.id for item in index.references]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate poster reference IDs")
        return index.references
    except (OSError, ValueError):
        logger.warning("Poster reference index is unavailable or invalid")
        return []


def reference_images(reference: PosterReference) -> list[str]:
    """로컬에 준비한 전체 포스터와 상단 확대 이미지만 모델에 보낸다."""
    if not settings.poster_reference_images_path:
        return []
    images = []
    directory = Path(settings.poster_reference_images_path)
    for suffix in ("", "-header"):
        path = directory / f"{reference.id}{suffix}.jpg"
        try:
            if path.stat().st_size > 800_000:
                continue
            image = path.read_bytes()
            if image.startswith(b"\xff\xd8"):
                images.append("data:image/jpeg;base64," + base64.b64encode(image).decode("ascii"))
        except OSError:
            continue
    return images
