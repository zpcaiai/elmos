package io.elmos.cas;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.function.LongSupplier;

/**
 * ELMOS-CAS-024 through ELMOS-CAS-031. The action cache proper.
 *
 * <p>Everything here exists to make one guarantee: a hit is indistinguishable from having run the
 * action, for this caller, right now. That is stricter than "the inputs match". It also requires
 * that the caller is allowed to see the result, that the result was produced by an identity we
 * still trust, and that the result has not silently rotted.
 *
 * <p>Failure caching is opt-in and short lived. Caching a failure is caching the absence of an
 * output, and the most common failure in a build platform - a registry timeout, an evicted
 * runner, a full disk - has nothing to do with the inputs. Remembering those as results is how a
 * cache turns a five-minute incident into a day-long outage that survives the fix.
 */
public final class ActionCache {

    public enum CacheOutcome {
        HIT,
        MISS,
        BYPASS,
        STALE,
        DENIED,
        INVALIDATED
    }

    public enum RiskTier {
        STANDARD,
        HIGH
    }

    /** ELMOS-CAS-026. Writes require an authenticated, attested runner or service identity. */
    public record WriterIdentity(String serviceId, String trustDomain, String nodeId, boolean attested) {
        public WriterIdentity {
            serviceId = CasText.required(serviceId, "serviceId");
            trustDomain = CasText.required(trustDomain, "trustDomain");
            nodeId = CasText.required(nodeId, "nodeId");
        }
    }

    /**
     * ELMOS-CAS-027. A verification receipt bound to the exact signed subject.
     *
     * <p>There is deliberately no public constructor that accepts {@code verified=true}. External
     * callers may describe an unverified signature for rejection paths, but only
     * {@link ResultSignature.Verifier} and the package-local durable-index reader can reconstruct
     * a verified receipt. The envelope digest is recalculated from the complete entry both before
     * a write and after JDBC readback, so a receipt cannot be replayed over changed result,
     * authorization, risk or writer metadata.
     */
    public static final class ResultAttestation {
        private final String signerId;
        private final String algorithm;
        private final CasDigest signatureDigest;
        private final String envelopeVersion;
        private final CasDigest envelopeDigest;
        private final long signedAtEpochMillis;
        private final boolean verified;

        private ResultAttestation(String signerId, String algorithm, CasDigest signatureDigest,
                                  String envelopeVersion, CasDigest envelopeDigest,
                                  long signedAtEpochMillis,
                                  boolean verified) {
            this.signerId = CasText.required(signerId, "signerId");
            this.algorithm = CasText.required(algorithm, "algorithm");
            this.signatureDigest = Objects.requireNonNull(signatureDigest, "signatureDigest");
            this.envelopeVersion = CasText.required(envelopeVersion, "envelopeVersion");
            this.envelopeDigest = Objects.requireNonNull(envelopeDigest, "envelopeDigest");
            if (signedAtEpochMillis < 0) {
                throw new IllegalArgumentException("signedAtEpochMillis must not be negative");
            }
            this.signedAtEpochMillis = signedAtEpochMillis;
            this.verified = verified;
        }

        public static ResultAttestation unverified(String signerId, String algorithm,
                                                   CasDigest signatureDigest,
                                                   String envelopeVersion,
                                                   CasDigest envelopeDigest,
                                                   long signedAtEpochMillis) {
            return new ResultAttestation(signerId, algorithm, signatureDigest, envelopeVersion,
                    envelopeDigest,
                    signedAtEpochMillis, false);
        }

        static ResultAttestation verified(String signerId, String algorithm,
                                          CasDigest signatureDigest, String envelopeVersion,
                                          CasDigest envelopeDigest,
                                          long signedAtEpochMillis) {
            return new ResultAttestation(signerId, algorithm, signatureDigest, envelopeVersion,
                    envelopeDigest,
                    signedAtEpochMillis, true);
        }

        public String signerId() {
            return signerId;
        }

        public String algorithm() {
            return algorithm;
        }

        public CasDigest signatureDigest() {
            return signatureDigest;
        }

        public String envelopeVersion() {
            return envelopeVersion;
        }

        public CasDigest envelopeDigest() {
            return envelopeDigest;
        }

        public long signedAtEpochMillis() {
            return signedAtEpochMillis;
        }

        public boolean verified() {
            return verified;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ResultAttestation that)) {
                return false;
            }
            return signedAtEpochMillis == that.signedAtEpochMillis
                    && verified == that.verified
                    && signerId.equals(that.signerId)
                    && algorithm.equals(that.algorithm)
                    && signatureDigest.equals(that.signatureDigest)
                    && envelopeVersion.equals(that.envelopeVersion)
                    && envelopeDigest.equals(that.envelopeDigest);
        }

        @Override
        public int hashCode() {
            return Objects.hash(signerId, algorithm, signatureDigest, envelopeVersion, envelopeDigest,
                    signedAtEpochMillis, verified);
        }

        @Override
        public String toString() {
            return "ResultAttestation[signerId=" + signerId
                    + ", algorithm=" + algorithm
                    + ", signatureDigest=" + signatureDigest
                    + ", envelopeVersion=" + envelopeVersion
                    + ", envelopeDigest=" + envelopeDigest
                    + ", signedAtEpochMillis=" + signedAtEpochMillis
                    + ", verified=" + verified + "]";
        }
    }

    public record FailureCachePolicy(Set<ActionResultRecord.FailureClass> cacheable, long ttlMillis) {
        public FailureCachePolicy {
            cacheable = Set.copyOf(cacheable);
            if (!cacheable.isEmpty() && ttlMillis <= 0) {
                throw new IllegalArgumentException(
                        "cacheable failures require a strictly positive ttlMillis");
            }
            for (ActionResultRecord.FailureClass failureClass : cacheable) {
                if (!failureClass.deterministicGivenInputs()) {
                    throw new IllegalArgumentException(failureClass
                            + " is not deterministic given the inputs and must never be cached as a result");
                }
            }
        }

        /** Nothing is remembered as a failure unless the deployment explicitly opts in. */
        public static FailureCachePolicy none() {
            return new FailureCachePolicy(Set.of(), 0);
        }

        public static FailureCachePolicy deterministicOnly(long ttlMillis) {
            return new FailureCachePolicy(Set.of(ActionResultRecord.FailureClass.CODE,
                    ActionResultRecord.FailureClass.POLICY, ActionResultRecord.FailureClass.SECURITY), ttlMillis);
        }
    }

    /**
     * ELMOS-CAS-030. A fraction of hits are re-executed and compared. Sampling is deterministic in
     * the key so that the same action is sampled on every runner - a randomly sampled cache makes
     * a nondeterminism report irreproducible, which is the one thing it must not be.
     */
    public record SampleRecomputePolicy(int oneInN) {
        public SampleRecomputePolicy {
            if (oneInN < 0) {
                throw new IllegalArgumentException("oneInN must not be negative");
            }
        }

        public static SampleRecomputePolicy disabled() {
            return new SampleRecomputePolicy(0);
        }

        boolean samples(ActionKey key) {
            if (oneInN == 0) {
                return false;
            }
            long bucket = Long.parseUnsignedLong(key.digest().hex().substring(0, 8), 16);
            return bucket % oneInN == 0;
        }
    }

    public record RecomputeRequest(ActionKey key, CasDigest expectedOutputManifestDigest, String reason) {
    }

    public record Lookup(CacheOutcome outcome,
                         String reason,
                         Optional<ActionResultRecord> result,
                         Optional<RecomputeRequest> recompute) {

        public static Lookup miss(String reason) {
            return new Lookup(CacheOutcome.MISS, reason, Optional.empty(), Optional.empty());
        }

        public static Lookup denied(String reason) {
            return new Lookup(CacheOutcome.DENIED, reason, Optional.empty(), Optional.empty());
        }
    }

    public record Entry(ActionKey key,
                        ActionResultRecord result,
                        CasAccessPolicy.ProducerContext producer,
                        WriterIdentity writer,
                        Optional<ResultAttestation> attestation,
                        RiskTier riskTier,
                        long storedAtEpochMillis,
                        Optional<Long> expiresAtEpochMillis) {
        public Entry {
            Objects.requireNonNull(key, "key");
            Objects.requireNonNull(result, "result");
            Objects.requireNonNull(producer, "producer");
            Objects.requireNonNull(writer, "writer");
            Objects.requireNonNull(attestation, "attestation");
            Objects.requireNonNull(riskTier, "riskTier");
            Objects.requireNonNull(expiresAtEpochMillis, "expiresAtEpochMillis");
            if (!key.tenantId().equals(producer.tenantId())) {
                throw new IllegalArgumentException("action entry tenant does not match producer");
            }
            if (!writer.attested()) {
                throw new IllegalArgumentException("durable action entry requires an attested writer");
            }
            if (attestation.filter(ResultAttestation::verified).isEmpty()
                    && attestation.isPresent()) {
                throw new IllegalArgumentException("unverified result attestation cannot be persisted");
            }
            if (attestation.filter(receipt -> ResultSignature.binds(
                    receipt, key, result, producer, writer, riskTier)).isEmpty()
                    && attestation.isPresent()) {
                throw new IllegalArgumentException(
                        "result attestation does not bind the complete action entry");
            }
            if (riskTier == RiskTier.HIGH
                    && attestation.filter(ResultAttestation::verified).isEmpty()) {
                throw new IllegalArgumentException(
                        "high-risk action entry requires a verified result attestation");
            }
            if (storedAtEpochMillis < 0) {
                throw new IllegalArgumentException("storedAtEpochMillis must not be negative");
            }
            if (expiresAtEpochMillis.filter(expiry -> expiry <= storedAtEpochMillis).isPresent()) {
                throw new IllegalArgumentException("action entry expiry must follow storage time");
            }
        }
    }

    public record Invalidation(CasDigest keyDigest, String reason, long atEpochMillis) {
    }

    private final TenantCasStore store;
    private final CasAccessPolicy accessPolicy;
    private final FailureCachePolicy failurePolicy;
    private final SampleRecomputePolicy samplePolicy;
    private final LongSupplier clock;
    private final CasMetrics metrics;
    private final CasTelemetry telemetry;
    private final ActionCacheIndex index;

    /** Compatibility-only process view; durable lookups always use {@link #index}. */
    private final Map<CasDigest, Entry> processEntries = new java.util.concurrent.ConcurrentHashMap<>();
    private final Set<String> quarantinedNodes = Collections.synchronizedSet(new LinkedHashSet<>());
    private final List<Invalidation> invalidations = Collections.synchronizedList(new ArrayList<>());
    private final List<String> nondeterminismIncidents = Collections.synchronizedList(new ArrayList<>());

    public ActionCache(CasStore store, CasAccessPolicy accessPolicy, FailureCachePolicy failurePolicy,
                       SampleRecomputePolicy samplePolicy, LongSupplier clock, CasMetrics metrics) {
        this(store, accessPolicy, failurePolicy, samplePolicy, clock, metrics,
                new InMemoryActionCacheIndex(), CasTelemetry.noop());
    }

    /** ELMOS-CAS-039. Same cache, with OpenTelemetry spans and instruments attached. */
    public ActionCache(CasStore store, CasAccessPolicy accessPolicy, FailureCachePolicy failurePolicy,
                       SampleRecomputePolicy samplePolicy, LongSupplier clock, CasMetrics metrics,
                       CasTelemetry telemetry) {
        this(store, accessPolicy, failurePolicy, samplePolicy, clock, metrics,
                new InMemoryActionCacheIndex(), telemetry);
    }

    /** Production constructor. Multiple cache instances sharing {@code index} observe the same entries. */
    public ActionCache(CasStore store, CasAccessPolicy accessPolicy, FailureCachePolicy failurePolicy,
                       SampleRecomputePolicy samplePolicy, LongSupplier clock, CasMetrics metrics,
                       ActionCacheIndex index, CasTelemetry telemetry) {
        this(TenantCasStore.global(store), accessPolicy, failurePolicy, samplePolicy, clock, metrics,
                index, telemetry);
    }

    public ActionCache(TenantCasStore store, CasAccessPolicy accessPolicy,
                       FailureCachePolicy failurePolicy, SampleRecomputePolicy samplePolicy,
                       LongSupplier clock, CasMetrics metrics, ActionCacheIndex index,
                       CasTelemetry telemetry) {
        this.store = Objects.requireNonNull(store, "store");
        this.accessPolicy = accessPolicy;
        this.failurePolicy = failurePolicy;
        this.samplePolicy = samplePolicy;
        this.clock = clock;
        this.metrics = metrics;
        this.index = Objects.requireNonNull(index, "index");
        this.telemetry = Objects.requireNonNull(telemetry, "telemetry");
    }

    /**
     * @throws CasExceptions.CasAccessDeniedException when the writer is unattested, quarantined, or
     *                                                a high-risk result arrives without a verified
     *                                                attestation
     */
    public Optional<Entry> put(ActionKey key, ActionResultRecord result, CasAccessPolicy.ProducerContext producer,
                               WriterIdentity writer, RiskTier riskTier, Optional<ResultAttestation> attestation) {
        if (!writer.attested()) {
            throw new CasExceptions.CasAccessDeniedException("WRITER_NOT_ATTESTED", writer.serviceId());
        }
        if (attestation.isPresent() && attestation.filter(ResultAttestation::verified).isEmpty()) {
            throw new CasExceptions.CasAccessDeniedException(
                    "RESULT_ATTESTATION_UNVERIFIED", attestation.orElseThrow().signerId());
        }
        if (attestation.filter(receipt -> ResultSignature.binds(
                receipt, key, result, producer, writer, riskTier)).isEmpty()
                && attestation.isPresent()) {
            throw new CasExceptions.CasAccessDeniedException(
                    "RESULT_ATTESTATION_SUBJECT_MISMATCH", key.shortForm());
        }
        if (quarantinedNodes.contains(writer.nodeId())
                || index.isNodeQuarantined(key.tenantId(), writer.nodeId())) {
            throw new CasExceptions.CasAccessDeniedException("WRITER_NODE_QUARANTINED", writer.nodeId());
        }
        if (riskTier == RiskTier.HIGH && attestation.filter(ResultAttestation::verified).isEmpty()) {
            throw new CasExceptions.CasAccessDeniedException("HIGH_RISK_RESULT_UNSIGNED", key.shortForm());
        }
        if (!producer.tenantId().equals(key.tenantId())) {
            throw new CasExceptions.CasAccessDeniedException("PRODUCER_TENANT_MISMATCH",
                    producer.tenantId() + " != " + key.tenantId());
        }
        CasStore tenantOutputStore = store.forTenant(key.tenantId());
        if (!tenantOutputStore.contains(result.outputManifestDigest())) {
            // Storing a pointer to an object that is not durable yet creates an entry that hits and
            // then fails to materialise, which is worse than a miss.
            throw new CasExceptions.CasNotFoundException(result.outputManifestDigest());
        }
        // contains() is only an existence/size probe. Verify the immutable manifest before a
        // durable index entry is allowed to point at it.
        tenantOutputStore.get(result.outputManifestDigest());
        long storedAt = clock.getAsLong();
        Optional<Long> expiry = Optional.empty();
        if (result.status() == ActionResultRecord.Status.FAILED) {
            ActionResultRecord.FailureClass failureClass = result.failureClass().orElseThrow();
            if (!failurePolicy.cacheable().contains(failureClass)) {
                metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.BYPASS, "FAILURE_NOT_CACHEABLE:" + failureClass);
                return Optional.empty();
            }
            try {
                expiry = Optional.of(Math.addExact(storedAt, failurePolicy.ttlMillis()));
            } catch (ArithmeticException overflow) {
                throw new IllegalArgumentException("failure-cache expiry exceeds epoch range", overflow);
            }
        } else if (!result.reusable()) {
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.BYPASS, "RESULT_NOT_REUSABLE:" + result.status());
            return Optional.empty();
        }
        Entry entry = new Entry(key, result, producer, writer, attestation, riskTier, storedAt, expiry);
        index.store(entry);
        processEntries.putIfAbsent(key.digest(), entry);
        try (CasTelemetry.Span span = telemetry.startSpan("cas.action_cache.store",
                CasTelemetry.SpanKind.INTERNAL, Optional.empty())) {
            span.attribute("cas.action_key", key.shortForm());
            span.attribute("elmos.tenant_id", key.tenantId());
            span.attribute("cas.risk_tier", riskTier.name());
            span.attribute("cas.result_status", result.status().name());
            span.attribute("cas.output_manifest", result.outputManifestDigest().compact());
            span.status(CasTelemetry.SpanStatus.OK, "stored");
        }
        telemetry.counter("cas.action_cache.stores", "1", 1,
                Map.of("tenant", key.tenantId(), "status", result.status().name()));
        return Optional.of(entry);
    }

    public Lookup get(ActionKey key, CasAccessPolicy.ReaderContext reader, boolean bypassRequested) {
        try (CasTelemetry.Span span = telemetry.startSpan("cas.action_cache.lookup",
                CasTelemetry.SpanKind.INTERNAL, Optional.empty())) {
            span.attribute("cas.action_key", key.shortForm());
            span.attribute("elmos.tenant_id", reader.tenantId());
            span.attribute("cas.bypass_requested", Boolean.toString(bypassRequested));
            Lookup lookup = lookup(key, reader, bypassRequested);
            span.attribute("cas.outcome", lookup.outcome().name());
            span.attribute("cas.reason", lookup.reason());
            span.status(lookup.outcome() == CacheOutcome.DENIED
                    ? CasTelemetry.SpanStatus.ERROR : CasTelemetry.SpanStatus.OK, lookup.reason());
            telemetry.counter("cas.action_cache.lookups", "1", 1,
                    Map.of("outcome", lookup.outcome().name(), "reason", lookup.reason(),
                            "tenant", reader.tenantId()));
            lookup.result().ifPresent(result -> telemetry.histogram("cas.action_cache.wall_seconds_avoided",
                    "s", Math.round(result.resourceUsage().wallSeconds()),
                    Map.of("tenant", reader.tenantId())));
            return lookup;
        }
    }

    private Lookup lookup(ActionKey key, CasAccessPolicy.ReaderContext reader, boolean bypassRequested) {
        if (bypassRequested) {
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.BYPASS, "CALLER_REQUESTED_BYPASS");
            return new Lookup(CacheOutcome.BYPASS, "CALLER_REQUESTED_BYPASS", Optional.empty(), Optional.empty());
        }
        Optional<Entry> indexed = index.find(key);
        if (indexed.isEmpty()) {
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.MISS, "NO_ENTRY");
            return Lookup.miss("NO_ENTRY");
        }
        Entry entry = indexed.orElseThrow();
        if (quarantinedNodes.contains(entry.writer().nodeId())
                || index.isNodeQuarantined(key.tenantId(), entry.writer().nodeId())) {
            index.invalidate(key, "PRODUCER_NODE_QUARANTINED", clock.getAsLong());
            processEntries.remove(key.digest());
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.INVALIDATED, "PRODUCER_NODE_QUARANTINED");
            return new Lookup(CacheOutcome.INVALIDATED, "PRODUCER_NODE_QUARANTINED", Optional.empty(), Optional.empty());
        }
        long now = clock.getAsLong();
        if (entry.expiresAtEpochMillis().filter(expiry -> now > expiry).isPresent()) {
            index.invalidate(key, "FAILURE_TTL_EXPIRED", now);
            processEntries.remove(key.digest());
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.STALE, "FAILURE_TTL_EXPIRED");
            return new Lookup(CacheOutcome.STALE, "FAILURE_TTL_EXPIRED", Optional.empty(), Optional.empty());
        }
        CasAccessPolicy.Decision decision = accessPolicy.evaluateRead(reader, entry.producer());
        if (!decision.allowed()) {
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.DENIED, decision.reason());
            return Lookup.denied(decision.reason());
        }
        CasStore tenantOutputStore = store.forTenant(entry.producer().tenantId());
        if (!tenantOutputStore.contains(entry.result().outputManifestDigest())) {
            // The output was collected out from under the entry. Report the real cause instead of
            // letting the caller discover it as a missing artifact three steps later.
            index.invalidate(key, "OUTPUT_MANIFEST_MISSING", now);
            processEntries.remove(key.digest());
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.INVALIDATED, "OUTPUT_MANIFEST_MISSING");
            return new Lookup(CacheOutcome.INVALIDATED, "OUTPUT_MANIFEST_MISSING", Optional.empty(), Optional.empty());
        }
        try {
            // A hit is not reusable until the manifest bytes themselves pass the store's digest
            // verification. This is intentionally stricter than a cheap contains() probe.
            tenantOutputStore.get(entry.result().outputManifestDigest());
        } catch (CasExceptions.CasNotFoundException collectedDuringRead) {
            index.invalidate(key, "OUTPUT_MANIFEST_MISSING", now);
            processEntries.remove(key.digest());
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.INVALIDATED,
                    "OUTPUT_MANIFEST_MISSING");
            return new Lookup(CacheOutcome.INVALIDATED, "OUTPUT_MANIFEST_MISSING",
                    Optional.empty(), Optional.empty());
        } catch (CasExceptions.CasCorruptionException poisoned) {
            index.invalidate(key, "OUTPUT_MANIFEST_CORRUPT", now);
            processEntries.remove(key.digest());
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.INVALIDATED,
                    "OUTPUT_MANIFEST_CORRUPT");
            return new Lookup(CacheOutcome.INVALIDATED, "OUTPUT_MANIFEST_CORRUPT",
                    Optional.empty(), Optional.empty());
        }
        Optional<RecomputeRequest> recompute = samplePolicy.samples(key)
                ? Optional.of(new RecomputeRequest(key, entry.result().outputManifestDigest(), "SAMPLED_VERIFICATION"))
                : Optional.empty();
        metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.HIT, "EXACT");
        metrics.recordSavings(entry.result().resourceUsage().wallSeconds(),
                entry.result().resourceUsage().readBytes() + entry.result().resourceUsage().writtenBytes(),
                entry.result().resourceUsage().cpuSeconds());
        return new Lookup(CacheOutcome.HIT, "EXACT", Optional.of(entry.result()), recompute);
    }

    /**
     * Reports the outcome of a sampled re-execution. A mismatch means either the cache was
     * poisoned or the action is nondeterministic; both make every entry from that node suspect,
     * so the node is quarantined (ELMOS-CAS-031) rather than just the one entry dropped.
     */
    public boolean confirmRecompute(ActionKey key, CasDigest observedOutputManifestDigest) {
        Optional<Entry> indexed = index.find(key);
        if (indexed.isEmpty()) {
            return true;
        }
        Entry entry = indexed.orElseThrow();
        if (entry.result().outputManifestDigest().equals(observedOutputManifestDigest)) {
            return true;
        }
        // Quarantine first. If the process dies between durable operations, every lookup already
        // refuses the node; invalidating one key first would leave its other outputs reusable
        // during that crash window.
        quarantineNode(key.tenantId(), entry.writer().nodeId(),
                "produced " + entry.result().outputManifestDigest().compact()
                + " but recompute produced " + observedOutputManifestDigest.compact());
        nondeterminismIncidents.add(key.shortForm() + ":" + entry.writer().nodeId());
        return false;
    }

    public void invalidate(ActionKey key, String reason) {
        if (index.invalidate(key, reason, clock.getAsLong())) {
            processEntries.remove(key.digest());
            invalidations.add(new Invalidation(key.digest(), reason, clock.getAsLong()));
            metrics.record(CasMetrics.Layer.ACTION, CacheOutcome.INVALIDATED, reason);
        }
    }

    /**
     * Process-local compatibility operation for the original single-tenant cache.
     *
     * @deprecated production callers must use the tenant-scoped overload; a node name is not a
     *             globally unique authorization identity.
     */
    @Deprecated(forRemoval = false)
    public int quarantineNode(String nodeId, String reason) {
        quarantinedNodes.add(CasText.required(nodeId, "nodeId"));
        String invalidationReason = quarantineInvalidationReason(reason);
        List<CasDigest> affected = processEntries.values().stream()
                .filter(entry -> entry.writer().nodeId().equals(nodeId))
                .map(entry -> entry.key().digest())
                .toList();
        affected.forEach(digest -> {
            Entry entry = processEntries.remove(digest);
            if (entry != null) {
                index.invalidate(entry.key(), invalidationReason, clock.getAsLong());
            }
            invalidations.add(new Invalidation(digest, invalidationReason, clock.getAsLong()));
        });
        return affected.size();
    }

    /** Durable tenant-scoped quarantine used by production callers and sampled recomputation. */
    public int quarantineNode(String tenantId, String nodeId, String reason) {
        String tenant = CasText.required(tenantId, "tenantId");
        String node = CasText.required(nodeId, "nodeId");
        String detail = CasText.required(reason, "reason");
        long now = clock.getAsLong();
        index.quarantineNode(tenant, node, detail, now);
        int affected = index.invalidateByWriter(
                tenant, node, quarantineInvalidationReason(detail), now);
        processEntries.entrySet().removeIf(item -> item.getValue().key().tenantId().equals(tenant)
                && item.getValue().writer().nodeId().equals(node));
        return affected;
    }

    public boolean isNodeQuarantined(String tenantId, String nodeId) {
        return index.isNodeQuarantined(CasText.required(tenantId, "tenantId"),
                CasText.required(nodeId, "nodeId"));
    }

    public Set<String> quarantinedNodes() {
        synchronized (quarantinedNodes) {
            return Set.copyOf(quarantinedNodes);
        }
    }

    public List<Invalidation> invalidations() {
        synchronized (invalidations) {
            return List.copyOf(invalidations);
        }
    }

    public List<String> nondeterminismIncidents() {
        synchronized (nondeterminismIncidents) {
            return List.copyOf(nondeterminismIncidents);
        }
    }

    /** Every object the cache currently keeps alive, for the collector's mark phase. */
    public Map<CasDigest, CasDigest> liveOutputManifests() {
        Map<CasDigest, CasDigest> live = new LinkedHashMap<>();
        processEntries.forEach((keyDigest, entry) -> live.put(keyDigest, entry.result().outputManifestDigest()));
        return Collections.unmodifiableMap(live);
    }

    /** Tenant-scoped durable view for the collector's mark phase. */
    public Map<CasDigest, CasDigest> liveOutputManifests(String tenantId) {
        return index.liveOutputManifests(CasText.required(tenantId, "tenantId"));
    }

    public int size() {
        return processEntries.size();
    }

    public int size(String tenantId) {
        return index.size(CasText.required(tenantId, "tenantId"));
    }

    private static String quarantineInvalidationReason(String detail) {
        String value = CasText.required(detail, "reason");
        return "NODE_QUARANTINED:" + CasDigest.ofUtf8(value).hex();
    }
}
