"""Report Agent. 채용 종료 결과를 요약한 최종 리포트를 만든다. 숫자는 SQL 집계 값을 그대로 쓴다."""

from hiremate_ai.agents.generation.report.agent import write_report
from hiremate_ai.agents.generation.report.profiles import load_profiles
from hiremate_ai.agents.generation.report.types import ReportContent, ReportInput

__all__ = ["ReportContent", "ReportInput", "load_profiles", "write_report"]
