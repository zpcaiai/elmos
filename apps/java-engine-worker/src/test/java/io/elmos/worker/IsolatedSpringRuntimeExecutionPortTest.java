package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static io.elmos.worker.SpringUpgradeModels.*;
import static org.assertj.core.api.Assertions.assertThat;

class IsolatedSpringRuntimeExecutionPortTest {
    private static final byte[] SECRET =
            "runtime-secret-0123456789abcdef0123456789".getBytes(StandardCharsets.UTF_8);
    private static final Instant NOW = Instant.parse("2026-07-26T11:00:00Z");

    @TempDir Path temporary;
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) server.stop(0);
    }

    @Test
    void materializesDigestBoundJarAndCompletesStartLogsStopProtocol() throws Exception {
        ObjectMapper json = new ObjectMapper().findAndRegisterModules();
        List<String> actions = new ArrayList<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/spring-runtimes", exchange -> {
            byte[] body = exchange.getRequestBody().readAllBytes();
            verifySignature(exchange, body);
            JsonNode request = json.readTree(body);
            String action = request.path("action").asText();
            actions.add(action);
            if ("START".equals(action)) {
                assertThat(request.path("artifactRelativePath").asText())
                        .isEqualTo("123e4567-e89b-42d3-a456-426614174000/verified-application.jar");
                assertThat(request.path("artifactSha256").asText()).isEqualTo("e".repeat(64));
            }
            String health = "START".equals(action) ? "/actuator/health" : null;
            String status = switch (action) {
                case "START", "LOGS" -> "HEALTHY";
                case "STOP" -> "STOPPED";
                default -> "BLOCKED";
            };
            respond(exchange, json.writeValueAsBytes(Map.of(
                    "status", status,
                    "runtimeId", request.path("runtimeId").asText(),
                    "imageDigest", "sha256:" + "d".repeat(64),
                    "port", 8080,
                    "healthPath", health == null ? "" : health,
                    "logs", List.of("rootless runtime " + action),
                    "logsTruncated", false
            )), 200);
        });
        server.start();

        Path secret = temporary.resolve("runtime.secret");
        Files.write(secret, SECRET);
        Path migrated = temporary.resolve("runs/migrated");
        Files.createDirectories(migrated);
        Path artifact = temporary.resolve("runs/download.zip");
        Files.write(artifact, new byte[]{1, 2, 3});
        String runId = "123e4567-e89b-42d3-a456-426614174000";
        Path runRoot = temporary.resolve("runs").resolve(runId);
        Files.createDirectories(runRoot.resolve("evidence"));
        json.writerWithDefaultPrettyPrinter().writeValue(
                runRoot.resolve("evidence/independent-validation.json").toFile(),
                Map.of(
                        "remote_runtime_artifact_relative_path", runId + "/verified-application.jar",
                        "remote_runtime_artifact_sha256", "e".repeat(64),
                        "remote_runtime_artifact_bytes", 4096
                )
        );
        IsolatedSpringRuntimeExecutionPort runtime = new IsolatedSpringRuntimeExecutionPort(
                new StubTransformer(),
                temporary.resolve("runs"),
                java.net.URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                secret,
                json,
                Clock.fixed(NOW, ZoneOffset.UTC)
        );
        ExecutionResult result = new ExecutionResult(
                "a".repeat(40),
                "snapshot-1",
                "b".repeat(64),
                new Fingerprint(SOURCE_BOOT, SOURCE_JAVA, "maven",
                        List.of(), List.of("web"), List.of(), Map.of()),
                "evidence/fcm.json",
                migrated,
                artifact,
                sha256(artifact),
                Files.size(artifact),
                List.of("/actuator/health")
        );
        StartRequest request = new StartRequest(
                "org-a", SourceMode.PUBLIC_GIT, "https://github.com/a/b.git", "main",
                null, null, null, false, "idem"
        );
        List<String> logs = new ArrayList<>();
        SpringUpgradeExecutionPort.Control control = new SpringUpgradeExecutionPort.Control() {
            @Override public void stage(Stage stage, String message) {}
            @Override public void log(String line) { logs.add(line); }
            @Override public void process(Process process) {}
            @Override public boolean cancelled() { return false; }
        };

        RuntimeHandle handle = runtime.start(result, request, runRoot, control);
        assertThat(handle.runtimeId()).isEqualTo(runId);
        assertThat(handle.organizationId()).isEqualTo("org-a");
        assertThat(handle.port()).isEqualTo(8080);
        assertThat(handle.healthPath()).isEqualTo("/actuator/health");
        assertThat(runtime.runtimeLogs(handle)).containsExactly("rootless runtime LOGS");
        runtime.stop(handle, control);

        assertThat(actions).containsExactly("START", "LOGS", "STOP");
        assertThat(logs).contains("rootless runtime START", "rootless runtime STOP");
    }

    private static void verifySignature(HttpExchange exchange, byte[] body) {
        String timestamp = exchange.getRequestHeaders().getFirst("X-ELMOS-Runtime-Timestamp");
        String nonce = exchange.getRequestHeaders().getFirst("X-ELMOS-Runtime-Nonce");
        String actual = exchange.getRequestHeaders().getFirst("X-ELMOS-Runtime-Signature");
        assertThat(actual).isEqualTo(sign(timestamp, nonce, body));
    }

    private static String sign(String timestamp, String nonce, byte[] body) {
        try {
            String bodySha = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(body));
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(SECRET, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(
                    (timestamp + "\n" + nonce + "\n" + bodySha).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new RuntimeException(error);
        }
    }

    private static void respond(HttpExchange exchange, byte[] body, int status) throws IOException {
        exchange.getResponseHeaders().set("content-type", "application/json");
        exchange.sendResponseHeaders(status, body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }

    private static String sha256(Path path) throws Exception {
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)));
    }

    private static final class StubTransformer implements SpringUpgradeExecutionPort {
        @Override public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
            throw new UnsupportedOperationException();
        }
        @Override public RuntimeHandle start(ExecutionResult result, StartRequest request, Path runRoot, Control control) {
            throw new UnsupportedOperationException();
        }
        @Override public void stop(RuntimeHandle handle, Control control) {}
        @Override public boolean configured() { return true; }
        @Override public String configurationReason() { return "test"; }
    }
}
