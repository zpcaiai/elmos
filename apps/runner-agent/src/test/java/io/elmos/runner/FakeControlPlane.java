package io.elmos.runner;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * In-process control plane used by the agent self-test.
 *
 * <p>It speaks the real protocol over real HTTP - no mocking framework and no
 * stubbed client - so the test exercises the actual serialisation, headers,
 * status-code handling and failure taxonomy the agent will meet in production.</p>
 */
public final class FakeControlPlane implements AutoCloseable {

    public record Completion(String leaseId, String status, String resultStatus, String failureCode) {
    }

    public record PublishedArtifact(String leaseId, String role, String filename, String contentObjectId) {
    }

    private final HttpServer server;
    private final List<Map<String, Object>> pendingLeases = new CopyOnWriteArrayList<>();

    public final List<Completion> completions = new CopyOnWriteArrayList<>();
    public final List<PublishedArtifact> published = new CopyOnWriteArrayList<>();
    public final List<byte[]> uploads = new CopyOnWriteArrayList<>();
    public final List<Map<String, Object>> heartbeats = new CopyOnWriteArrayList<>();
    public final AtomicInteger heartbeatCount = new AtomicInteger();
    public final AtomicInteger claimCount = new AtomicInteger();
    public final AtomicInteger registrationCount = new AtomicInteger();

    public final AtomicBoolean cancelRequested = new AtomicBoolean(false);
    public final AtomicBoolean pauseRequested = new AtomicBoolean(false);
    public final AtomicBoolean drainRequested = new AtomicBoolean(false);
    /** When true every lease heartbeat answers 409, simulating a lease taken over. */
    public final AtomicBoolean leaseStolen = new AtomicBoolean(false);
    private final AtomicBoolean closed = new AtomicBoolean(false);

    public FakeControlPlane() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/runner/v1/nodes", exchange -> {
            String path = exchange.getRequestURI().getPath();
            readBody(exchange);
            if (path.endsWith("/credential/rotate")) {
                respond(exchange, 200, Map.of(
                        "status", "ROTATED",
                        "nodeCredentialExpiresAt", "2030-01-01T00:00:00Z"));
            } else if (path.endsWith("/resume")) {
                respond(exchange, 200, Map.of(
                        "status", "RESUMED",
                        "nodeCredentialExpiresAt", "2030-01-01T00:00:00Z"));
            } else if (path.endsWith("/heartbeat")) {
                respond(exchange, 200, Map.of("drainRequested", drainRequested.get()));
            } else {
                registrationCount.incrementAndGet();
                respond(exchange, 202, Map.of(
                        "status", "REGISTERED",
                        "nodeCredentialExpiresAt", "2030-01-01T00:00:00Z"));
            }
        });

        server.createContext("/runner/v1/leases/claim", exchange -> {
            readBody(exchange);
            claimCount.incrementAndGet();
            List<Map<String, Object>> batch = new ArrayList<>(pendingLeases);
            pendingLeases.clear();
            respond(exchange, 200, Map.of("leases", batch));
        });

        server.createContext("/runner/v1/leases/", exchange -> {
            String path = exchange.getRequestURI().getPath();
            String body = readBody(exchange);
            String leaseId = leaseIdFrom(path);

            if (path.endsWith("/heartbeat")) {
                heartbeatCount.incrementAndGet();
                heartbeats.add(Json.parseObject(body));
                if (leaseStolen.get()) {
                    respond(exchange, 409, Map.of("status", "ERROR", "code", "ELMOS_LEASE_NOT_ACTIVE"));
                    return;
                }
                respond(exchange, 200, Map.of(
                        "cancelRequested", cancelRequested.get(),
                        "pauseRequested", pauseRequested.get(),
                        "leaseExpiresAt", "2030-01-01T00:00:00Z"));
                return;
            }
            if (path.endsWith("/complete")) {
                Map<String, Object> parsed = Json.parseObject(body);
                completions.add(new Completion(leaseId,
                        Json.string(parsed, "status", ""),
                        Json.string(parsed, "resultStatus", ""),
                        Json.string(parsed, "failureCode", null)));
                respond(exchange, 200, Map.of("applied", true));
                return;
            }
            if (path.endsWith("/artifacts/upload-ticket")) {
                Map<String, Object> parsed = Json.parseObject(body);
                String contentObjectId = "obj-" + Json.string(parsed, "contentSha256", "").substring(0, 12);
                respond(exchange, 200, Map.of(
                        "uploadUrl", baseUrl() + "/upload/" + contentObjectId,
                        "storageKey", "org/obj/" + contentObjectId,
                        "contentObjectId", contentObjectId,
                        "requiredHeaders", Map.of()));
                return;
            }
            if (path.endsWith("/artifacts/publish")) {
                Map<String, Object> parsed = Json.parseObject(body);
                published.add(new PublishedArtifact(leaseId,
                        Json.string(parsed, "artifactRole", ""),
                        Json.string(parsed, "filename", ""),
                        Json.string(parsed, "contentObjectId", "")));
                respond(exchange, 200, Map.of("status", "PUBLISHED"));
                return;
            }
            respond(exchange, 404, Map.of("status", "ERROR", "code", "UNKNOWN_PATH"));
        });

        // Stands in for the object store's presigned PUT endpoint.
        server.createContext("/upload/", exchange -> {
            byte[] bytes = exchange.getRequestBody().readAllBytes();
            uploads.add(bytes);
            respond(exchange, 200, Map.of("ok", true));
        });

        server.setExecutor(null);
        server.start();
    }

    public String baseUrl() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    public void enqueueLease(String jobId, String leaseId, String image, int wallSeconds) {
        Map<String, Object> lease = new LinkedHashMap<>();
        lease.put("jobId", jobId);
        lease.put("leaseId", leaseId);
        lease.put("leaseToken", "token-" + leaseId);
        lease.put("businessLine", "GENERATION");
        lease.put("jobKind", "project-synthesis");
        lease.put("runnerImage", image);
        lease.put("budgetWallSeconds", wallSeconds);
        lease.put("budgetCpuMillis", 2000);
        lease.put("budgetMemoryMib", 2048);
        lease.put("attempt", 1);
        lease.put("checkpointCursor", Map.of());
        lease.put("requestPayload", Map.of("targets", List.of("java")));
        pendingLeases.add(lease);
    }

    public ControlPlaneClient.Lease lease(String jobId, String leaseId, String image, int wallSeconds) {
        return lease(jobId, leaseId, image, wallSeconds, Map.of());
    }

    public ControlPlaneClient.Lease lease(
            String jobId,
            String leaseId,
            String image,
            int wallSeconds,
            Map<String, Object> checkpoint
    ) {
        return new ControlPlaneClient.Lease(jobId, leaseId, "token-" + leaseId, "GENERATION",
                "project-synthesis", image, wallSeconds, 2000, 2048, 1, checkpoint,
                Map.of("targets", List.of("java")));
    }

    private static String leaseIdFrom(String path) {
        String[] parts = path.split("/");
        return parts.length > 4 ? parts[4] : "";
    }

    private static String readBody(HttpExchange exchange) throws IOException {
        return new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
    }

    private static void respond(HttpExchange exchange, int status, Map<String, Object> body) throws IOException {
        byte[] bytes = Json.write(body).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public void partition() {
        if (closed.compareAndSet(false, true)) {
            server.stop(0);
        }
    }

    @Override
    public void close() {
        partition();
    }
}
