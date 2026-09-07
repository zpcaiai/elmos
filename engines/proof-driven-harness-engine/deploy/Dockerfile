# syntax=docker/dockerfile:1.7
# PYTHON_BASE intentionally has no default. The release pipeline must provide
# an immutable image reference such as registry.example/python@sha256:<64 hex>.
ARG PYTHON_BASE
FROM ${PYTHON_BASE} AS build
ARG PYTHON_BASE
RUN python -c 'import os,re; value=os.environ.get("PYTHON_BASE", ""); assert re.fullmatch(r"[^@]+@sha256:[0-9a-f]{64}", value), "PYTHON_BASE must be digest pinned"'

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
COPY adapters ./adapters
COPY api ./api
COPY examples ./examples
COPY migrations ./migrations
COPY observability ./observability
COPY openapi ./openapi
COPY policies ./policies
COPY schemas ./schemas
COPY supply-chain ./supply-chain
COPY tools ./tools
COPY verification ./verification
COPY deploy ./deploy
COPY deploy/requirements-production.txt ./requirements-production.txt
RUN python -m pip wheel --wheel-dir /wheels -r requirements-production.txt
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir /wheels .

ARG PYTHON_BASE
FROM ${PYTHON_BASE} AS runtime

ARG SOURCE_REVISION
ARG RELEASE_MANIFEST_SHA256
RUN python -c 'import os,re; revision=os.environ.get("SOURCE_REVISION", ""); manifest=os.environ.get("RELEASE_MANIFEST_SHA256", ""); assert re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision), "SOURCE_REVISION must be an exact Git object id"; assert re.fullmatch(r"sha256:[0-9a-f]{64}", manifest), "RELEASE_MANIFEST_SHA256 must be pinned"'
LABEL org.opencontainers.image.title="Elmos Proof-Driven Harness" \
      org.opencontainers.image.version="3.1.0" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      ai.elmos.release-manifest="${RELEASE_MANIFEST_SHA256}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    ELMOS_RUNTIME_MODE=production \
    ELMOS_RUNTIME_ASSURANCE_FACTORY="" \
    ELMOS_HOST=0.0.0.0 \
    ELMOS_PORT=8080

COPY --from=build /wheels /wheels
RUN python -m pip install --no-cache-dir --no-compile --no-index --find-links=/wheels \
      "psycopg[binary]==3.2.13" elmos-proof-driven-harness-engine==3.1.0 \
    && RELEASE_CONTRACT_PATH="$(python -c 'import pathlib,sysconfig; print(pathlib.Path(sysconfig.get_path("data")) / "share/elmos-proof-harness/tools/release_contract.py")')" \
    && python "${RELEASE_CONTRACT_PATH}" --check-installed \
         --expected-manifest-sha256 "${RELEASE_MANIFEST_SHA256}" \
    && rm -rf /wheels \
    && python -c "import elmos_proof_harness, psycopg; assert psycopg.__version__ == '3.2.13'"

USER 65532:65532
EXPOSE 8080
ENTRYPOINT ["elmos-proof-harness"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080"]
