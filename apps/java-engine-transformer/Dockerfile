FROM maven:3.9.11-eclipse-temurin-17@sha256:e4a7ace3dc0d645ed97f8d9ad0b0d3f0b14fa8d150138f27f116d7105a639b82 AS java17

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/root/.m2 \
    mvn -B -pl apps/java-engine-transformer -am -DskipTests package \
    && cp -R framework-packs/spring-boot-2-7-18-to-3-5-3/corpus/development/source /tmp/elmos-seed-project \
    && rm -rf /tmp/elmos-seed-project/target /tmp/elmos-seed-project/.git /tmp/elmos-seed-project/.elmos \
    && mkdir -p /tmp/elmos-seed-project/.elmos \
    && cp framework-packs/spring-boot-2-7-18-to-3-5-3/recipes/spring-boot-2.7.18-to-3.5.3.yml /tmp/elmos-seed-project/.elmos/openrewrite.yml \
    && mvn -B --no-transfer-progress -f /tmp/elmos-seed-project/pom.xml test \
    && mvn -B --no-transfer-progress -f /tmp/elmos-seed-project/pom.xml \
       org.openrewrite.maven:rewrite-maven-plugin:6.44.0:run \
       -Drewrite.configLocation=/tmp/elmos-seed-project/.elmos/openrewrite.yml \
       -Drewrite.activeRecipes=io.elmos.openrewrite.SpringBoot2_7_18To3_5_3Java21 \
       -Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-spring:6.35.0 \
       -Drewrite.exportDatatables=true \
    && mvn -B --no-transfer-progress -f /tmp/elmos-seed-project/pom.xml verify \
    && mkdir -p /opt/elmos/maven-seed \
    && cp -R /root/.m2/repository/. /opt/elmos/maven-seed/

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
RUN groupadd --gid 10001 elmos \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/elmos --shell /usr/sbin/nologin elmos \
    && mkdir -p /app /workspace/run \
    && chown -R 10001:10001 /app /workspace /home/elmos
COPY --from=java17 /opt/java/openjdk /opt/java/openjdk-17
COPY --from=build /src/apps/java-engine-transformer/target/elmos-java-engine-transformer-0.1.0-SNAPSHOT-exec.jar /app/app.jar
COPY --from=build /opt/elmos/maven-seed /opt/elmos/maven-seed
COPY --chown=10001:10001 apps/java-engine-transformer/entrypoint.sh /app/entrypoint.sh
RUN chmod -R a-w /opt/elmos/maven-seed \
    && chmod 0555 /app/entrypoint.sh
ENV ELMOS_SOURCE_JAVA_HOME=/opt/java/openjdk-17 \
    ELMOS_TARGET_JAVA_HOME=/opt/java/openjdk \
    ELMOS_MAVEN_EXECUTABLE=/usr/share/maven/bin/mvn \
    ELMOS_MAVEN_DEPENDENCY_SEED=/opt/elmos/maven-seed
USER 10001:10001
EXPOSE 8083
ENTRYPOINT ["/app/entrypoint.sh"]
