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
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class CasAlertingTest {

    private static final long NOW = 1_800_000_000_000L;

    private static CasAlerting.HealthSnapshot healthy() {
        return CasAlerting.HealthSnapshot.healthy();
    }

    private static CasAlerting.Evaluator evaluator(CasAlerting.Sink... sinks) {
        return CasAlerting.Evaluator.standard(List.of(sinks));
    }

    @Test void aHealthySnapshotFiresNothing() {
        var sink = new CasAlerting.CollectingSink();
        assertTrue(evaluator(sink).evaluate(healthy(), NOW).isEmpty());
        assertTrue(sink.delivered().isEmpty());
    }

    @Test void aSingleCorruptionEventPages() {
        var sink = new CasAlerting.CollectingSink();
        var snapshot = new CasAlerting.HealthSnapshot(1, List.of(), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 0);

        var fired = evaluator(sink).evaluate(snapshot, NOW);
        assertEquals(1, fired.size());
        assertEquals("CAS_POISONING_DETECTED", fired.get(0).ruleId());
        assertEquals(CasAlerting.Severity.PAGE, fired.get(0).severity());
        assertEquals(1, sink.delivered().size());
    }

    @Test void everyQuarantinedNodeGetsItsOwnAlert() {
        var sink = new CasAlerting.CollectingSink();
        var snapshot = new CasAlerting.HealthSnapshot(0, List.of("node-3", "node-9"), 0, 0, 0,
                1.0d, 1_000, 0, 0, 0, 0, 0);

        var fired = evaluator(sink).evaluate(snapshot, NOW);
        assertEquals(2, fired.size());
        assertEquals(List.of("node-3", "node-9"), fired.stream().map(CasAlerting.Alert::key).toList());
        assertTrue(fired.stream().allMatch(alert -> alert.severity() == CasAlerting.Severity.CRITICAL));
    }

    @Test void aStaleDurabilityBacklogPagesWhileMerelyLargeOneWarns() {
        var large = new CasAlerting.HealthSnapshot(0, List.of(), 500, 1_000_000, 1_000,
                1.0d, 1_000, 0, 0, 0, 0, 0);
        var stale = new CasAlerting.HealthSnapshot(0, List.of(), 1, 4_096, 30 * 60 * 1000L,
                1.0d, 1_000, 0, 0, 0, 0, 0);

        assertEquals(CasAlerting.Severity.WARNING,
                evaluator(new CasAlerting.CollectingSink()).evaluate(large, NOW).get(0).severity());
        assertEquals(CasAlerting.Severity.PAGE,
                evaluator(new CasAlerting.CollectingSink()).evaluate(stale, NOW).get(0).severity());
    }

    @Test void aColdCacheDoesNotFireTheHitRateRule() {
        var coldStart = new CasAlerting.HealthSnapshot(0, List.of(), 0, 0, 0, 0.0d, 5, 0, 0, 0, 0, 0);
        assertTrue(evaluator(new CasAlerting.CollectingSink()).evaluate(coldStart, NOW).isEmpty(),
                "below the minimum sample size the hit rate is meaningless");

        var collapsed = new CasAlerting.HealthSnapshot(0, List.of(), 0, 0, 0, 0.31d, 5_000, 0, 0, 0, 0, 0);
        var fired = evaluator(new CasAlerting.CollectingSink()).evaluate(collapsed, NOW);
        assertEquals(1, fired.size());
        assertEquals("CAS_HIT_RATE_COLLAPSE", fired.get(0).ruleId());
        assertEquals(CasAlerting.Severity.WARNING, fired.get(0).severity());
        assertEquals("0.3100", fired.get(0).attributes().get("hit_rate"));
    }

    @Test void reconciliationDriftSeparatesLostDataFromWastedSpace() {
        var snapshot = new CasAlerting.HealthSnapshot(0, List.of(), 0, 0, 0, 1.0d, 1_000,
                4, 100L * 1024 * 1024 * 1024, 40, 250, 0);
        var fired = evaluator(new CasAlerting.CollectingSink()).evaluate(snapshot, NOW);

        Map<String, CasAlerting.Severity> bySubKey = new java.util.LinkedHashMap<>();
        fired.forEach(alert -> bySubKey.put(alert.key(), alert.severity()));
        assertEquals(CasAlerting.Severity.CRITICAL, bySubKey.get("missing-objects"));
        assertEquals(CasAlerting.Severity.INFO, bySubKey.get("orphans"));
        assertEquals(CasAlerting.Severity.WARNING, bySubKey.get("incomplete-uploads"));
        assertEquals(CasAlerting.Severity.WARNING, bySubKey.get("replication"));
    }

    @Test void repeatFiringsInsideTheWindowAreSuppressedAndCounted() {
        var sink = new CasAlerting.CollectingSink();
        var evaluator = evaluator(sink);
        var snapshot = new CasAlerting.HealthSnapshot(1, List.of(), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 0);

        assertEquals(1, evaluator.evaluate(snapshot, NOW).size());
        assertTrue(evaluator.evaluate(snapshot, NOW + 60_000).isEmpty());
        assertTrue(evaluator.evaluate(snapshot, NOW + 120_000).isEmpty());
        assertEquals(Long.valueOf(2), evaluator.currentlySuppressed().get("CAS_POISONING_DETECTED/global"));

        var refired = evaluator.evaluate(snapshot, NOW + 20 * 60_000);
        assertEquals(1, refired.size());
        assertEquals(2, refired.get(0).suppressedSinceLastFiring(),
                "the operator must be told what happened while they were not being paged");
        assertTrue(evaluator.currentlySuppressed().isEmpty());
        assertEquals(2, sink.delivered().size());
    }

    @Test void twoDifferentNodesAreNotCollapsedIntoOneIncident() {
        var evaluator = evaluator(new CasAlerting.CollectingSink());
        var first = new CasAlerting.HealthSnapshot(0, List.of("node-1"), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 0);
        var both = new CasAlerting.HealthSnapshot(0, List.of("node-1", "node-2"), 0, 0, 0, 1.0d,
                1_000, 0, 0, 0, 0, 0);

        assertEquals(1, evaluator.evaluate(first, NOW).size());
        var second = evaluator.evaluate(both, NOW + 1_000);
        assertEquals(1, second.size());
        assertEquals("node-2", second.get(0).key());
    }

    @Test void alertsAreDeliveredToAWebhookAsJson() throws Exception {
        List<String> bodies = new ArrayList<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            bodies.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            exchange.sendResponseHeaders(204, -1);
            exchange.close();
        });
        server.start();
        try {
            var webhook = new CasAlerting.WebhookSink(
                    URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/alerts"),
                    HttpClient.newHttpClient(), Duration.ofSeconds(5));
            var snapshot = new CasAlerting.HealthSnapshot(3, List.of(), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 0);

            evaluator(webhook).evaluate(snapshot, NOW);

            assertEquals(1, bodies.size());
            assertTrue(bodies.get(0).contains("\"rule_id\":\"CAS_POISONING_DETECTED\""));
            assertTrue(bodies.get(0).contains("\"severity\":\"PAGE\""));
            assertTrue(bodies.get(0).contains("\"events\":\"3\""));
            assertTrue(webhook.failures().isEmpty());
        } finally {
            server.stop(0);
        }
    }

    @Test void aBrokenWebhookIsRecordedRatherThanThrown() throws IOException {
        AtomicInteger requests = new AtomicInteger();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            requests.incrementAndGet();
            exchange.sendResponseHeaders(500, -1);
            exchange.close();
        });
        server.start();
        try {
            var webhook = new CasAlerting.WebhookSink(
                    URI.create("http://127.0.0.1:" + server.getAddress().getPort() + "/alerts"),
                    HttpClient.newHttpClient(), Duration.ofSeconds(5));
            var snapshot = new CasAlerting.HealthSnapshot(1, List.of(), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 0);

            var fired = evaluator(webhook).evaluate(snapshot, NOW);

            assertEquals(1, fired.size(), "evaluation must not fail because delivery did");
            assertEquals(1, requests.get());
            assertEquals(1, webhook.failures().size());
        } finally {
            server.stop(0);
        }
    }

    @Test void theSnapshotCanBeAssembledFromTheLiveComponents() {
        InMemoryCasStore local = new InMemoryCasStore("l1");
        InMemoryCasStore shared = new InMemoryCasStore("l2");
        var tiered = new TieredCasStore(local, shared, TieredCasStore.TierPolicy.unbounded(), () -> NOW);
        byte[] content = "not yet durable".getBytes(StandardCharsets.UTF_8);
        CasDigest digest = CasDigest.of(content);
        tiered.put(digest, content);

        CasMetrics metrics = new CasMetrics();
        metrics.record(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.HIT, "EXACT");
        metrics.record(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.MISS, "NO_ENTRY");
        var cache = new ActionCache(shared, new CasAccessPolicy(), ActionCache.FailureCachePolicy.none(),
                ActionCache.SampleRecomputePolicy.disabled(), () -> NOW, metrics);
        cache.quarantineNode("node-7", "sampled recompute mismatch");

        var reconciler = new CasReconciler(shared, ignored -> Optional.empty());
        var report = reconciler.reconcile(Map.of(), Map.of(), Optional.empty(), 0, NOW);

        var snapshot = CasAlerting.HealthSnapshot.from(tiered, cache, metrics, report, 0, 1_000, 0, 0);

        assertEquals(1, snapshot.pendingDurabilityObjects());
        assertEquals(content.length, snapshot.pendingDurabilityBytes());
        assertEquals(List.of("node-7"), snapshot.quarantinedNodes());
        assertEquals(2, snapshot.actionCacheLookups());
        assertEquals(0.5d, snapshot.actionCacheHitRate());
    }

    @Test void telemetryFailuresAreThemselvesAlertable() {
        var snapshot = new CasAlerting.HealthSnapshot(0, List.of(), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 5);
        var fired = evaluator(new CasAlerting.CollectingSink()).evaluate(snapshot, NOW);
        assertEquals(1, fired.size());
        assertEquals("CAS_TELEMETRY_EXPORT_FAILING", fired.get(0).ruleId());
    }
}
