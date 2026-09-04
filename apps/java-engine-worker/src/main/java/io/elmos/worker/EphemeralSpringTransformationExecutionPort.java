package io.elmos.worker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import static io.elmos.worker.SpringUpgradeModels.*;

/**
 * Control-plane adapter for a per-run transformation container. The long-lived Worker does not
 * execute repository code and has no Docker socket; the Workspace broker owns container lifecycle.
 */
final class EphemeralSpringTransformationExecutionPort implements SpringUpgradeExecutionPort {
    private static final long MAX_RESPONSE_BYTES = 512L * 1024;
    private final Path workspaceRoot;
    private final URI endpoint;
    private final byte[] secret;
    private final ObjectMapper json;
    private final Clock clock;
    private final HttpClient client;
    private final boolean experimentalRoutesEnabled;

    EphemeralSpringTransformationExecutionPort(
            Path workspaceRoot,
            URI brokerBaseUrl,
            Path secretFile,
            boolean experimentalRoutesEnabled,
            ObjectMapper json,
            Clock clock
    ) {
        this.workspaceRoot = workspaceRoot.toAbsolutePath().normalize();
        this.endpoint = endpoint(brokerBaseUrl);
        this.secret = readSecret(secretFile);
        this.experimentalRoutesEnabled = experimentalRoutesEnabled;
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public ExecutionResult execute(StartRequest request, Path rawRunRoot, Control control) {
        Path runRoot = confinedExecutionRoot(rawRunRoot);
        String runId = runRoot.getParent().getFileName().toString();
        byte[] body = write(new TransformationRequest("TRANSFORM", runId, request));
        HttpRequest httpRequest = signedRequest(body, Duration.ofMinutes(100));
        CompletableFuture<HttpResponse<byte[]>> future =
                client.sendAsync(httpRequest, HttpResponse.BodyHandlers.ofByteArray());
        int observedProgress = 0;
        try {
            while (true) {
                observedProgress = drainProgress(runRoot, observedProgress, control);
                if (control.cancelled() || Thread.currentThread().isInterrupted()) {
                    future.cancel(true);
                    cancel(runId);
                    throw blocked("TRANSFORMATION_CANCELLED",
                            "The ephemeral transformation was cancelled and its container was removed.");
                }
                try {
                    HttpResponse<byte[]> response = future.get(250, TimeUnit.MILLISECONDS);
                    drainProgress(runRoot, observedProgress, control);
                    return result(runRoot, runId, response);
                } catch (TimeoutException ignored) {
                    // Continue draining durable progress while the isolated container runs.
                }
            }
        } catch (InterruptedException error) {
            future.cancel(true);
            cancelWithClearedInterrupt(runId);
            Thread.currentThread().interrupt();
            throw blocked("TRANSFORMATION_CANCELLED",
                    "The ephemeral transformation was interrupted and its container was removed.");
        } catch (ExecutionException error) {
            cancel(runId);
            throw blocked("EPHEMERAL_TRANSFORMER_UNAVAILABLE",
                    "The per-run transformation service is unavailable.");
        } catch (CancellationException error) {
            cancel(runId);
            throw blocked("TRANSFORMATION_CANCELLED",
                    "The ephemeral transformation was cancelled and its container was removed.");
        }
    }

    @Override
    public RuntimeHandle start(
            ExecutionResult result,
            StartRequest request,
            Path runRoot,
            Control control
    ) {
        throw blocked("ISOLATED_APPLICATION_RUNNER_NOT_CONFIGURED",
                "Application startup requires the dedicated rootless Runtime service.");
    }

    @Override public void stop(RuntimeHandle handle, Control control) {}
    @Override public boolean configured() { return true; }
    @Override public boolean experimentalRoutesEnabled() { return experimentalRoutesEnabled; }
    @Override public String configurationReason() {
        return "Per-run rootless transformation broker is configured; repository code cannot access control Worker credentials.";
    }
    @Override public String runtimeConfigurationReason() {
        return "Configure the separate rootless application Runtime service.";
    }

    private ExecutionResult result(
            Path runRoot,
            String runId,
            HttpResponse<byte[]> response
    ) {
        if (response.body().length > MAX_RESPONSE_BYTES) {
            throw blocked("EPHEMERAL_TRANSFORMER_PROTOCOL_ERROR",
                    "Transformation response exceeded policy.");
        }
        if (response.statusCode() != 200) throw transformationFailure(response);
        try {
            TransformationResponse value = json.readValue(response.body(), TransformationResponse.class);
            if (value == null
                    || !"SUCCEEDED".equals(value.status())
                    || !runId.equals(value.runId())
                    || value.resolvedCommitSha() == null
                    || !value.resolvedCommitSha().matches("[0-9a-f]{40}")
                    || value.snapshotId() == null
                    || value.snapshotDigest() == null
                    || !value.snapshotDigest().matches("[0-9a-f]{64}")
                    || value.fingerprint() == null
                    || value.artifactSha256() == null
                    || !value.artifactSha256().matches("[0-9a-f]{64}")
                    || value.artifactSize() <= 0
                    || value.artifactSize() > 512L * 1024 * 1024
                    || value.healthCandidates() == null
                    || value.healthCandidates().isEmpty()) {
                throw blocked("EPHEMERAL_TRANSFORMER_PROTOCOL_ERROR",
                        "Transformation response violates the exact route contract.");
            }
            Path migrated = confinedOutput(runRoot, value.migratedRepositoryRelativePath(), true);
            Path artifact = confinedOutput(runRoot, value.downloadArtifactRelativePath(), false);
            Path fcm = confinedOutput(runRoot, value.fcmArtifact(), false);
            if (!Files.isRegularFile(fcm, LinkOption.NOFOLLOW_LINKS)
                    || Files.size(artifact) != value.artifactSize()
                    || !value.artifactSha256().equals(sha256(artifact))) {
                throw blocked("TRANSFORM_ARTIFACT_DIGEST_MISMATCH",
                        "Transformation outputs differ from the broker response.");
            }
            return new ExecutionResult(
                    value.resolvedCommitSha(),
                    value.snapshotId(),
                    value.snapshotDigest(),
                    value.fingerprint(),
                    value.fcmArtifact(),
                    migrated,
                    artifact,
                    value.artifactSha256(),
                    value.artifactSize(),
                    value.healthCandidates()
            );
        } catch (BlockedException error) {
            throw error;
        } catch (IOException | RuntimeException error) {
            if (error instanceof BlockedException blocked) throw blocked;
            throw blocked("EPHEMERAL_TRANSFORMER_PROTOCOL_ERROR",
                    "Transformation response or output is invalid.");
        }
    }

    private int drainProgress(Path runRoot, int observed, Control control) {
        Path path = runRoot.resolve("evidence/transform-progress.jsonl");
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) return observed;
        try {
            List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
            if (lines.size() > 10_000) {
                throw blocked("TRANSFORM_PROGRESS_REJECTED",
                        "Transformation progress exceeded its bounded Evidence limit.");
            }
            int start = Math.min(observed, lines.size());
            for (int index = start; index < lines.size(); index++) {
                String line = lines.get(index);
                if (line.length() > 8_192) continue;
                JsonNode value = json.readTree(line);
                String kind = value.path("kind").asText();
                String message = value.path("message").asText();
                if ("stage".equals(kind)) {
                    try {
                        control.stage(Stage.valueOf(value.path("stage").asText()), message);
                    } catch (IllegalArgumentException ignored) {
                        control.log("ephemeral transformer reported an unknown stage");
                    }
                } else if ("log".equals(kind)) {
                    control.log(message);
                }
            }
            return lines.size();
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("TRANSFORM_PROGRESS_UNAVAILABLE",
                    "Transformation progress Evidence could not be read.");
        }
    }

    private void cancelWithClearedInterrupt(String runId) {
        boolean interrupted = Thread.interrupted();
        try {
            cancel(runId);
        } finally {
            if (interrupted) Thread.currentThread().interrupt();
        }
    }

    private void cancel(String runId) {
        try {
            byte[] body = write(new TransformationRequest("CANCEL", runId, null));
            client.send(
                    signedRequest(body, Duration.ofSeconds(20)),
                    HttpResponse.BodyHandlers.discarding()
            );
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        } catch (RuntimeException | IOException ignored) {
            // The broker also force-cleans the container in its request finally block.
        }
    }

    private HttpRequest signedRequest(byte[] body, Duration timeout) {
        String timestamp = Long.toString(clock.instant().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        return HttpRequest.newBuilder(endpoint)
                .timeout(timeout)
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("X-ELMOS-Transformer-Timestamp", timestamp)
                .header("X-ELMOS-Transformer-Nonce", nonce)
                .header("X-ELMOS-Transformer-Signature", sign(secret, timestamp, nonce, body))
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
    }

    private BlockedException transformationFailure(HttpResponse<byte[]> response) {
        try {
            JsonNode value = json.readTree(response.body());
            String code = value.path("code").asText("TRANSFORMATION_FAILED");
            String message = value.path("message").asText("Transformation failed.");
            if (!code.matches("[A-Z0-9_]{3,80}")) code = "TRANSFORMATION_FAILED";
            if (message.length() > 500) message = "Transformation failed.";
            return blocked(code, message);
        } catch (IOException error) {
            return blocked("EPHEMERAL_TRANSFORMER_UNAVAILABLE",
                    "Transformation service rejected the request without a valid receipt.");
        }
    }

    private Path confinedExecutionRoot(Path raw) {
        Path value = raw.toAbsolutePath().normalize();
        Path parent = value.getParent();
        String runId = parent == null ? "" : parent.getFileName().toString();
        try {
            UUID.fromString(runId);
        } catch (IllegalArgumentException error) {
            throw blocked("WORKSPACE_PATH_REJECTED",
                    "Transformation execution path has no valid Run identity.");
        }
        Path expected = workspaceRoot.resolve("spring-upgrades")
                .resolve(runId)
                .resolve("execution")
                .normalize();
        if (!value.equals(expected)
                || !Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(value)) {
            throw blocked("WORKSPACE_PATH_REJECTED",
                    "Transformation execution path is outside its isolated Run workspace.");
        }
        return value;
    }

    private static Path confinedOutput(Path runRoot, String relativeValue, boolean directory) {
        try {
            Path relative = Path.of(relativeValue);
            Path value = runRoot.resolve(relative).normalize();
            boolean expectedType = directory
                    ? Files.isDirectory(value, LinkOption.NOFOLLOW_LINKS)
                    : Files.isRegularFile(value, LinkOption.NOFOLLOW_LINKS);
            if (relative.isAbsolute()
                    || relative.normalize().startsWith("..")
                    || !value.startsWith(runRoot)
                    || value.equals(runRoot)
                    || Files.isSymbolicLink(value)
                    || !expectedType) {
                throw blocked("TRANSFORM_OUTPUT_PATH_REJECTED",
                        "Transformation output is unavailable or outside its run.");
            }
            return value;
        } catch (java.nio.file.InvalidPathException error) {
            throw blocked("TRANSFORM_OUTPUT_PATH_REJECTED",
                    "Transformation output path is invalid.");
        }
    }

    private byte[] write(Object value) {
        try {
            return json.writeValueAsBytes(value);
        } catch (IOException error) {
            throw new IllegalStateException("transformation request could not be encoded", error);
        }
    }

    private static URI endpoint(URI base) {
        Objects.requireNonNull(base);
        if (!List.of("http", "https").contains(base.getScheme())
                || base.getHost() == null
                || base.getUserInfo() != null
                || base.getQuery() != null
                || base.getFragment() != null) {
            throw new IllegalArgumentException("transformation broker base URL is invalid");
        }
        String normalized = base.toString().endsWith("/") ? base.toString() : base + "/";
        return URI.create(normalized).resolve("internal/v1/spring-transformations");
    }

    private static byte[] readSecret(Path path) {
        try {
            if (!Files.isRegularFile(path) || Files.isSymbolicLink(path)) {
                throw new IllegalStateException("transformation broker HMAC secret file is unavailable");
            }
            byte[] raw = Files.readAllBytes(path);
            if (raw.length > 4096) throw new IllegalStateException("transformation broker HMAC secret is too large");
            byte[] value = new String(raw, StandardCharsets.UTF_8).trim().getBytes(StandardCharsets.UTF_8);
            if (value.length < 32) throw new IllegalStateException("transformation broker HMAC secret must contain at least 32 bytes");
            return value;
        } catch (IOException error) {
            throw new IllegalStateException("transformation broker HMAC secret file could not be read", error);
        }
    }

    private static String sha256(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (var input = Files.newInputStream(path)) {
                byte[] buffer = new byte[64 * 1024];
                int count;
                while ((count = input.read(buffer)) >= 0) digest.update(buffer, 0, count);
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception error) {
            throw blocked("TRANSFORM_ARTIFACT_DIGEST_UNAVAILABLE",
                    "Transformation Artifact digest could not be calculated.");
        }
    }

    private static String sign(byte[] secret, String timestamp, String nonce, byte[] body) {
        try {
            String bodySha = HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256").digest(body));
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(
                    (timestamp + "\n" + nonce + "\n" + bodySha).getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException("transformation request signing failed", error);
        }
    }

    private static BlockedException blocked(String code, String message) {
        return new BlockedException(code, message);
    }

    private record TransformationRequest(String action, String runId, StartRequest request) {}

    private record TransformationResponse(
            String status,
            String runId,
            String resolvedCommitSha,
            String snapshotId,
            String snapshotDigest,
            Fingerprint fingerprint,
            String fcmArtifact,
            String migratedRepositoryRelativePath,
            String downloadArtifactRelativePath,
            String artifactSha256,
            long artifactSize,
            List<String> healthCandidates
    ) {}
}
