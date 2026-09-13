package io.elmos.productionworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermission;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProductionWorkerRegistrationLoopTest {
    @TempDir
    Path temporary;

    @Test
    @Timeout(value = 90, unit = TimeUnit.SECONDS)
    void closeDrainsInFlightRegistrationAndStopsFutureRefresh() throws Exception {
        HttpServer server = null;
        ExecutorService serverExecutor = null;
        ProductionWorkerAttemptService service = null;
        Thread registrationThread = null;
        Thread closeThread = null;
        CountDownLatch registrationStarted = new CountDownLatch(1);
        CountDownLatch releaseRegistration = new CountDownLatch(1);
        CountDownLatch closeFinished = new CountDownLatch(1);
        AtomicReference<Throwable> closeFailure = new AtomicReference<>();
        try {
            AtomicInteger registrations = new AtomicInteger();
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext(
                    "/internal/v1/production-runtime/workers/register",
                    exchange -> {
                        try {
                            exchange.getRequestBody().readAllBytes();
                            registrations.incrementAndGet();
                            registrationStarted.countDown();
                            try {
                                releaseRegistration.await(10, TimeUnit.SECONDS);
                            } catch (InterruptedException ex) {
                                Thread.currentThread().interrupt();
                            }
                            exchange.sendResponseHeaders(204, -1);
                        } finally {
                            exchange.close();
                        }
                    });
            serverExecutor = Executors.newSingleThreadExecutor();
            server.setExecutor(serverExecutor);
            server.start();

            ObjectMapper json = new ObjectMapper();
            UUID workerId = UUID.randomUUID();
            URI controlPlane = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            ProductionWorkerRouteCatalog routes = new ProductionWorkerRouteCatalog(
                    routeCatalog(json, controlPlane), json, true);
            OwnerOnlyProviderCredentialFile credential =
                    new OwnerOnlyProviderCredentialFile(credential());
            service = new ProductionWorkerAttemptService(
                    json, routes, credential, workerId, controlPlane,
                    1, 10, temporary.resolve("state"), true);
            ProductionWorkerRegistrationLoop loop = new ProductionWorkerRegistrationLoop(
                    json, routes, credential, workerId,
                    "registration-test-worker", "PRODUCTION_RUNTIME",
                    controlPlane.resolve("/worker"), controlPlane,
                    "test-region", "test-zone", 1, service, true);
            ProductionWorkerAttemptService runningService = service;

            registrationThread = Thread.ofPlatform()
                    .daemon(true)
                    .name("production-worker-registration-test")
                    .unstarted(loop::register);
            closeThread = Thread.ofPlatform()
                    .daemon(true)
                    .name("production-worker-registration-close-test")
                    .unstarted(() -> {
                        try {
                            runningService.close();
                        } catch (Throwable throwable) {
                            closeFailure.set(throwable);
                        } finally {
                            closeFinished.countDown();
                        }
                    });

            registrationThread.start();
            assertTrue(registrationStarted.await(5, TimeUnit.SECONDS),
                    "the live registration path did not reach the real server");
            closeThread.start();
            awaitNotAcceptingWork(runningService);
            assertFalse(closeFinished.await(100, TimeUnit.MILLISECONDS),
                    "close returned before the in-flight registration drained");

            releaseRegistration.countDown();
            registrationThread.join(5_000L);
            assertFalse(registrationThread.isAlive());
            assertTrue(closeFinished.await(5, TimeUnit.SECONDS));
            closeThread.join(5_000L);
            assertFalse(closeThread.isAlive());
            assertNull(closeFailure.get());
            assertTrue(runningService.executorsTerminated());

            loop.register();

            assertEquals(1, registrations.get(),
                    "a closed worker must not refresh its registration");
        } finally {
            releaseRegistration.countDown();
            if (server != null) {
                server.stop(0);
                server = null;
            }
            if (registrationThread != null && registrationThread.isAlive()) {
                registrationThread.interrupt();
                registrationThread.join(12_000L);
            }
            if (closeThread != null && closeThread.isAlive()) {
                closeThread.interrupt();
                closeThread.join(32_000L);
            }
            try {
                if (service != null && !service.executorsTerminated()) {
                    service.close();
                }
            } finally {
                if (serverExecutor != null) {
                    serverExecutor.shutdownNow();
                    assertTrue(serverExecutor.awaitTermination(5, TimeUnit.SECONDS),
                            "registration server executor did not terminate");
                }
            }
        }
    }

    private static void awaitNotAcceptingWork(
            ProductionWorkerAttemptService service
    ) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2L);
        while (service.acceptingWork() && System.nanoTime() < deadline) {
            Thread.sleep(5L);
        }
        assertFalse(service.acceptingWork(), "worker close did not start");
    }

    private Path routeCatalog(ObjectMapper json, URI base) throws IOException {
        Path path = temporary.resolve("routes.json");
        Files.write(path, json.writeValueAsBytes(Map.of(
                "schema_version", 1,
                "routes", List.of(Map.of(
                        "job_type", "PROJECT_GENERATION",
                        "work_type", "synthesize",
                        "endpoint", base.resolve("/v1/execute").toString(),
                        "reconciliation_endpoint", base.resolve("/v1/reconcile").toString(),
                        "timeout_seconds", 5)))));
        return path;
    }

    private Path credential() throws IOException {
        Path path = temporary.resolve("workload-token");
        Files.writeString(path, "registration-test-token\n");
        try {
            Files.setPosixFilePermissions(path, Set.of(
                    PosixFilePermission.OWNER_READ,
                    PosixFilePermission.OWNER_WRITE));
        } catch (UnsupportedOperationException ignored) {
            // The production reader applies equivalent non-POSIX checks.
        }
        return path;
    }
}
