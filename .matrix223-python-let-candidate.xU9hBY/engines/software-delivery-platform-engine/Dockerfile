FROM maven:3.9.11-eclipse-temurin-21@sha256:66f7d4ef603ef4fe9592494c9f7981e3b2af447010225d33738efda5556f33c2 AS build
WORKDIR /workspace
COPY . .
RUN mvn -B -pl engines/software-delivery-platform-engine -am package -DskipTests

FROM eclipse-temurin:21.0.8_9-jre-alpine@sha256:5d86cf6fece431ed36d8e93edce193127ce1659067650691b4399a693b9b8f69
RUN addgroup -S elmos && adduser -S -G elmos -u 10001 elmos
WORKDIR /app
COPY --from=build /workspace/engines/software-delivery-platform-engine/target/*-exec.jar app.jar
USER 10001
EXPOSE 8096
ENTRYPOINT ["java","-jar","/app/app.jar"]
