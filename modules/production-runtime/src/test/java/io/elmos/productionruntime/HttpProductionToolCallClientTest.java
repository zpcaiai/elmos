package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallStatus;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class HttpProductionToolCallClientTest {
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) server.stop(0);
    }

    @Test
    void exactToolCallProtocolExposesEveryDurableTransition() throws Exception {
        UUID toolCallId = UUID.randomUUID();
        List<String> paths = Collections.synchronizedList(new ArrayList<>());
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/production-runtime/billing", exchange -> {
            paths.add(exchange.getRequestURI().getPath());
            exchange.getRequestBody().readAllBytes();
            byte[] response = exchange.getRequestURI().getPath().endsWith("/tool-calls")
                    ? ("{\"toolCallId\":\"" + toolCallId
                    + "\",\"status\":\"CREATED\",\"providerRequestId\":null,"
                    + "\"responseArtifactId\":null}").getBytes(StandardCharsets.UTF_8)
                    : new byte[0];
            if (response.length == 0) {
                exchange.sendResponseHeaders(204, -1);
            } else {
                exchange.sendResponseHeaders(200, response.length);
                exchange.getResponseBody().write(response);
            }
            exchange.close();
        });
        server.start();

        HttpProductionToolCallClient client = client();
        ToolCallRequest request = request();
        var receipt = client.begin(request);
        assertEquals(toolCallId, receipt.toolCallId());
        assertEquals(ToolCallStatus.CREATED, receipt.status());
        client.claimProviderDispatch(request.tenantId(), toolCallId);
        client.markProviderAccepted(request.tenantId(), toolCallId, "provider-tool-1");
        client.markProviderUnknown(
                request.tenantId(), toolCallId, "provider-tool-1", "TIMEOUT");
        client.complete(request.tenantId(), toolCallId, UUID.randomUUID());
        client.markProviderFailed(request.tenantId(), toolCallId, "TERMINAL_FAILURE");

        assertEquals(List.of(
                "/internal/v1/production-runtime/billing/tool-calls",
                "/internal/v1/production-runtime/billing/tool-calls/" + toolCallId
                        + "/claim-provider-dispatch",
                "/internal/v1/production-runtime/billing/tool-calls/" + toolCallId
                        + "/accepted",
                "/internal/v1/production-runtime/billing/tool-calls/" + toolCallId
                        + "/unknown",
                "/internal/v1/production-runtime/billing/tool-calls/" + toolCallId
                        + "/complete",
                "/internal/v1/production-runtime/billing/tool-calls/" + toolCallId
                        + "/failed"
        ), paths);
    }

    @Test
    void oversizedRemoteResponseFailsClosed() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/production-runtime/billing", exchange -> {
            exchange.getRequestBody().readAllBytes();
            byte[] response = new byte[1_048_577];
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();

        ProductionRuntimeException failure = assertThrows(
                ProductionRuntimeException.class, () -> client().begin(request()));
        assertEquals("TOOL_CALL_REMOTE_RESPONSE_TOO_LARGE", failure.code());
    }

    private HttpProductionToolCallClient client() {
        return new HttpProductionToolCallClient(
                URI.create("http://127.0.0.1:" + server.getAddress().getPort()
                        + "/internal/v1/production-runtime/billing"),
                () -> "test-workload-token",
                new ObjectMapper(),
                Duration.ofSeconds(2), Duration.ofSeconds(5), true);
    }

    private static ToolCallRequest request() {
        return new ToolCallRequest(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), "compiler", "tool-idempotency", "request-hash");
    }
}
