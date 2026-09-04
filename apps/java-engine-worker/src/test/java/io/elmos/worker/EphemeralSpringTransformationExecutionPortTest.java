package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.elmos.security.SpringHmacProtocol;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.security.MessageDigest;
import java.time.Clock;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

import static io.elmos.worker.SpringUpgradeModels.*;
import static org.junit.jupiter.api.Assertions.*;

class EphemeralSpringTransformationExecutionPortTest {
    @TempDir Path temporary;

    @Test
    void productionRequiresHttpsAndTestTransportAllowsOnlyLoopbackHttp() throws Exception {
        Path secret = secretFile(
                "transport-secret",
                "transformer-transport-test-secret-0123456789".getBytes(StandardCharsets.UTF_8));
        ObjectMapper json = new ObjectMapper().findAndRegisterModules();

        assertDoesNotThrow(() -> new EphemeralSpringTransformationExecutionPort(
                temporary,
                URI.create("https://transformer.example.test"),
                secret,
                false,
                json,
                Clock.systemUTC()
        ));

        IllegalArgumentException productionHttp = assertThrows(
                IllegalArgumentException.class,
                () -> new EphemeralSpringTransformationExecutionPort(
                        temporary,
                        URI.create("http://127.0.0.1:8083"),
                        secret,
                        false,
                        json,
                        Clock.systemUTC()
                ));
        assertTrue(productionHttp.getMessage().contains("absolute HTTPS"));
        assertThrows(IllegalArgumentException.class, () -> new EphemeralSpringTransformationExecutionPort(
                temporary,
                URI.create("/relative-transformer"),
                secret,
                false,
                json,
                Clock.systemUTC()
        ));

        assertDoesNotThrow(() -> new EphemeralSpringTransformationExecutionPort(
                temporary,
                URI.create("http://127.0.0.1:8083"),
                secret,
                false,
                json,
                Clock.systemUTC(),
                true
        ));
        assertThrows(IllegalArgumentException.class, () -> new EphemeralSpringTransformationExecutionPort(
                temporary,
                URI.create("http://transformer.example.test:8083"),
                secret,
                false,
                json,
                Clock.systemUTC(),
                true
        ));
    }

    @Test
    void executesThroughDigestBoundHmacBrokerAndReadsDurableProgress() throws Exception {
        ObjectMapper json = new ObjectMapper().findAndRegisterModules();
        byte[] secret = "transformer-test-secret-with-at-least-32-bytes".getBytes(StandardCharsets.UTF_8);
        Path secretFile = secretFile("secret", secret);
        String runId = "11111111-2222-3333-4444-555555555555";
        Path workspace = temporary.resolve("workspace");
        Path runRoot = workspace.resolve("spring-upgrades").resolve(runId).resolve("execution");
        Files.createDirectories(runRoot.resolve("migrated"));
        Files.createDirectories(runRoot.resolve("artifacts"));
        Files.createDirectories(runRoot.resolve("evidence"));
        Files.writeString(runRoot.resolve("evidence/framework-contract-model.json"), "{}");
        Files.writeString(runRoot.resolve("evidence/transform-progress.jsonl"),
                json.writeValueAsString(Map.of(
                        "kind", "stage",
                        "stage", "FINGERPRINT",
                        "message", "exact tuple detected"
                )) + "\n" + json.writeValueAsString(Map.of(
                        "kind", "log",
                        "message", "fingerprint spring-boot=2.7.18"
                )) + "\n");
        byte[] artifactBytes = "exact transformed artifact".getBytes(StandardCharsets.UTF_8);
        Path artifact = runRoot.resolve("artifacts/migrated.zip");
        Files.write(artifact, artifactBytes);
        String artifactSha = sha256(artifactBytes);

        AtomicBoolean authenticated = new AtomicBoolean();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/spring-transformations", exchange -> {
            byte[] requestBody = exchange.getRequestBody().readAllBytes();
            JsonNode request = json.readTree(requestBody);
            assertEquals("TRANSFORM", request.path("action").asText());
            assertEquals(runId, request.path("runId").asText());
            String timestamp = exchange.getRequestHeaders().getFirst("X-ELMOS-Transformer-Timestamp");
            String nonce = exchange.getRequestHeaders().getFirst("X-ELMOS-Transformer-Nonce");
            String signature = exchange.getRequestHeaders().getFirst("X-ELMOS-Transformer-Signature");
            assertEquals(sign(secret, timestamp, nonce, requestBody), signature);
            authenticated.set(true);
            byte[] response = json.writeValueAsBytes(Map.ofEntries(
                    Map.entry("status", "SUCCEEDED"),
                    Map.entry("runId", runId),
                    Map.entry("resolvedCommitSha", "a".repeat(40)),
                    Map.entry("snapshotId", "snapshot-test"),
                    Map.entry("snapshotDigest", "b".repeat(64)),
                    Map.entry("fingerprint", Map.of(
                            "springBootVersion", "2.7.18",
                            "javaVersion", "17",
                            "buildTool", "maven",
                            "modules", List.of(),
                            "activeCapabilities", List.of("web"),
                            "unknowns", List.of(),
                            "sourceTraces", Map.of()
                    )),
                    Map.entry("fcmArtifact", "evidence/framework-contract-model.json"),
                    Map.entry("migratedRepositoryRelativePath", "migrated"),
                    Map.entry("downloadArtifactRelativePath", "artifacts/migrated.zip"),
                    Map.entry("artifactSha256", artifactSha),
                    Map.entry("artifactSize", (long) artifactBytes.length),
                    Map.entry("healthCandidates", List.of("/actuator/health"))
            ));
            send(exchange, 200, response);
        });
        server.start();
        try {
            EphemeralSpringTransformationExecutionPort port =
                    new EphemeralSpringTransformationExecutionPort(
                            workspace,
                            URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                            secretFile,
                            false,
                            json,
                            Clock.systemUTC(),
                            true
                    );
            List<Stage> stages = new ArrayList<>();
            List<String> logs = new ArrayList<>();
            SpringUpgradeExecutionPort.Control control = new SpringUpgradeExecutionPort.Control() {
                @Override public void stage(Stage stage, String message) { stages.add(stage); }
                @Override public void log(String line) { logs.add(line); }
                @Override public void process(Process process) {}
                @Override public boolean cancelled() { return false; }
            };
            ExecutionResult result = port.execute(
                    new StartRequest(
                            "org-test",
                            SourceMode.PUBLIC_GIT,
                            "https://github.com/acme/orders.git",
                            "main",
                            "a".repeat(40),
                            null,
                            null,
                            false,
                            "idempotency-test"
                    ),
                    runRoot,
                    control
            );

            assertTrue(authenticated.get());
            assertEquals(artifactSha, result.artifactSha256());
            assertEquals("2.7.18", result.fingerprint().springBootVersion());
            assertTrue(stages.contains(Stage.FINGERPRINT));
            assertTrue(logs.stream().anyMatch(line -> line.contains("spring-boot=2.7.18")));
            assertTrue(port.configured());
            assertFalse(port.runtimeConfigured());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void rejectsBrokerArtifactDigestMismatch() throws Exception {
        ObjectMapper json = new ObjectMapper().findAndRegisterModules();
        byte[] secret = "transformer-test-secret-with-at-least-32-bytes".getBytes(StandardCharsets.UTF_8);
        Path secretFile = secretFile("mismatch-secret", secret);
        String runId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
        Path workspace = temporary.resolve("mismatch-workspace");
        Path runRoot = workspace.resolve("spring-upgrades").resolve(runId).resolve("execution");
        Files.createDirectories(runRoot.resolve("migrated"));
        Files.createDirectories(runRoot.resolve("artifacts"));
        Files.createDirectories(runRoot.resolve("evidence"));
        Files.writeString(runRoot.resolve("evidence/framework-contract-model.json"), "{}");
        Files.writeString(runRoot.resolve("artifacts/migrated.zip"), "actual");

        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/spring-transformations", exchange -> send(
                exchange,
                200,
                json.writeValueAsBytes(Map.ofEntries(
                        Map.entry("status", "SUCCEEDED"),
                        Map.entry("runId", runId),
                        Map.entry("resolvedCommitSha", "a".repeat(40)),
                        Map.entry("snapshotId", "snapshot-test"),
                        Map.entry("snapshotDigest", "b".repeat(64)),
                        Map.entry("fingerprint", Map.of(
                                "springBootVersion", "2.7.18",
                                "javaVersion", "17",
                                "buildTool", "maven",
                                "modules", List.of(),
                                "activeCapabilities", List.of(),
                                "unknowns", List.of(),
                                "sourceTraces", Map.of()
                        )),
                        Map.entry("fcmArtifact", "evidence/framework-contract-model.json"),
                        Map.entry("migratedRepositoryRelativePath", "migrated"),
                        Map.entry("downloadArtifactRelativePath", "artifacts/migrated.zip"),
                        Map.entry("artifactSha256", "f".repeat(64)),
                        Map.entry("artifactSize", 6L),
                        Map.entry("healthCandidates", List.of("/health"))
                ))
        ));
        server.start();
        try {
            EphemeralSpringTransformationExecutionPort port =
                    new EphemeralSpringTransformationExecutionPort(
                            workspace,
                            URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                            secretFile,
                            false,
                            json,
                            Clock.systemUTC(),
                            true
                    );
            BlockedException error = assertThrows(BlockedException.class, () -> port.execute(
                    new StartRequest(
                            "org-test", SourceMode.PUBLIC_GIT,
                            "https://github.com/acme/orders.git", "main",
                            "a".repeat(40), null, null, false, "key"
                    ),
                    runRoot,
                    noOpControl()
            ));
            assertEquals("TRANSFORM_ARTIFACT_DIGEST_MISMATCH", error.code());
        } finally {
            server.stop(0);
        }
    }

    private static SpringUpgradeExecutionPort.Control noOpControl() {
        return new SpringUpgradeExecutionPort.Control() {
            @Override public void stage(Stage stage, String message) {}
            @Override public void log(String line) {}
            @Override public void process(Process process) {}
            @Override public boolean cancelled() { return false; }
        };
    }

    private Path secretFile(String name, byte[] value) throws Exception {
        Path path = temporary.toRealPath().resolve(name);
        Files.write(path, value);
        Files.setPosixFilePermissions(path, Set.of(
                PosixFilePermission.OWNER_READ,
                PosixFilePermission.OWNER_WRITE));
        return path;
    }

    private static void send(HttpExchange exchange, int status, byte[] body) throws java.io.IOException {
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static String sign(
            byte[] secret,
            String timestamp,
            String nonce,
            byte[] body
    ) {
        return SpringHmacProtocol.sign(
                secret, SpringHmacProtocol.Role.TRANSFORMER, timestamp, nonce, body);
    }
}
