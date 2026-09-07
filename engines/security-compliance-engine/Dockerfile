FROM eclipse-temurin:21-jre@sha256:273396ed5998598ed1091e8d72711c2d36980a0e65103859c55a4e977a41ffd3
WORKDIR /app
COPY engines/security-compliance-engine/target/elmos-security-compliance-engine-0.1.0-SNAPSHOT-exec.jar app.jar
USER 65532:65532
EXPOSE 8091
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
