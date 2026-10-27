"""독립 면접 분석의 레시피. Root의 비교 자료가 있는 분석에는 사용하지 않는다."""

from hiremate_ai.agents.analysis.interview.agent import MAX_RETRIES, PROFILE_SYSTEM
from hiremate_ai.agents.analysis.interview.types import InterviewAnalysis, InterviewDraft
from hiremate_ai.llm.client import LlmClient
from hiremate_ai.llm.recipe import analysis_recipe, fingerprint


def interview_recipe(llm: LlmClient) -> str | None:
    recipe = analysis_recipe(llm)
    return (
        fingerprint(
            {
                "version": "interview-analysis-1",
                "llm": recipe,
                "system": PROFILE_SYSTEM,
                "schema": InterviewDraft.model_json_schema(),
                "output_schema": InterviewAnalysis.model_json_schema(),
                "retries": MAX_RETRIES,
            }
        )
        if recipe is not None
        else None
    )
