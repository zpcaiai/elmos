package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ToolCallRequest;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** Least-privilege SDK for the Billing-owned, distinct ToolCall boundary. */
public final class HttpProductionToolCallClient implements ProductionToolCallPort {
    private static final int MAX_REQUEST_BYTES = 1_048_576;
    private static final int MAX_RESPONSE_BYTES = 1_048_576;

    @FunctionalInterface
    public interface CredentialSource { String read(); }

    private final URI endpoint;
    private final CredentialSource credentials;
    private final ObjectMapper json;
    private final Duration timeout;
    private final HttpClient http;

    public HttpProductionToolCallClient(
            URI endpoint,
            CredentialSource credentials,
            ObjectMapper json,
            Duration connectTimeout,
            Duration timeout,
            boolean allowServiceMeshHttp
    ) {
        this.endpoint = validateEndpoint(endpoint, allowServiceMeshHttp);
        this.credentials = Objects.requireNonNull(credentials, "credentials");
        this.json = Objects.requireNonNull(json, "json");
        if (connectTimeout == null || connectTimeout.isZero() || connectTimeout.isNegative()
                || connectTimeout.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException("tool-call connectTimeout out of range");
        }
        if (timeout == null || timeout.compareTo(Duration.ofSeconds(1)) < 0
                || timeout.compareTo(Duration.ofMinutes(5)) > 0) {
            throw new IllegalArgumentException("tool-call timeout out of range");
        }
        this.timeout = timeout;
        this.http = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public ToolCallReceipt begin(ToolCallRequest request) {
        return post("/tool-calls", request, ToolCallReceipt.class);
    }

    @Override
    public void claimProviderDispatch(UUID tenantId, UUID toolCallId) {
        post("/tool-calls/" + toolCallId + "/claim-provider-dispatch",
                Map.of("tenantId", tenantId), Void.class);
    }

    @Override
    public void markProviderAccepted(
            UUID tenantId, UUID toolCallId, String providerRequestId
    ) {
        post("/tool-calls/" + toolCallId + "/accepted",
                Map.of("tenantId", tenantId, "providerRequestId", providerRequestId),
                Void.class);
    }

    @Override
    public void markProviderUnknown(
            UUID tenantId, UUID toolCallId, String providerStatus
    ) {
        markProviderUnknown(tenantId, toolCallId, null, providerStatus);
    }

    @Override
    public void markProviderUnknown(
            UUID tenantId,
            UUID toolCallId,
            String providerRequestId,
            String providerStatus
    ) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("tenantId", tenantId);
        body.put("providerRequestId", providerRequestId);
        body.put("providerStatus", providerStatus);
        post("/tool-calls/" + toolCallId + "/unknown", body, Void.class);
    }

    @Override
    public void markProviderFailed(
            UUID tenantId, UUID toolCallId, String providerStatus
    ) {
        post("/tool-calls/" + toolCallId + "/failed",
                Map.of("tenantId", tenantId, "providerStatus", providerStatus),
                Void.class);
    }

    @Override
    public void complete(UUID tenantId, UUID toolCallId, UUID responseArtifactId) {
        post("/tool-calls/" + toolCallId + "/complete",
                Map.of("tenantId", tenantId, "responseArtifactId", responseArtifactId),
                Void.class);
    }

    private <T> T post(String path, Object body, Class<T> type) {
        try {
            byte[] requestBytes = json.writeValueAsBytes(body);
            if (requestBytes.length > MAX_REQUEST_BYTES) {
                throw new ProductionRuntimeException(
                        "TOOL_CALL_REMOTE_REQUEST_TOO_LARGE",
                        "tool-call request exceeds the bounded internal protocol");
            }
            HttpRequest request = request(path)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(requestBytes))
                    .build();
            HttpResponse<InputStream> response = http.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            byte[] responseBytes;
            try (InputStream input = response.body()) {
                responseBytes = input.readNBytes(MAX_RESPONSE_BYTES + 1);
            }
            if (responseBytes.length > MAX_RESPONSE_BYTES) {
                throw new ProductionRuntimeException(
                        "TOOL_CALL_REMOTE_RESPONSE_TOO_LARGE",
                        "tool-call response exceeds the bounded internal protocol");
            }
            return decode(response.statusCode(), responseBytes, type);
        } catch (java.net.http.HttpTimeoutException ex) {
            throw unknown(ex);
        } catch (IOException ex) {
            throw unknown(ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unknown(ex);
        }
    }

    private HttpRequest.Builder request(String path) {
        String credential = credentials.read();
        if (credential == null || credential.isBlank() || credential.length() > 16_384
                || credential.indexOf('\n') >= 0 || credential.indexOf('\r') >= 0) {
            throw new ProductionRuntimeException(
                    "TOOL_CALL_CREDENTIAL_INVALID",
                    "tool-call workload credential is malformed");
        }
        String root = endpoint.toString().replaceAll("/+$", "");
        return HttpRequest.newBuilder(URI.create(root + path))
                .timeout(timeout)
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + credential);
    }

    private <T> T decode(int status, byte[] body, Class<T> type) throws IOException {
        if (status < 200 || status >= 300) {
            JsonNode error;
            try { error = json.readTree(body); }
            catch (IOException ignored) { error = null; }
            String code = error == null ? "TOOL_CALL_REMOTE_HTTP_" + status
                    : error.path("code").asText("TOOL_CALL_REMOTE_HTTP_" + status);
            throw new ProductionRuntimeException(code, "tool-call service rejected the operation");
        }
        if (type == Void.class || body.length == 0) return null;
        return json.readValue(body, type);
    }

    private static ProductionRuntimeException unknown(Exception ex) {
        return new ProductionRuntimeException(
                "TOOL_CALL_REMOTE_OUTCOME_UNKNOWN",
                "tool-call transport outcome requires reconciliation with the same idempotency key",
                ex);
    }

    private static URI validateEndpoint(URI endpoint, boolean meshHttp) {
        Objects.requireNonNull(endpoint, "endpoint");
        if (endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("tool-call endpoint is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && meshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!secure && !mesh) {
            throw new IllegalArgumentException(
                    "tool-call endpoint requires HTTPS or approved mesh HTTP");
        }
        return endpoint;
    }

    private static boolean loopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }
}
