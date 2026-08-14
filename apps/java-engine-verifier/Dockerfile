ARG ELMOS_SOURCE_REVISION
ARG ELMOS_SOURCE_CONTEXT_SHA256
ARG ELMOS_SOURCE_STATUS_SHA256

FROM eclipse-temurin:17-jdk-jammy@sha256:29467857e8bde40ab1f7befecbda0ea764b95afec1cc7f89aa90f7a766577e19 AS verifier-jdk17

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS source
ARG ELMOS_SOURCE_REVISION
ARG ELMOS_SOURCE_CONTEXT_SHA256
ARG ELMOS_SOURCE_STATUS_SHA256
WORKDIR /src
COPY . .
RUN set -eu; \
    test "${#ELMOS_SOURCE_REVISION}" -eq 40; \
    test "${#ELMOS_SOURCE_CONTEXT_SHA256}" -eq 64; \
    test "${#ELMOS_SOURCE_STATUS_SHA256}" -eq 64; \
    case "$ELMOS_SOURCE_REVISION$ELMOS_SOURCE_CONTEXT_SHA256$ELMOS_SOURCE_STATUS_SHA256" in \
      *[!0-9a-f]*) exit 64 ;; \
    esac; \
    mkdir -p /opt/elmos; \
    printf '%s\n' "$ELMOS_SOURCE_CONTEXT_SHA256" > /opt/elmos/source-context.sha256; \
    printf '%s\n' "$ELMOS_SOURCE_STATUS_SHA256" > /opt/elmos/source-status.sha256

FROM source AS build
RUN --mount=type=cache,target=/root/.m2 \
    set -eu; \
    attempt=1; \
    until mvn -B --strict-checksums \
        -Dmaven.wagon.http.retryHandler.count=5 \
        -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
        -Dmaven.artifact.threads=1 \
        -pl apps/java-engine-verifier -am -DskipTests package; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /root/.m2/repository -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done
COPY --from=verifier-jdk17 /opt/java/openjdk /opt/java/openjdk-17
RUN --mount=type=cache,id=elmos-java-engine-verifier-maven-3.9.11,target=/opt/elmos/maven-cache,sharing=locked \
    set -eu; \
    attempt=1; \
    until JAVA_HOME=/opt/java/openjdk-17 PATH=/opt/java/openjdk-17/bin:${PATH} \
      mvn -B --strict-checksums --no-transfer-progress \
      -Dmaven.wagon.http.retryHandler.count=5 \
      -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
      -Dmaven.artifact.threads=1 \
      -Dmaven.repo.local=/opt/elmos/maven-cache \
      -f apps/java-engine-verifier/cache-seeds/spring-boot-2.7.18-java-17/pom.xml \
      org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline \
      verify; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /opt/elmos/maven-cache -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done
RUN --mount=type=cache,id=elmos-java-engine-verifier-maven-3.9.11,target=/opt/elmos/maven-cache,sharing=locked \
    set -eu; \
    attempt=1; \
    until JAVA_HOME=/opt/java/openjdk-17 PATH=/opt/java/openjdk-17/bin:${PATH} \
      mvn -B --strict-checksums --no-transfer-progress \
      -Dmaven.wagon.http.retryHandler.count=5 \
      -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
      -Dmaven.artifact.threads=1 \
      -Dmaven.repo.local=/opt/elmos/maven-cache \
      -f apps/java-engine-verifier/cache-seeds/spring-boot-3.2.12-java-17/pom.xml \
      org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline \
      verify; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /opt/elmos/maven-cache -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done
RUN --mount=type=cache,id=elmos-java-engine-verifier-maven-3.9.11,target=/opt/elmos/maven-cache,sharing=locked \
    set -eu; \
    attempt=1; \
    until JAVA_HOME=/opt/java/openjdk PATH=/opt/java/openjdk/bin:${PATH} \
      mvn -B --strict-checksums --no-transfer-progress \
      -Dmaven.wagon.http.retryHandler.count=5 \
      -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
      -Dmaven.artifact.threads=1 \
      -Dmaven.repo.local=/opt/elmos/maven-cache \
      -f apps/java-engine-verifier/cache-seeds/spring-boot-3.5.3-java-21/pom.xml \
      org.apache.maven.plugins:maven-dependency-plugin:3.8.1:go-offline \
      verify; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /opt/elmos/maven-cache -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done
RUN --mount=type=cache,id=elmos-java-engine-verifier-maven-3.9.11,target=/tmp/elmos-verifier-maven-cache,sharing=locked \
    mkdir -p /opt/elmos/maven-cache \
    && cp -R /tmp/elmos-verifier-maven-cache/. /opt/elmos/maven-cache/

FROM scratch AS source-context-digest
COPY --from=source /opt/elmos/source-context.sha256 /source-context.sha256
COPY --from=source /opt/elmos/source-status.sha256 /source-status.sha256

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
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
RUN groupadd --gid 10002 verifier \
    && useradd --uid 10002 --gid 10002 --create-home --home-dir /home/verifier --shell /usr/sbin/nologin verifier \
    && mkdir -p /app /input/runs /verification /home/verifier/.m2 \
    && chown -R 10002:10002 /app /verification /home/verifier
COPY --from=build /src/apps/java-engine-verifier/target/elmos-java-engine-verifier-0.1.0-SNAPSHOT-exec.jar /app/app.jar
COPY --from=build --chown=0:0 /opt/elmos/maven-cache /opt/elmos/maven-cache
COPY --from=source /opt/elmos/source-context.sha256 /opt/elmos/source-context.sha256
COPY --from=source /opt/elmos/source-status.sha256 /opt/elmos/source-status.sha256
COPY --from=verifier-jdk17 /opt/java/openjdk /opt/java/openjdk-17
RUN chmod -R a+rX /opt/elmos/maven-cache
RUN chmod -R a-w /opt/elmos/maven-cache
ENV ELMOS_VERIFIER_JAVA_HOME=/opt/java/openjdk \
    ELMOS_VERIFIER_JAVA_HOMES=17=/opt/java/openjdk-17 \
    ELMOS_VERIFIER_MAVEN_EXECUTABLE=/usr/share/maven/bin/mvn \
    ELMOS_VERIFIER_DEPENDENCY_CACHE_ROOT=/opt/elmos/maven-cache
USER 10002:10002
EXPOSE 8082
ENTRYPOINT ["java","-XX:MaxRAMPercentage=70","-jar","/app/app.jar"]
