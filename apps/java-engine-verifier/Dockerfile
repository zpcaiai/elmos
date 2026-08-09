FROM eclipse-temurin:17-jdk-jammy@sha256:29467857e8bde40ab1f7befecbda0ea764b95afec1cc7f89aa90f7a766577e19 AS verifier-jdk17

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS source
WORKDIR /src
COPY . .
RUN mkdir -p /opt/elmos \
    && find . -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 sha256sum \
      | sha256sum \
      | cut -d ' ' -f 1 > /opt/elmos/source-context.sha256

FROM source AS build
ARG ELMOS_EXPECTED_SOURCE_CONTEXT_SHA256=""
RUN set -eu; \
    actual="$(cat /opt/elmos/source-context.sha256)"; \
    if [ -n "$ELMOS_EXPECTED_SOURCE_CONTEXT_SHA256" ]; then \
      test "$actual" = "$ELMOS_EXPECTED_SOURCE_CONTEXT_SHA256"; \
    fi
RUN --mount=type=cache,target=/root/.m2 \
    set -eu; \
    attempt=1; \
    until mvn -B --strict-checksums \
        -Dmaven.wagon.http.retryHandler.count=5 \
        -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
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

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
RUN groupadd --gid 10002 verifier \
    && useradd --uid 10002 --gid 10002 --create-home --home-dir /home/verifier --shell /usr/sbin/nologin verifier \
    && mkdir -p /app /input/runs /verification /home/verifier/.m2 \
    && chown -R 10002:10002 /app /verification /home/verifier
COPY --from=build /src/apps/java-engine-verifier/target/elmos-java-engine-verifier-0.1.0-SNAPSHOT-exec.jar /app/app.jar
COPY --from=build --chown=0:0 /opt/elmos/maven-cache /opt/elmos/maven-cache
COPY --from=source /opt/elmos/source-context.sha256 /opt/elmos/source-context.sha256
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
