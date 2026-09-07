package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.ProductionRuntimeModels.OutboxMessage;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HttpTransactionalOutboxTransportTest {
    private HttpServer server;

    @AfterEach
    void stop() {
        if (server != null) server.stop(0);
    }

    @Test
    void exactCanonicalDigestAndEventIdentityAreAcknowledged() throws Exception {
        AtomicReference<String> idempotency = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();
        start(exchange -> {
            byte[] body = exchange.getRequestBody().readAllBytes();
            String digest = JdbcProductionProviderPayloadStore.sha256(body);
            assertEquals(digest,
                    exchange.getRequestHeaders().getFirst("X-ELMOS-Event-SHA256"));
            idempotency.set(exchange.getRequestHeaders().getFirst("Idempotency-Key"));
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            respond(exchange, 200, "{\"eventId\":42,\"status\":\"ACKNOWLEDGED\","
                    + "\"payloadSha256\":\"" + digest + "\"}");
        });

        transport().publish(event());

        assertEquals("elmos-outbox-v1:42", idempotency.get());
        assertEquals("Bearer outbox-secret", authorization.get());
    }

    @Test
    void mismatchedOrOversizedAcknowledgementFailsClosed() throws Exception {
        start(exchange -> {
            exchange.getRequestBody().readAllBytes();
            respond(exchange, 200,
                    "{\"eventId\":41,\"status\":\"ACKNOWLEDGED\",\"payloadSha256\":\""
                            + "0".repeat(64) + "\"}");
        });
        ProductionRuntimeException mismatch = assertThrows(
                ProductionRuntimeException.class, () -> transport().publish(event()));
        assertEquals("OUTBOX_ACKNOWLEDGEMENT_MISMATCH", mismatch.code());

        server.stop(0);
        start(exchange -> {
            exchange.getRequestBody().readAllBytes();
            respond(exchange, 200, "x".repeat(64 * 1024 + 1));
        });
        ProductionRuntimeException oversized = assertThrows(
                ProductionRuntimeException.class, () -> transport().publish(event()));
        assertEquals("OUTBOX_ACKNOWLEDGEMENT_TOO_LARGE", oversized.code());
    }

    private HttpTransactionalOutboxTransport transport() {
        return new HttpTransactionalOutboxTransport(
                URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/v1/events"),
                () -> "outbox-secret", new ObjectMapper(),
                Duration.ofSeconds(2), Duration.ofSeconds(5), true);
    }

    private static OutboxMessage event() {
        return new OutboxMessage(
                42, UUID.randomUUID(), "WORK_ITEM", UUID.randomUUID(),
                "WORK_ITEM_COMPLETED", "{\"status\":\"SUCCEEDED\"}", UUID.randomUUID());
    }

    private void start(Handler handler) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/events", exchange -> {
            try {
                handler.handle(exchange);
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

    @FunctionalInterface
    private interface Handler {
        void handle(HttpExchange exchange) throws IOException;
    }
}
