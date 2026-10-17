"""모든 Agent가 같이 쓰는 가드레일 (아키텍처 규칙 6, 7)."""

import re
import unicodedata
from collections.abc import Iterable

from hiremate_ai.contract import ApplicantDocument, DocumentType, Evidence

# backend StubRootAgent.BLOCKED를 바탕으로, 직무 표현인 "장애 대응", "API 키", "5세대"는 막지 않게 좁혔다.
# 구체적인 차단 범위는 법무 검토 후 정한다 (기획 v7 §12)
_BLOCKED_ATTRIBUTE = re.compile(
    r"나이|연령|\d+\s*(?:살|세(?!대))|성별|남자|여자|남성|여성|출신|고향|지역|결혼|혼인|기혼|미혼|자녀"
    r"|키가|키\s*\d|몸무게|체중|외모|신체|장애(?:인|\s*(?:여부|유무|등급))|장애가\s*있|장애를\s*가진"
)

BLOCKED_REPLY = (
    "나이, 성별, 출신 지역, 혼인 여부, 신체 조건으로는 지원자를 찾거나 거르지 않아요. "
    "직무와 관련된 경험이나 역량으로 다시 말씀해 주세요."
)
"""차별 조건으로 찾거나 거르는 요청에 돌려주는 답. backend stub과 같은 문구다."""

_SPACES = re.compile(r"\s+")
_LEADING_MARKS = re.compile(r"^[\s·•\-*\"'“”‘’]+|[\s\"'“”‘’]+$")


def blocked_attribute(message: str) -> str | None:
    """요청에 채용 판단에 쓰면 안 되는 조건이 있으면 그 낱말을 돌려준다 (규칙 6)."""
    match = _BLOCKED_ATTRIBUTE.search(message)
    return match.group() if match else None


def evidence_source(sentence: str, documents: Iterable[ApplicantDocument]) -> DocumentType | None:
    """근거 문장이 실제로 들어 있는 제출 문서 종류. 공백과 앞뒤 따옴표 · 글머리표 차이는 무시한다 (규칙 7)."""
    needle = _normalize(_LEADING_MARKS.sub("", sentence))
    if not needle:
        return None
    for document in documents:
        if needle in _normalize(document.text):
            return document.type
    return None


def verified_evidence(highlights: Iterable[Evidence], documents: list[ApplicantDocument]) -> list[Evidence]:
    """원문에서 찾은 근거만 남긴다. 모델이 문서 종류를 잘못 적었으면 실제 문서로 고친다."""
    verified = []
    for evidence in highlights:
        source = evidence_source(evidence.sentence, documents)
        if source is not None:
            verified.append(evidence.model_copy(update={"document": source}))
    return verified


def _normalize(text: str) -> str:
    return _SPACES.sub("", unicodedata.normalize("NFKC", text))
