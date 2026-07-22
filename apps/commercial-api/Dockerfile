FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -pl apps/commercial-api -am package
FROM eclipse-temurin:21-jre@sha256:27339648ce6fc450b3b14701ba8f40141186273fc61f24d93c0e4d6b5b27c396
RUN groupadd --gid 10001 elmos && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin elmos
WORKDIR /opt/elmos
COPY --from=build /workspace/apps/commercial-api/target/elmos-commercial-api-0.1.0-SNAPSHOT-exec.jar app.jar
USER 10001:10001
EXPOSE 8085
ENTRYPOINT ["java","-jar","/opt/elmos/app.jar"]
