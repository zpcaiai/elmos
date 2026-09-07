package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/**
 * Real HTTP adapter for the exact OpenAI Responses, Anthropic Messages and
 * Gemini generateContent protocol profiles.
 *
 * <p>Transport uncertainty is never retried here. A timeout, interruption,
 * malformed success response, response-artifact failure or 5xx becomes
 * {@code UNKNOWN}; the durable model-call reconciler must decide what happens
 * next.</p>
 */
public final class HttpProductionModelProviderAdapter implements ProductionModelProviderPort {
    public enum Protocol {
        OPENAI_RESPONSES_V1,
        ANTHROPIC_MESSAGES_2023_06_01,
        GEMINI_GENERATE_CONTENT_V1BETA
    }

    @FunctionalInterface
    public interface CredentialSource {
        String read();
    }

    public record Profile(
            String provider,
            String model,
            Protocol protocol,
            URI endpoint,
            Duration connectTimeout,
            Duration requestTimeout,
            int maxResponseBytes,
            boolean allowPlaintextLoopbackForTests
    ) {
        public Profile {
            ProductionRuntimeModels.requireText(provider, "provider", 80);
            ProductionRuntimeModels.requireText(model, "model", 200);
            Objects.requireNonNull(protocol, "protocol");
            Objects.requireNonNull(endpoint, "endpoint");
            if (endpoint.getHost() == null || endpoint.getUserInfo() != null
                    || endpoint.getQuery() != null || endpoint.getFragment() != null) {
                throw new IllegalArgumentException(
                        "provider endpoint must have a host and no user-info, query, or fragment");
            }
            boolean https = "https".equalsIgnoreCase(endpoint.getScheme());
            if (!https && !(allowPlaintextLoopbackForTests && isLoopback(endpoint))) {
                throw new IllegalArgumentException("provider endpoint must use HTTPS");
            }
            if (connectTimeout == null || connectTimeout.isZero() || connectTimeout.isNegative()
                    || connectTimeout.compareTo(Duration.ofSeconds(30)) > 0) {
                throw new IllegalArgumentException("connectTimeout must be within (0, 30s]");
            }
            if (requestTimeout == null || requestTimeout.compareTo(Duration.ofSeconds(1)) < 0
                    || requestTimeout.compareTo(Duration.ofMinutes(30)) > 0) {
                throw new IllegalArgumentException("requestTimeout must be within [1s, 30m]");
            }
            if (maxResponseBytes < 1_024 || maxResponseBytes > 64 * 1024 * 1024) {
                throw new IllegalArgumentException("maxResponseBytes must be between 1 KiB and 64 MiB");
            }
            validateEndpoint(protocol, endpoint, model);
        }

        private static boolean isLoopback(URI endpoint) {
            try {
                String host = endpoint.getHost();
                return host != null && InetAddress.getByName(host).isLoopbackAddress();
            } catch (Exception ex) {
                return false;
            }
        }

        private static void validateEndpoint(Protocol protocol, URI endpoint, String model) {
            String path = endpoint.getPath();
            if (protocol == Protocol.OPENAI_RESPONSES_V1 && !path.endsWith("/v1/responses")) {
                throw new IllegalArgumentException("OpenAI profile endpoint must end in /v1/responses");
            }
            if (protocol == Protocol.ANTHROPIC_MESSAGES_2023_06_01 && !path.endsWith("/v1/messages")) {
                throw new IllegalArgumentException("Anthropic profile endpoint must end in /v1/messages");
            }
            if (protocol == Protocol.GEMINI_GENERATE_CONTENT_V1BETA
                    && !path.endsWith("/v1beta/models/" + model + ":generateContent")) {
                throw new IllegalArgumentException("Gemini endpoint must bind the exact model generateContent path");
            }
        }
    }

    private final Profile profile;
    private final CredentialSource credentials;
    private final ProductionProviderPayloadPort payloads;
    private final ProductionProviderArtifactPort artifacts;
    private final ObjectMapper json;
    private final HttpClient http;

    public HttpProductionModelProviderAdapter(
            Profile profile,
            CredentialSource credentials,
            ProductionProviderPayloadPort payloads,
            ProductionProviderArtifactPort artifacts,
            ObjectMapper json
    ) {
        this.profile = Objects.requireNonNull(profile, "profile");
        this.credentials = Objects.requireNonNull(credentials, "credentials");
        this.payloads = Objects.requireNonNull(payloads, "payloads");
        this.artifacts = Objects.requireNonNull(artifacts, "artifacts");
        this.json = Objects.requireNonNull(json, "json");
        this.http = HttpClient.newBuilder()
                .connectTimeout(profile.connectTimeout())
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public ProviderResult execute(ModelCallRequest request) {
        Objects.requireNonNull(request, "request");
        if (!profile.provider().equals(request.provider()) || !profile.model().equals(request.model())) {
            return ProviderResult.rejected("PROVIDER_PROFILE_BINDING_MISMATCH");
        }
        ProductionProviderPayloadPort.MaterializedPayload payload;
        try {
            payload = payloads.materialize(request);
            verifyPayloadBinding(request, payload.bytes());
            verifyJsonModelBinding(request, payload.bytes());
        } catch (RuntimeException ex) {
            return ProviderResult.rejected(safeCode(ex, "PROVIDER_REQUEST_INVALID"));
        }
        HttpRequest.Builder builder = HttpRequest.newBuilder(profile.endpoint())
                .timeout(profile.requestTimeout())
                .header("Accept", "application/json")
                .header("Content-Type", payload.mediaType())
                .POST(HttpRequest.BodyPublishers.ofByteArray(payload.bytes()));
        applyAuthorization(builder, request.idempotencyKey());
        return send(request, builder.build(), false);
    }

    @Override
    public ProviderResult reconcile(String providerRequestId) {
        return ProviderResult.unknown("RECONCILIATION_CONTEXT_REQUIRED");
    }

    @Override
    public ProviderResult reconcile(ProviderReconciliationRequest reconciliation) {
        Objects.requireNonNull(reconciliation, "reconciliation");
        ModelCallRequest request = reconciliation.request();
        if (!profile.provider().equals(request.provider()) || !profile.model().equals(request.model())) {
            return ProviderResult.rejected("PROVIDER_PROFILE_BINDING_MISMATCH");
        }
        if (profile.protocol() != Protocol.OPENAI_RESPONSES_V1) {
            return ProviderResult.unknown("PROVIDER_PROFILE_HAS_NO_SAFE_LOOKUP_API");
        }
        String providerRequestId = reconciliation.providerRequestId();
        if (!providerRequestId.matches("[A-Za-z0-9._:-]{1,500}")) {
            return ProviderResult.rejected("PROVIDER_REQUEST_ID_INVALID");
        }
        URI lookup = URI.create(profile.endpoint().toString() + "/" + providerRequestId);
        HttpRequest.Builder builder = HttpRequest.newBuilder(lookup)
                .timeout(profile.requestTimeout())
                .header("Accept", "application/json")
                .GET();
        applyAuthorization(builder, request.idempotencyKey());
        return send(request, builder.build(), true);
    }

    private ProviderResult send(ModelCallRequest request, HttpRequest httpRequest, boolean reconciliation) {
        try {
            HttpResponse<InputStream> response = http.send(httpRequest, HttpResponse.BodyHandlers.ofInputStream());
            byte[] body;
            try (InputStream input = response.body()) {
                body = readBounded(input, profile.maxResponseBytes());
            }
            int status = response.statusCode();
            if (status >= 500 || status == 408 || status == 429) {
                String requestId = bestEffortProviderRequestId(body, response);
                return requestId == null
                        ? ProviderResult.unknown("HTTP_" + status)
                        : ProviderResult.unknown(requestId, "HTTP_" + status);
            }
            if (status == 404 && reconciliation) {
                return ProviderResult.unknown("PROVIDER_LOOKUP_NOT_FOUND");
            }
            if (status < 200 || status >= 300) {
                return ProviderResult.rejected("HTTP_" + status);
            }
            JsonNode root = json.readTree(body);
            String providerRequestId = providerRequestId(root, response);
            if (providerRequestId == null || providerRequestId.isBlank()) {
                return ProviderResult.unknown("PROVIDER_REQUEST_ID_MISSING");
            }
            String providerStatus = text(root, "status");
            if (isPending(providerStatus)) {
                return ProviderResult.accepted(providerRequestId);
            }
            if (isTerminalFailure(providerStatus)) {
                return ProviderResult.rejected("PROVIDER_STATUS_" + providerStatus.toUpperCase(Locale.ROOT));
            }
            UUID artifactId;
            try {
                artifactId = artifacts.store(request, providerRequestId, body, "application/json");
            } catch (RuntimeException ex) {
                return ProviderResult.unknown("RESPONSE_ARTIFACT_NOT_COMMITTED");
            }
            return ProviderResult.complete(providerRequestId, artifactId);
        } catch (java.net.http.HttpTimeoutException ex) {
            return ProviderResult.unknown("TIMEOUT_AFTER_POSSIBLE_SEND");
        } catch (IOException ex) {
            return ProviderResult.unknown("TRANSPORT_OUTCOME_UNKNOWN");
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return ProviderResult.unknown("INTERRUPTED_OUTCOME_UNKNOWN");
        } catch (RuntimeException ex) {
            return ProviderResult.unknown(safeCode(ex, "PROVIDER_RESPONSE_INVALID"));
        }
    }

    private void applyAuthorization(HttpRequest.Builder builder, String idempotencyKey) {
        String credential = credentials.read();
        if (credential == null || credential.isBlank() || credential.length() > 16_384
                || credential.indexOf('\n') >= 0 || credential.indexOf('\r') >= 0) {
            throw new ProductionRuntimeException("PROVIDER_CREDENTIAL_INVALID", "provider credential is missing or malformed");
        }
        switch (profile.protocol()) {
            case OPENAI_RESPONSES_V1 -> builder
                    .header("Authorization", "Bearer " + credential)
                    .header("X-Client-Request-Id", stableRequestUuid(idempotencyKey).toString());
            case ANTHROPIC_MESSAGES_2023_06_01 -> builder
                    .header("x-api-key", credential)
                    .header("anthropic-version", "2023-06-01");
            case GEMINI_GENERATE_CONTENT_V1BETA -> builder.header("x-goog-api-key", credential);
        }
    }

    private void verifyPayloadBinding(ModelCallRequest request, byte[] bytes) {
        String actual = JdbcProductionProviderPayloadStore.sha256(bytes);
        if (!actual.equalsIgnoreCase(request.requestHash())) {
            throw new ProductionRuntimeException("PROVIDER_REQUEST_DIGEST_MISMATCH", "materialized bytes do not match requestHash");
        }
    }

    private void verifyJsonModelBinding(ModelCallRequest request, byte[] bytes) {
        try {
            JsonNode root = json.readTree(bytes);
            if (root == null || !root.isObject()) {
                throw new ProductionRuntimeException("PROVIDER_REQUEST_JSON_INVALID", "provider request must be a JSON object");
            }
            if (profile.protocol() != Protocol.GEMINI_GENERATE_CONTENT_V1BETA) {
                JsonNode model = root.get("model");
                if (model == null || !request.model().equals(model.asText())) {
                    throw new ProductionRuntimeException("PROVIDER_REQUEST_MODEL_MISMATCH", "request JSON is not bound to the selected model");
                }
            }
        } catch (IOException ex) {
            throw new ProductionRuntimeException("PROVIDER_REQUEST_JSON_INVALID", "provider request is not valid JSON", ex);
        }
    }

    private String providerRequestId(JsonNode root, HttpResponse<?> response) {
        String field = profile.protocol() == Protocol.GEMINI_GENERATE_CONTENT_V1BETA ? "responseId" : "id";
        String value = text(root, field);
        if (value != null && !value.isBlank()) return value;
        for (String header : new String[]{"x-request-id", "request-id", "x-goog-request-id"}) {
            var candidate = response.headers().firstValue(header);
            if (candidate.isPresent() && !candidate.get().isBlank()) return candidate.get();
        }
        return null;
    }

    private String bestEffortProviderRequestId(byte[] body, HttpResponse<?> response) {
        try {
            JsonNode root = json.readTree(body);
            if (root != null && root.isObject()) {
                String value = providerRequestId(root, response);
                if (validProviderRequestId(value)) return value;
            }
        } catch (IOException ignored) {
            // The request-id response headers below remain usable even when an
            // error body is not JSON.
        }
        for (String header : new String[]{"x-request-id", "request-id", "x-goog-request-id"}) {
            String value = response.headers().firstValue(header).orElse(null);
            if (validProviderRequestId(value)) return value;
        }
        return null;
    }

    private static boolean validProviderRequestId(String value) {
        return value != null && value.matches("[A-Za-z0-9._:-]{1,500}");
    }

    private static String text(JsonNode root, String field) {
        JsonNode node = root.get(field);
        return node == null || node.isNull() ? null : node.asText();
    }

    private static boolean isPending(String status) {
        if (status == null) return false;
        return switch (status.toLowerCase(Locale.ROOT)) {
            case "queued", "in_progress", "processing", "pending" -> true;
            default -> false;
        };
    }

    private static boolean isTerminalFailure(String status) {
        if (status == null) return false;
        return switch (status.toLowerCase(Locale.ROOT)) {
            case "failed", "cancelled", "canceled", "incomplete", "expired" -> true;
            default -> false;
        };
    }

    private static byte[] readBounded(InputStream input, int maximum) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream(Math.min(maximum, 64 * 1024));
        byte[] buffer = new byte[16 * 1024];
        int total = 0;
        int read;
        while ((read = input.read(buffer)) != -1) {
            total += read;
            if (total > maximum) throw new IOException("provider response exceeds configured byte limit");
            output.write(buffer, 0, read);
        }
        return output.toByteArray();
    }

    private static UUID stableRequestUuid(String key) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(key.getBytes(StandardCharsets.UTF_8));
            digest[6] = (byte) ((digest[6] & 0x0f) | 0x50);
            digest[8] = (byte) ((digest[8] & 0x3f) | 0x80);
            long high = 0;
            long low = 0;
            for (int i = 0; i < 8; i++) high = (high << 8) | (digest[i] & 0xffL);
            for (int i = 8; i < 16; i++) low = (low << 8) | (digest[i] & 0xffL);
            return new UUID(high, low);
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IllegalStateException("SHA-256 unavailable", ex);
        }
    }

    private static String safeCode(RuntimeException ex, String fallback) {
        if (ex instanceof ProductionRuntimeException runtimeException) return runtimeException.code();
        return fallback;
    }
}
