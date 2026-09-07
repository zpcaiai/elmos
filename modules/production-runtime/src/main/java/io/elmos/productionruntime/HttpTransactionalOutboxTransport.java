package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import io.elmos.productionruntime.ProductionRuntimeModels.OutboxMessage;

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

/**
 * HTTPS delivery adapter for the transactional outbox.
 *
 * <p>A generic 2xx is insufficient: the receiver must echo the exact event id
 * and canonical body digest. This prevents a proxy-generated success page or a
 * mismatched consumer acknowledgement from advancing PostgreSQL to
 * {@code published_at}.</p>
 */
public final class HttpTransactionalOutboxTransport
        implements TransactionalOutboxPublisher.Transport {
    private static final int MAX_ACKNOWLEDGEMENT_BYTES = 64 * 1024;
    @FunctionalInterface
    public interface CredentialSource { String read(); }

    private final URI endpoint;
    private final CredentialSource credentials;
    private final ObjectMapper json;
    private final HttpClient http;
    private final Duration timeout;

    public HttpTransactionalOutboxTransport(
            URI endpoint,
            CredentialSource credentials,
            ObjectMapper objectMapper,
            Duration connectTimeout,
            Duration timeout,
            boolean allowServiceMeshHttp
    ) {
        this.endpoint = validateEndpoint(endpoint, allowServiceMeshHttp);
        this.credentials = Objects.requireNonNull(credentials, "credentials");
        Objects.requireNonNull(objectMapper, "objectMapper");
        this.json = objectMapper.copy()
                .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY)
                .enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
        if (connectTimeout == null || connectTimeout.isZero() || connectTimeout.isNegative()
                || connectTimeout.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException("outbox connectTimeout out of range");
        }
        if (timeout == null || timeout.compareTo(Duration.ofSeconds(1)) < 0
                || timeout.compareTo(Duration.ofMinutes(5)) > 0) {
            throw new IllegalArgumentException("outbox timeout out of range");
        }
        this.timeout = timeout;
        this.http = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public void publish(OutboxMessage event) {
        Objects.requireNonNull(event, "event");
        try {
            JsonNode payload = json.readTree(event.payloadJson());
            if (payload == null || !payload.isObject()) {
                throw new ProductionRuntimeException(
                        "OUTBOX_PAYLOAD_INVALID", "outbox payload must be a JSON object");
            }
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("schemaVersion", 1);
            envelope.put("eventId", event.id());
            envelope.put("tenantId", event.tenantId());
            envelope.put("aggregateType", event.aggregateType());
            envelope.put("aggregateId", event.aggregateId());
            envelope.put("eventType", event.eventType());
            envelope.put("payload", payload);
            byte[] body = json.writeValueAsBytes(envelope);
            String digest = JdbcProductionProviderPayloadStore.sha256(body);
            String credential = credentials.read();
            if (credential == null || credential.isBlank() || credential.length() > 16_384
                    || credential.indexOf('\n') >= 0 || credential.indexOf('\r') >= 0) {
                throw new ProductionRuntimeException(
                        "OUTBOX_CREDENTIAL_INVALID", "outbox credential is malformed");
            }
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(timeout)
                    .header("Accept", "application/json")
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + credential)
                    .header("Idempotency-Key", "elmos-outbox-v1:" + event.id())
                    .header("X-ELMOS-Event-SHA256", digest)
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            HttpResponse<InputStream> response = http.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            byte[] acknowledgementBytes;
            try (InputStream input = response.body()) {
                acknowledgementBytes = input.readNBytes(MAX_ACKNOWLEDGEMENT_BYTES + 1);
            }
            if (acknowledgementBytes.length > MAX_ACKNOWLEDGEMENT_BYTES) {
                throw new ProductionRuntimeException(
                        "OUTBOX_ACKNOWLEDGEMENT_TOO_LARGE",
                        "outbox receiver acknowledgement exceeds the byte limit");
            }
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new ProductionRuntimeException(
                        "OUTBOX_DELIVERY_HTTP_" + response.statusCode(),
                        "outbox receiver did not acknowledge the event");
            }
            JsonNode acknowledgement = json.readTree(acknowledgementBytes);
            if (acknowledgement == null
                    || acknowledgement.path("eventId").asLong(Long.MIN_VALUE) != event.id()
                    || !"ACKNOWLEDGED".equals(acknowledgement.path("status").asText())
                    || !digest.equals(acknowledgement.path("payloadSha256").asText())) {
                throw new ProductionRuntimeException(
                        "OUTBOX_ACKNOWLEDGEMENT_MISMATCH",
                        "outbox receiver acknowledgement is not bound to the delivered bytes");
            }
        } catch (java.net.http.HttpTimeoutException ex) {
            throw unknown("OUTBOX_DELIVERY_TIMEOUT", ex);
        } catch (IOException ex) {
            throw unknown("OUTBOX_DELIVERY_UNKNOWN", ex);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw unknown("OUTBOX_DELIVERY_INTERRUPTED", ex);
        }
    }

    private static ProductionRuntimeException unknown(String code, Exception cause) {
        return new ProductionRuntimeException(
                code, "outbox delivery outcome is unknown and must be retried with the same event id", cause);
    }

    private static URI validateEndpoint(URI endpoint, boolean allowServiceMeshHttp) {
        Objects.requireNonNull(endpoint, "endpoint");
        if (endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("outbox endpoint is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && allowServiceMeshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!secure && !mesh) {
            throw new IllegalArgumentException("outbox endpoint requires HTTPS or approved mesh HTTP");
        }
        return endpoint;
    }

    private static boolean loopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }
}
