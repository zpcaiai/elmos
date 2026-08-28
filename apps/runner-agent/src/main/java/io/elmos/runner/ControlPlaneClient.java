package io.elmos.runner;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * HTTP client for the runner-facing control-plane API.
 *
 * <p>Failure taxonomy matters more than convenience here, so responses are split
 * into three kinds and each has a different correct reaction:</p>
 *
 * <ul>
 *   <li><b>Transport / 5xx</b> - retryable. The control plane may be restarting.</li>
 *   <li><b>409 / 412 / 403</b> - the lease is gone or was never ours. Never retry;
 *       abandon the work immediately.</li>
 *   <li><b>4xx other</b> - a bug in this agent. Fail the job with a stable code.</li>
 * </ul>
 */
public final class ControlPlaneClient {
    private static final SecureRandom RANDOM = new SecureRandom();

    public static final class TransportException extends RuntimeException {
        private static final long serialVersionUID = 1L;

        public TransportException(String message) {
            super(message);
        }
    }

    /** The lease is no longer valid. Stop working on it; do not retry. */
    public static final class LeaseLostException extends RuntimeException {
        private static final long serialVersionUID = 1L;
        private final String code;

        public LeaseLostException(String code) {
            super(code);
            this.code = code;
        }

        public String code() {
            return code;
        }
    }

    public record Lease(
            String jobId,
            String leaseId,
            String leaseToken,
            String businessLine,
            String jobKind,
            String runnerImage,
            int budgetWallSeconds,
            int budgetCpuMillis,
            int budgetMemoryMib,
            int attempt,
            Map<String, Object> checkpointCursor,
            Map<String, Object> requestPayload) {
    }

    /** Independent control signals returned by a lease heartbeat. */
    public record HeartbeatSignals(boolean cancelRequested, boolean pauseRequested) {
    }

    public record UploadTicket(
            String uploadUrl,
            String storageKey,
            String contentObjectId,
            Map<String, String> requiredHeaders) {
    }

    private final AgentConfig config;
    private final HttpClient http;
    private final NodeCredentialStore credentialStore;
    private final boolean resumeExistingNode;
    private volatile String nodeToken;
    private volatile Instant nodeTokenExpiresAt;
    private String pendingNextNodeToken;
    private String pendingRotationRequestId;

    public ControlPlaneClient(AgentConfig config) {
        this.config = config;
        this.credentialStore = new NodeCredentialStore(
                config.workRoot(), opaqueToken());
        NodeCredentialStore.State credential =
                credentialStore.state();
        this.nodeToken = credential.currentToken();
        this.resumeExistingNode = credential.preexisting();
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    // ---- node lifecycle ----------------------------------------------------

    public void register(SandboxAttestation attestation) {
        if (resumeExistingNode) {
            recoverPendingRotation();
            Map<String, Object> response = post(
                    "/runner/v1/nodes/" + config.runnerNodeId()
                            + "/resume",
                    Map.of(),
                    nodeHeaders(),
                    10);
            nodeTokenExpiresAt = Instant.parse(
                    Json.string(
                            response,
                            "nodeCredentialExpiresAt",
                            ""));
            return;
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("poolId", config.poolId());
        body.put("agentVersion", RunnerAgentMain.VERSION);
        body.put("capabilities", config.capabilities());
        body.put("maxConcurrency", config.maxConcurrency());
        body.put("nodeTokenSha256", sha256(nodeToken));
        body.put("attestation", attestation.toWire());
        Map<String, Object> response =
                post("/runner/v1/nodes", body, enrolmentHeaders(), 10);
        nodeTokenExpiresAt = Instant.parse(
                Json.string(response, "nodeCredentialExpiresAt", ""));
        credentialStore.markEnrolled();
    }

    /** @return true when the control plane has asked this node to drain. */
    public boolean nodeHeartbeat() {
        rotateNodeCredentialIfNeeded();
        Map<String, Object> response = post(
                "/runner/v1/nodes/" + config.runnerNodeId() + "/heartbeat",
                Map.of(), nodeHeaders(), 10);
        return Json.bool(response, "drainRequested", false);
    }

    // ---- lease lifecycle ---------------------------------------------------

    public List<Lease> claim(int limit, List<String> availableImages) {
        if (availableImages == null || availableImages.isEmpty()
                || availableImages.size() > 32) {
            throw new IllegalArgumentException("RUNNER_AVAILABLE_IMAGES_REQUIRED");
        }
        availableImages.forEach(ContainerRuntime::validateImage);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("capabilities", config.capabilities());
        body.put("availableImages", List.copyOf(availableImages));
        body.put("limit", limit);
        body.put("leaseSeconds", config.leaseSeconds());

        Map<String, Object> response = post(
                "/runner/v1/leases/claim", body, nodeHeaders(), 20);
        List<Lease> leases = new ArrayList<>();
        for (Map<String, Object> item : Json.objects(response, "leases")) {
            leases.add(new Lease(
                    Json.string(item, "jobId", ""),
                    Json.string(item, "leaseId", ""),
                    Json.string(item, "leaseToken", ""),
                    Json.string(item, "businessLine", ""),
                    Json.string(item, "jobKind", ""),
                    Json.string(item, "runnerImage", ""),
                    Json.integer(item, "budgetWallSeconds", 3600),
                    Json.integer(item, "budgetCpuMillis", 4000),
                    Json.integer(item, "budgetMemoryMib", 8192),
                    Json.integer(item, "attempt", 1),
                    Json.object(item, "checkpointCursor"),
                    Json.object(item, "requestPayload")));
        }
        return leases;
    }

    /** @return the durable cancel and pause signals for this lease. */
    public HeartbeatSignals heartbeat(
            Lease lease,
            String stage,
            int progress,
            Map<String, Object> checkpoint
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("stage", stage);
        body.put("progress", progress);
        body.put("checkpoint", checkpoint);
        body.put("leaseSeconds", config.leaseSeconds());

        Map<String, Object> response = post(
                "/runner/v1/leases/" + lease.leaseId() + "/heartbeat",
                body, leaseHeaders(lease), 10);
        return new HeartbeatSignals(
                Json.bool(response, "cancelRequested", false),
                Json.bool(response, "pauseRequested", false));
    }

    public void complete(Lease lease, String status, String resultStatus, String failureCode) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("status", status);
        body.put("resultStatus", resultStatus);
        body.put("failureCode", failureCode);
        post("/runner/v1/leases/" + lease.leaseId() + "/complete", body, leaseHeaders(lease), 15);
    }

    // ---- artifacts ---------------------------------------------------------

    public UploadTicket requestUploadTicket(Lease lease, String contentSha256, long byteSize, String mediaType) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("jobId", lease.jobId());
        body.put("contentSha256", contentSha256);
        body.put("byteSize", byteSize);
        body.put("mediaType", mediaType);

        Map<String, Object> response = post(
                "/runner/v1/leases/" + lease.leaseId() + "/artifacts/upload-ticket",
                body, leaseHeaders(lease), 15);
        return new UploadTicket(
                Json.string(response, "uploadUrl", ""),
                Json.string(response, "storageKey", ""),
                Json.string(response, "contentObjectId", ""),
                strings(Json.object(response, "requiredHeaders")));
    }

    /** Uploads bytes straight to object storage. The control plane is not in this path. */
    public void uploadArtifact(UploadTicket ticket, Path file, String mediaType) {
        try {
            HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(ticket.uploadUrl()))
                    .timeout(Duration.ofMinutes(10))
                    .header("Content-Type", mediaType)
                    .PUT(HttpRequest.BodyPublishers.ofFile(file));
            if (!ticket.requiredHeaders().isEmpty()) {
                builder.headers(flatten(ticket.requiredHeaders()));
            }
            HttpRequest request = builder.build();
            HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() / 100 != 2) {
                throw new TransportException("ARTIFACT_UPLOAD_REJECTED_" + response.statusCode());
            }
        } catch (IOException ex) {
            throw new TransportException("ARTIFACT_UPLOAD_IO");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new TransportException("ARTIFACT_UPLOAD_INTERRUPTED");
        }
    }

    /** Asks the control plane to recompute the digest server-side and publish. */
    public void publishArtifact(
            Lease lease,
            String contentObjectId,
            String contentSha256,
            long byteSize,
            String role,
            String filename) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("jobId", lease.jobId());
        body.put("contentObjectId", contentObjectId);
        body.put("contentSha256", contentSha256);
        body.put("byteSize", byteSize);
        body.put("artifactRole", role);
        body.put("filename", filename);
        body.put("retentionClass", "STANDARD");
        post("/runner/v1/leases/" + lease.leaseId() + "/artifacts/publish", body, leaseHeaders(lease), 60);
    }

    private static Map<String, String> strings(Map<String, Object> values) {
        Map<String, String> result = new LinkedHashMap<>();
        values.forEach((key, value) -> result.put(key, String.valueOf(value)));
        return Map.copyOf(result);
    }

    private static String[] flatten(Map<String, String> headers) {
        String[] values = new String[headers.size() * 2];
        int index = 0;
        for (Map.Entry<String, String> entry : headers.entrySet()) {
            values[index++] = entry.getKey();
            values[index++] = entry.getValue();
        }
        return values;
    }

    // ---- transport ---------------------------------------------------------

    private Map<String, String> enrolmentHeaders() {
        return Map.of("X-Elmos-Runner-Enrolment", config.enrolmentToken());
    }

    private Map<String, String> nodeHeaders() {
        return Map.of("X-Elmos-Runner-Token", nodeToken);
    }

    /**
     * Client-generated rotation is safe across an unknown HTTP response. The
     * pending next token and request id remain stable until the server confirms;
     * the server accepts the old digest only for this exact idempotent retry.
     */
    synchronized void rotateNodeCredentialIfNeeded() {
        if (nodeTokenExpiresAt == null
                || nodeTokenExpiresAt.isAfter(Instant.now().plusSeconds(3600))) {
            return;
        }
        NodeCredentialStore.State durable =
                credentialStore.state();
        if (durable.hasPendingRotation()) {
            pendingNextNodeToken = durable.pendingToken();
            pendingRotationRequestId =
                    durable.rotationRequestId();
        } else if (pendingNextNodeToken == null) {
            String next = opaqueToken();
            String requestId =
                    "rotate-" + java.util.UUID.randomUUID();
            credentialStore.stageRotation(next, requestId);
            pendingNextNodeToken = next;
            pendingRotationRequestId = requestId;
        }
        Map<String, Object> body = Map.of(
                "runnerNodeId", config.runnerNodeId(),
                "nextTokenSha256", sha256(pendingNextNodeToken),
                "rotationRequestId", pendingRotationRequestId);
        Map<String, Object> response = post(
                "/runner/v1/nodes/" + config.runnerNodeId() + "/credential/rotate",
                body,
                Map.of("X-Elmos-Runner-Token", nodeToken),
                10);
        nodeToken = pendingNextNodeToken;
        nodeTokenExpiresAt = Instant.parse(
                Json.string(response, "nodeCredentialExpiresAt", ""));
        credentialStore.commitPending();
        pendingNextNodeToken = null;
        pendingRotationRequestId = null;
    }

    /**
     * Resolves a crash during rotation without guessing server state. The pending
     * token is tried first; if it already authenticates, the server committed. If
     * not, the exact old/new/request tuple is retried idempotently.
     */
    private synchronized void recoverPendingRotation() {
        NodeCredentialStore.State durable =
                credentialStore.state();
        if (!durable.hasPendingRotation()) {
            return;
        }
        try {
            Map<String, Object> resumed = post(
                    "/runner/v1/nodes/" + config.runnerNodeId()
                            + "/resume",
                    Map.of(),
                    Map.of(
                            "X-Elmos-Runner-Token",
                            durable.pendingToken()),
                    10);
            nodeToken = durable.pendingToken();
            nodeTokenExpiresAt = Instant.parse(
                    Json.string(
                            resumed,
                            "nodeCredentialExpiresAt",
                            ""));
            credentialStore.commitPending();
            return;
        } catch (LeaseLostException rejectedPendingToken) {
            // The server still has the current token; replay the exact rotation.
        }

        Map<String, Object> response = post(
                "/runner/v1/nodes/" + config.runnerNodeId()
                        + "/credential/rotate",
                Map.of(
                        "runnerNodeId", config.runnerNodeId(),
                        "nextTokenSha256",
                        sha256(durable.pendingToken()),
                        "rotationRequestId",
                        durable.rotationRequestId()),
                Map.of(
                        "X-Elmos-Runner-Token",
                        durable.currentToken()),
                10);
        nodeToken = durable.pendingToken();
        nodeTokenExpiresAt = Instant.parse(
                Json.string(
                        response,
                        "nodeCredentialExpiresAt",
                        ""));
        credentialStore.commitPending();
    }

    private Map<String, String> leaseHeaders(Lease lease) {
        return Map.of("X-Elmos-Lease-Token", lease.leaseToken());
    }

    private Map<String, Object> post(String path, Map<String, Object> body, Map<String, String> headers, int timeoutSeconds) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(config.controlPlaneBaseUrl() + path))
                .timeout(Duration.ofSeconds(timeoutSeconds))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .header("User-Agent", "elmos-runner-agent/" + RunnerAgentMain.VERSION)
                .POST(HttpRequest.BodyPublishers.ofString(Json.write(body)));
        headers.forEach(builder::header);

        HttpResponse<String> response;
        try {
            response = http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        } catch (IOException ex) {
            throw new TransportException("CONTROL_PLANE_IO");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new TransportException("CONTROL_PLANE_INTERRUPTED");
        }

        int status = response.statusCode();
        if (status / 100 == 2) {
            String payload = response.body();
            return payload == null || payload.isBlank() ? Map.of() : Json.parseObject(payload);
        }

        String code = extractCode(response.body());
        if (status == 403 || status == 409 || status == 412 || status == 404) {
            // Somebody else owns this work now, or we were never entitled to it.
            // Retrying would be the double-run bug.
            throw new LeaseLostException(code);
        }
        if (status / 100 == 5 || status == 429) {
            throw new TransportException(code);
        }
        throw new IllegalStateException("CONTROL_PLANE_REJECTED_" + code);
    }

    private static String extractCode(String body) {
        try {
            if (body != null && !body.isBlank()) {
                return Json.string(Json.parseObject(body), "code", "CONTROL_PLANE_ERROR");
            }
        } catch (RuntimeException ignored) {
            // A non-JSON error body is itself only worth a generic code; the raw
            // text is deliberately not propagated.
        }
        return "CONTROL_PLANE_ERROR";
    }

    private static String opaqueToken() {
        byte[] bytes = new byte[48];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }
}
