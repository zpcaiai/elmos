# syntax=docker/dockerfile:1.7
# The release pipeline MUST pass an allowlisted digest-pinned Python image, for
# example: --build-arg RUNTIME_IMAGE=registry.example/python@sha256:<digest>.
ARG RUNTIME_IMAGE
FROM ${RUNTIME_IMAGE}
ARG RUNTIME_IMAGE

RUN case "${RUNTIME_IMAGE}" in *@sha256:????????????????????????????????????????????????????????????????) ;; *) echo "RUNTIME_IMAGE must be digest pinned" >&2; exit 64 ;; esac

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/elmos-pdhi/src \
    TMPDIR=/tmp

WORKDIR /opt/elmos-pdhi
COPY --chown=65532:65532 src/ /opt/elmos-pdhi/src/
COPY --chown=65532:65532 README.md pyproject.toml /opt/elmos-pdhi/

USER 65532:65532
ENTRYPOINT ["python", "-m", "elmos_pdhi.cli"]
CMD ["gate-status"]
