package io.elmos.productionruntime;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeModels.FinalUsage;
import io.elmos.productionruntime.ProductionRuntimeModels.MeterSnapshot;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallReceipt;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRecoveryCandidate;
import io.elmos.productionruntime.ProductionRuntimeModels.ModelCallRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.ReservationResult;
import io.elmos.productionruntime.ProductionRuntimeModels.ReserveRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpRequest;
import io.elmos.productionruntime.ProductionRuntimeModels.TopUpResult;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

/** Least-privilege HTTP boundary from scheduler/projector pods to Billing. */
public final class HttpProductionBillingClient implements ProductionBillingPort {
    private static final int MAX_RESPONSE_BYTES = 1_048_576;
    @FunctionalInterface
    public interface CredentialSource { String read(); }

    private final URI endpoint;
    private final CredentialSource credentials;
    private final ObjectMapper json;
    private final Duration timeout;
    private final HttpClient http;

    public HttpProductionBillingClient(
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
            throw new IllegalArgumentException("billing connectTimeout out of range");
        }
        if (timeout == null || timeout.compareTo(Duration.ofSeconds(1)) < 0
                || timeout.compareTo(Duration.ofMinutes(5)) > 0) {
            throw new IllegalArgumentException("billing timeout out of range");
        }
        this.timeout = timeout;
        this.http = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public ReservationResult reserve(ReserveRequest request) {
        return post("/reservations", request, ReservationResult.class);
    }

    @Override
    public void release(UUID tenantId, UUID reservationId, String reason) {
        post("/reservations/" + reservationId + "/release",
                Map.of("tenantId", tenantId, "reason", reason == null ? "UNSPECIFIED" : reason),
                Void.class);
    }

    @Override
    public void settle(FinalUsage usage) {
        post("/settlements", usage, Void.class);
    }

    @Override
    public MeterSnapshot recordMeter(MeterSnapshot meter) {
        return post("/meters", meter, MeterSnapshot.class);
    }

    @Override
    public ModelCallReceipt beginModelCall(ModelCallRequest request) {
        return post("/model-calls", request, ModelCallReceipt.class);
    }

    @Override
    public void claimProviderDispatch(UUID tenantId, UUID modelCallId) {
        post("/model-calls/" + modelCallId + "/claim-provider-dispatch",
                Map.of("tenantId", tenantId), Void.class);
    }

    @Override
    public void markProviderAccepted(UUID tenantId, UUID modelCallId, String providerRequestId) {
        post("/model-calls/" + modelCallId + "/accepted",
                Map.of("tenantId", tenantId, "providerRequestId", providerRequestId), Void.class);
    }

    @Override
    public void markProviderUnknown(UUID tenantId, UUID modelCallId, String providerStatus) {
        markProviderUnknown(tenantId, modelCallId, null, providerStatus);
    }

    @Override
    public void markProviderUnknown(
            UUID tenantId, UUID modelCallId, String providerRequestId, String providerStatus
    ) {
        var body = new java.util.LinkedHashMap<String, Object>();
        body.put("tenantId", tenantId);
        body.put("providerRequestId", providerRequestId);
        body.put("providerStatus", providerStatus);
        post("/model-calls/" + modelCallId + "/unknown", body, Void.class);
    }

    @Override
    public void completeModelCall(
            UUID tenantId, UUID modelCallId, String providerRequestId, UUID responseArtifactId
    ) {
        post("/model-calls/" + modelCallId + "/complete",
                Map.of(
                        "tenantId", tenantId,
                        "providerRequestId", providerRequestId,
                        "responseArtifactId", responseArtifactId),
                Void.class);
    }

    @Override
    public void markProviderFailed(UUID tenantId, UUID modelCallId, String providerStatus) {
        post("/model-calls/" + modelCallId + "/failed",
                Map.of("tenantId", tenantId, "providerStatus", providerStatus), Void.class);
    }

    @Override
    public TopUpResult applyVerifiedTopUp(TopUpRequest request) {
        return post("/topups", request, TopUpResult.class);
    }

    @Override
    public int expireReservations(int limit) {
        JsonNode result = post("/recovery/expire-reservations",
                Map.of("limit", limit), JsonNode.class);
        return result.path("expired").asInt();
    }

    @Override
    public List<ModelCallRecoveryCandidate> uncertainModelCalls(int limit) {
        JsonNode result = get("/recovery/model-calls?limit=" + limit);
        return json.convertValue(result, new TypeReference<>() {});
    }

    private <T> T post(String path, Object body, Class<T> type) {
        try {
            byte[] bytes = json.writeValueAsBytes(body);
            HttpRequest request = request(path)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(bytes)).build();
            BoundedResponse response = send(request);
            return decode(response.status(), response.body(), type);
        } catch (java.net.http.HttpTimeoutException ex) {
            throw unknown(ex);
        } catch (IOException ex) {
            throw unknown(ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unknown(ex);
        }
    }

    private JsonNode get(String path) {
        try {
            HttpRequest request = request(path).GET().build();
            BoundedResponse response = send(request);
            return decode(response.status(), response.body(), JsonNode.class);
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
                    "BILLING_CREDENTIAL_INVALID", "billing workload credential is malformed");
        }
        String root = endpoint.toString().replaceAll("/+$", "");
        return HttpRequest.newBuilder(URI.create(root + path))
                .timeout(timeout)
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + credential);
    }

    private BoundedResponse send(HttpRequest request) throws IOException, InterruptedException {
        HttpResponse<InputStream> response = http.send(
                request, HttpResponse.BodyHandlers.ofInputStream());
        byte[] body;
        try (InputStream input = response.body()) {
            body = input.readNBytes(MAX_RESPONSE_BYTES + 1);
        }
        if (body.length > MAX_RESPONSE_BYTES) {
            throw new ProductionRuntimeException(
                    "BILLING_REMOTE_RESPONSE_TOO_LARGE",
                    "billing response exceeds the bounded internal protocol");
        }
        return new BoundedResponse(response.statusCode(), body);
    }

    private <T> T decode(int status, byte[] body, Class<T> type) throws IOException {
        if (status < 200 || status >= 300) {
            JsonNode error;
            try { error = json.readTree(body); }
            catch (IOException ignored) { error = null; }
            String code = error == null ? "BILLING_REMOTE_HTTP_" + status
                    : error.path("code").asText("BILLING_REMOTE_HTTP_" + status);
            throw new ProductionRuntimeException(code, "billing service rejected the operation");
        }
        if (type == Void.class || body.length == 0) return null;
        if (type == JsonNode.class) return type.cast(json.readTree(body));
        return json.readValue(body, type);
    }

    private static ProductionRuntimeException unknown(Exception ex) {
        return new ProductionRuntimeException(
                "BILLING_REMOTE_OUTCOME_UNKNOWN",
                "billing transport outcome must be reconciled using the same idempotency key", ex);
    }

    private static URI validateEndpoint(URI endpoint, boolean meshHttp) {
        Objects.requireNonNull(endpoint, "endpoint");
        if (endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("billing endpoint is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && meshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!secure && !mesh) {
            throw new IllegalArgumentException("billing endpoint requires HTTPS or approved mesh HTTP");
        }
        return endpoint;
    }

    private static boolean loopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }

    private record BoundedResponse(int status, byte[] body) {}
}
