package io.elmos.cas;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/**
 * OTLP/HTTP JSON exporter for {@link CasTelemetry.Recording}.
 *
 * <p>Speaks the protocol an OpenTelemetry collector already accepts on {@code /v1/traces} and
 * {@code /v1/metrics}, so this module needs no SDK and no collector-side special casing.
 *
 * <p>Two behaviours are deliberate and worth not "simplifying" later:
 *
 * <ul>
 *   <li><b>Export never throws into the caller's path.</b> A telemetry outage must not fail a
 *       build. Failures are counted and reported by {@link Result}; the caller decides whether a
 *       run of failures is itself alertable.</li>
 *   <li><b>Batches are bounded and nothing is cleared until everything succeeded.</b> Dropping
 *       the overflow silently is how a collector hiccup becomes a permanently wrong dashboard.</li>
 * </ul>
 */
public final class OtlpExporter {

    private static final long[] BUCKET_BOUNDS = {1, 10, 100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000};
    static final String SCOPE_NAME = "io.elmos.cas";
    static final String SCOPE_VERSION = "1.0.0";

    public record Config(URI endpoint, String serviceName, String deploymentEnvironment,
                         int maximumBatchSize, int maximumAttempts, Duration timeout) {
        public Config {
            Objects.requireNonNull(endpoint, "endpoint");
            serviceName = CasText.required(serviceName, "serviceName");
            deploymentEnvironment = CasText.required(deploymentEnvironment, "deploymentEnvironment");
            if (maximumBatchSize < 1) {
                throw new IllegalArgumentException("maximumBatchSize must be at least 1");
            }
            if (maximumAttempts < 1) {
                throw new IllegalArgumentException("maximumAttempts must be at least 1");
            }
            Objects.requireNonNull(timeout, "timeout");
        }

        public static Config of(URI endpoint) {
            return new Config(endpoint, "elmos-cas", "production", 512, 3, Duration.ofSeconds(10));
        }
    }

    public record Result(int spansExported, int metricsExported, int requests, int failures,
                         List<String> failureReasons) {
        public Result {
            failureReasons = List.copyOf(failureReasons);
        }

        public boolean healthy() {
            return failures == 0;
        }
    }

    private final Config config;
    private final HttpClient http;

    public OtlpExporter(Config config, HttpClient http) {
        this.config = config;
        this.http = http;
    }

    public static OtlpExporter create(Config config) {
        return new OtlpExporter(config, HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5)).build());
    }

    /** Drains the recording and ships it. The recording is cleared only when everything landed. */
    public Result export(CasTelemetry.Recording recording) {
        List<CasTelemetry.FinishedSpan> spans = recording.spans();
        List<CasTelemetry.MetricPoint> metrics = recording.metrics();
        int requests = 0;
        int failures = 0;
        int spansExported = 0;
        int metricsExported = 0;
        List<String> reasons = new ArrayList<>();

        for (int offset = 0; offset < spans.size(); offset += config.maximumBatchSize()) {
            List<CasTelemetry.FinishedSpan> batch =
                    spans.subList(offset, Math.min(spans.size(), offset + config.maximumBatchSize()));
            requests++;
            String failure = post("/v1/traces", tracePayload(batch));
            if (failure == null) {
                spansExported += batch.size();
            } else {
                failures++;
                reasons.add(failure);
            }
        }
        if (!metrics.isEmpty()) {
            requests++;
            String failure = post("/v1/metrics", metricPayload(metrics));
            if (failure == null) {
                metricsExported = metrics.size();
            } else {
                failures++;
                reasons.add(failure);
            }
        }
        if (failures == 0) {
            recording.clear();
        }
        return new Result(spansExported, metricsExported, requests, failures, reasons);
    }

    String tracePayload(List<CasTelemetry.FinishedSpan> spans) {
        StringBuilder json = new StringBuilder("{\"resourceSpans\":[{");
        json.append("\"resource\":").append(resource()).append(',');
        json.append("\"scopeSpans\":[{\"scope\":").append(scope()).append(",\"spans\":[");
        for (int index = 0; index < spans.size(); index++) {
            CasTelemetry.FinishedSpan span = spans.get(index);
            if (index > 0) {
                json.append(',');
            }
            json.append("{\"traceId\":").append(string(span.traceId()))
                    .append(",\"spanId\":").append(string(span.spanId()));
            if (!span.parentSpanId().isEmpty()) {
                json.append(",\"parentSpanId\":").append(string(span.parentSpanId()));
            }
            json.append(",\"name\":").append(string(span.name()))
                    .append(",\"kind\":").append(span.kind().code())
                    .append(",\"startTimeUnixNano\":").append(string(Long.toString(span.startUnixNanos())))
                    .append(",\"endTimeUnixNano\":").append(string(Long.toString(span.endUnixNanos())))
                    .append(",\"attributes\":").append(attributes(span.stringAttributes(), span.longAttributes()))
                    .append(",\"status\":{\"code\":").append(span.status().code());
            if (!span.statusDescription().isEmpty()) {
                json.append(",\"message\":").append(string(span.statusDescription()));
            }
            json.append("}}");
        }
        return json.append("]}]}]}").toString();
    }

    String metricPayload(List<CasTelemetry.MetricPoint> points) {
        Map<String, List<CasTelemetry.MetricPoint>> sums = new LinkedHashMap<>();
        Map<String, List<CasTelemetry.MetricPoint>> histograms = new LinkedHashMap<>();
        for (CasTelemetry.MetricPoint point : points) {
            (point.monotonicSum() ? sums : histograms)
                    .computeIfAbsent(point.name() + ' ' + point.unit(), key -> new ArrayList<>())
                    .add(point);
        }
        StringBuilder json = new StringBuilder("{\"resourceMetrics\":[{");
        json.append("\"resource\":").append(resource()).append(',');
        json.append("\"scopeMetrics\":[{\"scope\":").append(scope()).append(",\"metrics\":[");
        boolean first = true;
        for (Map.Entry<String, List<CasTelemetry.MetricPoint>> metric : sums.entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append(sumMetric(metric.getKey(), metric.getValue()));
        }
        for (Map.Entry<String, List<CasTelemetry.MetricPoint>> metric : histograms.entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append(histogramMetric(metric.getKey(), metric.getValue()));
        }
        return json.append("]}]}]}").toString();
    }

    private String sumMetric(String key, List<CasTelemetry.MetricPoint> points) {
        String[] parts = key.split(" ", -1);
        // A cumulative sum supersedes its own earlier points, so only the latest value per
        // attribute set is shipped.
        Map<String, CasTelemetry.MetricPoint> latest = new LinkedHashMap<>();
        points.forEach(point -> latest.put(point.attributes().toString(), point));
        StringBuilder json = new StringBuilder("{\"name\":").append(string(parts[0]))
                .append(",\"unit\":").append(string(parts[1]))
                .append(",\"sum\":{\"aggregationTemporality\":2,\"isMonotonic\":true,\"dataPoints\":[");
        boolean first = true;
        for (CasTelemetry.MetricPoint point : latest.values()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append("{\"attributes\":").append(attributes(point.attributes(), Map.of()))
                    .append(",\"timeUnixNano\":").append(string(Long.toString(point.timeUnixNanos())))
                    .append(",\"asInt\":").append(string(Long.toString(point.value()))).append('}');
        }
        return json.append("]}}").toString();
    }

    private String histogramMetric(String key, List<CasTelemetry.MetricPoint> points) {
        String[] parts = key.split(" ", -1);
        Map<String, List<CasTelemetry.MetricPoint>> bySeries = new LinkedHashMap<>();
        points.forEach(point -> bySeries.computeIfAbsent(point.attributes().toString(),
                series -> new ArrayList<>()).add(point));
        StringBuilder json = new StringBuilder("{\"name\":").append(string(parts[0]))
                .append(",\"unit\":").append(string(parts[1]))
                .append(",\"histogram\":{\"aggregationTemporality\":2,\"dataPoints\":[");
        boolean first = true;
        for (List<CasTelemetry.MetricPoint> series : bySeries.values()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            long[] counts = new long[BUCKET_BOUNDS.length + 1];
            long sum = 0;
            long max = Long.MIN_VALUE;
            long min = Long.MAX_VALUE;
            for (CasTelemetry.MetricPoint point : series) {
                sum += point.value();
                max = Math.max(max, point.value());
                min = Math.min(min, point.value());
                counts[bucketOf(point.value())]++;
            }
            json.append("{\"attributes\":").append(attributes(series.get(0).attributes(), Map.of()))
                    .append(",\"timeUnixNano\":")
                    .append(string(Long.toString(series.get(series.size() - 1).timeUnixNanos())))
                    .append(",\"count\":").append(string(Long.toString(series.size())))
                    .append(",\"sum\":").append(sum)
                    .append(",\"min\":").append(min).append(",\"max\":").append(max)
                    .append(",\"explicitBounds\":[");
            for (int index = 0; index < BUCKET_BOUNDS.length; index++) {
                json.append(index > 0 ? "," : "").append(BUCKET_BOUNDS[index]);
            }
            json.append("],\"bucketCounts\":[");
            for (int index = 0; index < counts.length; index++) {
                json.append(index > 0 ? "," : "").append(string(Long.toString(counts[index])));
            }
            json.append("]}");
        }
        return json.append("]}}").toString();
    }

    private static int bucketOf(long value) {
        for (int index = 0; index < BUCKET_BOUNDS.length; index++) {
            if (value <= BUCKET_BOUNDS[index]) {
                return index;
            }
        }
        return BUCKET_BOUNDS.length;
    }

    private String resource() {
        Map<String, String> attributes = new TreeMap<>();
        attributes.put("service.name", config.serviceName());
        attributes.put("service.version", SCOPE_VERSION);
        attributes.put("deployment.environment", config.deploymentEnvironment());
        return "{\"attributes\":" + attributes(attributes, Map.of()) + "}";
    }

    private static String scope() {
        return "{\"name\":" + string(SCOPE_NAME) + ",\"version\":" + string(SCOPE_VERSION) + "}";
    }

    private static String attributes(Map<String, String> strings, Map<String, Long> longs) {
        StringBuilder json = new StringBuilder("[");
        boolean first = true;
        for (Map.Entry<String, String> attribute : new TreeMap<>(strings).entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append("{\"key\":").append(string(attribute.getKey()))
                    .append(",\"value\":{\"stringValue\":").append(string(attribute.getValue())).append("}}");
        }
        for (Map.Entry<String, Long> attribute : new TreeMap<>(longs).entrySet()) {
            if (!first) {
                json.append(',');
            }
            first = false;
            json.append("{\"key\":").append(string(attribute.getKey()))
                    .append(",\"value\":{\"intValue\":").append(string(Long.toString(attribute.getValue())))
                    .append("}}");
        }
        return json.append(']').toString();
    }

    private static String string(String value) {
        return CasManifest.CanonicalEncoder.jsonString(value);
    }

    /** @return null on success, a reason string on failure; never throws */
    private String post(String path, String payload) {
        RuntimeException last = null;
        for (int attempt = 1; attempt <= config.maximumAttempts(); attempt++) {
            try {
                HttpRequest request = HttpRequest.newBuilder(
                                URI.create(config.endpoint().toString().replaceAll("/$", "") + path))
                        .timeout(config.timeout())
                        .header("content-type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(payload, StandardCharsets.UTF_8))
                        .build();
                HttpResponse<String> response = http.send(request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() >= 200 && response.statusCode() < 300) {
                    return null;
                }
                if (response.statusCode() < 500) {
                    return path + " rejected with " + response.statusCode();
                }
                last = new IllegalStateException(path + " returned " + response.statusCode());
            } catch (java.io.IOException error) {
                last = new IllegalStateException(path + " transport failure: " + error.getMessage());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return path + " interrupted";
            }
        }
        return last.getMessage();
    }
}
