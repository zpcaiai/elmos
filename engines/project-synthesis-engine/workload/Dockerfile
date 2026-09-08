# ELMOS generation workload image.
#
# Runs the project-synthesis engine inside the runner-agent sandbox contract:
# read-only root filesystem, no network, non-root, /elmos/in -> /elmos/out.
#
# The engine is pure-stdlib Python (see pyproject.toml: dependencies = []),
# so the image installs it by direct copy - no package resolution, no
# network, and the bytes that ship are the bytes in this repository.
#
# Toolchain boundary (deliberate): this image carries the engine only.
# Generated-project verification toolchains (JDK/Maven, .NET SDK, Go,
# Node/pnpm, Gradle, PHP, Rust, uv+pytest) are NOT baked in, so every
# generated target whose toolchain is absent reports NOT_RUN and the
# pipeline result is PARTIAL - the same honest boundary the local runner
# shows on a machine without toolchains. A toolchain-complete image must be
# built separately on a machine allowed to reach the pinned upstream images
# in src/elmos_project_synthesis/container_images.py; it must never be
# emulated by weakening verification.

# Pinned to the same digest the engine pins for generated python:3.12 images.
FROM python:3.12.12-slim@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c

ENV PYTHONPATH=/opt/elmos-engine/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ELMOS_INPUT_DIR=/elmos/in \
    ELMOS_OUTPUT_DIR=/elmos/out \
    ELMOS_WORKLOAD_WORK_DIR=/elmos/tmp

WORKDIR /opt/elmos-engine

COPY src/elmos_project_synthesis ./src/elmos_project_synthesis
COPY workload/entrypoint.py ./workload/entrypoint.py

# Build-time integrity gate: the engine must import and the entrypoint must
# self-check inside this exact filesystem before the image is usable.
RUN python -m elmos_project_synthesis.cli --help > /dev/null \
    && python workload/entrypoint.py --self-check

# Never root. The runner-agent overrides uid:gid per job; the image default
# only matters for out-of-band manual runs.
USER 65532:65532

ENTRYPOINT ["python", "/opt/elmos-engine/workload/entrypoint.py"]
