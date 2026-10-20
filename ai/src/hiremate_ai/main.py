from fastapi import FastAPI

from hiremate_ai.agents.generation.posting import router as posting
from hiremate_ai.agents.root import router as root
from hiremate_ai.api import communication, health

app = FastAPI(title="HireMate AI")
app.include_router(health.router)
app.include_router(root.router)
app.include_router(communication.router)
app.include_router(posting.router)
