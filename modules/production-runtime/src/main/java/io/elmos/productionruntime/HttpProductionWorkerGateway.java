package io.elmos.productionruntime;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGateway;
import io.elmos.productionruntime.ProductionRuntimeCoordinator.WorkerGatewayResult;
import io.elmos.productionruntime.ProductionRuntimeModels.DispatchEnvelope;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;

/** Exact-worker HTTP protocol with explicit UNKNOWN transport semantics. */
public final class HttpProductionWorkerGateway implements WorkerGateway {
    private static final int MAX_RESPONSE_BYTES = 65_536;
    @FunctionalInterface
    public interface WorkloadCredentialSource { String read(); }

    private final ObjectMapper json;
    private final WorkloadCredentialSource credentials;
    private final Duration timeout;
    private final boolean allowServiceMeshHttp;
    private final HttpClient http;

    public HttpProductionWorkerGateway(
            ObjectMapper json,
            WorkloadCredentialSource credentials,
            Duration connectTimeout,
            Duration timeout,
            boolean allowServiceMeshHttp
    ) {
        this.json = Objects.requireNonNull(json, "json");
        this.credentials = Objects.requireNonNull(credentials, "credentials");
        if (connectTimeout == null || connectTimeout.isNegative() || connectTimeout.isZero()
                || connectTimeout.compareTo(Duration.ofSeconds(30)) > 0) {
            throw new IllegalArgumentException("connectTimeout out of range");
        }
        if (timeout == null || timeout.compareTo(Duration.ofSeconds(1)) < 0
                || timeout.compareTo(Duration.ofMinutes(5)) > 0) {
            throw new IllegalArgumentException("timeout out of range");
        }
        this.timeout = timeout;
        this.allowServiceMeshHttp = allowServiceMeshHttp;
        this.http = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Override
    public WorkerGatewayResult dispatch(DispatchEnvelope envelope) {
        try {
            URI uri = endpoint(envelope, "/internal/v1/production-runtime/dispatch");
            byte[] body = json.writeValueAsBytes(envelope);
            HttpRequest request = base(uri, envelope)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            return result(send(request));
        } catch (java.net.http.HttpTimeoutException ex) {
            return WorkerGatewayResult.UNKNOWN;
        } catch (IOException ex) {
            return WorkerGatewayResult.UNKNOWN;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return WorkerGatewayResult.UNKNOWN;
        }
    }

    @Override
    public WorkerGatewayResult reconcile(DispatchEnvelope envelope) {
        try {
            URI uri = endpoint(envelope,
                    "/internal/v1/production-runtime/attempts/" + envelope.attemptId());
            HttpRequest request = base(uri, envelope).GET().build();
            BoundedResponse response = send(request);
            if (response.status() == 404) {
                // This is an exact, individually addressed worker with a
                // durable inbox. Its authenticated 404 is authoritative that
                // this attempt was never accepted, so replay the byte-identical
                // envelope and idempotency key through the worker inbox.
                return dispatch(envelope);
            }
            return result(response);
        } catch (java.net.http.HttpTimeoutException ex) {
            return WorkerGatewayResult.UNKNOWN;
        } catch (IOException ex) {
            return WorkerGatewayResult.UNKNOWN;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return WorkerGatewayResult.UNKNOWN;
        }
    }

    private HttpRequest.Builder base(URI uri, DispatchEnvelope envelope) {
        String credential = credentials.read();
        if (credential == null || credential.isBlank() || credential.indexOf('\n') >= 0
                || credential.indexOf('\r') >= 0) {
            throw new ProductionRuntimeException(
                    "WORKER_CREDENTIAL_INVALID", "worker workload credential is missing or malformed");
        }
        return HttpRequest.newBuilder(uri)
                .timeout(timeout)
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + credential)
                .header("X-ELMOS-Tenant-Id", envelope.tenantId().toString())
                .header("X-ELMOS-Worker-Id", envelope.workerId().toString())
                .header("X-ELMOS-Attempt-Id", envelope.attemptId().toString())
                .header("X-ELMOS-Fencing-Token", Long.toString(envelope.fencingToken()))
                .header("Idempotency-Key", envelope.dispatchIdempotencyKey());
    }

    private WorkerGatewayResult result(BoundedResponse response) {
        int status = response.status();
        if (status == 409 || status == 422) return WorkerGatewayResult.REJECTED;
        if (status < 200 || status >= 300) return WorkerGatewayResult.UNKNOWN;
        try {
            JsonNode value = json.readTree(response.body());
            String state = value.path("status").asText("");
            return switch (state) {
                case "ACKED", "RUNNING", "SUCCEEDED", "ALREADY_ACCEPTED" -> WorkerGatewayResult.ACKED;
                case "REJECTED" -> WorkerGatewayResult.REJECTED;
                default -> WorkerGatewayResult.UNKNOWN;
            };
        } catch (IOException ex) {
            return WorkerGatewayResult.UNKNOWN;
        }
    }

    private BoundedResponse send(HttpRequest request) throws IOException, InterruptedException {
        HttpResponse<InputStream> response = http.send(
                request, HttpResponse.BodyHandlers.ofInputStream());
        byte[] body;
        try (InputStream input = response.body()) {
            body = input.readNBytes(MAX_RESPONSE_BYTES + 1);
        }
        if (body.length > MAX_RESPONSE_BYTES) {
            throw new IOException("worker response exceeds bounded protocol");
        }
        return new BoundedResponse(response.statusCode(), body);
    }

    private URI endpoint(DispatchEnvelope envelope, String suffix) {
        URI base = URI.create(envelope.endpointUri());
        if (base.getUserInfo() != null || base.getQuery() != null || base.getFragment() != null
                || base.getHost() == null) {
            throw new ProductionRuntimeException("WORKER_ENDPOINT_INVALID", "worker endpoint URI is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(base.getScheme());
        boolean mesh = "http".equalsIgnoreCase(base.getScheme()) && allowServiceMeshHttp
                && (base.getHost().endsWith(".svc") || base.getHost().endsWith(".svc.cluster.local")
                || isLoopback(base.getHost()));
        if (!secure && !mesh) {
            throw new ProductionRuntimeException(
                    "WORKER_ENDPOINT_INSECURE", "worker endpoint requires HTTPS or an approved service-mesh address");
        }
        String root = base.toString().replaceAll("/+$", "");
        return URI.create(root + suffix);
    }

    private static boolean isLoopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }

    private record BoundedResponse(int status, byte[] body) {}
}
