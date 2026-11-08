FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# uv 다운로드 캐시는 BuildKit 캐시 마운트에 두어 이미지 층에 남기지 않는다
COPY ai/pyproject.toml ai/uv.lock ai/.python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY ai/src ./src
COPY contract/DOCUMENT_JSON_README.md ./contract/DOCUMENT_JSON_README.md
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM build AS embedding-build
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --group ncs

FROM python:3.13-slim-bookworm AS embedding
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HF_HOME=/var/cache/huggingface NCS_EMBED_HOST=0.0.0.0
COPY --from=embedding-build /app /app
RUN mkdir -p /var/cache/huggingface && chown 10001:10001 /var/cache/huggingface
USER 10001:10001
EXPOSE 8002
CMD ["python", "-m", "hiremate_ai.ncs_search"]

FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY --from=build /app /app
USER 10001:10001
EXPOSE 8001
CMD ["uvicorn", "hiremate_ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
