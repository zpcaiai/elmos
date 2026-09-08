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
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

import static io.elmos.worker.SpringUpgradeModels.*;

/**
 * Independent validation client. The verifier is a separate service whose input mount is
 * read-only and whose binary has no transform capability.
 */
final class HttpSpringUpgradeIndependentValidator implements SpringUpgradeIndependentValidationPort {
    private final Path workspaceRoot;
    private final URI endpoint;
    private final String expectedVerifierId;
    private final byte[] secret;
    private final ObjectMapper json;
    private final Clock clock;
    private final HttpClient client;

    HttpSpringUpgradeIndependentValidator(
            Path workspaceRoot,
            URI verifierBaseUrl,
            Path secretFile,
            String expectedVerifierId,
            ObjectMapper json,
            Clock clock
    ) {
        this(workspaceRoot, verifierBaseUrl, secretFile, expectedVerifierId, json, clock, false);
    }

    /**
     * Package-private transport escape hatch for loopback-only protocol tests.
     * Production configuration always uses the HTTPS-only constructor above.
     */
    HttpSpringUpgradeIndependentValidator(
            Path workspaceRoot,
            URI verifierBaseUrl,
            Path secretFile,
            String expectedVerifierId,
            ObjectMapper json,
            Clock clock,
            boolean allowLoopbackHttpForTests
    ) {
        this.workspaceRoot = workspaceRoot.toAbsolutePath().normalize();
        this.endpoint = endpoint(verifierBaseUrl, allowLoopbackHttpForTests);
        this.expectedVerifierId = requireIdentifier(expectedVerifierId);
        this.secret = SpringHmacProtocol.readSecret(secretFile, "independent verifier");
        this.json = Objects.requireNonNull(json);
        this.clock = Objects.requireNonNull(clock);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public IndependentValidationResult validate(
            ExecutionResult result,
            Path rawRunRoot,
            SpringUpgradeExecutionPort.Control control
    ) {
        Path runRoot = confined(rawRunRoot);
        Path artifact = result.downloadArtifact().toAbsolutePath().normalize();
        if (!artifact.startsWith(workspaceRoot)
                || !Files.isRegularFile(artifact, LinkOption.NOFOLLOW_LINKS)
                || Files.isSymbolicLink(artifact)) {
            throw blocked("ARTIFACT_UNAVAILABLE",
                    "Candidate artifact is unavailable for independent validation.");
        }
        control.stage(Stage.INDEPENDENT_VALIDATION,
                "Physically separate verifier is compiling and testing the immutable artifact");
        if (control.cancelled()) {
            throw blocked("INDEPENDENT_VALIDATION_CANCELLED",
                    "Independent validation was cancelled.");
        }
        try {
            TargetTuple target = targetTuple(result, runRoot);
            byte[] body = json.writeValueAsBytes(new VerificationRequest(
                    runRoot.getFileName().toString(),
                    workspaceRoot.relativize(artifact).toString(),
                    result.artifactSha256(),
                    target.springBoot(),
                    target.java()
            ));
            String timestamp = Long.toString(clock.instant().getEpochSecond());
            String nonce = UUID.randomUUID().toString();
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofMinutes(35))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .header("X-ELMOS-Verifier-Timestamp", timestamp)
                    .header("X-ELMOS-Verifier-Nonce", nonce)
                    .header("X-ELMOS-Verifier-Signature", SpringHmacProtocol.sign(
                            secret, SpringHmacProtocol.Role.VERIFIER, timestamp, nonce, body))
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            HttpResponse<byte[]> response = client.send(
                    request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.body().length > 256 * 1024) {
                throw blocked("INDEPENDENT_VERIFIER_PROTOCOL_ERROR",
                        "Independent verifier response exceeded its policy limit.");
            }
            if (response.statusCode() != 200) {
                throw verifierFailure(response);
            }
            VerificationResponse decision = json.readValue(response.body(), VerificationResponse.class);
            validateDecision(decision, result, target);
            Instant decidedAt = Objects.requireNonNull(decision.decidedAt());
            Path evidence = runRoot.resolve("evidence/independent-validation.json");
            Map<String, Object> receipt = new LinkedHashMap<>();
            receipt.put("schema_version", "2.0");
            receipt.put("producer_role", "TRANSFORMER");
            receipt.put("verifier_role", "INDEPENDENT_VALIDATOR");
            receipt.put("verifier_id", decision.verifierId());
            receipt.put("verifier_endpoint_authority", endpoint.getAuthority());
            receipt.put("fresh_artifact_workspace", decision.freshArtifactWorkspace());
            receipt.put("transform_capability", decision.transformCapability());
            receipt.put("physically_separate_verifier_service", decision.physicallySeparateVerifierService());
            receipt.put("artifact_sha256", decision.artifactSha256());
            receipt.put("target_spring_boot", decision.targetSpringBoot());
            receipt.put("target_java", decision.targetJava());
            receipt.put("remote_evidence_relative_path", decision.evidenceRelativePath());
            receipt.put("remote_evidence_sha256", decision.evidenceSha256());
            receipt.put("remote_evidence_bytes", decision.evidenceBytes());
            receipt.put("remote_log_relative_path", decision.logRelativePath());
            receipt.put("remote_log_sha256", decision.logSha256());
            receipt.put("remote_log_bytes", decision.logBytes());
            receipt.put("remote_runtime_artifact_relative_path", decision.runtimeArtifactRelativePath());
            receipt.put("remote_runtime_artifact_sha256", decision.runtimeArtifactSha256());
            receipt.put("remote_runtime_artifact_bytes", decision.runtimeArtifactBytes());
            receipt.put("command", decision.command());
            receipt.put("status", decision.status());
            receipt.put("decided_at", decidedAt);
            atomicJson(evidence, receipt);
            control.log("Independent verifier PASS: " + decision.verifierId()
                    + " evidence=" + decision.evidenceSha256());
            return new IndependentValidationResult(
                    "PASS",
                    decision.verifierId(),
                    decision.artifactSha256(),
                    runRoot.relativize(evidence).toString(),
                    decidedAt
            );
        } catch (BlockedException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw blocked("INDEPENDENT_VALIDATION_INTERRUPTED",
                    "Independent verifier request was interrupted.");
        } catch (IOException | RuntimeException error) {
            if (error instanceof BlockedException blocked) throw blocked;
            throw blocked("INDEPENDENT_VERIFIER_UNAVAILABLE",
                    "Independent verifier could not be reached or returned an invalid response.");
        }
    }

    @Override
    public boolean configured() {
        return true;
    }

    @Override
    public String configurationReason() {
        return "Separate read-only artifact verifier is configured with digest-bound HMAC requests.";
    }

    private void validateDecision(
            VerificationResponse decision,
            ExecutionResult result,
            TargetTuple target
    ) {
        if (decision == null
                || !"PASS".equals(decision.status())
                || !expectedVerifierId.equals(decision.verifierId())
                || !result.artifactSha256().equals(decision.artifactSha256())
                || !target.springBoot().equals(decision.targetSpringBoot())
                || !target.java().equals(decision.targetJava())
                || !decision.freshArtifactWorkspace()
                || decision.transformCapability()
                || !decision.physicallySeparateVerifierService()
                || decision.evidenceRelativePath() == null
                || !decision.evidenceRelativePath().matches("[a-zA-Z0-9._/-]{3,512}")
                || decision.logRelativePath() == null
                || !decision.logRelativePath().matches("[a-zA-Z0-9._/-]{3,512}")
                || decision.evidenceSha256() == null
                || !decision.evidenceSha256().matches("[0-9a-f]{64}")
                || decision.logSha256() == null
                || !decision.logSha256().matches("[0-9a-f]{64}")
                || decision.runtimeArtifactRelativePath() == null
                || !decision.runtimeArtifactRelativePath().matches("[a-zA-Z0-9._/-]{3,512}")
                || decision.runtimeArtifactSha256() == null
                || !decision.runtimeArtifactSha256().matches("[0-9a-f]{64}")
                || decision.evidenceBytes() <= 0
                || decision.logBytes() < 0
                || decision.runtimeArtifactBytes() <= 0
                || decision.command() == null
                || !decision.command().contains("verify")
                || decision.decidedAt() == null) {
            throw blocked("INDEPENDENT_VERIFIER_PROTOCOL_ERROR",
                    "Independent verifier returned a decision that violates the verification contract.");
        }
    }

    private TargetTuple targetTuple(ExecutionResult result, Path runRoot) {
        try {
            Path fcm = runRoot.resolve(result.fcmArtifact()).normalize();
            if (!fcm.startsWith(runRoot)
                    || !Files.isRegularFile(fcm, LinkOption.NOFOLLOW_LINKS)
                    || Files.isSymbolicLink(fcm)) {
                throw blocked("FCM_TARGET_TUPLE_UNAVAILABLE",
                        "Authoritative Framework Contract Model is unavailable to the verifier client.");
            }
            JsonNode tuple = json.readTree(fcm.toFile()).path("exact_tuple");
            String boot = tuple.path("targetSpringBoot").asText("");
            String java = tuple.path("targetJava").asText("");
            if (!supportedTarget(boot, java)) {
                throw blocked("FCM_TARGET_TUPLE_UNSUPPORTED",
                        "Framework Contract Model requested a target outside the verifier allowlist.");
            }
            return new TargetTuple(boot, java);
        } catch (BlockedException error) {
            throw error;
        } catch (IOException error) {
            throw blocked("FCM_TARGET_TUPLE_UNAVAILABLE",
                    "Authoritative Framework Contract Model could not be read by the verifier client.");
        }
    }

    private static boolean supportedTarget(String boot, String java) {
        return ("2.7.18".equals(boot) && "17".equals(java))
                || ("3.2.12".equals(boot) && "17".equals(java))
                || ("3.5.3".equals(boot) && "21".equals(java));
    }

    private BlockedException verifierFailure(HttpResponse<byte[]> response) {
        try {
            JsonNode payload = json.readTree(response.body());
            String code = payload.path("code").asText("INDEPENDENT_VALIDATION_FAILED");
            String message = payload.path("message").asText("Independent verification failed.");
            if (!code.matches("[A-Z0-9_]{3,80}")) code = "INDEPENDENT_VALIDATION_FAILED";
            if (message.length() > 500) message = "Independent verification failed.";
            return blocked(code, message);
        } catch (IOException error) {
            return blocked("INDEPENDENT_VERIFIER_UNAVAILABLE",
                    "Independent verifier rejected the request without a valid failure receipt.");
        }
    }

    private Path confined(Path raw) {
        Path path = raw.toAbsolutePath().normalize();
        if (!path.startsWith(workspaceRoot) || path.equals(workspaceRoot)) {
            throw blocked("WORKSPACE_PATH_REJECTED",
                    "Independent validation path must remain below the workspace root.");
        }
        return path;
    }

    private void atomicJson(Path path, Object value) throws IOException {
        Files.createDirectories(path.getParent());
        Path temporary = Files.createTempFile(path.getParent(), path.getFileName().toString(), ".tmp");
        try {
            json.writerWithDefaultPrettyPrinter().writeValue(temporary.toFile(), value);
            try {
                Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, path, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
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
                || base.getFragment() != null
                || base.getQuery() != null) {
            throw new IllegalArgumentException(
                    "independent verifier base URL must use absolute HTTPS");
        }
        String normalized = base.toString().endsWith("/")
                ? base.toString()
                : base + "/";
        return URI.create(normalized).resolve("internal/v1/spring-verifications");
    }

    private static boolean loopbackHost(String host) {
        return host != null && ("localhost".equalsIgnoreCase(host)
                || "127.0.0.1".equals(host)
                || "::1".equals(host)
                || "[::1]".equals(host));
    }

    private static String requireIdentifier(String value) {
        if (value == null || !value.matches("[a-zA-Z0-9._-]{3,96}")) {
            throw new IllegalArgumentException("independent verifier ID is invalid");
        }
        return value;
    }

    private static BlockedException blocked(String code, String message) {
        return new BlockedException(code, message);
    }

    private record VerificationRequest(
            String runId,
            String artifactRelativePath,
            String artifactSha256,
            String targetSpringBoot,
            String targetJava
    ) {}

    private record TargetTuple(String springBoot, String java) {}

    private record VerificationResponse(
            String status,
            String verifierId,
            String artifactSha256,
            String targetSpringBoot,
            String targetJava,
            boolean freshArtifactWorkspace,
            boolean transformCapability,
            boolean physicallySeparateVerifierService,
            String evidenceRelativePath,
            String logRelativePath,
            String evidenceSha256,
            long evidenceBytes,
            String logSha256,
            long logBytes,
            String runtimeArtifactRelativePath,
            String runtimeArtifactSha256,
            long runtimeArtifactBytes,
            List<String> command,
            Instant decidedAt
    ) {}
}
