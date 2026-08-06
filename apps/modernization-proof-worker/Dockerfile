FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -pl apps/modernization-proof-worker -am -DskipTests package

FROM eclipse-temurin:21-jre@sha256:27339648ce6fc450b3b14701ba8f40141186273fc61f24d93c0e4d6b5b27c396
LABEL org.opencontainers.image.title="ELMOS Modernization Proof Worker" \
      org.opencontainers.image.description="Fail-closed Batch 105-108 proof-loop worker" \
      org.opencontainers.image.source="https://github.com/zpcaiai/elmos" \
      io.elmos.runner.capability="modernization:proof-loop"
RUN groupadd --gid 65532 elmos \
    && useradd --uid 65532 --gid 65532 --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin elmos \
    && mkdir -p /opt/elmos \
    && chown -R 65532:65532 /opt/elmos
COPY --from=build --chown=65532:65532 \
    /workspace/apps/modernization-proof-worker/target/modernization-proof-worker-0.1.0-SNAPSHOT-exec.jar \
    /opt/elmos/modernization-proof-worker.jar
WORKDIR /opt/elmos
USER 65532:65532
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError"
ENTRYPOINT ["java", "-jar", "/opt/elmos/modernization-proof-worker.jar"]
