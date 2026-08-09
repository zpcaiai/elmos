FROM maven:3.9.11-eclipse-temurin-8@sha256:e3c149f44c95b0e9dd131862b3df67b3f061f7f6f3898a87b170564b3a943611 AS java8

FROM maven:3.9.11-eclipse-temurin-11@sha256:c095e2421eaf3e5cb1573fd0474e68e17062866d454362349e17bbb75f44031e AS java11

FROM maven:3.9.11-eclipse-temurin-17@sha256:e4a7ace3dc0d645ed97f8d9ad0b0d3f0b14fa8d150138f27f116d7105a639b82 AS java17

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
        -pl apps/java-engine-transformer -am -DskipTests package; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /root/.m2/repository -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done
RUN cp -R framework-packs/spring-boot-2-7-18-to-3-5-3/corpus/development/source /tmp/elmos-seed-source \
    && rm -rf /tmp/elmos-seed-source/target /tmp/elmos-seed-source/.git /tmp/elmos-seed-source/.elmos \
    && cp framework-packs/spring-boot-2-7-18-to-3-5-3/recipes/spring-boot-2.7.18-to-3.5.3.yml /tmp/elmos-openrewrite.yml \
    && chmod -R a-w /tmp/elmos-seed-source /tmp/elmos-openrewrite.yml
RUN --mount=type=cache,target=/root/.m2 \
    set -eu; \
    rm -rf /tmp/elmos-source-test-project; \
    cp -R /tmp/elmos-seed-source /tmp/elmos-source-test-project; \
    chmod -R u+w /tmp/elmos-source-test-project; \
    attempt=1; \
    until mvn -B --strict-checksums --no-transfer-progress \
        -Dmaven.wagon.http.retryHandler.count=5 \
        -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
        -f /tmp/elmos-source-test-project/pom.xml test; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /root/.m2/repository -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done
RUN --mount=type=cache,target=/root/.m2 \
    set -eu; \
    attempt=1; \
    while :; do \
      rm -rf /tmp/elmos-rewrite-project; \
      cp -R /tmp/elmos-seed-source /tmp/elmos-rewrite-project; \
      chmod -R u+w /tmp/elmos-rewrite-project; \
      mkdir -p /tmp/elmos-rewrite-project/.elmos; \
      cp /tmp/elmos-openrewrite.yml /tmp/elmos-rewrite-project/.elmos/openrewrite.yml; \
      if mvn -B --strict-checksums --no-transfer-progress \
        -Dmaven.wagon.http.retryHandler.count=5 \
        -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
        -f /tmp/elmos-rewrite-project/pom.xml \
        org.openrewrite.maven:rewrite-maven-plugin:6.44.0:run \
        -Drewrite.configLocation=/tmp/elmos-rewrite-project/.elmos/openrewrite.yml \
        -Drewrite.activeRecipes=io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21 \
        -Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:6.35.0 \
        -Drewrite.exportDatatables=true; then \
        break; \
      fi; \
      rm -rf /tmp/elmos-rewrite-project; \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /root/.m2/repository -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done; \
    attempt=1; \
    until mvn -B --strict-checksums --no-transfer-progress \
        -Dmaven.wagon.http.retryHandler.count=5 \
        -Dmaven.wagon.httpconnectionManager.ttlSeconds=25 \
        -f /tmp/elmos-rewrite-project/pom.xml verify; do \
      if [ "$attempt" -ge 3 ]; then exit 1; fi; \
      attempt=$((attempt + 1)); \
      find /root/.m2/repository -type f \( -name '*.lastUpdated' -o -name '*.part' \) -delete; \
    done; \
    mkdir -p /opt/elmos/maven-seed; \
    cp -R /root/.m2/repository/. /opt/elmos/maven-seed/

FROM scratch AS source-context-digest
COPY --from=source /opt/elmos/source-context.sha256 /source-context.sha256

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
RUN groupadd --gid 10001 elmos \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/elmos --shell /usr/sbin/nologin elmos \
    && mkdir -p /app /workspace/run \
    && chown -R 10001:10001 /app /workspace /home/elmos
COPY --from=java8 /opt/java/openjdk /opt/java/openjdk-8
COPY --from=java11 /opt/java/openjdk /opt/java/openjdk-11
COPY --from=java17 /opt/java/openjdk /opt/java/openjdk-17
COPY --from=build /src/apps/java-engine-transformer/target/elmos-java-engine-transformer-0.1.0-SNAPSHOT-exec.jar /app/app.jar
COPY --from=build /opt/elmos/maven-seed /opt/elmos/maven-seed
COPY --from=source /opt/elmos/source-context.sha256 /opt/elmos/source-context.sha256
COPY --chown=10001:10001 apps/java-engine-transformer/entrypoint.sh /app/entrypoint.sh
RUN chmod -R a-w /opt/elmos/maven-seed \
    && chmod 0555 /app/entrypoint.sh
ENV ELMOS_SOURCE_JAVA_HOME=/opt/java/openjdk-17 \
    ELMOS_TARGET_JAVA_HOME=/opt/java/openjdk \
    ELMOS_TRANSFORMER_JAVA_HOMES=8=/opt/java/openjdk-8,11=/opt/java/openjdk-11 \
    ELMOS_MAVEN_EXECUTABLE=/usr/share/maven/bin/mvn \
    ELMOS_MAVEN_DEPENDENCY_SEED=/opt/elmos/maven-seed
USER 10001:10001
EXPOSE 8083
ENTRYPOINT ["/app/entrypoint.sh"]
