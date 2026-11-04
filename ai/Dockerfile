FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY ai/pyproject.toml ai/uv.lock ai/.python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY ai/src ./src
RUN uv sync --locked --no-dev

FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY --from=build /app /app
USER 10001:10001
EXPOSE 8001
CMD ["uvicorn", "hiremate_ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
