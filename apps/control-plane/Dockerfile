FROM maven:3.9.10-amazoncorretto-21 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -pl apps/control-plane -am package
FROM amazoncorretto:21.0.6-alpine3.21
RUN addgroup -S elmos && adduser -S -G elmos -u 10001 elmos
USER 10001
COPY --from=build /workspace/apps/control-plane/target/elmos-control-plane-0.1.0-SNAPSHOT-exec.jar /app.jar
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app.jar"]
