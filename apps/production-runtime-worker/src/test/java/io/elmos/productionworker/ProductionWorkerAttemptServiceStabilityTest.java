package io.elmos.productionworker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import io.elmos.productionruntime.ProductionRuntimeException;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Duration;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductionWorkerAttemptServiceStabilityTest {
    @TempDir
    Path temporary;

    private HttpServer server;
    private ExecutorService serverExecutor;
    private ProductionWorkerAttemptService service;
    private final CountDownLatch reconciliationStarted = new CountDownLatch(1);
    private final CountDownLatch releaseReconciliation = new CountDownLatch(1);
    private final CountDownLatch heartbeatDuringReconciliation = new CountDownLatch(1);
    private final AtomicBoolean reconciliationRunning = new AtomicBoolean();
    private final AtomicInteger heartbeats = new AtomicInteger();
    private final CountDownLatch completionReceived = new CountDownLatch(1);
    private final AtomicReference<String> completionBody = new AtomicReference<>();

    @AfterEach
    void stop() {
        releaseReconciliation.countDown();
        if (service != null) service.close();
        if (server != null) server.stop(0);
        if (serverExecutor != null) serverExecutor.shutdownNow();
    }

    @Test
    void malformedOrUnknownRouteIsRejectedBeforeAckAndNeverBecomesRunning()
            throws Exception {
        ObjectMapper json = new ObjectMapper();
        UUID workerId = UUID.randomUUID();
        URI base = URI.create("http://127.0.0.1:65534");
        service = service(json, workerId, base, routeCatalog(json, base),
                Duration.ofSeconds(10), Duration.ofSeconds(10));

        DispatchEnvelope malformed = envelope(workerId, base, Map.of(
                "jobId", UUID.randomUUID().toString(),
                "jobType", "PROJECT_GENERATION"));
        ProductionRuntimeException malformedFailure = assertThrows(
                ProductionRuntimeException.class, () -> service.accept(malformed));
        assertEquals("WORKER_DISPATCH_PAYLOAD_INVALID", malformedFailure.code());
        assertNull(service.find(malformed.attemptId()));

        DispatchEnvelope unknown = envelope(workerId, base, Map.of(
                "jobId", UUID.randomUUID().toString(),
                "jobType", "PROJECT_GENERATION",
                "workType", "unknown-route"));
        ProductionRuntimeException unknownFailure = assertThrows(
                ProductionRuntimeException.class, () -> service.accept(unknown));
        assertEquals("WORKER_ROUTE_NOT_CONFIGURED", unknownFailure.code());
        assertNull(service.find(unknown.attemptId()));
    }

    @Test
    void slowProviderReconciliationDoesNotBlockLeaseHeartbeat() throws Exception {
        startSlowReconciliationServer();
        ObjectMapper json = new ObjectMapper();
        UUID workerId = UUID.randomUUID();
        URI base = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
        service = service(json, workerId, base, routeCatalog(json, base),
                Duration.ofMillis(25), Duration.ofMillis(25));

        DispatchEnvelope envelope = envelope(workerId, base, Map.of(
                "jobId", UUID.randomUUID().toString(),
                "jobType", "PROJECT_GENERATION",
                "workType", "synthesize"));
        service.accept(envelope);

        assertTrue(reconciliationStarted.await(3, TimeUnit.SECONDS),
                "provider reconciliation did not start");
        assertTrue(heartbeatDuringReconciliation.await(2, TimeUnit.SECONDS),
                "heartbeat was blocked behind slow provider reconciliation");
        assertTrue(reconciliationRunning.get());
        assertTrue(heartbeats.get() >= 1);
    }

    @Test
    void closeShutsDownEveryOwnedExecutorAndIsIdempotent() throws Exception {
        ObjectMapper json = new ObjectMapper();
        UUID workerId = UUID.randomUUID();
        URI base = URI.create("http://127.0.0.1:65534");
        service = service(json, workerId, base, routeCatalog(json, base),
                Duration.ofSeconds(10), Duration.ofSeconds(10));

        assertFalse(service.executorsShutdown());
        service.close();
        assertTrue(service.executorsShutdown());
        service.close();
        assertTrue(service.executorsShutdown());
    }

    @Test
    void bareEngineSuccessIsReportedAsFailureWithoutOutputVerification()
            throws Exception {
        startMissingOutputVerificationServer();
        ObjectMapper json = new ObjectMapper();
        UUID workerId = UUID.randomUUID();
        URI base = URI.create("http://127.0.0.1:" + server.getAddress().getPort());
        service = service(json, workerId, base, routeCatalog(json, base),
                Duration.ofSeconds(10), Duration.ofSeconds(10));

        service.accept(envelope(workerId, base, Map.of(
                "jobId", UUID.randomUUID().toString(),
                "jobType", "PROJECT_GENERATION",
                "workType", "synthesize")));

        assertTrue(completionReceived.await(3, TimeUnit.SECONDS));
        JsonNode completion = json.readTree(completionBody.get()).path("completion");
        assertEquals("FAILED", completion.path("status").asText());
        assertEquals("ENGINE_OUTPUT_VERIFICATION_REQUIRED",
                completion.path("errorCode").asText());
        assertTrue(json.readTree(completionBody.get())
                .path("outputVerification").isNull());
    }

    private ProductionWorkerAttemptService service(
            ObjectMapper json,
            UUID workerId,
            URI controlPlane,
            Path routesPath,
            Duration heartbeatInterval,
            Duration reconciliationInterval
    ) throws IOException {
        return new ProductionWorkerAttemptService(
                json,
                new ProductionWorkerRouteCatalog(routesPath, json, true),
                new OwnerOnlyProviderCredentialFile(credential()),
                workerId,
                controlPlane,
                2,
                100,
                temporary.resolve("state-" + UUID.randomUUID()),
                true,
                heartbeatInterval,
                reconciliationInterval);
    }

    private DispatchEnvelope envelope(
            UUID workerId,
            URI endpoint,
            Map<String, Object> payload
    ) {
        UUID attemptId = UUID.randomUUID();
        return new DispatchEnvelope(
                UUID.randomUUID(), UUID.randomUUID(), attemptId, workerId, 7,
                endpoint.toString(), "dispatch:v1:" + attemptId, payload);
    }

    private Path routeCatalog(ObjectMapper json, URI base) throws IOException {
        Path path = temporary.resolve("routes-" + UUID.randomUUID() + ".json");
        Files.write(path, json.writeValueAsBytes(Map.of(
                "schema_version", 1,
                "routes", java.util.List.of(Map.of(
                        "job_type", "PROJECT_GENERATION",
                        "work_type", "synthesize",
                        "endpoint", base.resolve("/v1/execute").toString(),
                        "reconciliation_endpoint", base.resolve("/v1/reconcile").toString(),
                        "timeout_seconds", 5)))));
        return path;
    }

    private Path credential() throws IOException {
        Path path = temporary.resolve("workload-token-" + UUID.randomUUID());
        Files.writeString(path, "worker-stability-test-token\n");
        try {
            Files.setPosixFilePermissions(path, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE));
        } catch (UnsupportedOperationException ignored) {
            // The production reader applies the equivalent platform ACL check.
        }
        return path;
    }

    private void startSlowReconciliationServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        serverExecutor = Executors.newCachedThreadPool();
        server.setExecutor(serverExecutor);
        server.createContext("/", exchange -> {
            try {
                exchange.getRequestBody().readAllBytes();
                String path = exchange.getRequestURI().getPath();
                if ("/v1/execute".equals(path)) {
                    respond(exchange, 500, "{\"status\":\"UNKNOWN\"}");
                } else if ("/v1/reconcile".equals(path)) {
                    reconciliationRunning.set(true);
                    reconciliationStarted.countDown();
                    try {
                        releaseReconciliation.await(5, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        reconciliationRunning.set(false);
                    }
                    respond(exchange, 202, "{\"status\":\"PENDING\"}");
                } else if (path.endsWith("/heartbeat")) {
                    heartbeats.incrementAndGet();
                    if (reconciliationRunning.get()) {
                        heartbeatDuringReconciliation.countDown();
                    }
                    respond(exchange, 200, "{\"status\":\"LEASE_EXTENDED\"}");
                } else {
                    respond(exchange, 404, "{\"status\":\"NOT_FOUND\"}");
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
    }

    private void startMissingOutputVerificationServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        serverExecutor = Executors.newCachedThreadPool();
        server.setExecutor(serverExecutor);
        server.createContext("/", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                if ("/v1/execute".equals(path)) {
                    exchange.getRequestBody().readAllBytes();
                    respond(exchange, 200, "{\"status\":\"SUCCEEDED\"}");
                } else if (path.endsWith("/completions")) {
                    completionBody.set(new String(
                            exchange.getRequestBody().readAllBytes(),
                            StandardCharsets.UTF_8));
                    completionReceived.countDown();
                    respond(exchange, 200, "{\"status\":\"COMMITTED\"}");
                } else if (path.endsWith("/heartbeat")) {
                    exchange.getRequestBody().readAllBytes();
                    respond(exchange, 200, "{\"status\":\"LEASE_EXTENDED\"}");
                } else {
                    exchange.getRequestBody().readAllBytes();
                    respond(exchange, 404, "{\"status\":\"NOT_FOUND\"}");
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
    }

    private static void respond(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
}
