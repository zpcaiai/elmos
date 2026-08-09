FROM gradle:9.6.1-jdk21-alpine AS build
WORKDIR /workspace
COPY . .
RUN gradle :app:bootJar --no-daemon

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S app && adduser -S app -G app
WORKDIR /app
COPY --from=build /workspace/app/build/libs/control-plane.jar /app/app.jar
USER app
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
