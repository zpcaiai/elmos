package io.elmos.productionworker;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.OwnerOnlyProviderCredentialFile;
import io.elmos.productionruntime.ProductionRuntimeModels.WorkerRegistration;
import org.springframework.scheduling.annotation.Scheduled;

import java.net.InetAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Objects;
import java.util.UUID;

/** Registration heartbeat; absence makes the scheduler stop selecting this worker. */
final class ProductionWorkerRegistrationLoop {
    private final ObjectMapper json;
    private final ProductionWorkerRouteCatalog routes;
    private final OwnerOnlyProviderCredentialFile credential;
    private final WorkerRegistration registration;
    private final URI endpoint;
    private final ProductionWorkerAttemptService attempts;
    private final HttpClient http;

    ProductionWorkerRegistrationLoop(
            ObjectMapper json,
            ProductionWorkerRouteCatalog routes,
            OwnerOnlyProviderCredentialFile credential,
            UUID workerId,
            String workerName,
            String workerType,
            URI advertisedEndpoint,
            URI controlPlane,
            String region,
            String zone,
            int maxConcurrent,
            ProductionWorkerAttemptService attempts,
            boolean meshHttp
    ) {
        this.json = Objects.requireNonNull(json, "json");
        this.routes = Objects.requireNonNull(routes, "routes");
        this.credential = Objects.requireNonNull(credential, "credential");
        this.attempts = Objects.requireNonNull(attempts, "attempts");
        validate(controlPlane, meshHttp);
        validate(advertisedEndpoint, meshHttp);
        this.endpoint = controlPlane.resolve("/internal/v1/production-runtime/workers/register");
        this.registration = new WorkerRegistration(
                workerId, workerName, workerType, advertisedEndpoint.toString(),
                region, zone, routes.capabilities(maxConcurrent));
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    @Scheduled(initialDelay = 0, fixedDelay = 30000)
    void register() {
        if (!attempts.journalHealthy()) return;
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(10))
                    .header("Content-Type", "application/json")
                    .header("Authorization", "Bearer " + credential.read())
                    .header("X-ELMOS-Worker-Id", registration.workerId().toString())
                    .POST(HttpRequest.BodyPublishers.ofByteArray(
                            json.writeValueAsBytes(registration)))
                    .build();
            http.send(request, HttpResponse.BodyHandlers.discarding());
        } catch (Exception ignored) {
            // Scheduler freshness selection expires this worker after two
            // minutes; registration loss therefore fails closed automatically.
        }
    }

    private static void validate(URI endpoint, boolean meshHttp) {
        if (endpoint == null || endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new IllegalArgumentException("worker/control-plane endpoint is malformed");
        }
        boolean secure = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && meshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!secure && !mesh) throw new IllegalArgumentException("worker/control-plane endpoint must be secure");
    }

    private static boolean loopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }
}
