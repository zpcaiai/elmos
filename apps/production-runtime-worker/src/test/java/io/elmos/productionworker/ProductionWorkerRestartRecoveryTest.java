package io.elmos.productionworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
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
import java.nio.file.StandardCopyOption;
import java.nio.file.attribute.PosixFilePermission;
import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductionWorkerRestartRecoveryTest {
    @TempDir
    Path temporary;

    private HttpServer server;
    private ExecutorService serverExecutor;
    private ProductionWorkerAttemptService first;
    private ProductionWorkerAttemptService recovered;
    private final CountDownLatch executionStarted = new CountDownLatch(1);
    private final CountDownLatch releaseExecution = new CountDownLatch(1);
    private final AtomicInteger executions = new AtomicInteger();
    private final AtomicInteger reconciliations = new AtomicInteger();
    private final AtomicInteger completions = new AtomicInteger();

    @AfterEach
    void stop() {
        releaseExecution.countDown();
        if (first != null) first.close();
        if (recovered != null) recovered.close();
        if (server != null) server.stop(0);
        if (serverExecutor != null) serverExecutor.shutdownNow();
    }

    @Test
    void runningJournalRestartsThroughReconciliationWithoutSecondExecution()
            throws Exception {
        startServer();
        ObjectMapper json = new ObjectMapper();
        UUID workerId = UUID.randomUUID();
        Path credentialPath = credential();
        Path routePath = routeCatalog(json);
        Path liveState = temporary.resolve("live-state");
        Path crashSnapshot = temporary.resolve("crash-snapshot");
        URI controlPlane = URI.create(
                "http://127.0.0.1:" + server.getAddress().getPort());
        ProductionWorkerRouteCatalog routes = new ProductionWorkerRouteCatalog(
                routePath, json, true);
        OwnerOnlyProviderCredentialFile credential =
                new OwnerOnlyProviderCredentialFile(credentialPath);
        first = service(
                json, routes, credential, workerId, controlPlane, liveState);

        DispatchEnvelope envelope = envelope(workerId, controlPlane);
        first.accept(envelope);
        assertTrue(executionStarted.await(5, TimeUnit.SECONDS));
        awaitStatus(first, envelope.attemptId(),
                ProductionWorkerAttemptService.LocalStatus.RUNNING, Duration.ofSeconds(5));

        Files.createDirectories(crashSnapshot);
        secureDirectory(crashSnapshot);
        try (var records = Files.list(liveState)) {
            Path record = records.filter(path -> path.getFileName().toString().endsWith(".json"))
                    .findFirst().orElseThrow();
            Files.copy(record, crashSnapshot.resolve(record.getFileName()),
                    StandardCopyOption.COPY_ATTRIBUTES);
        }

        recovered = service(
                json, routes, credential, workerId, controlPlane, crashSnapshot);
        awaitStatus(recovered, envelope.attemptId(),
                ProductionWorkerAttemptService.LocalStatus.SUCCEEDED,
                Duration.ofSeconds(8));

        assertEquals(1, executions.get(),
                "restarted UNKNOWN work must use reconciliation, never a second execute");
        assertTrue(reconciliations.get() >= 1);
        awaitCounter(completions, Duration.ofSeconds(3));
    }

    private ProductionWorkerAttemptService service(
            ObjectMapper json,
            ProductionWorkerRouteCatalog routes,
            OwnerOnlyProviderCredentialFile credential,
            UUID workerId,
            URI controlPlane,
            Path state
    ) {
        return new ProductionWorkerAttemptService(
                json, routes, credential, workerId, controlPlane,
                1, 100, state, true);
    }

    private DispatchEnvelope envelope(UUID workerId, URI controlPlane) {
        UUID attempt = UUID.randomUUID();
        return new DispatchEnvelope(
                UUID.randomUUID(), UUID.randomUUID(), attempt, workerId, 7,
                controlPlane.toString(), "dispatch:v1:" + attempt,
                Map.of(
                        "jobId", UUID.randomUUID().toString(),
                        "jobType", "PROJECT_GENERATION",
                        "workType", "synthesize"));
    }

    private Path routeCatalog(ObjectMapper json) throws IOException {
        Path path = temporary.resolve("routes.json");
        String base = "http://127.0.0.1:" + server.getAddress().getPort();
        Files.write(path, json.writeValueAsBytes(Map.of(
                "schema_version", 1,
                "routes", java.util.List.of(Map.of(
                        "job_type", "PROJECT_GENERATION",
                        "work_type", "synthesize",
                        "endpoint", base + "/v1/execute",
                        "reconciliation_endpoint", base + "/v1/reconcile",
                        "timeout_seconds", 30)))));
        return path;
    }

    private Path credential() throws IOException {
        Path path = temporary.resolve("workload-token");
        Files.writeString(path, "qualification-workload-token\n");
        try {
            Files.setPosixFilePermissions(path, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE));
        } catch (UnsupportedOperationException ignored) {
            // The production credential reader still performs regular-file and
            // no-symlink checks on a non-POSIX test filesystem.
        }
        return path;
    }

    private static void secureDirectory(Path path) throws IOException {
        try {
            Files.setPosixFilePermissions(path, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE,
                    PosixFilePermission.OWNER_EXECUTE,
                    PosixFilePermission.GROUP_READ,
                    PosixFilePermission.GROUP_WRITE,
                    PosixFilePermission.GROUP_EXECUTE));
        } catch (UnsupportedOperationException ignored) {
            // Equivalent ACL is supplied by the test filesystem.
        }
    }

    private void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        serverExecutor = Executors.newCachedThreadPool();
        server.setExecutor(serverExecutor);
        server.createContext("/", exchange -> {
            try {
                String path = exchange.getRequestURI().getPath();
                if ("/v1/execute".equals(path)) {
                    executions.incrementAndGet();
                    executionStarted.countDown();
                    try {
                        releaseExecution.await(15, TimeUnit.SECONDS);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                    respond(exchange, 200, "{\"status\":\"SUCCEEDED\"}");
                } else if ("/v1/reconcile".equals(path)) {
                    reconciliations.incrementAndGet();
                    exchange.getRequestBody().readAllBytes();
                    respond(exchange, 200, "{\"status\":\"SUCCEEDED\"}");
                } else if (path.endsWith("/heartbeat")) {
                    exchange.getRequestBody().readAllBytes();
                    respond(exchange, 200, "{\"status\":\"LEASE_EXTENDED\"}");
                } else if (path.endsWith("/completions")) {
                    completions.incrementAndGet();
                    exchange.getRequestBody().readAllBytes();
                    respond(exchange, 200, "{\"status\":\"COMMITTED\"}");
                } else {
                    respond(exchange, 404, "{\"status\":\"NOT_FOUND\"}");
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
    }

    private static void awaitStatus(
            ProductionWorkerAttemptService service,
            UUID attemptId,
            ProductionWorkerAttemptService.LocalStatus expected,
            Duration timeout
    ) throws InterruptedException {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline)) {
            var view = service.find(attemptId);
            if (view != null && view.status() == expected) return;
            Thread.sleep(25);
        }
        var view = service.find(attemptId);
        assertEquals(expected, view == null ? null : view.status());
    }

    private static void awaitCounter(AtomicInteger counter, Duration timeout)
            throws InterruptedException {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline)) {
            if (counter.get() >= 1) return;
            Thread.sleep(25);
        }
        assertTrue(counter.get() >= 1);
    }

    private static void respond(HttpExchange exchange, int status, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
}
