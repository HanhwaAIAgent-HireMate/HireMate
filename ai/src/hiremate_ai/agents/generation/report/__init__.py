"""Report Agent. 전형 결과 · 지원자 비교 · 최종 리포트의 부품 설계서를 만든다 (backend가 넘긴 묶음만 읽는다)."""

from hiremate_ai.agents.generation.report.bundle import ReportBundle
from hiremate_ai.agents.generation.report.compose import ComposedReport, compose_report
from hiremate_ai.agents.generation.report.enrich import enrich
from hiremate_ai.agents.generation.report.explain import DistributionFacts, DistributionNote, explain_distribution

__all__ = [
    "ComposedReport",
    "DistributionFacts",
    "DistributionNote",
    "ReportBundle",
    "compose_report",
    "enrich",
    "explain_distribution",
]
