"""Application Agent. 지원 문서를 분석해 지원자 프로필(근거 · 출처 포함)과 서류 점수를 만든다.

Application 부분(extract)이 서류에서 사실과 근거를 뽑고, Assessment 부분(judge · review · score)이
공고의 자격요건과 우대사항(NCS 평가 조건)에 대조해 서류 점수 · 보류를 정한다.
Root Agent는 analyze_application을 import해 부른다.
"""

from hiremate_ai.agents.analysis.application.service import analyze_application

__all__ = ["analyze_application"]
