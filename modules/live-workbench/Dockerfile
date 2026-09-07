FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /workspace
COPY . .
RUN --mount=type=cache,target=/root/.m2,sharing=locked \
    mvn -B -pl modules/live-workbench -am package -DskipTests

FROM eclipse-temurin:21-jre@sha256:273396ed5998598ed1091e8d72711c2d36980a0e65103859c55a4e977a41ffd3
RUN groupadd --gid 10001 elmos \
    && useradd --uid 10001 --gid 10001 --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin elmos
WORKDIR /opt/elmos
COPY --from=build /workspace/modules/live-workbench/target/elmos-live-workbench-0.1.0-SNAPSHOT-exec.jar app.jar
USER 10001:10001
EXPOSE 8092
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=4 \
  CMD ["bash", "-ec", "exec 3<>/dev/tcp/127.0.0.1/8092; printf 'GET /actuator/health/readiness HTTP/1.0\r\nHost: localhost\r\n\r\n' >&3; grep -q '\"status\":\"UP\"' <&3"]
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-Djava.io.tmpdir=/tmp", "-jar", "/opt/elmos/app.jar"]
