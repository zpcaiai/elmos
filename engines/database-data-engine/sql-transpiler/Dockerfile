FROM ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv
FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c

COPY --from=uv /uv /uvx /usr/local/bin/
RUN groupadd --gid 10001 elmos \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin elmos \
    && mkdir -p /app \
    && chown 10001:10001 /app

WORKDIR /app
COPY engines/database-data-engine/sql-transpiler/pyproject.toml \
     engines/database-data-engine/sql-transpiler/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY engines/database-data-engine/sql-transpiler/src ./src
RUN uv sync --frozen --no-dev \
    && chown -R 10001:10001 /app

USER 10001:10001
ENV ELMOS_CHINADB_PREFLIGHT_PORT=8101 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_SYNC=1

EXPOSE 8101
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=4 \
  CMD ["./.venv/bin/python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('ELMOS_CHINADB_PREFLIGHT_PORT','8101')+'/health',timeout=2).read()"]
ENTRYPOINT ["./.venv/bin/elmos-chinadb-preflight"]
