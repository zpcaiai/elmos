package io.elmos.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static io.elmos.verifier.VerificationModels.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SpringArtifactVerifierTest {
    private static final byte[] SECRET =
            "0123456789abcdef0123456789abcdef".getBytes(StandardCharsets.UTF_8);
    private static final Instant NOW = Instant.parse("2026-07-26T10:00:00Z");

    @TempDir Path temporary;
    private Path input;
    private Path evidence;
    private ObjectMapper json;
    private SpringArtifactVerifier verifier;

    @BeforeEach
    void setUp() throws IOException {
        input = temporary.resolve("input");
        evidence = temporary.resolve("evidence");
        Files.createDirectories(input);
        json = new ObjectMapper().findAndRegisterModules();
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        MavenVerification maven = fakeMaven();
        verifier = new SpringArtifactVerifier(
                "verifier-a",
                input,
                evidence,
                new VerifierAuthentication(SECRET, clock, 90),
                maven,
                json,
                clock
        );
    }

    private static MavenVerification fakeMaven() {
        return (project, log) -> {
            try {
                Files.writeString(log, "[INFO] BUILD SUCCESS\n", StandardOpenOption.CREATE_NEW);
                createBootJar(project.resolve("target/application.jar"));
                return List.of("/usr/share/maven/bin/mvn", "-B", "--no-transfer-progress", "verify");
            } catch (IOException error) {
                throw new IllegalStateException(error);
            }
        };
    }

    @Test
    void validatesImmutableArtifactAndReplaysStoredDigestBoundReceipt() throws Exception {
        Path artifact = input.resolve("spring-upgrades/run/download/project.zip");
        writeProject(artifact, "3.5.3", "21");
        Request request = new Request(
                UUID.randomUUID().toString(),
                input.relativize(artifact).toString(),
                sha256(artifact)
        );

        Response first = invoke(request, UUID.randomUUID().toString());
        Response replay = invoke(request, UUID.randomUUID().toString());

        assertThat(first.status()).isEqualTo("PASS");
        assertThat(first.physicallySeparateVerifierService()).isTrue();
        assertThat(first.transformCapability()).isFalse();
        assertThat(first.artifactSha256()).isEqualTo(request.artifactSha256());
        assertThat(first.evidenceSha256()).hasSize(64);
        assertThat(first.logSha256()).hasSize(64);
        assertThat(first.runtimeArtifactSha256()).hasSize(64);
        assertThat(first.runtimeArtifactBytes()).isPositive();
        assertThat(replay).isEqualTo(first);
        assertThat(Files.exists(evidence.resolve(first.evidenceRelativePath()))).isTrue();
        assertThat(Files.exists(evidence.resolve(first.logRelativePath()))).isTrue();
        assertThat(Files.exists(evidence.resolve(first.runtimeArtifactRelativePath()))).isTrue();
        assertThat(evidence.resolve(request.runId()).resolve(request.artifactSha256().substring(0, 16))
                .resolve("candidate")).doesNotExist();
    }

    @Test
    void rejectsDigestMismatchBeforeExecution() throws Exception {
        Path artifact = input.resolve("project.zip");
        writeProject(artifact, "3.5.3", "21");
        Request request = new Request(
                UUID.randomUUID().toString(),
                "project.zip",
                "0".repeat(64)
        );

        assertThatThrownBy(() -> invoke(request, UUID.randomUUID().toString()))
                .isInstanceOf(Rejected.class)
                .extracting(error -> ((Rejected) error).code())
                .isEqualTo("ARTIFACT_DIGEST_MISMATCH");
    }

    @Test
    void rejectsZipSlipAndExactTargetTupleMismatch() throws Exception {
        Path malicious = input.resolve("malicious.zip");
        Files.createDirectories(malicious.getParent());
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(malicious))) {
            zip.putNextEntry(new ZipEntry("../escape"));
            zip.write("no".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
        Request maliciousRequest = new Request(
                UUID.randomUUID().toString(), "malicious.zip", sha256(malicious));
        assertThatThrownBy(() -> invoke(maliciousRequest, UUID.randomUUID().toString()))
                .isInstanceOf(Rejected.class)
                .extracting(error -> ((Rejected) error).code())
                .isEqualTo("ARTIFACT_EXTRACTION_REJECTED");

        Path wrong = input.resolve("wrong.zip");
        writeProject(wrong, "3.4.0", "21");
        Request wrongRequest = new Request(
                UUID.randomUUID().toString(), "wrong.zip", sha256(wrong));
        assertThatThrownBy(() -> invoke(wrongRequest, UUID.randomUUID().toString()))
                .isInstanceOf(Rejected.class)
                .extracting(error -> ((Rejected) error).code())
                .isEqualTo("TARGET_TUPLE_MISMATCH");
    }

    @Test
    void rejectsReplayAndInvalidSignature() throws Exception {
        Path artifact = input.resolve("project.zip");
        writeProject(artifact, "3.5.3", "21");
        Request request = new Request(
                UUID.randomUUID().toString(), "project.zip", sha256(artifact));
        byte[] body = json.writeValueAsBytes(request);
        String timestamp = Long.toString(NOW.getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        String signature = VerifierAuthentication.sign(SECRET, timestamp, nonce, body);

        verifier.verify(timestamp, nonce, signature, body);
        assertThatThrownBy(() -> verifier.verify(timestamp, nonce, signature, body))
                .isInstanceOf(Rejected.class)
                .extracting(error -> ((Rejected) error).code())
                .isEqualTo("UNAUTHORIZED");

        assertThatThrownBy(() -> verifier.verify(
                timestamp, UUID.randomUUID().toString(), "0".repeat(64), body))
                .isInstanceOf(Rejected.class)
                .extracting(error -> ((Rejected) error).code())
                .isEqualTo("UNAUTHORIZED");
    }

    @Test
    void selectsTheExactJava17VerifierForOlderBootTargets() throws Exception {
        Clock clock = Clock.fixed(NOW, ZoneOffset.UTC);
        verifier = new SpringArtifactVerifier(
                "verifier-a",
                input,
                evidence,
                new VerifierAuthentication(SECRET, clock, 90),
                Map.of("17", fakeMaven()),
                json,
                clock
        );
        Path artifact = input.resolve("boot-2.7-java17.zip");
        writeProject(artifact, "2.7.18", "17");
        Request request = new Request(
                UUID.randomUUID().toString(), "boot-2.7-java17.zip", sha256(artifact),
                "2.7.18", "17");

        Response response = invoke(request, UUID.randomUUID().toString());

        assertThat(response.status()).isEqualTo("PASS");
        assertThat(response.targetSpringBoot()).isEqualTo("2.7.18");
        assertThat(response.targetJava()).isEqualTo("17");
    }

    @Test
    void oldThreeFieldWireRequestDefaultsOnlyToTheOriginalTarget() throws Exception {
        Request restored = json.readValue("""
                {
                  "runId": "123e4567-e89b-42d3-a456-426614174000",
                  "artifactRelativePath": "candidate.zip",
                  "artifactSha256": "%s"
                }
                """.formatted("a".repeat(64)), Request.class);

        assertThat(restored.targetSpringBoot()).isEqualTo("3.5.3");
        assertThat(restored.targetJava()).isEqualTo("21");
    }

    private Response invoke(Request request, String nonce) throws Exception {
        byte[] body = json.writeValueAsBytes(request);
        String timestamp = Long.toString(NOW.getEpochSecond());
        return verifier.verify(
                timestamp,
                nonce,
                VerifierAuthentication.sign(SECRET, timestamp, nonce, body),
                body
        );
    }

    private static void writeProject(Path artifact, String boot, String java) throws IOException {
        Files.createDirectories(artifact.getParent());
        String pom = """
                <?xml version="1.0" encoding="UTF-8"?>
                <project xmlns="http://maven.apache.org/POM/4.0.0">
                  <modelVersion>4.0.0</modelVersion>
                  <parent>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-parent</artifactId>
                    <version>%s</version>
                  </parent>
                  <groupId>example</groupId><artifactId>demo</artifactId><version>1.0</version>
                  <properties><java.version>%s</java.version></properties>
                </project>
                """.formatted(boot, java);
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(artifact))) {
            zip.putNextEntry(new ZipEntry("pom.xml"));
            zip.write(pom.getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
    }

    private static void createBootJar(Path path) throws IOException {
        Files.createDirectories(path.getParent());
        try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(path))) {
            zip.putNextEntry(new ZipEntry("META-INF/MANIFEST.MF"));
            zip.write("Manifest-Version: 1.0\n".getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
            zip.putNextEntry(new ZipEntry("BOOT-INF/classes/"));
            zip.closeEntry();
        }
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }
}
