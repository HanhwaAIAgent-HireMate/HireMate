"""NCS 참고 검색이 주고받는 값."""

import math

from pydantic import BaseModel, Field, field_validator

DENSE_DIM = 1024
"""BGE-M3 Dense 벡터 차원."""
SPARSE_DIM = 250002
"""BGE-M3 Sparse 벡터 차원(어휘 크기)."""


class QueryVectors(BaseModel):
    """BGE-M3 벡터 한 쌍. sparse는 0부터 센 토큰 번호 → 가중치다."""

    dense: list[float]
    sparse: dict[int, float]

    @field_validator("dense")
    @classmethod
    def _dense(cls, value: list[float]) -> list[float]:
        if len(value) != DENSE_DIM or not all(math.isfinite(x) for x in value) or not any(value):
            raise ValueError(f"Dense 벡터는 값이 있는 {DENSE_DIM}차원이어야 합니다.")
        return value

    @field_validator("sparse")
    @classmethod
    def _sparse(cls, value: dict[int, float]) -> dict[int, float]:
        if not value or any(not 0 <= k < SPARSE_DIM or not math.isfinite(v) or v <= 0 for k, v in value.items()):
            raise ValueError("Sparse 벡터의 토큰 번호나 가중치가 올바르지 않습니다.")
        return value


class NcsTask(BaseModel):
    """주요 업무 묶음 하나. 직무 › 능력단위 › 주요 업무 아래 '책임 및 역할' 문장들이다."""

    chunk_id: str
    duty_name: str
    unit_code: str
    unit_name: str
    task_name: str
    sentences: list[str]


class NcsTaskRecord(NcsTask):
    """적재 파일의 한 줄. 묶음과 그 묶음의 벡터다."""

    duty_code: str = Field(pattern=r"^\d{8}$")
    unit_code: str = Field(pattern=r"^\d{10}_\d{2}v\d+$")
    sentences: list[str] = Field(min_length=1)
    vectors: QueryVectors

    @field_validator("sentences")
    @classmethod
    def _sentences(cls, value: list[str]) -> list[str]:
        if any(not sentence.strip() for sentence in value):
            raise ValueError("빈 문장이 있습니다.")
        return value


class NcsUnit(BaseModel):
    """모델이 고를 능력단위 하나와 그 주요 업무 이름들."""

    code: str
    name: str
    duty_name: str
    task_names: list[str]
