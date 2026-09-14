FROM eclipse-temurin:21-jre
WORKDIR /app
RUN useradd -r -u 10001 elmos
COPY app.jar /app/app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/app.jar"]
