import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from hiremate_ai.agents.analysis.application.types import ApplicationAnalysis, ScreeningRubric
from hiremate_ai.agents.analysis.interview import InterviewAnalysisInput
from hiremate_ai.agents.analysis.interview.router import InterviewAnalysis
from hiremate_ai.agents.generation.interview.router import QuestionsRequest
from hiremate_ai.agents.generation.interview.types import (
    CitedQuestionDraft,
    FollowUpsRequest,
    InterviewFollowUps,
    InterviewQuestionDraft,
)
from hiremate_ai.agents.generation.posting.poster import PosterDesign, PosterProposal, PosterTurn
from hiremate_ai.agents.generation.posting.types import NcsSource, PostingDraftContext, PostingFocus, PostingSuggestion
from hiremate_ai.agents.generation.report import ComposedReport, ReportBundle
from hiremate_ai.agents.root.types import ChatApplied, ChatContext, ChatHistoryTurn, ChatPlan, ChatStatus
from hiremate_ai.api.profile import CandidateProfileView
from hiremate_ai.contract import (
    ApplicantDetail,
    CandidateAnalysis,
    CompanyFactors,
    CompanyProfile,
    DocumentIndexRequest,
    DocumentIndexResult,
    DocumentNormalizationRequest,
    DocumentSource,
    FeatureLabels,
    InterviewerMemo,
    InterviewView,
    Job,
    JobResult,
    NormalizedDocument,
    PostingContent,
    TalentFit,
    TalentFitRequest,
)

CONTRACT_DIR = Path(__file__).resolve().parents[2] / "contract"

# 샘플 파일 이름 → 타입. backend의 ContractSampleTests.SAMPLES와 같게 유지한다.
SAMPLES: dict[str, type[BaseModel]] = {
    "ApplicantDetail": ApplicantDetail,
    "DocumentSource": DocumentSource,
    "NormalizedDocument": NormalizedDocument,
    "DocumentNormalizationRequest": DocumentNormalizationRequest,
    "DocumentIndexRequest": DocumentIndexRequest,
    "DocumentIndexResult": DocumentIndexResult,
    "ApplicationAnalysis": ApplicationAnalysis,
    "CandidateAnalysis": CandidateAnalysis,
    "CandidateProfileView": CandidateProfileView,
    "ChatApplied": ChatApplied,
    "ChatContext": ChatContext,
    "ChatHistoryTurn": ChatHistoryTurn,
    "ChatPlan": ChatPlan,
    "ChatStatus": ChatStatus,
    "CompanyProfile": CompanyProfile,
    "ComposedReport": ComposedReport,
    "FeatureLabels": FeatureLabels,
    "CompanyFactors": CompanyFactors,
    "InterviewAnalysis": InterviewAnalysis,
    "InterviewView": InterviewView,
    "InterviewFollowUps": InterviewFollowUps,
    "InterviewFollowUpsRequest": FollowUpsRequest,
    "InterviewQuestionDraft": InterviewQuestionDraft,
    "CitedQuestionDraft": CitedQuestionDraft,
    "InterviewerMemo": InterviewerMemo,
    "InterviewAnalysisInput": InterviewAnalysisInput,
    "InterviewQuestionsRequest": QuestionsRequest,
    "Job": Job,
    "JobResult": JobResult,
    "NcsSource": NcsSource,
    "PostingContent": PostingContent,
    "PosterDesign": PosterDesign,
    "PosterProposal": PosterProposal,
    "PosterTurn": PosterTurn,
    "PostingDraftContext": PostingDraftContext,
    "PostingFocus": PostingFocus,
    "PostingSuggestion": PostingSuggestion,
    "ReportBundle": ReportBundle,
    "ScreeningRubric": ScreeningRubric,
    "TalentFit": TalentFit,
    "TalentFitRequest": TalentFitRequest,
}


def test_every_sample_has_a_type() -> None:
    files = {path.stem for path in CONTRACT_DIR.glob("*.json")}

    assert files == set(SAMPLES)


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_sample_round_trip(name: str) -> None:
    sample = json.loads((CONTRACT_DIR / f"{name}.json").read_text(encoding="utf-8"))

    model = SAMPLES[name].model_validate(sample)

    assert model.model_dump(mode="json") == sample
