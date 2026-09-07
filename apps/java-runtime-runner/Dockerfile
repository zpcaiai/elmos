ARG ELMOS_SOURCE_REVISION
ARG ELMOS_SOURCE_CONTEXT_SHA256
ARG ELMOS_SOURCE_STATUS_SHA256

FROM eclipse-temurin:17-jdk-jammy@sha256:29467857e8bde40ab1f7befecbda0ea764b95afec1cc7f89aa90f7a766577e19 AS runtime-java17

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
ARG ELMOS_SOURCE_REVISION
ARG ELMOS_SOURCE_CONTEXT_SHA256
ARG ELMOS_SOURCE_STATUS_SHA256
WORKDIR /src
COPY apps/java-runtime-runner/HealthProbe.java /src/io/elmos/runner/HealthProbe.java
RUN set -eu; \
    test "${#ELMOS_SOURCE_REVISION}" -eq 40; \
    test "${#ELMOS_SOURCE_CONTEXT_SHA256}" -eq 64; \
    test "${#ELMOS_SOURCE_STATUS_SHA256}" -eq 64; \
    case "$ELMOS_SOURCE_REVISION$ELMOS_SOURCE_CONTEXT_SHA256$ELMOS_SOURCE_STATUS_SHA256" in \
      *[!0-9a-f]*) exit 64 ;; \
    esac; \
    mkdir -p /opt/elmos; \
    printf '%s\n' "$ELMOS_SOURCE_CONTEXT_SHA256" > /opt/elmos/source-context.sha256; \
    printf '%s\n' "$ELMOS_SOURCE_STATUS_SHA256" > /opt/elmos/source-status.sha256; \
    javac --release 17 -d /runner /src/io/elmos/runner/HealthProbe.java

FROM scratch AS source-context-digest
COPY --from=build /opt/elmos/source-context.sha256 /source-context.sha256
COPY --from=build /opt/elmos/source-status.sha256 /source-status.sha256

FROM eclipse-temurin:21-jre@sha256:8cef5fc7bebe421363ab543a2f4db5caf7d119d8db67d56b0f56c485d2de4d55
ARG ELMOS_SOURCE_REVISION
ARG ELMOS_SOURCE_CONTEXT_SHA256
ARG ELMOS_SOURCE_STATUS_SHA256
LABEL org.opencontainers.image.revision="${ELMOS_SOURCE_REVISION}" \
      io.elmos.evidence.scope="spring-modernization-local" \
      io.elmos.evidence.class="LOCAL_NON_CERTIFYING" \
      io.elmos.build.source-status="CLEAN_SOURCE" \
      io.elmos.build.source-dirty="false" \
      io.elmos.build.context-sha256="${ELMOS_SOURCE_CONTEXT_SHA256}" \
      io.elmos.build.context-status-sha256="${ELMOS_SOURCE_STATUS_SHA256}"
RUN groupadd --gid 10003 runtime \
    && useradd --uid 10003 --gid 10003 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin runtime \
    && mkdir -p /app /runner \
    && chown -R 10003:10003 /app /runner
COPY --from=build /runner /runner
COPY --from=build /opt/elmos/source-context.sha256 /opt/elmos/source-context.sha256
COPY --from=build /opt/elmos/source-status.sha256 /opt/elmos/source-status.sha256
COPY --from=runtime-java17 /opt/java/openjdk /opt/java/openjdk-17
USER 10003:10003
WORKDIR /app
ENTRYPOINT ["/opt/java/openjdk/bin/java"]
