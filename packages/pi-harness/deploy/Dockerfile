ARG PYTHON_IMAGE=scratch
FROM ${PYTHON_IMAGE}

ARG PYTHON_IMAGE
ARG APP_UID=65532
ARG APP_GID=65532
RUN case "${PYTHON_IMAGE}" in *@sha256:*) true ;; *) exit 64 ;; esac \
    && groupadd --gid "${APP_GID}" pi-harness \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin pi-harness

WORKDIR /opt/pi-harness
COPY deploy/requirements-production.lock ./deploy/requirements-production.lock
RUN python -m pip install --no-cache-dir --require-hashes -r deploy/requirements-production.lock

COPY pyproject.toml ./
COPY sql ./sql
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation . \
    && python -m pip check

USER ${APP_UID}:${APP_GID}
EXPOSE 8787
ENTRYPOINT ["elmos-pi-harness"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8787"]
