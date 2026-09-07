package io.elmos.cas;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class CasTelemetryTest {

    private static final String PINNED_IMAGE = "registry.internal/elmos/java21@sha256:" + "a".repeat(64);

    private final AtomicLong nanos = new AtomicLong(1_800_000_000_000_000_000L);
    private final AtomicLong millis = new AtomicLong(1_800_000_000_000L);

    /** Advances on every read so a span always has a non-zero duration. */
    private long tick() {
        return nanos.addAndGet(1_000_000);
    }

    private static CasDigest digest(String text) {
        return CasDigest.of(text.getBytes(StandardCharsets.UTF_8));
    }

    /** Minimal OTLP/HTTP collector: records bodies per path and can be told to fail. */
    private static final class MockCollector implements AutoCloseable {
        private final HttpServer server;
        private final List<String> tracePayloads = new ArrayList<>();
        private final List<String> metricPayloads = new ArrayList<>();
        private final AtomicInteger failNext = new AtomicInteger();
        private final AtomicInteger requests = new AtomicInteger();

        MockCollector() throws IOException {
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                requests.incrementAndGet();
                String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
                if (failNext.get() > 0) {
                    failNext.decrementAndGet();
                    exchange.sendResponseHeaders(503, -1);
                    exchange.close();
                    return;
                }
                if (exchange.getRequestURI().getPath().endsWith("/v1/traces")) {
                    tracePayloads.add(body);
                } else {
                    metricPayloads.add(body);
                }
                exchange.sendResponseHeaders(200, -1);
                exchange.close();
            });
            server.start();
        }

        URI endpoint() {
            return URI.create("http://127.0.0.1:" + server.getAddress().getPort());
        }

        @Override
        public void close() {
            server.stop(0);
        }
    }

    private static ActionKey key(String module) {
        return new ActionKeyBuilder()
                .tenant("tenant-a", "project-a")
                .sourceTree(digest("source-" + module))
                .toolchainImage(PINNED_IMAGE)
                .command(List.of("./mvnw", "verify"))
                .workingDirectory("/workspace/source")
                .declaredOutputs(List.of("target"))
                .policy(digest("policy"))
                .permissionScope(Set.of("repo:read"))
                .sandbox("S2", digest("sandbox"))
                .dataResidency("eu-west")
                .environmentContract(ActionKeyBuilder.EnvironmentContract.of())
                .environment(Map.of())
                .build();
    }

    @Test void spansCarryParentageAttributesAndStatus() {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        CasTelemetry.Span parent = recording.startSpan("cas.parent", CasTelemetry.SpanKind.INTERNAL,
                Optional.empty());
        CasTelemetry.Span child = recording.startSpan("cas.child", CasTelemetry.SpanKind.CLIENT,
                Optional.of(parent));
        child.attribute("cas.tier", "L2").attribute("cas.object_bytes", 4096L)
                .status(CasTelemetry.SpanStatus.OK, "read-through");
        child.close();
        parent.close();

        var childSpan = recording.span("cas.child").orElseThrow();
        assertEquals(parent.traceId(), childSpan.traceId(), "a child must join its parent's trace");
        assertEquals(parent.spanId(), childSpan.parentSpanId());
        assertEquals(32, childSpan.traceId().length());
        assertEquals(16, childSpan.spanId().length());
        assertEquals("L2", childSpan.stringAttributes().get("cas.tier"));
        assertEquals(Long.valueOf(4096), childSpan.longAttributes().get("cas.object_bytes"));
        assertEquals(CasTelemetry.SpanStatus.OK, childSpan.status());
        assertTrue(childSpan.durationNanos() > 0);
    }

    @Test void closingASpanTwiceRecordsItOnce() {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        try (CasTelemetry.Span span = recording.startSpan("cas.once", CasTelemetry.SpanKind.INTERNAL,
                Optional.empty())) {
            span.close();
        }
        assertEquals(1, recording.spans().size());
    }

    @Test void theActionCacheEmitsOneSpanAndOneCounterPerLookup() {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        InMemoryCasStore store = new InMemoryCasStore("l2");
        var cache = new ActionCache(store, new CasAccessPolicy(), ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), millis::get, new CasMetrics(), recording);

        ActionKey actionKey = key("a");
        CasDigest manifest = digest("output");
        store.put(manifest, "output".getBytes(StandardCharsets.UTF_8));
        var producer = new CasAccessPolicy.ProducerContext("tenant-a", "project-a", Set.of("repo:read"),
                "eu-west", CasAccessPolicy.SecurityTier.INTERNAL, CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                PINNED_IMAGE, Optional.of(digest("provenance")));
        var reader = new CasAccessPolicy.ReaderContext("tenant-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, false);
        var result = ActionResultRecord.succeeded("act-1", "receipt-1", manifest, digest("provenance"),
                new ActionResultRecord.ResourceUsage(12, 256, 10, 10, 0, 61),
                "2026-08-19T06:30:00Z", "2026-08-19T06:31:01Z");

        cache.put(actionKey, result, producer,
                new ActionCache.WriterIdentity("runner", "elmos.internal", "node-1", true),
                ActionCache.RiskTier.STANDARD, Optional.empty());
        cache.get(actionKey, reader, false);
        cache.get(key("missing"), reader, false);

        assertTrue(recording.span("cas.action_cache.store").isPresent());
        var lookups = recording.spans().stream()
                .filter(span -> span.name().equals("cas.action_cache.lookup")).toList();
        assertEquals(2, lookups.size());
        assertEquals("HIT", lookups.get(0).stringAttributes().get("cas.outcome"));
        assertEquals("MISS", lookups.get(1).stringAttributes().get("cas.outcome"));
        assertEquals("tenant-a", lookups.get(0).stringAttributes().get("elmos.tenant_id"));

        assertEquals(1, recording.counterValue("cas.action_cache.lookups",
                Map.of("outcome", "HIT", "reason", "EXACT", "tenant", "tenant-a")));
        assertEquals(1, recording.counterValue("cas.action_cache.lookups",
                Map.of("outcome", "MISS", "reason", "NO_ENTRY", "tenant", "tenant-a")));
        assertTrue(recording.metrics().stream().anyMatch(point ->
                point.name().equals("cas.action_cache.wall_seconds_avoided") && point.value() == 61));
    }

    @Test void aDeniedLookupIsAnErrorSpan() {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        InMemoryCasStore store = new InMemoryCasStore("l2");
        var cache = new ActionCache(store, new CasAccessPolicy(), ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), millis::get, new CasMetrics(), recording);
        ActionKey actionKey = key("a");
        CasDigest manifest = digest("privileged");
        store.put(manifest, "privileged".getBytes(StandardCharsets.UTF_8));
        var producer = new CasAccessPolicy.ProducerContext("tenant-a", "project-a",
                Set.of("repo:read", "secret:read"), "eu-west", CasAccessPolicy.SecurityTier.INTERNAL,
                CasObjectModel.Sensitivity.GENERATED_OUTPUT, PINNED_IMAGE, Optional.of(digest("provenance")));
        cache.put(actionKey, ActionResultRecord.succeeded("act-1", "receipt-1", manifest, digest("provenance"),
                        new ActionResultRecord.ResourceUsage(1, 1, 0, 0, 0, 1), "s", "f"), producer,
                new ActionCache.WriterIdentity("runner", "elmos.internal", "node-1", true),
                ActionCache.RiskTier.STANDARD, Optional.empty());

        cache.get(actionKey, new CasAccessPolicy.ReaderContext("tenant-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, false), false);

        var lookup = recording.spans().stream()
                .filter(span -> span.name().equals("cas.action_cache.lookup")).findFirst().orElseThrow();
        assertEquals(CasTelemetry.SpanStatus.ERROR, lookup.status());
        assertEquals("PERMISSION_DOWNGRADE", lookup.statusDescription());
    }

    @Test void theTieredStoreRecordsTierAndTransferredBytes() {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        var tiered = new TieredCasStore(local, shared, TieredCasStore.TierPolicy.unbounded(), millis::get)
                .withTelemetry(recording);

        byte[] content = "telemetry payload".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(content);
        tiered.putDurable(digest, content);
        tiered.get(digest);
        local.delete(digest);
        tiered.get(digest);

        var gets = recording.spans().stream().filter(span -> span.name().equals("cas.store.get")).toList();
        assertEquals(2, gets.size());
        assertEquals("L1", gets.get(0).stringAttributes().get("cas.tier"));
        assertEquals("L2", gets.get(1).stringAttributes().get("cas.tier"));
        assertEquals(Long.valueOf(content.length), gets.get(0).longAttributes().get("cas.object_bytes"));
        assertEquals(1, recording.counterValue("cas.store.reads", Map.of("tier", "L1")));
        assertTrue(recording.metrics().stream().anyMatch(point ->
                point.name().equals("cas.transfer.bytes") && point.attributes().get("direction").equals("upload")));
    }

    @Test void theTracePayloadFollowsTheOtlpShape() throws Exception {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        CasTelemetry.Span parent = recording.startSpan("cas.parent", CasTelemetry.SpanKind.INTERNAL,
                Optional.empty());
        CasTelemetry.Span child = recording.startSpan("cas.child", CasTelemetry.SpanKind.CLIENT,
                Optional.of(parent));
        child.attribute("cas.tier", "L2").attribute("cas.object_bytes", 7L)
                .status(CasTelemetry.SpanStatus.ERROR, "poisoned");
        child.close();
        parent.close();

        try (MockCollector collector = new MockCollector()) {
            var exporter = new OtlpExporter(OtlpExporter.Config.of(collector.endpoint()),
                    HttpClient.newHttpClient());
            String payload = exporter.tracePayload(recording.spans());

            assertTrue(payload.startsWith("{\"resourceSpans\":[{\"resource\":{\"attributes\":["));
            assertTrue(payload.contains("\"key\":\"service.name\",\"value\":{\"stringValue\":\"elmos-cas\"}"));
            assertTrue(payload.contains("\"name\":\"io.elmos.cas\""));
            assertTrue(payload.contains("\"name\":\"cas.child\",\"kind\":3"));
            assertTrue(payload.contains("\"parentSpanId\":\"" + parent.spanId() + "\""));
            assertTrue(payload.contains("\"value\":{\"intValue\":\"7\"}"));
            assertTrue(payload.contains("\"status\":{\"code\":2,\"message\":\"poisoned\"}"));
            assertTrue(payload.contains("\"startTimeUnixNano\":\""));
        }
    }

    @Test void theMetricPayloadCarriesCumulativeSumsAndExplicitHistogramBuckets() throws Exception {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        recording.counter("cas.action_cache.lookups", "1", 1, Map.of("outcome", "HIT"));
        recording.counter("cas.action_cache.lookups", "1", 1, Map.of("outcome", "HIT"));
        recording.histogram("cas.transfer.bytes", "By", 5, Map.of("direction", "upload"));
        recording.histogram("cas.transfer.bytes", "By", 5_000, Map.of("direction", "upload"));

        try (MockCollector collector = new MockCollector()) {
            var exporter = new OtlpExporter(OtlpExporter.Config.of(collector.endpoint()),
                    HttpClient.newHttpClient());
            String payload = exporter.metricPayload(recording.metrics());

            assertTrue(payload.contains("\"aggregationTemporality\":2,\"isMonotonic\":true"));
            assertTrue(payload.contains("\"asInt\":\"2\""), "a cumulative sum ships its latest value");
            assertTrue(payload.contains("\"name\":\"cas.transfer.bytes\",\"unit\":\"By\""));
            assertTrue(payload.contains("\"explicitBounds\":[1,10,100,1000,10000,100000,1000000,10000000]"));
            assertTrue(payload.contains("\"count\":\"2\""));
            assertTrue(payload.contains("\"sum\":5005"));
            assertTrue(payload.contains("\"min\":5,\"max\":5000"));
        }
    }

    @Test void exportShipsBothSignalsAndClearsTheRecording() throws Exception {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        recording.startSpan("cas.one", CasTelemetry.SpanKind.INTERNAL, Optional.empty()).close();
        recording.counter("cas.action_cache.lookups", "1", 1, Map.of("outcome", "HIT"));

        try (MockCollector collector = new MockCollector()) {
            var exporter = new OtlpExporter(OtlpExporter.Config.of(collector.endpoint()),
                    HttpClient.newHttpClient());
            var result = exporter.export(recording);

            assertTrue(result.healthy());
            assertEquals(1, result.spansExported());
            assertEquals(1, result.metricsExported());
            assertEquals(1, collector.tracePayloads.size());
            assertEquals(1, collector.metricPayloads.size());
            assertTrue(recording.spans().isEmpty());
            assertTrue(recording.metrics().isEmpty());
        }
    }

    @Test void largeSpanSetsAreSplitIntoBoundedBatches() throws Exception {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        for (int index = 0; index < 7; index++) {
            recording.startSpan("cas.span-" + index, CasTelemetry.SpanKind.INTERNAL, Optional.empty()).close();
        }
        try (MockCollector collector = new MockCollector()) {
            var config = new OtlpExporter.Config(collector.endpoint(), "elmos-cas", "test", 3, 1,
                    Duration.ofSeconds(5));
            var result = new OtlpExporter(config, HttpClient.newHttpClient()).export(recording);

            assertEquals(7, result.spansExported());
            assertEquals(3, collector.tracePayloads.size());
        }
    }

    @Test void aCollectorOutageIsReportedAndTheRecordingIsKept() throws Exception {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        recording.startSpan("cas.kept", CasTelemetry.SpanKind.INTERNAL, Optional.empty()).close();

        try (MockCollector collector = new MockCollector()) {
            collector.failNext.set(10);
            var config = new OtlpExporter.Config(collector.endpoint(), "elmos-cas", "test", 512, 2,
                    Duration.ofSeconds(5));
            var result = new OtlpExporter(config, HttpClient.newHttpClient()).export(recording);

            assertFalse(result.healthy());
            assertEquals(0, result.spansExported());
            assertEquals(1, result.failures());
            assertFalse(recording.spans().isEmpty(), "nothing may be dropped when the collector is down");
        }
    }

    @Test void aTransientCollectorFailureIsRetried() throws Exception {
        var recording = CasTelemetry.Recording.deterministic(this::tick);
        recording.startSpan("cas.retried", CasTelemetry.SpanKind.INTERNAL, Optional.empty()).close();

        try (MockCollector collector = new MockCollector()) {
            collector.failNext.set(1);
            var config = new OtlpExporter.Config(collector.endpoint(), "elmos-cas", "test", 512, 3,
                    Duration.ofSeconds(5));
            var result = new OtlpExporter(config, HttpClient.newHttpClient()).export(recording);

            assertTrue(result.healthy());
            assertEquals(1, result.spansExported());
            assertEquals(2, collector.requests.get());
        }
    }

    @Test void theNoopTelemetryCostsNothingAndKeepsTheCacheBehaviourIdentical() {
        InMemoryCasStore store = new InMemoryCasStore("l2");
        var withoutTelemetry = new ActionCache(store, new CasAccessPolicy(),
                ActionCache.FailureCachePolicy.none(), ActionCache.SampleRecomputePolicy.disabled(),
                millis::get, new CasMetrics());
        var reader = new CasAccessPolicy.ReaderContext("tenant-a", Set.of("repo:read"), "eu-west",
                CasAccessPolicy.SecurityTier.INTERNAL, false);
        assertEquals(ActionCache.CacheOutcome.MISS, withoutTelemetry.get(key("a"), reader, false).outcome());
    }
}
