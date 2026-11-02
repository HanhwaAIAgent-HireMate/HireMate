"""모든 Agent가 같이 쓰는 가드레일 (아키텍처 규칙 6, 7)."""

import re
import unicodedata
from collections.abc import Iterable

from hiremate_ai.contract import ApplicantDocument, DocumentType, Evidence

# backend StubRootAgent.BLOCKED를 바탕으로, 직무 표현인 "장애 대응", "API 키", "5세대"는 막지 않게 좁혔다.
# 블라인드 여부와 관계없이 막는다 (고령자고용법, 남녀고용평등법, 장애인차별금지법, 채용절차법).
# 구체적인 차단 범위는 법무 검토 후 정한다 (기획 v7 §12)
_BLOCKED_ATTRIBUTE = re.compile(
    r"나이|연령|\d+\s*(?:살|세(?!대))|성별|남자|여자|남성|여성|출신|고향|지역|결혼|혼인|기혼|미혼|자녀|여대|여고"
    r"|키가|키\s*\d|몸무게|체중|외모|신체|장애(?:인|\s*(?:여부|유무|등급))|장애가\s*있|장애를\s*가진"
)

# 출신 학교. 출신 지역과 달리 블라인드 채용일 때만 막는다. 학교를 가리키지 않는 "출신"은 출신 지역으로 보고 늘 막는다.
# "30대 출신"처럼 숫자 뒤의 "대"나 성별을 가리키는 "여대"는 학교로 보지 않는다.
_SCHOOL_ORIGIN = r"(?:(?!여)[가-힣A-Za-z]대|SKY|대학교?|대학원|학교|고등학교|고교)\s*출신|출신\s*(?:학교|대학교?|교)"
_SCHOOL_ORIGIN_PATTERN = re.compile(_SCHOOL_ORIGIN)

# 블라인드 채용에서 가리는 학력 조건. 직무와 관련된 전공, 자격, 경력은 막지 않는다.
_BLIND_ATTRIBUTE = re.compile(
    _SCHOOL_ORIGIN + r"|(?:[가-힣A-Za-z]대|대학교?|대학원)\s*(?:나온|졸업)|대학교|학교명|대학명"
    r"|학력|학벌|학위|학사|석사|박사|대졸|고졸|전문대|명문대|지방대|인서울|학점"
    r"|(?<![A-Za-z])(?:SKY|GPA)(?![A-Za-z])"
)

BLOCKED_REPLY = (
    "나이, 성별, 출신 지역, 혼인 여부, 신체 조건으로는 지원자를 찾거나 거르지 않아요. "
    "직무와 관련된 경험이나 역량으로 다시 말씀해 주세요."
)
"""차별 조건으로 찾거나 거르는 요청에 돌려주는 답. backend stub과 같은 문구다."""

BLIND_BLOCKED_REPLY = (
    "블라인드 채용이라 학력이나 출신 학교로는 지원자를 찾거나 거르지 않아요. "
    "직무와 관련된 경험이나 역량으로 다시 말씀해 주세요."
)
"""블라인드 채용에서 학력 조건으로 찾거나 거르는 요청에 돌려주는 답."""

_SPACES = re.compile(r"\s+")
_LEADING_MARKS = re.compile(r"^[\s·•\-*\"'“”‘’]+|[\s\"'“”‘’]+$")


def blocked_attribute(message: str, *, blind: bool = False) -> str | None:
    """요청에 채용 판단에 쓰면 안 되는 조건이 있으면 그 낱말을 돌려준다 (규칙 6).

    나이, 성별, 출신 지역, 혼인 여부, 신체 조건, 장애는 늘 막는다.
    학력과 출신 학교는 블라인드 채용(`blind`)일 때만 막는다.
    """
    match = _BLOCKED_ATTRIBUTE.search(_SCHOOL_ORIGIN_PATTERN.sub(" ", message))
    if match is None and blind:
        match = _BLIND_ATTRIBUTE.search(message)
    return match.group() if match else None


def blocked_reply(term: str) -> str:
    """`blocked_attribute`가 돌려준 낱말에 맞는 안내. 블라인드 채용이라 막은 학력 조건이면 `BLIND_BLOCKED_REPLY`다."""
    return BLOCKED_REPLY if blocked_attribute(term) else BLIND_BLOCKED_REPLY


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
