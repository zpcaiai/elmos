FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/root/.m2 mvn -B -pl apps/java-engine-verifier -am -DskipTests package
RUN mvn -B --no-transfer-progress \
    -Dmaven.repo.local=/opt/elmos/maven-cache \
    -f framework-packs/spring-boot-2-7-18-to-3-5-3/corpus/development/migrated/pom.xml \
    verify

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
RUN groupadd --gid 10002 verifier \
    && useradd --uid 10002 --gid 10002 --create-home --home-dir /home/verifier --shell /usr/sbin/nologin verifier \
    && mkdir -p /app /input/runs /verification /home/verifier/.m2 \
    && chown -R 10002:10002 /app /verification /home/verifier
COPY --from=build /src/apps/java-engine-verifier/target/elmos-java-engine-verifier-0.1.0-SNAPSHOT-exec.jar /app/app.jar
COPY --from=build --chown=10002:10002 /opt/elmos/maven-cache /opt/elmos/maven-cache
ENV ELMOS_VERIFIER_JAVA_HOME=/opt/java/openjdk \
    ELMOS_VERIFIER_MAVEN_EXECUTABLE=/usr/share/maven/bin/mvn \
    ELMOS_VERIFIER_DEPENDENCY_CACHE_ROOT=/opt/elmos/maven-cache
USER 10002:10002
EXPOSE 8082
ENTRYPOINT ["java","-XX:MaxRAMPercentage=70","-jar","/app/app.jar"]
