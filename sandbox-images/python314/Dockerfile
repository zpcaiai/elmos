FROM ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv
FROM python:3.14.6-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30
COPY --from=uv /uv /uvx /usr/local/bin/
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --create-home elmos
USER 10001:10001
WORKDIR /workspace
ENV UV_OFFLINE=1 UV_NO_PROGRESS=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python3.14"]

