FROM maven:3.9.16-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY . .
RUN mvn -q -pl engine-cli -am package

FROM eclipse-temurin:21-jre-alpine
WORKDIR /engine
COPY --from=build /workspace/engine-cli/target/java-engine-cli.jar /engine/java-engine-cli.jar
ENTRYPOINT ["java", "-jar", "/engine/java-engine-cli.jar"]
