from fastapi import FastAPI

from hiremate_ai.api import health

app = FastAPI(title="HireMate AI")
app.include_router(health.router)
