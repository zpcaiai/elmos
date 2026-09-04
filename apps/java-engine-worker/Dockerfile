FROM maven:3.9.11-eclipse-temurin-8@sha256:e3c149f44c95b0e9dd131862b3df67b3f061f7f6f3898a87b170564b3a943611 AS java8

FROM maven:3.9.11-eclipse-temurin-11@sha256:c095e2421eaf3e5cb1573fd0474e68e17062866d454362349e17bbb75f44031e AS java11

FROM maven:3.9.11-eclipse-temurin-17@sha256:e4a7ace3dc0d645ed97f8d9ad0b0d3f0b14fa8d150138f27f116d7105a639b82 AS java17

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /src
COPY . .
RUN --mount=type=cache,target=/root/.m2 mvn -B -pl apps/java-engine-worker -am -DskipTests package

FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237
RUN groupadd --gid 10001 elmos \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/elmos --shell /usr/sbin/nologin elmos \
    && mkdir -p /app /workspace/private-runner /home/elmos/.m2 \
    && chown -R 10001:10001 /app /workspace/private-runner /home/elmos
COPY --from=java8 /opt/java/openjdk /opt/java/openjdk-8
COPY --from=java11 /opt/java/openjdk /opt/java/openjdk-11
COPY --from=java17 /opt/java/openjdk /opt/java/openjdk-17
COPY --from=build /src/apps/java-engine-worker/target/elmos-java-engine-worker-0.1.0-SNAPSHOT-exec.jar /app/app.jar
ENV ELMOS_SOURCE_JAVA_HOME=/opt/java/openjdk-17 \
    ELMOS_TARGET_JAVA_HOME=/opt/java/openjdk \
    ELMOS_SPRING_UPGRADE_JAVA_HOMES=8=/opt/java/openjdk-8,11=/opt/java/openjdk-11 \
    ELMOS_MAVEN_EXECUTABLE=/usr/share/maven/bin/mvn
USER 10001:10001
EXPOSE 8081
ENTRYPOINT ["java","-XX:MaxRAMPercentage=70","-jar","/app/app.jar"]
CMD []
