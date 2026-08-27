ARG PYTHON_IMAGE=python:3.13-slim@sha256:REPLACE_WITH_RELEASE_TIME_PINNED_DIGEST
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

RUN groupadd --system --gid 10001 elmos \
 && useradd --system --uid 10001 --gid 10001 --home /nonexistent --shell /usr/sbin/nologin elmos

WORKDIR /app
COPY pyproject.toml VERSION ./
COPY reference-kernel ./reference-kernel
RUN python -m pip install --no-cache-dir .

USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=2)"
ENTRYPOINT ["elmos-formal-server"]
