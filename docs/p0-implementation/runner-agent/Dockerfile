# ELMOS Runner Agent.
#
# The agent supervises workload containers; it never executes customer code
# itself. It therefore needs a JRE and a container client, and nothing else.
#
# Base images are digest-pinned to match the repository-wide supply-chain rule
# (see docs/project-synthesis: every non-scratch base image is fixed to an
# official multi-architecture manifest digest). Replace the digests below with
# the ones your allowlist has approved before building.

# --- build -------------------------------------------------------------------
FROM docker.io/library/eclipse-temurin:21-jdk@sha256:REPLACE_WITH_APPROVED_DIGEST AS build
WORKDIR /src
COPY src ./src
RUN mkdir -p /out/classes \
 && javac -Xlint:all -Werror -d /out/classes $(find src/main/java -name '*.java') \
 && printf 'Main-Class: io.elmos.runner.RunnerAgentMain\n' > /out/manifest.txt \
 && jar --create --file /out/elmos-runner-agent.jar --manifest /out/manifest.txt -C /out/classes .

# --- runtime -----------------------------------------------------------------
FROM docker.io/library/eclipse-temurin:21-jre@sha256:REPLACE_WITH_APPROVED_DIGEST

# The agent runs as a dedicated non-root user. On a rootless podman host this
# maps into the operator's subuid range; nothing here ever needs uid 0.
RUN groupadd --gid 65532 elmos \
 && useradd --uid 65532 --gid 65532 --home-dir /home/elmos --create-home --shell /usr/sbin/nologin elmos \
 && mkdir -p /var/lib/elmos-runner \
 && chown -R 65532:65532 /var/lib/elmos-runner

COPY --from=build --chown=65532:65532 /out/elmos-runner-agent.jar /opt/elmos/elmos-runner-agent.jar

USER 65532:65532
WORKDIR /home/elmos

# Work root must be a writable volume; the container root itself stays read-only
# (the agent's own attestation probe checks exactly this).
VOLUME ["/var/lib/elmos-runner"]

ENV ELMOS_RUNNER_WORK_ROOT=/var/lib/elmos-runner \
    ELMOS_RUNNER_METRICS_PORT=9464 \
    JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=75 -XX:+ExitOnOutOfMemoryError"

EXPOSE 9464

# Liveness is the agent's own /healthz, which turns unhealthy when registration
# fails - a node that cannot register should be restarted, not left idle.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["/bin/sh", "-c", "exec 3<>/dev/tcp/127.0.0.1/9464 && printf 'GET /healthz HTTP/1.0\\r\\n\\r\\n' >&3 && head -1 <&3 | grep -q '200'"]

ENTRYPOINT ["java", "-jar", "/opt/elmos/elmos-runner-agent.jar"]
