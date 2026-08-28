package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import io.elmos.productionruntime.HttpProductionModelProviderAdapter.Profile;
import io.elmos.productionruntime.HttpProductionModelProviderAdapter.Protocol;
import io.elmos.productionruntime.ProductionModelProviderPort.ProviderReconciliationRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HttpProductionModelProviderAdapterTest {
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) server.stop(0);
    }

    @Test
    void openAiExecutesExactDurableBytesWithStableClientRequestId() throws Exception {
        AtomicReference<byte[]> received = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();
        AtomicReference<String> clientRequestId = new AtomicReference<>();
        start("/v1/responses", exchange -> {
            received.set(exchange.getRequestBody().readAllBytes());
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            clientRequestId.set(exchange.getRequestHeaders().getFirst("X-Client-Request-Id"));
            respond(exchange, 200, "{\"id\":\"resp_123\",\"status\":\"completed\",\"output\":[]}");
        });
        byte[] body = "{\"model\":\"gpt-test\",\"input\":\"hello\"}".getBytes(StandardCharsets.UTF_8);
        ModelCallRequest request = request("openai", "gpt-test", body);
        CapturingArtifacts artifacts = new CapturingArtifacts();
        var adapter = adapter(Protocol.OPENAI_RESPONSES_V1, "openai", "gpt-test",
                "/v1/responses", body, artifacts);

        var result = adapter.execute(request);

        assertEquals(ProductionModelProviderPort.Status.COMPLETE, result.status());
        assertEquals("resp_123", result.providerRequestId());
        assertNotNull(result.responseArtifactId());
        assertEquals("Bearer test-secret", authorization.get());
        assertEquals(UUID.fromString(clientRequestId.get()).toString(), clientRequestId.get());
        assertTrue(java.security.MessageDigest.isEqual(body, received.get()));
        assertEquals("resp_123", artifacts.providerRequestId.get());
    }

    @Test
    void anthropicAndGeminiUseExactVersionedAuthenticationProfiles() throws Exception {
        Map<String, String> headers = new ConcurrentHashMap<>();
        start("/v1/messages", exchange -> {
            headers.put("key", exchange.getRequestHeaders().getFirst("x-api-key"));
            headers.put("version", exchange.getRequestHeaders().getFirst("anthropic-version"));
            respond(exchange, 200, "{\"id\":\"msg_123\",\"type\":\"message\",\"content\":[]}");
        });
        byte[] anthropicBody = "{\"model\":\"claude-test\",\"max_tokens\":8,\"messages\":[]}".getBytes(StandardCharsets.UTF_8);
        var anthropic = adapter(Protocol.ANTHROPIC_MESSAGES_2023_06_01,
                "anthropic", "claude-test", "/v1/messages", anthropicBody, new CapturingArtifacts());
        assertEquals(ProductionModelProviderPort.Status.COMPLETE,
                anthropic.execute(request("anthropic", "claude-test", anthropicBody)).status());
        assertEquals("test-secret", headers.get("key"));
        assertEquals("2023-06-01", headers.get("version"));

        server.stop(0);
        start("/v1beta/models/gemini-test:generateContent", exchange -> {
            headers.put("google", exchange.getRequestHeaders().getFirst("x-goog-api-key"));
            respond(exchange, 200, "{\"responseId\":\"gemini_123\",\"candidates\":[]}");
        });
        byte[] geminiBody = "{\"contents\":[{\"parts\":[{\"text\":\"hello\"}]}]}".getBytes(StandardCharsets.UTF_8);
        var gemini = adapter(Protocol.GEMINI_GENERATE_CONTENT_V1BETA,
                "gemini", "gemini-test", "/v1beta/models/gemini-test:generateContent",
                geminiBody, new CapturingArtifacts());
        assertEquals(ProductionModelProviderPort.Status.COMPLETE,
                gemini.execute(request("gemini", "gemini-test", geminiBody)).status());
        assertEquals("test-secret", headers.get("google"));
    }

    @Test
    void transportAndMalformedSuccessRemainUnknownAndAreNeverRetried() throws Exception {
        AtomicInteger calls = new AtomicInteger();
        start("/v1/responses", exchange -> {
            calls.incrementAndGet();
            respond(exchange, 503, "{\"error\":{\"type\":\"overloaded\"}}");
        });
        byte[] body = "{\"model\":\"gpt-test\",\"input\":\"hello\"}".getBytes(StandardCharsets.UTF_8);
        var adapter = adapter(Protocol.OPENAI_RESPONSES_V1, "openai", "gpt-test",
                "/v1/responses", body, new CapturingArtifacts());

        var result = adapter.execute(request("openai", "gpt-test", body));

        assertEquals(ProductionModelProviderPort.Status.UNKNOWN, result.status());
        assertEquals("HTTP_503", result.providerStatus());
        assertEquals(1, calls.get(), "adapter must not retry an uncertain provider outcome");

        server.stop(0);
        start("/v1/responses", exchange -> respond(exchange, 200, "{\"status\":\"completed\"}"));
        adapter = adapter(Protocol.OPENAI_RESPONSES_V1, "openai", "gpt-test",
                "/v1/responses", body, new CapturingArtifacts());
        assertEquals("PROVIDER_REQUEST_ID_MISSING",
                adapter.execute(request("openai", "gpt-test", body)).providerStatus());
    }

    @Test
    void openAiReconciliationIsContextBoundAndPersistsRecoveredResponse() throws Exception {
        AtomicReference<String> method = new AtomicReference<>();
        start("/v1/responses/resp_recover", exchange -> {
            method.set(exchange.getRequestMethod());
            respond(exchange, 200, "{\"id\":\"resp_recover\",\"status\":\"completed\",\"output\":[]}");
        });
        byte[] body = "{\"model\":\"gpt-test\",\"input\":\"hello\"}".getBytes(StandardCharsets.UTF_8);
        ModelCallRequest request = request("openai", "gpt-test", body);
        CapturingArtifacts artifacts = new CapturingArtifacts();
        var adapter = adapter(Protocol.OPENAI_RESPONSES_V1, "openai", "gpt-test",
                "/v1/responses", body, artifacts);

        var result = adapter.reconcile(new ProviderReconciliationRequest(
                request, UUID.randomUUID(), "resp_recover"));

        assertEquals("GET", method.get());
        assertEquals(ProductionModelProviderPort.Status.COMPLETE, result.status());
        assertEquals("resp_recover", artifacts.providerRequestId.get());
        assertEquals(ProductionModelProviderPort.Status.UNKNOWN,
                adapter.reconcile("resp_recover").status());
    }

    @Test
    void profilesRejectWrongModelDigestAndUnsafeEndpoints() throws Exception {
        start("/v1/responses", exchange -> respond(exchange, 200,
                "{\"id\":\"resp_never\",\"status\":\"completed\"}"));
        byte[] body = "{\"model\":\"different\",\"input\":\"hello\"}".getBytes(StandardCharsets.UTF_8);
        var adapter = adapter(Protocol.OPENAI_RESPONSES_V1, "openai", "gpt-test",
                "/v1/responses", body, new CapturingArtifacts());
        assertEquals("PROVIDER_REQUEST_MODEL_MISMATCH",
                adapter.execute(request("openai", "gpt-test", body)).providerStatus());

        assertThrows(IllegalArgumentException.class, () -> new Profile(
                "openai", "gpt-test", Protocol.OPENAI_RESPONSES_V1,
                URI.create("http://provider.example/v1/responses"), Duration.ofSeconds(2),
                Duration.ofSeconds(5), 1024, false));
        assertThrows(IllegalArgumentException.class, () -> new Profile(
                "openai", "gpt-test", Protocol.OPENAI_RESPONSES_V1,
                URI.create("https://api.openai.com/v1/chat/completions"), Duration.ofSeconds(2),
                Duration.ofSeconds(5), 1024, false));
    }

    private HttpProductionModelProviderAdapter adapter(
            Protocol protocol,
            String provider,
            String model,
            String path,
            byte[] body,
            CapturingArtifacts artifacts
    ) {
        URI endpoint = URI.create("http://127.0.0.1:" + server.getAddress().getPort() + path);
        Profile profile = new Profile(provider, model, protocol, endpoint,
                Duration.ofSeconds(2), Duration.ofSeconds(5), 1024 * 1024, true);
        return new HttpProductionModelProviderAdapter(profile, () -> "test-secret",
                request -> new ProductionProviderPayloadPort.MaterializedPayload(body, "application/json"),
                artifacts, new ObjectMapper());
    }

    private ModelCallRequest request(String provider, String model, byte[] body) {
        return new ModelCallRequest(
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), provider, model,
                "stable-model-call-key", JdbcProductionProviderPayloadStore.sha256(body));
    }

    private void start(String path, ExchangeHandler handler) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext(path, exchange -> {
            try {
                handler.handle(exchange);
            } finally {
                exchange.close();
            }
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
    private interface ExchangeHandler {
        void handle(HttpExchange exchange) throws IOException;
    }

    private static final class CapturingArtifacts implements ProductionProviderArtifactPort {
        private final UUID artifactId = UUID.randomUUID();
        private final AtomicReference<String> providerRequestId = new AtomicReference<>();

        @Override
        public UUID store(ModelCallRequest request, String requestId, byte[] responseBytes, String mediaType) {
            assertEquals("application/json", mediaType);
            assertTrue(responseBytes.length > 0);
            providerRequestId.set(requestId);
            return artifactId;
        }
    }
}
