package io.elmos.productionworker;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.elmos.productionruntime.ProductionRuntimeException;

import java.io.IOException;
import java.net.InetAddress;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

/** Immutable allow-list from exact workload tuple to internal engine endpoint. */
final class ProductionWorkerRouteCatalog {
    record Route(
            String jobType,
            String workType,
            URI endpoint,
            URI reconciliationEndpoint,
            Duration timeout
    ) {}
    private record Key(String jobType, String workType) {}

    private final Map<Key, Route> routes;

    ProductionWorkerRouteCatalog(Path path, ObjectMapper json, boolean allowServiceMeshHttp) {
        Objects.requireNonNull(path, "path");
        Objects.requireNonNull(json, "json");
        try {
            if (Files.isSymbolicLink(path) || !Files.isRegularFile(path)) {
                throw new ProductionRuntimeException(
                        "WORKER_ROUTE_CATALOG_INVALID", "worker route catalog must be a regular non-symlink file");
            }
            JsonNode root = json.readTree(path.toFile());
            if (root.path("schema_version").asInt() != 1 || !root.path("routes").isArray()) {
                throw new ProductionRuntimeException(
                        "WORKER_ROUTE_CATALOG_INVALID", "worker route catalog schema is invalid");
            }
            Map<Key, Route> loaded = new HashMap<>();
            for (JsonNode entry : root.path("routes")) {
                String jobType = text(entry, "job_type", 80);
                String workType = text(entry, "work_type", 120);
                URI endpoint = URI.create(text(entry, "endpoint", 2_000));
                URI reconciliationEndpoint = URI.create(
                        text(entry, "reconciliation_endpoint", 2_000));
                int timeoutSeconds = entry.path("timeout_seconds").asInt();
                if (timeoutSeconds < 1 || timeoutSeconds > 3600) {
                    throw new ProductionRuntimeException(
                            "WORKER_ROUTE_TIMEOUT_INVALID", "worker route timeout is outside [1s, 1h]");
                }
                validateEndpoint(endpoint, allowServiceMeshHttp);
                validateEndpoint(reconciliationEndpoint, allowServiceMeshHttp);
                Route route = new Route(
                        jobType, workType, endpoint, reconciliationEndpoint,
                        Duration.ofSeconds(timeoutSeconds));
                if (loaded.put(new Key(jobType, workType), route) != null) {
                    throw new ProductionRuntimeException(
                            "WORKER_ROUTE_DUPLICATE", "duplicate exact worker route tuple");
                }
            }
            if (loaded.isEmpty()) {
                throw new ProductionRuntimeException(
                        "WORKER_ROUTE_CATALOG_EMPTY", "worker route catalog has no exact routes");
            }
            this.routes = Map.copyOf(loaded);
        } catch (IOException | IllegalArgumentException ex) {
            if (ex instanceof ProductionRuntimeException runtime) throw runtime;
            throw new ProductionRuntimeException(
                    "WORKER_ROUTE_CATALOG_INVALID", "worker route catalog cannot be parsed", ex);
        }
    }

    Route require(String jobType, String workType) {
        Route route = routes.get(new Key(jobType, workType));
        if (route == null) {
            throw new ProductionRuntimeException(
                    "WORKER_ROUTE_NOT_CONFIGURED",
                    "no exact engine route exists for " + jobType + "/" + workType);
        }
        return route;
    }

    Map<String, Object> capabilities(int maxConcurrent) {
        if (maxConcurrent < 1 || maxConcurrent > 1024) {
            throw new IllegalArgumentException("maxConcurrent must be between 1 and 1024");
        }
        return Map.of(
                "routeTuples", routes.keySet().stream()
                        .map(key -> key.jobType() + ":" + key.workType())
                        .sorted().toList(),
                "maxConcurrent", maxConcurrent);
    }

    private static String text(JsonNode node, String field, int max) {
        String value = node.path(field).asText("");
        if (value.isBlank() || value.length() > max) {
            throw new ProductionRuntimeException(
                    "WORKER_ROUTE_CATALOG_INVALID", "worker route " + field + " is invalid");
        }
        return value;
    }

    private static void validateEndpoint(URI endpoint, boolean allowServiceMeshHttp) {
        if (endpoint.getHost() == null || endpoint.getUserInfo() != null
                || endpoint.getQuery() != null || endpoint.getFragment() != null) {
            throw new ProductionRuntimeException(
                    "WORKER_ROUTE_ENDPOINT_INVALID", "worker route endpoint URI is malformed");
        }
        boolean https = "https".equalsIgnoreCase(endpoint.getScheme());
        boolean mesh = "http".equalsIgnoreCase(endpoint.getScheme()) && allowServiceMeshHttp
                && (endpoint.getHost().endsWith(".svc")
                || endpoint.getHost().endsWith(".svc.cluster.local")
                || loopback(endpoint.getHost()));
        if (!https && !mesh) {
            throw new ProductionRuntimeException(
                    "WORKER_ROUTE_ENDPOINT_INSECURE", "worker route requires HTTPS or approved mesh HTTP");
        }
    }

    private static boolean loopback(String host) {
        try { return InetAddress.getByName(host).isLoopbackAddress(); }
        catch (Exception ex) { return false; }
    }
}
