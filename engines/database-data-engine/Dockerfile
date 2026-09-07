FROM maven:3.9.10-amazoncorretto-21 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -pl engines/database-data-engine -am package

FROM amazoncorretto:21.0.6-alpine3.21
RUN addgroup -S elmos && adduser -S -G elmos -u 10001 elmos
USER 10001
COPY --from=build /workspace/engines/database-data-engine/target/elmos-database-data-engine-0.1.0-SNAPSHOT-exec.jar /app.jar
ENV ELMOS_DATABASE_DATA_PORT=8089
EXPOSE 8089
ENTRYPOINT ["java","-jar","/app.jar"]
