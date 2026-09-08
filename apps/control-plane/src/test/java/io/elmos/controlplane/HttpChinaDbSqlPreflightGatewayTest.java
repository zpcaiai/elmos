package io.elmos.controlplane;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HttpChinaDbSqlPreflightGatewayTest {
    private static final String SNAPSHOT = "sha256:" + "a".repeat(64);
    private final ObjectMapper json = new ObjectMapper();

    @Test
    void fixedWorkerHopForwardsTrustedIdentityAndMapsStaleSnapshot() throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicReference<String> organization = new AtomicReference<>();
        AtomicReference<String> actor = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<byte[]> receivedBody = new AtomicReference<>();
        server.createContext("/engine/v1/sql-preflight/assess", exchange -> {
            assertEquals("POST", exchange.getRequestMethod());
            organization.set(exchange.getRequestHeaders().getFirst("X-ELMOS-Organization-ID"));
            actor.set(exchange.getRequestHeaders().getFirst("X-ELMOS-Actor-ID"));
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            receivedBody.set(exchange.getRequestBody().readAllBytes());
            exchange.sendResponseHeaders(409, -1);
            exchange.close();
        });
        server.start();
        try {
            String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
            var gateway = new HttpChinaDbSqlPreflightGateway(
                    true, baseUrl, Duration.ofSeconds(1), Duration.ofSeconds(30), json);
            byte[] request = request().getBytes(StandardCharsets.UTF_8);

            ChinaDbSqlPreflightFailure failure = assertThrows(
                    ChinaDbSqlPreflightFailure.class,
                    () -> gateway.assess(request, "org-a", "actor-a"));

            assertEquals("CHINADB_SQL_PREFLIGHT_CAPABILITY_SNAPSHOT_STALE", failure.errorCode());
            assertEquals("BLOCKED", failure.body().get("status"));
            assertEquals("NOT_CERTIFIED", failure.body().get("certification"));
            assertEquals("org-a", organization.get());
            assertEquals("actor-a", actor.get());
            assertNull(authorization.get());
            assertArrayEquals(request, receivedBody.get());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void nonLocalPlainHttpWorkerDestinationsAreRejected() {
        assertThrows(IllegalStateException.class, () -> new HttpChinaDbSqlPreflightGateway(
                true,
                "http://example.com:8089",
                Duration.ofSeconds(1),
                Duration.ofSeconds(2),
                json));
    }

    private String request() throws Exception {
        ObjectNode request = json.createObjectNode();
        request.put("schemaVersion", "1.0");
        request.put("queryId", "query-1");
        request.put("sourceProfile", "postgresql-17.5");
        request.put("targetId", "dm8");
        request.put("targetVersion", "8.1.3.140");
        request.put("targetEdition", "enterprise");
        request.put("compatibilityMode", "oracle");
        request.put("targetDriver", "dmjdbc-8.1.3.140");
        request.put("targetCharset", "UTF-8");
        request.put("targetCollation", "BINARY");
        request.put("targetTimeZone", "Asia/Shanghai");
        request.put("capabilitySnapshotDigest", SNAPSHOT);
        request.put("sql", "SELECT 1");
        request.putArray("parameters");
        return json.writeValueAsString(request);
    }
}
