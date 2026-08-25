FROM ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv
FROM python:3.14.6-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30
COPY --from=uv /uv /uvx /usr/local/bin/
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --create-home elmos && mkdir -p /workspaces /app && chown -R 10001:10001 /workspaces /app
WORKDIR /app
COPY engines/python-engine/pyproject.toml engines/python-engine/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY engines/python-engine/src ./src
COPY engines/python-engine/compatibility-registry ./compatibility-registry
RUN uv sync --frozen --no-dev && chown -R 10001:10001 /app
USER 10001:10001
ENV ELMOS_PYTHON_WORKSPACE_ROOT=/workspaces UV_NO_SYNC=1 PYTHONUNBUFFERED=1
EXPOSE 8087
ENTRYPOINT ["uv", "run", "--frozen", "uvicorn", "elmos_python.worker.main:app", "--host", "0.0.0.0", "--port", "8087"]

