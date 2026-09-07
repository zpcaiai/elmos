FROM ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv
FROM nvidia/cuda:13.0.2-cudnn-runtime-ubuntu24.04@sha256:14d94b039cb94bbd5da559f303b46bc4b0d5d6c24ab1a9d7b186e566ed3400dc
COPY --from=uv /uv /uvx /usr/local/bin/
RUN uv python install --install-dir /opt/python --no-bin 3.13.11 \
    && ln -s /opt/python/cpython-3.13.11-linux-x86_64-gnu/bin/python3.13 /usr/local/bin/python3.13 \
    && groupadd --gid 10001 elmos \
    && useradd --uid 10001 --gid 10001 --create-home elmos
USER 10001:10001
WORKDIR /workspace
ENV UV_OFFLINE=1 UV_NO_PROGRESS=1 PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python3.13"]
