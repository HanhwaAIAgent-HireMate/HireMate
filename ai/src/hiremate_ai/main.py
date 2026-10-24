from fastapi import FastAPI

from hiremate_ai.agents.analysis.application import router as application
from hiremate_ai.agents.analysis.interview import router as interview_analysis
from hiremate_ai.agents.generation.interview import router as interview_generation
from hiremate_ai.agents.generation.posting import router as posting
from hiremate_ai.agents.root import router as root
from hiremate_ai.api import assessment, communication, health, interview, profile, report

app = FastAPI(title="HireMate AI")
app.include_router(health.router)
app.include_router(root.router)
app.include_router(communication.router)
app.include_router(posting.router)
app.include_router(report.router)
app.include_router(assessment.router)
app.include_router(interview.router)
app.include_router(application.router)
app.include_router(interview_generation.router)
app.include_router(interview_analysis.router)
app.include_router(profile.router)
