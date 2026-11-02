"""근거 원문의 강도. 성과를 숫자와 단위로 적은 문장(정량)과 한 일만 적은 문장(서술)을 코드가 나눈다.

'응답 시간을 800ms에서 120ms로 줄였습니다'는 정량, 'MySQL 예약 테이블을 설계했습니다'는 서술이다.
모델에게 묻지 않아 같은 문장이면 늘 같은 결과다. 판정은 바꾸지 않고, 근거를 고르는 순서와 화면 표시에만 쓴다.
연도(2023년), 버전(Java 17), 팀 인원(3명)은 성과 수치가 아니라 단위에서 뺀다.
"""

import re

from hiremate_ai.agents.generation.report.bundle import Strength

_UNITS = (
    "%|퍼센트|배|ms|밀리초|초|분|시간|일|주|개월|건|회|번|개|원|만|억|천|위|점|줄|라인"
    "|TPS|QPS|RPS|tps|qps|rps|GB|MB|TB|KB|x|X|k|K|M"
)
# 영문 단위는 낱말의 앞부분이면 단위가 아니다 (3 Microservices)
_QUANT = re.compile(rf"\d[\d,.]*\s*(?:{_UNITS})(?![A-Za-z])")


def quote_strength(sentence: str | None) -> Strength | None:
    """원문 한 문장의 강도. 원문이 없으면 None이다."""
    if not sentence:
        return None
    return Strength.QUANT if _QUANT.search(sentence) else Strength.CLAIM
