"""Application Agent. 지원 문서를 분석해 지원자 프로필(근거 · 출처 포함)과 항목별 판정을 만든다. 점수는 매기지 않는다.

Application 부분(extract)이 서류에서 사실과 근거를 뽑고, Assessment 부분(judge · review)이
공고의 자격요건과 우대사항에 대조해 항목마다 판정한다.
Root Agent는 review_application_documents로 저장 없이 제출 문서의 사실과 근거를 검토한다.
"""

from hiremate_ai.agents.analysis.application.index import index_document
from hiremate_ai.agents.analysis.application.normalize import normalize_document, verbatim_document
from hiremate_ai.agents.analysis.application.service import analyze_application, review_application_documents

__all__ = [
    "analyze_application",
    "review_application_documents",
    "normalize_document",
    "verbatim_document",
    "index_document",
]
