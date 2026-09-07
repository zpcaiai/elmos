package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.security.SpringHmacProtocol;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.*;
import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

import static io.elmos.worker.SpringUpgradeModels.*;

/**
 * Decorates transformation with a physically separate per-run rootless application runtime.
 * The control Worker never receives a Docker socket.
 */
final class IsolatedSpringRuntimeExecutionPort implements SpringUpgradeExecutionPort {
    private final SpringUpgradeExecutionPort transformer;
    private final Path workspaceRoot;
    private final URI endpoint;
    private final byte[] secret;
    private final ObjectMapper json;
    private final Clock clock;
    private final HttpClient client;

    IsolatedSpringRuntimeExecutionPort(
            SpringUpgradeExecutionPort transformer,
            Path workspaceRoot,
            URI runtimeBaseUrl,
            Path secretFile,
            ObjectMapper json,
            Clock clock
    ) {
        this(transformer, workspaceRoot, runtimeBaseUrl, secretFile, json, clock, false);
    }

    /**
     * Package-private transport escape hatch for loopback-only protocol tests.
     * Production configuration always uses the HTTPS-only constructor above.
     */
    IsolatedSpringRuntimeExecutionPort(
            SpringUpgradeExecutionPort transformer,
            Path workspaceRoot,
            URI runtimeBaseUrl,
            Path secretFile,
            ObjectMapper json,
            Clock clock,
            boolean allowLoopbackHttpForTests
    ) {
        this.transformer = Objects.requireNonNull(transformer);
        this.workspaceRoot = workspaceRoot.toAbsolutePath().normalize();
        this.endpoint = endpoint(runtimeBaseUrl, allowLoopbackHttpForTests);
        this.secret = SpringHmacProtocol.readSecret(secretFile, "Rootless Runtime");
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public ExecutionResult execute(StartRequest request, Path runRoot, Control control) {
        return transformer.execute(request, runRoot, control);
    }

    @Override
    public RuntimeHandle start(
            ExecutionResult result,
            StartRequest request,
            Path rawRunRoot,
            Control control
    ) {
        Path runRoot = confined(rawRunRoot);
        control.stage(Stage.START_APPLICATION,
                "Starting the independently built Boot JAR in a dedicated rootless runtime");
        RuntimeArtifact runtimeArtifact = verifiedRuntimeArtifact(runRoot);
        RuntimeResponse response = request(new RuntimeRequest(
                "START",
                runRoot.getFileName().toString(),
                request.organizationId(),
                runtimeArtifact.relativePath(),
                runtimeArtifact.sha256(),
                result.healthCandidates(),
                request.targetJava()
        ));
        if (!"HEALTHY".equals(response.status())
                || !runRoot.getFileName().toString().equals(response.runtimeId())
                || response.port() != 8080
                || response.healthPath() == null
                || !result.healthCandidates().contains(response.healthPath())) {
            throw blocked("ISOLATED_RUNTIME_PROTOCOL_ERROR",
                    "Rootless Runtime service returned an invalid health decision.");
        }
        response.logs().forEach(control::log);
        control.stage(Stage.HEALTH_CHECK,
                "Dedicated rootless runtime passed loopback health check");
        return new RuntimeHandle(
                null,
                response.runtimeId(),
                request.organizationId(),
                response.port(),
                response.healthPath()
        );
    }

    @Override
    public void stop(RuntimeHandle handle, Control control) {
        if (handle == null || handle.runtimeId() == null) return;
        control.stage(Stage.STOP_APPLICATION,
                "Stopping and deleting the dedicated rootless runtime");
        RuntimeResponse response = request(new RuntimeRequest(
                "STOP",
                handle.runtimeId(),
                handle.organizationId(),
                null,
                null,
                List.of(),
                null
        ));
        if (!"STOPPED".equals(response.status())) {
            throw blocked("ISOLATED_RUNTIME_STOP_FAILED",
                    "Rootless Runtime service did not confirm cleanup.");
        }
        response.logs().forEach(control::log);
    }

    @Override
    public List<String> runtimeLogs(RuntimeHandle handle) {
        if (handle == null || handle.runtimeId() == null) return List.of();
        RuntimeResponse response = request(new RuntimeRequest(
                "LOGS",
                handle.runtimeId(),
                handle.organizationId(),
                null,
                null,
                List.of(),
                null
        ));
        return response.logs();
    }

    @Override public boolean configured() { return transformer.configured(); }
    @Override public boolean experimentalRoutesEnabled() { return transformer.experimentalRoutesEnabled(); }
    @Override public String configurationReason() { return transformer.configurationReason(); }
    @Override public boolean runtimeConfigured() { return true; }
    @Override public String runtimeConfigurationReason() {
        return "Per-run rootless Docker runtime is configured through the isolated Workspace service.";
    }

    private RuntimeResponse request(RuntimeRequest payload) {
        try {
            byte[] body = json.writeValueAsBytes(payload);
            String timestamp = Long.toString(clock.instant().getEpochSecond());
            String nonce = UUID.randomUUID().toString();
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds("START".equals(payload.action()) ? 100 : 30))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .header("X-ELMOS-Runtime-Timestamp", timestamp)
                    .header("X-ELMOS-Runtime-Nonce", nonce)
                    .header("X-ELMOS-Runtime-Signature", SpringHmacProtocol.sign(
                            secret, SpringHmacProtocol.Role.RUNTIME, timestamp, nonce, body))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            HttpResponse<byte[]> response = client.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.body().length > 5 * 1024 * 1024) {
                throw blocked("ISOLATED_RUNTIME_PROTOCOL_ERROR",
                        "Rootless Runtime response exceeded its policy limit.");
            }
            if (response.statusCode() != 200) throw runtimeFailure(response);
            RuntimeResponse value = json.readValue(response.body(), RuntimeResponse.class);
            if (value == null
                    || value.runtimeId() == null
                    || !value.runtimeId().equals(payload.runtimeId())
                    || value.logs() == null) {
                throw blocked("ISOLATED_RUNTIME_PROTOCOL_ERROR",
                        "Rootless Runtime service returned an invalid response.");
            }
            return value;
        } catch (BlockedException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("ISOLATED_RUNTIME_INTERRUPTED",
                    "Rootless Runtime request was interrupted.");
        } catch (IOException | RuntimeException error) {
            if (error instanceof BlockedException blocked) throw blocked;
            throw blocked("ISOLATED_RUNTIME_UNAVAILABLE",
                    "Rootless Runtime service is unavailable or returned invalid data.");
        }
    }

    private BlockedException runtimeFailure(HttpResponse<byte[]> response) {
        try {
            JsonNode payload = json.readTree(response.body());
            String code = payload.path("code").asText("ISOLATED_RUNTIME_FAILED");
            String message = payload.path("message").asText("Rootless Runtime operation failed.");
            if (!code.matches("[A-Z0-9_]{3,80}")) code = "ISOLATED_RUNTIME_FAILED";
            if (message.length() > 500) message = "Rootless Runtime operation failed.";
            return blocked(code, message);
        } catch (IOException error) {
            return blocked("ISOLATED_RUNTIME_UNAVAILABLE",
                    "Rootless Runtime service rejected the request without a valid failure receipt.");
        }
    }

    private Path confined(Path raw) {
        Path path = raw.toAbsolutePath().normalize();
        if (!path.startsWith(workspaceRoot) || path.equals(workspaceRoot)) {
            throw blocked("WORKSPACE_PATH_REJECTED",
                    "Runtime path must remain below the workspace root.");
        }
        return path;
    }

    private RuntimeArtifact verifiedRuntimeArtifact(Path runRoot) {
        Path receipt = runRoot.resolve("evidence/independent-validation.json");
        try {
            JsonNode value = json.readTree(receipt.toFile());
            String path = value.path("remote_runtime_artifact_relative_path").asText();
            String sha = value.path("remote_runtime_artifact_sha256").asText();
            long bytes = value.path("remote_runtime_artifact_bytes").asLong();
            if (!path.matches("[a-zA-Z0-9._/-]{3,512}")
                    || path.startsWith("/")
                    || path.contains("..")
                    || !sha.matches("[0-9a-f]{64}")
                    || bytes <= 0) {
                throw blocked("VERIFIED_RUNTIME_ARTIFACT_RECEIPT_INVALID",
                        "Independent verifier did not provide a valid executable Artifact receipt.");
            }
            return new RuntimeArtifact(path, sha, bytes);
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("VERIFIED_RUNTIME_ARTIFACT_RECEIPT_UNAVAILABLE",
                    "Independent verifier executable Artifact receipt is unavailable.");
        }
    }

    private static URI endpoint(URI base, boolean allowLoopbackHttpForTests) {
        Objects.requireNonNull(base);
        boolean https = "https".equalsIgnoreCase(base.getScheme());
        boolean testLoopbackHttp = allowLoopbackHttpForTests
                && "http".equalsIgnoreCase(base.getScheme())
                && loopbackHost(base.getHost());
        if (!base.isAbsolute()
                || (!https && !testLoopbackHttp)
                || base.getHost() == null
                || base.getUserInfo() != null
                || base.getQuery() != null
                || base.getFragment() != null) {
            throw new IllegalArgumentException(
                    "Rootless Runtime base URL must use absolute HTTPS");
        }
        String normalized = base.toString().endsWith("/") ? base.toString() : base + "/";
        return URI.create(normalized).resolve("internal/v1/spring-runtimes");
    }

    private static boolean loopbackHost(String host) {
        return host != null && ("localhost".equalsIgnoreCase(host)
                || "127.0.0.1".equals(host)
                || "::1".equals(host)
                || "[::1]".equals(host));
    }

    private static BlockedException blocked(String code, String message) {
        return new BlockedException(code, message);
    }

    private record RuntimeRequest(
            String action,
            String runtimeId,
            String organizationId,
            String artifactRelativePath,
            String artifactSha256,
            List<String> healthCandidates,
            String targetJava
    ) {}

    private record RuntimeResponse(
            String status,
            String runtimeId,
            String imageDigest,
            int port,
            String healthPath,
            List<String> logs,
            boolean logsTruncated
    ) {}

    private record RuntimeArtifact(String relativePath, String sha256, long bytes) {}
}
