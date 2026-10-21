import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.types import ApplicationAnalysis, ScreeningRubric
from hiremate_ai.agents.generation.posting.types import PostingDraftContext, PostingSuggestion
from hiremate_ai.agents.root.types import ChatContext, ChatHistoryTurn, ChatPlan
from hiremate_ai.contract import ApplicantDetail, CandidateAnalysis, CompanyProfile, PostingContent

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"

# 샘플 파일 이름 → 타입. backend의 ContractSampleTests.SAMPLES와 같게 유지한다.
SAMPLES: dict[str, type[BaseModel]] = {
    "ApplicantDetail": ApplicantDetail,
    "ApplicationAnalysis": ApplicationAnalysis,
    "CandidateAnalysis": CandidateAnalysis,
    "ChatContext": ChatContext,
    "ChatHistoryTurn": ChatHistoryTurn,
    "ChatPlan": ChatPlan,
    "CompanyProfile": CompanyProfile,
    "PostingContent": PostingContent,
    "PostingDraftContext": PostingDraftContext,
    "PostingSuggestion": PostingSuggestion,
    "ScreeningRubric": ScreeningRubric,
}


def test_every_sample_has_a_type() -> None:
    files = {path.stem for path in CONTRACT_DIR.glob("*.json")}

    assert files == set(SAMPLES)


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_sample_round_trip(name: str) -> None:
    sample = json.loads((CONTRACT_DIR / f"{name}.json").read_text(encoding="utf-8"))

    model = SAMPLES[name].model_validate(sample)

    assert model.model_dump(mode="json") == sample
