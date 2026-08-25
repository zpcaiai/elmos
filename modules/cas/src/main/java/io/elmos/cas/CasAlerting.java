package io.elmos.cas;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;

/**
 * Alerting for the CAS: the rules an operator is woken up by, and the throttling that decides
 * whether they should be.
 *
 * <p>The rules are chosen by what is unrecoverable rather than by what is noisy. Losing an object
 * that only exists in L1 cannot be undone, so durability backlog pages. A poisoned object may
 * already be inside a customer's build, so poisoning pages. A hit rate that fell to 40 percent is
 * expensive and annoying but nothing is lost, so it warns.
 *
 * <p>Throttling is per rule <em>and</em> per key. A single poisoned node must not be able to
 * generate one page per affected object, but two different nodes going bad at once must produce
 * two alerts — collapsing those into one is how the second incident gets missed. Suppressed
 * occurrences are counted and reported on the next firing, so nothing disappears silently.
 */
public final class CasAlerting {

    public enum Severity {
        INFO,
        WARNING,
        CRITICAL,
        PAGE
    }

    /**
     * Everything the rules look at, gathered once. A snapshot rather than live references so an
     * evaluation is reproducible and can be replayed from a log line.
     */
    public record HealthSnapshot(long corruptionEventsInWindow,
                                 List<String> quarantinedNodes,
                                 int pendingDurabilityObjects,
                                 long pendingDurabilityBytes,
                                 long oldestPendingDurabilityAgeMillis,
                                 double actionCacheHitRate,
                                 long actionCacheLookups,
                                 int missingReferencedObjects,
                                 long orphanedBytes,
                                 int incompleteUploadSessions,
                                 int outstandingReplications,
                                 int telemetryExportFailures) {

        public HealthSnapshot {
            quarantinedNodes = List.copyOf(quarantinedNodes);
        }

        public static HealthSnapshot healthy() {
            return new HealthSnapshot(0, List.of(), 0, 0, 0, 1.0d, 1_000, 0, 0, 0, 0, 0);
        }

        /** Assembles a snapshot from the live components, so callers do not hand-roll it. */
        public static HealthSnapshot from(TieredCasStore store,
                                          ActionCache cache,
                                          CasMetrics metrics,
                                          CasReconciler.ReconciliationReport reconciliation,
                                          long corruptionEventsInWindow,
                                          long oldestPendingDurabilityAgeMillis,
                                          int outstandingReplications,
                                          int telemetryExportFailures) {
            long pendingBytes = store.pendingDurability().stream().mapToLong(CasDigest::sizeBytes).sum();
            long lookups = metrics.count(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.HIT)
                    + metrics.count(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.MISS)
                    + metrics.count(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.STALE)
                    + metrics.count(CasMetrics.Layer.ACTION, ActionCache.CacheOutcome.INVALIDATED);
            return new HealthSnapshot(corruptionEventsInWindow,
                    new ArrayList<>(cache.quarantinedNodes()),
                    store.pendingDurability().size(), pendingBytes, oldestPendingDurabilityAgeMillis,
                    metrics.exactHitRate(CasMetrics.Layer.ACTION), lookups,
                    reconciliation.missingBlobs().size(), reconciliation.orphanedBytes(),
                    reconciliation.incompleteUploadSessions().size(), outstandingReplications,
                    telemetryExportFailures);
        }
    }

    public record Alert(String ruleId, String key, Severity severity, String summary, String detail,
                        Map<String, String> attributes, long firedAtEpochMillis, long suppressedSinceLastFiring) {
        public Alert {
            ruleId = CasText.required(ruleId, "ruleId");
            key = CasText.required(key, "key");
            Objects.requireNonNull(severity, "severity");
            attributes = Map.copyOf(new TreeMap<>(attributes));
        }

        Alert withSuppressed(long suppressed) {
            return new Alert(ruleId, key, severity, summary, detail, attributes, firedAtEpochMillis, suppressed);
        }

        public String toJson() {
            StringBuilder json = new StringBuilder("{\"rule_id\":")
                    .append(CasManifest.CanonicalEncoder.jsonString(ruleId))
                    .append(",\"key\":").append(CasManifest.CanonicalEncoder.jsonString(key))
                    .append(",\"severity\":").append(CasManifest.CanonicalEncoder.jsonString(severity.name()))
                    .append(",\"summary\":").append(CasManifest.CanonicalEncoder.jsonString(summary))
                    .append(",\"detail\":").append(CasManifest.CanonicalEncoder.jsonString(detail))
                    .append(",\"fired_at\":").append(firedAtEpochMillis)
                    .append(",\"suppressed_since_last_firing\":").append(suppressedSinceLastFiring)
                    .append(",\"attributes\":{");
            boolean first = true;
            for (Map.Entry<String, String> attribute : attributes.entrySet()) {
                if (!first) {
                    json.append(',');
                }
                first = false;
                json.append(CasManifest.CanonicalEncoder.jsonString(attribute.getKey())).append(':')
                        .append(CasManifest.CanonicalEncoder.jsonString(attribute.getValue()));
            }
            return json.append("}}").toString();
        }
    }

    public interface Rule {
        String id();

        List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long nowEpochMillis);
    }

    public record Thresholds(int durabilityBacklogObjects,
                             long durabilityBacklogAgeMillis,
                             double minimumHitRate,
                             long minimumLookupsBeforeHitRateAlerts,
                             long orphanedBytesWarning,
                             int incompleteUploadSessionsWarning,
                             int outstandingReplicationsWarning,
                             int telemetryFailuresWarning) {

        public static Thresholds standard() {
            return new Thresholds(50, 5 * 60 * 1000L, 0.80d, 200, 50L * 1024 * 1024 * 1024, 25, 100, 3);
        }
    }

    /** Sinks never throw; a broken alerting path must not break the thing it is watching. */
    public interface Sink {
        void deliver(Alert alert);

        List<String> failures();
    }

    public static final class CollectingSink implements Sink {
        private final List<Alert> delivered = Collections.synchronizedList(new ArrayList<>());

        @Override
        public void deliver(Alert alert) {
            delivered.add(alert);
        }

        @Override
        public List<String> failures() {
            return List.of();
        }

        public List<Alert> delivered() {
            synchronized (delivered) {
                return List.copyOf(delivered);
            }
        }
    }

    public static final class WebhookSink implements Sink {
        private final URI endpoint;
        private final HttpClient http;
        private final Duration timeout;
        private final List<String> failures = Collections.synchronizedList(new ArrayList<>());

        public WebhookSink(URI endpoint, HttpClient http, Duration timeout) {
            this.endpoint = Objects.requireNonNull(endpoint, "endpoint");
            this.http = http;
            this.timeout = timeout;
        }

        @Override
        public void deliver(Alert alert) {
            try {
                HttpRequest request = HttpRequest.newBuilder(endpoint)
                        .timeout(timeout)
                        .header("content-type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(alert.toJson(), StandardCharsets.UTF_8))
                        .build();
                HttpResponse<Void> response = http.send(request, HttpResponse.BodyHandlers.discarding());
                if (response.statusCode() >= 300) {
                    failures.add(alert.ruleId() + " -> " + response.statusCode());
                }
            } catch (java.io.IOException error) {
                failures.add(alert.ruleId() + " -> " + error.getClass().getSimpleName());
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                failures.add(alert.ruleId() + " -> interrupted");
            }
        }

        @Override
        public List<String> failures() {
            synchronized (failures) {
                return List.copyOf(failures);
            }
        }
    }

    /** The five built-in rules plus telemetry health. */
    public static List<Rule> defaultRules() {
        return List.of(new PoisoningRule(), new QuarantinedNodeRule(), new DurabilityBacklogRule(),
                new HitRateRule(), new ReconciliationDriftRule(), new TelemetryHealthRule());
    }

    static final class PoisoningRule implements Rule {
        @Override
        public String id() {
            return "CAS_POISONING_DETECTED";
        }

        @Override
        public List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long now) {
            if (snapshot.corruptionEventsInWindow() == 0) {
                return List.of();
            }
            return List.of(new Alert(id(), "global", Severity.PAGE,
                    "Content-addressed object failed verification",
                    snapshot.corruptionEventsInWindow() + " corruption events in the evaluation window. "
                            + "Poisoned content may already be inside a customer build.",
                    Map.of("events", Long.toString(snapshot.corruptionEventsInWindow())), now, 0));
        }
    }

    static final class QuarantinedNodeRule implements Rule {
        @Override
        public String id() {
            return "CAS_NODE_QUARANTINED";
        }

        @Override
        public List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long now) {
            List<Alert> alerts = new ArrayList<>();
            for (String node : snapshot.quarantinedNodes()) {
                // One alert per node, not one per affected entry: a node that produced 4000 bad
                // results is one incident.
                alerts.add(new Alert(id(), node, Severity.CRITICAL,
                        "Cache node quarantined",
                        "Node " + node + " produced a result that failed sampled recomputation; "
                                + "its entries were invalidated and further writes are refused.",
                        Map.of("node", node), now, 0));
            }
            return alerts;
        }
    }

    static final class DurabilityBacklogRule implements Rule {
        @Override
        public String id() {
            return "CAS_DURABILITY_BACKLOG";
        }

        @Override
        public List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long now) {
            boolean tooMany = snapshot.pendingDurabilityObjects() > thresholds.durabilityBacklogObjects();
            boolean tooOld = snapshot.oldestPendingDurabilityAgeMillis() > thresholds.durabilityBacklogAgeMillis();
            if (!tooMany && !tooOld) {
                return List.of();
            }
            // Age is the dangerous half: a large backlog that drains is throughput, a stale one is
            // data that exists on exactly one reclaimable disk.
            Severity severity = tooOld ? Severity.PAGE : Severity.WARNING;
            return List.of(new Alert(id(), "global", severity,
                    "Objects are not reaching durable storage",
                    snapshot.pendingDurabilityObjects() + " objects (" + snapshot.pendingDurabilityBytes()
                            + " bytes) exist only in the local tier; oldest has waited "
                            + snapshot.oldestPendingDurabilityAgeMillis() + " ms.",
                    Map.of("objects", Integer.toString(snapshot.pendingDurabilityObjects()),
                            "bytes", Long.toString(snapshot.pendingDurabilityBytes()),
                            "oldest_age_ms", Long.toString(snapshot.oldestPendingDurabilityAgeMillis())),
                    now, 0));
        }
    }

    static final class HitRateRule implements Rule {
        @Override
        public String id() {
            return "CAS_HIT_RATE_COLLAPSE";
        }

        @Override
        public List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long now) {
            if (snapshot.actionCacheLookups() < thresholds.minimumLookupsBeforeHitRateAlerts()) {
                // Without a minimum sample every cold start pages somebody.
                return List.of();
            }
            if (snapshot.actionCacheHitRate() >= thresholds.minimumHitRate()) {
                return List.of();
            }
            return List.of(new Alert(id(), "global", Severity.WARNING,
                    "Action cache hit rate below target",
                    String.format("Hit rate %.4f over %d lookups, below %.2f. Expect an input that changes "
                                    + "every run to be in the action key.",
                            snapshot.actionCacheHitRate(), snapshot.actionCacheLookups(),
                            thresholds.minimumHitRate()),
                    Map.of("hit_rate", String.format("%.4f", snapshot.actionCacheHitRate()),
                            "lookups", Long.toString(snapshot.actionCacheLookups())), now, 0));
        }
    }

    static final class ReconciliationDriftRule implements Rule {
        @Override
        public String id() {
            return "CAS_RECONCILIATION_DRIFT";
        }

        @Override
        public List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long now) {
            List<Alert> alerts = new ArrayList<>();
            if (snapshot.missingReferencedObjects() > 0) {
                alerts.add(new Alert(id(), "missing-objects", Severity.CRITICAL,
                        "Referenced objects are absent from storage",
                        snapshot.missingReferencedObjects() + " objects are referenced by a snapshot, "
                                + "evidence pack or cached result but are not in any tier.",
                        Map.of("missing", Integer.toString(snapshot.missingReferencedObjects())), now, 0));
            }
            if (snapshot.orphanedBytes() > thresholds.orphanedBytesWarning()) {
                alerts.add(new Alert(id(), "orphans", Severity.INFO,
                        "Unreferenced objects are accumulating",
                        snapshot.orphanedBytes() + " bytes are unreferenced beyond the minimum age.",
                        Map.of("orphaned_bytes", Long.toString(snapshot.orphanedBytes())), now, 0));
            }
            if (snapshot.incompleteUploadSessions() > thresholds.incompleteUploadSessionsWarning()) {
                alerts.add(new Alert(id(), "incomplete-uploads", Severity.WARNING,
                        "Upload sessions are not completing",
                        snapshot.incompleteUploadSessions() + " sessions passed their deadline unfinished.",
                        Map.of("sessions", Integer.toString(snapshot.incompleteUploadSessions())), now, 0));
            }
            if (snapshot.outstandingReplications() > thresholds.outstandingReplicationsWarning()) {
                alerts.add(new Alert(id(), "replication", Severity.WARNING,
                        "Regional replication is falling behind",
                        snapshot.outstandingReplications() + " objects await replication to their declared "
                                + "replica regions.",
                        Map.of("outstanding", Integer.toString(snapshot.outstandingReplications())), now, 0));
            }
            return alerts;
        }
    }

    static final class TelemetryHealthRule implements Rule {
        @Override
        public String id() {
            return "CAS_TELEMETRY_EXPORT_FAILING";
        }

        @Override
        public List<Alert> evaluate(HealthSnapshot snapshot, Thresholds thresholds, long now) {
            if (snapshot.telemetryExportFailures() < thresholds.telemetryFailuresWarning()) {
                return List.of();
            }
            return List.of(new Alert(id(), "global", Severity.WARNING,
                    "Telemetry export is failing",
                    snapshot.telemetryExportFailures() + " consecutive OTLP export failures; the other "
                            + "rules are evaluating against data the collector never received.",
                    Map.of("failures", Integer.toString(snapshot.telemetryExportFailures())), now, 0));
        }
    }

    /** Evaluates rules, throttles duplicates, and fans out to sinks. */
    public static final class Evaluator {

        private final List<Rule> rules;
        private final Thresholds thresholds;
        private final long throttleWindowMillis;
        private final List<Sink> sinks;
        private final Map<String, Long> lastFiredAt = new LinkedHashMap<>();
        private final Map<String, Long> suppressedSince = new LinkedHashMap<>();

        public Evaluator(List<Rule> rules, Thresholds thresholds, long throttleWindowMillis, List<Sink> sinks) {
            CasText.requireNonEmpty(rules, "rules");
            this.rules = List.copyOf(rules);
            this.thresholds = thresholds;
            CasText.requirePositive(throttleWindowMillis, "throttleWindowMillis");
            this.throttleWindowMillis = throttleWindowMillis;
            this.sinks = List.copyOf(sinks);
        }

        public static Evaluator standard(List<Sink> sinks) {
            return new Evaluator(defaultRules(), Thresholds.standard(), 15 * 60 * 1000L, sinks);
        }

        public List<Alert> evaluate(HealthSnapshot snapshot, long nowEpochMillis) {
            List<Alert> fired = new ArrayList<>();
            for (Rule rule : rules) {
                for (Alert alert : rule.evaluate(snapshot, thresholds, nowEpochMillis)) {
                    String throttleKey = alert.ruleId() + '/' + alert.key();
                    Long previous = lastFiredAt.get(throttleKey);
                    if (previous != null && nowEpochMillis - previous < throttleWindowMillis) {
                        suppressedSince.merge(throttleKey, 1L, Long::sum);
                        continue;
                    }
                    Alert toDeliver = alert.withSuppressed(suppressedSince.getOrDefault(throttleKey, 0L));
                    lastFiredAt.put(throttleKey, nowEpochMillis);
                    suppressedSince.remove(throttleKey);
                    sinks.forEach(sink -> sink.deliver(toDeliver));
                    fired.add(toDeliver);
                }
            }
            return List.copyOf(fired);
        }

        public Map<String, Long> currentlySuppressed() {
            return Collections.unmodifiableMap(new LinkedHashMap<>(suppressedSince));
        }

        public Optional<Long> lastFiredAt(String ruleId, String key) {
            return Optional.ofNullable(lastFiredAt.get(ruleId + '/' + key));
        }
    }
}
