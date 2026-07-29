package io.elmos.runner;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
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

    public record UploadTicket(String uploadUrl, String storageKey, String contentObjectId) {
    }

    private final AgentConfig config;
    private final HttpClient http;

    public ControlPlaneClient(AgentConfig config) {
        this.config = config;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    // ---- node lifecycle ----------------------------------------------------

    public void register(SandboxAttestation attestation) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("poolId", config.poolId());
        body.put("agentVersion", RunnerAgentMain.VERSION);
        body.put("capabilities", config.capabilities());
        body.put("maxConcurrency", config.maxConcurrency());
        body.put("attestation", attestation.toWire());
        post("/runner/v1/nodes", body, enrolmentHeaders(), 10);
    }

    /** @return true when the control plane has asked this node to drain. */
    public boolean nodeHeartbeat() {
        Map<String, Object> response = post(
                "/runner/v1/nodes/" + config.runnerNodeId() + "/heartbeat",
                Map.of(), enrolmentHeaders(), 10);
        return Json.bool(response, "drainRequested", false);
    }

    // ---- lease lifecycle ---------------------------------------------------

    public List<Lease> claim(int limit) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("capabilities", config.capabilities());
        body.put("limit", limit);
        body.put("leaseSeconds", config.leaseSeconds());

        Map<String, Object> response = post("/runner/v1/leases/claim", body, enrolmentHeaders(), 20);
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

    /** @return true when the user has requested cancellation. */
    public boolean heartbeat(Lease lease, String stage, int progress, Map<String, Object> checkpoint) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("stage", stage);
        body.put("progress", progress);
        body.put("checkpoint", checkpoint);
        body.put("leaseSeconds", config.leaseSeconds());

        Map<String, Object> response = post(
                "/runner/v1/leases/" + lease.leaseId() + "/heartbeat",
                body, leaseHeaders(lease), 10);
        return Json.bool(response, "cancelRequested", false);
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
                Json.string(response, "contentObjectId", ""));
    }

    /** Uploads bytes straight to object storage. The control plane is not in this path. */
    public void uploadArtifact(UploadTicket ticket, Path file, String mediaType) {
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(ticket.uploadUrl()))
                    .timeout(Duration.ofMinutes(10))
                    .header("Content-Type", mediaType)
                    .PUT(HttpRequest.BodyPublishers.ofFile(file))
                    .build();
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
    public void publishArtifact(Lease lease, String contentObjectId, String role, String filename) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("runnerNodeId", config.runnerNodeId());
        body.put("contentObjectId", contentObjectId);
        body.put("artifactRole", role);
        body.put("filename", filename);
        post("/runner/v1/leases/" + lease.leaseId() + "/artifacts/publish", body, leaseHeaders(lease), 60);
    }

    // ---- transport ---------------------------------------------------------

    private Map<String, String> enrolmentHeaders() {
        return Map.of("X-Elmos-Runner-Enrolment", config.enrolmentToken());
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
}
