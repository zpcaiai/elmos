FROM maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -pl apps/workspace-service -am package -DskipTests

FROM eclipse-temurin:21-jre@sha256:273396ed5998598ed1091e8d72711c2d36980a0e65103859c55a4e977a41ffd3
WORKDIR /app
COPY --from=build /workspace/apps/workspace-service/target/elmos-workspace-service-0.1.0-SNAPSHOT-exec.jar /app/app.jar
USER 10001:10001
EXPOSE 8082
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
