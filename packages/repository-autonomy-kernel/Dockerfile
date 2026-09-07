# Pin PYTHON_BASE_IMAGE by digest in the release pipeline. The default keeps
# local development convenient while the image remains non-root and inert.
ARG PYTHON_BASE_IMAGE=python:3.12-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ELMOS_AUTONOMY_DB=/var/lib/elmos-autonomy/autonomy.sqlite

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-compile . \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin elmos \
    && mkdir -p /var/lib/elmos-autonomy \
    && chown -R 10001:10001 /app /var/lib/elmos-autonomy

USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/livez', timeout=2)"
ENTRYPOINT ["elmos-autonomy"]
CMD ["serve", "--db", "/var/lib/elmos-autonomy/autonomy.sqlite", "--host", "0.0.0.0", "--port", "8080"]
