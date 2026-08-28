package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGatewayResult;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;

class HttpProductionWorkerGatewayTest {
    private HttpServer server;

    @AfterEach
    void stop() {
        if (server != null) server.stop(0);
    }

    @Test
    void dispatchBindsExactWorkerAttemptFenceAndIdempotency() throws Exception {
        AtomicReference<String> worker = new AtomicReference<>();
        AtomicReference<String> attempt = new AtomicReference<>();
        AtomicReference<String> fence = new AtomicReference<>();
        AtomicReference<String> key = new AtomicReference<>();
        start("/internal/v1/production-runtime/dispatch", exchange -> {
            worker.set(exchange.getRequestHeaders().getFirst("X-ELMOS-Worker-Id"));
            attempt.set(exchange.getRequestHeaders().getFirst("X-ELMOS-Attempt-Id"));
            fence.set(exchange.getRequestHeaders().getFirst("X-ELMOS-Fencing-Token"));
            key.set(exchange.getRequestHeaders().getFirst("Idempotency-Key"));
            exchange.getRequestBody().readAllBytes();
            respond(exchange, 200, "{\"status\":\"ACKED\"}");
        });
        DispatchEnvelope envelope = envelope();
        var gateway = gateway();

        assertEquals(WorkerGatewayResult.ACKED, gateway.dispatch(envelope));
        assertEquals(envelope.workerId().toString(), worker.get());
        assertEquals(envelope.attemptId().toString(), attempt.get());
        assertEquals(Long.toString(envelope.fencingToken()), fence.get());
        assertEquals(envelope.dispatchIdempotencyKey(), key.get());
    }

    @Test
    void authenticatedMissingInboxReplaysExactlyButServerFailureStaysUnknown() throws Exception {
        AtomicInteger replayed = new AtomicInteger();
        start("/", exchange -> {
            if ("GET".equals(exchange.getRequestMethod())) {
                respond(exchange, 404, "{\"status\":\"NOT_FOUND\"}");
            } else {
                replayed.incrementAndGet();
                exchange.getRequestBody().readAllBytes();
                respond(exchange, 202, "{\"status\":\"ACKED\"}");
            }
        });
        DispatchEnvelope envelope = envelope();
        assertEquals(WorkerGatewayResult.ACKED, gateway().reconcile(envelope));
        assertEquals(1, replayed.get());
        server.stop(0);
        start("/", exchange -> respond(exchange, 503, "{\"status\":\"UNKNOWN\"}"));
        assertEquals(WorkerGatewayResult.UNKNOWN, gateway().reconcile(envelope()));
        server.stop(0);
        start("/",
                exchange -> respond(exchange, 200, "{\"status\":\"RUNNING\"}"));
        envelope = envelope();
        assertEquals(WorkerGatewayResult.ACKED, gateway().reconcile(envelope));
    }

    @Test
    void explicitWorkerConflictIsRejected() throws Exception {
        start("/internal/v1/production-runtime/dispatch",
                exchange -> respond(exchange, 409, "{\"status\":\"REJECTED\"}"));
        assertEquals(WorkerGatewayResult.REJECTED, gateway().dispatch(envelope()));
    }

    private HttpProductionWorkerGateway gateway() {
        return new HttpProductionWorkerGateway(
                new ObjectMapper(), () -> "workload-secret", Duration.ofSeconds(2),
                Duration.ofSeconds(5), true);
    }

    private DispatchEnvelope envelope() {
        UUID worker = UUID.randomUUID();
        return new DispatchEnvelope(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), worker, 7,
                "http://127.0.0.1:" + server.getAddress().getPort(),
                "dispatch-key", Map.of("workType", "inventory"));
    }

    private void start(String path, Handler handler) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(path, exchange -> {
            try { handler.handle(exchange); }
            finally { exchange.close(); }
        });
        server.start();
    }

    private static void respond(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    @FunctionalInterface
    interface Handler { void handle(HttpExchange exchange) throws IOException; }
}
