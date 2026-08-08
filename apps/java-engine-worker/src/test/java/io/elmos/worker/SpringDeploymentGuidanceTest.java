package io.elmos.worker;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertTrue;

class SpringDeploymentGuidanceTest {
    @TempDir Path temporaryDirectory;

    @Test void writesExactLocalAndFailClosedCloudGuidance() throws Exception {
        Files.writeString(temporaryDirectory.resolve("README.md"), "# Customer project\n\nOriginal content.\n");
        SpringDeploymentGuidance.writeTo(temporaryDirectory);

        String readme = Files.readString(temporaryDirectory.resolve("README.md"));
        String local = Files.readString(temporaryDirectory.resolve("docs/LOCAL_RUN.md"));
        String cloud = Files.readString(temporaryDirectory.resolve("docs/CLOUD_DEPLOYMENT.md"));
        String dockerfile = Files.readString(temporaryDirectory.resolve("deploy/cloud-run/Dockerfile"));
        String dockerignore = Files.readString(
                temporaryDirectory.resolve("deploy/cloud-run/Dockerfile.dockerignore"));
        String profile = Files.readString(
                temporaryDirectory.resolve("deploy/cloud-run/deployment-profile.json"));

        assertTrue(readme.contains("Original content."));
        assertTrue(readme.contains("docs/LOCAL_RUN.md"));
        assertTrue(readme.contains("云端执行、恢复和认证证据仍为 `NOT_RUN`"));

        assertTrue(local.contains("Spring Boot 3.5.3 / Java 21 / Maven 3.9.11"));
        assertTrue(local.contains("8 vCPU / 16 GB RAM / 40 GB"));
        assertTrue(local.contains("SERVER_ADDRESS=127.0.0.1 SERVER_PORT=8080"));

        assertTrue(cloud.contains("Google Cloud Run"));
        assertTrue(cloud.contains("--no-allow-unauthenticated"));
        assertTrue(cloud.contains("--image=\"$IMAGE_URI@$IMAGE_DIGEST\""));
        assertTrue(cloud.contains("禁止使用 `latest`"));

        assertTrue(dockerfile.contains(
                "maven:3.9.11-eclipse-temurin-21@sha256:6fdc855a6ed81d288ca7ca37ac6ff5e9308b612485c0801d70b25a858c83d237"));
        assertTrue(dockerfile.contains(
                "eclipse-temurin:21-jre@sha256:27339648ce6fc450b3b14701ba8f40141186273fc61f24d93c0e4d6b5b27c396"));
        assertTrue(dockerfile.contains("USER 10001:10001"));
        assertTrue(dockerignore.contains("**/.env.*"));
        assertTrue(dockerignore.contains("**/*.pem"));

        assertTrue(profile.contains("\"status\": \"CONFIGURATION_REQUIRED\""));
        assertTrue(profile.contains("\"external_execution_evidence\": \"NOT_RUN\""));
        assertTrue(profile.contains("\"image_reference_policy\": \"DIGEST_REQUIRED\""));
    }

    @Test void writesGradleSpecificLocalAndContainerGuidance() throws Exception {
        Files.writeString(temporaryDirectory.resolve("README.md"), "# Customer project\n");
        SpringDeploymentGuidance.writeTo(temporaryDirectory, "gradle");

        assertTrue(Files.readString(temporaryDirectory.resolve("docs/LOCAL_RUN.md"))
                .contains("Gradle 8.14.3"));
        assertTrue(Files.readString(temporaryDirectory.resolve("deploy/cloud-run/Dockerfile"))
                .contains("gradle:8.14.3-jdk21"));
        assertTrue(Files.readString(temporaryDirectory.resolve("deploy/cloud-run/Dockerfile.dockerignore"))
                .contains("**/.gradle"));
    }
}
