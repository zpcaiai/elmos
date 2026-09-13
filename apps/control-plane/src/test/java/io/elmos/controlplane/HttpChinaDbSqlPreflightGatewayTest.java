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
    void fixedWorkerHopAcceptsLocalEmittedAssessmentWithoutCertification() throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        AtomicReference<byte[]> receivedBody = new AtomicReference<>();
        byte[] payload = json.writeValueAsBytes(localEmitted());
        server.createContext("/engine/v1/sql-preflight/assess", exchange -> {
            receivedBody.set(exchange.getRequestBody().readAllBytes());
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, payload.length);
            try (var output = exchange.getResponseBody()) {
                output.write(payload);
            }
        });
        server.start();
        try {
            String baseUrl = "http://127.0.0.1:" + server.getAddress().getPort();
            var gateway = new HttpChinaDbSqlPreflightGateway(
                    true, baseUrl, Duration.ofSeconds(1), Duration.ofSeconds(30), json);
            byte[] request = request().getBytes(StandardCharsets.UTF_8);

            var result = gateway.assess(request, "org-a", "actor-a");

            assertEquals("LOCAL_EMITTED", result.path("state").textValue());
            assertEquals("SELECT 1;\n", result.path("targetSql").textValue());
            assertEquals("NOT_CERTIFIED", result.path("certification").textValue());
            assertEquals("NOT_RUN", result.path("verification").path("sourceExecution").textValue());
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

    private ObjectNode localEmitted() throws Exception {
        ObjectNode root = json.createObjectNode();
        root.put("schemaVersion", "1.0");
        root.put("queryId", "query-1");
        root.put("sourceProfile", "postgresql-17.5");
        ObjectNode target = root.putObject("target");
        target.put("id", "dm8");
        target.put("label", "DM8");
        target.put("version", "8.1.3.140");
        target.put("edition", "enterprise");
        target.put("compatibilityMode", "oracle");
        target.put("driver", "dmjdbc-8.1.3.140");
        target.put("charset", "UTF-8");
        target.put("collation", "BINARY");
        target.put("timeZone", "Asia/Shanghai");
        target.put("adapterId", "chinadb.dm8.target-adapter.v1");
        target.put("implementationStatus", "LOCAL_ADAPTER");
        root.put("routeId", "postgresql--to--dm8");
        root.put("state", "LOCAL_EMITTED");
        root.put("sourceDigest", "sha256:" + sha256Hex("SELECT 1"));
        root.put("capabilitySnapshotDigest", SNAPSHOT);
        ObjectNode statement = root.putArray("statements").addObject();
        statement.put("index", 0);
        statement.put("kind", "SELECT");
        statement.putObject("sourceAst").put("type", "Select");
        statement.putArray("obligations").add("TARGET_SEMANTICS_REVIEW_REQUIRED");
        ObjectNode blocker = root.putArray("blockers").addObject();
        blocker.put("code", "TARGET_CAPABILITY_SNAPSHOT_NOT_EXTERNALLY_VERIFIED");
        blocker.put("severity", "WARNING");
        blocker.putNull("statementIndex");
        blocker.put("message", "Local emission is not live-database evidence.");
        root.put("targetSql", "SELECT 1;\n");
        ObjectNode verification = root.putObject("verification");
        verification.put("sourceParse", "PASSED");
        verification.put("targetAdapter", "PASSED");
        verification.put("targetEmit", "PASSED");
        verification.put("targetReparse", "PASSED");
        verification.put("sourceExecution", "NOT_RUN");
        verification.put("targetExecution", "NOT_RUN");
        verification.put("resultEquivalence", "NOT_RUN");
        verification.put("externalExecution", "NOT_RUN");
        root.put("certification", "NOT_CERTIFIED");
        return root;
    }

    private static String sha256Hex(String value) throws Exception {
        byte[] digest = java.security.MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        return java.util.HexFormat.of().formatHex(digest);
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
