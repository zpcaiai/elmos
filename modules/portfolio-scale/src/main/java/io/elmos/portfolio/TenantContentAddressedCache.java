package io.elmos.portfolio;

import io.elmos.cas.CasCatalog;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasExceptions;
import io.elmos.cas.CasGarbageCollector;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.CasStore;
import io.elmos.cas.InMemoryCasCatalog;
import io.elmos.cas.InMemoryCasStore;
import io.elmos.cas.TieredCasStore;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.function.LongSupplier;

import static io.elmos.portfolio.PortfolioScaleModels.requireText;

/**
 * Portfolio-facing view of the content-addressed cache.
 *
 * <p>This used to be a {@code HashMap<String, byte[]>} with a cache key built by
 * {@code String.join("\0", ...)}. It now delegates to {@code modules/cas}, which changes three
 * things that mattered:
 *
 * <ul>
 *   <li><b>The key is length-prefixed.</b> Joining seven attacker-influenceable digests with a
 *       separator lets any one of them spell that separator and collapse two different input sets
 *       onto one key.</li>
 *   <li><b>Storage verifies on read.</b> The old class recomputed the digest in {@code get} but
 *       kept the poisoned bytes; the store quarantines them and refuses to serve them again.</li>
 *   <li><b>The object tier and index are replaceable.</b> A {@link TieredCasStore} can share
 *       immutable artifact bytes. The key-to-digest index is an {@link CasCatalog}
 *       {@link CasGarbageCollector.RootKind#ACTION_CACHE ACTION_CACHE} root, so a shared JDBC
 *       catalogue supplies tenant-RLS-scoped, cross-instance lookup and also protects a live
 *       cache result from collection.</li>
 * </ul>
 *
 * <p>The compatibility constructors deliberately retain an in-memory catalogue and a local-only
 * metadata policy. Production wiring must call
 * {@link #TenantContentAddressedCache(CasStore, CasCatalog, ArtifactPolicy)} with a shared object
 * store, shared durable catalogue and deployment-owned data policy. Supplying only a shared object
 * store does not create cross-instance hits and must retain the repository's
 * {@code SINGLE_HOST / NOT_CERTIFIED} posture.
 */
public final class TenantContentAddressedCache {

    private static final String ROOT_ID_PREFIX = "portfolio-cache-v1:";

    /** Mutable deployment policy kept outside the content identity. */
    public record ArtifactPolicy(
            String dataResidency,
            io.elmos.cas.CasAccessPolicy.SecurityTier securityTier,
            CasObjectModel.RetentionClass retentionClass
    ) {
        public ArtifactPolicy {
            requireText(dataResidency, "artifact data residency");
            Objects.requireNonNull(securityTier, "securityTier");
            Objects.requireNonNull(retentionClass, "retentionClass");
        }

        static ArtifactPolicy localOnly() {
            return new ArtifactPolicy(
                    "local",
                    io.elmos.cas.CasAccessPolicy.SecurityTier.INTERNAL,
                    CasObjectModel.RetentionClass.STANDARD);
        }
    }

    public record InputManifest(String sourceDigest, String dependencyDigest, String toolchainDigest,
                                String profileDigest, String policyDigest, String environmentDigest,
                                String generatorDigest) {
        public InputManifest {
            requireText(sourceDigest, "source digest");
            requireText(dependencyDigest, "dependency digest");
            requireText(toolchainDigest, "toolchain digest");
            requireText(profileDigest, "profile digest");
            requireText(policyDigest, "policy digest");
            requireText(environmentDigest, "environment digest");
            requireText(generatorDigest, "generator digest");
        }

        List<String> fields() {
            return List.of(sourceDigest, dependencyDigest, toolchainDigest, profileDigest,
                    policyDigest, environmentDigest, generatorDigest);
        }
    }

    public record ArtifactRef(String tenantId, String trustDomain, String cacheKey, String artifactDigest,
                              int sizeBytes, long generation) {

        /** Compatibility marker for references created before lifecycle generations existed. */
        public static final long UNKNOWN_GENERATION = -1L;

        /**
         * Compatibility constructor. An old reference may still be read, but it cannot authorize
         * lifecycle mutation because it cannot distinguish an old root from a rebuilt root.
         */
        public ArtifactRef(String tenantId, String trustDomain, String cacheKey,
                           String artifactDigest, int sizeBytes) {
            this(tenantId, trustDomain, cacheKey, artifactDigest, sizeBytes, UNKNOWN_GENERATION);
        }

        public ArtifactRef {
            requireText(tenantId, "artifact tenant");
            requireText(trustDomain, "artifact trust domain");
            if (cacheKey == null || !cacheKey.matches("[0-9a-f]{64}")) {
                throw new IllegalArgumentException("artifact cache key must be a sha256 hex digest");
            }
            if (artifactDigest == null || !artifactDigest.matches("sha256:[0-9a-f]{64}")) {
                throw new IllegalArgumentException("artifact digest must use canonical sha256 form");
            }
            if (sizeBytes < 0) {
                throw new IllegalArgumentException("artifact size must not be negative");
            }
            // A missing primitive field is commonly decoded as zero by record serializers. Zero
            // is therefore conservatively treated as the legacy/unknown value. A catalogue root
            // genuinely created at epoch zero stays readable but cannot authorize invalidation.
            if (generation == 0) {
                generation = UNKNOWN_GENERATION;
            }
            if (generation < UNKNOWN_GENERATION) {
                throw new IllegalArgumentException("artifact generation must be known or explicitly unknown");
            }
        }

        public boolean hasKnownGeneration() {
            return generation >= 0;
        }
    }

    /** A durable-index lookup result with a generation-bound reference and verified bytes. */
    public record CacheHit(ArtifactRef ref, byte[] bytes) {
        public CacheHit {
            Objects.requireNonNull(ref, "ref");
            Objects.requireNonNull(bytes, "bytes");
            bytes = bytes.clone();
            if (bytes.length != ref.sizeBytes() || !digest(bytes).equals(ref.artifactDigest())) {
                throw new IllegalArgumentException("cache hit bytes do not match the artifact reference");
            }
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    private final CasStore store;
    private final CasCatalog catalog;
    private final ArtifactPolicy policy;
    private final LongSupplier clock;

    /**
     * Local compatibility constructor. It is not a durable or cross-instance configuration.
     *
     * @deprecated production wiring must inject a shared {@link CasCatalog}
     */
    @Deprecated(forRemoval = false)
    public TenantContentAddressedCache() {
        this(new InMemoryCasStore("portfolio-cache"), new InMemoryCasCatalog(),
                ArtifactPolicy.localOnly());
    }

    /**
     * Local compatibility constructor. A shared store alone is not a shared cache index.
     *
     * @deprecated production wiring must inject the store and a shared {@link CasCatalog}
     */
    @Deprecated(forRemoval = false)
    public TenantContentAddressedCache(CasStore store) {
        this(store, new InMemoryCasCatalog(), ArtifactPolicy.localOnly());
    }

    /**
     * Local compatibility constructor. A durable catalogue also needs an explicit deployment
     * policy before it is production-shaped.
     *
     * @deprecated production wiring must inject an explicit {@link ArtifactPolicy}
     */
    @Deprecated(forRemoval = false)
    public TenantContentAddressedCache(CasStore store, CasCatalog catalog) {
        this(store, catalog, ArtifactPolicy.localOnly());
    }

    /**
     * Production-shaped constructor. Cross-instance use requires the store and catalogue to be
     * shared and the policy to be sourced from trusted deployment configuration.
     */
    public TenantContentAddressedCache(
            CasStore store,
            CasCatalog catalog,
            ArtifactPolicy policy
    ) {
        this(store, catalog, policy, System::currentTimeMillis);
    }

    TenantContentAddressedCache(
            CasStore store,
            CasCatalog catalog,
            ArtifactPolicy policy,
            LongSupplier clock
    ) {
        this.store = Objects.requireNonNull(store, "store");
        this.catalog = Objects.requireNonNull(catalog, "catalog");
        this.policy = Objects.requireNonNull(policy, "policy");
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public ArtifactRef put(String tenantId, String trustDomain, InputManifest manifest, byte[] bytes,
                           String expectedArtifactDigest, boolean signatureVerified) {
        requireText(tenantId, "cache tenant");
        requireText(trustDomain, "cache trust domain");
        if (!signatureVerified) {
            throw new IllegalArgumentException("artifact signature is not verified");
        }
        Objects.requireNonNull(manifest, "manifest");
        Objects.requireNonNull(bytes, "bytes");
        CasDigest artifact = CasDigest.of(bytes);
        if (!digest(artifact).equals(expectedArtifactDigest)) {
            throw new IllegalArgumentException("artifact digest mismatch");
        }
        String cacheKey = cacheKey(tenantId, trustDomain, manifest);
        String rootId = rootId(tenantId, trustDomain, cacheKey);
        Optional<IndexedArtifact> active = findIndexedArtifact(tenantId, rootId);
        if (active.isPresent() && !active.orElseThrow().digest().equals(artifact)) {
            throw new IllegalStateException(
                    "active cache key must be explicitly invalidated before rebinding");
        }
        long createdAt = now();
        CasCatalog.CatalogEntry entry = new CasCatalog.CatalogEntry(
                tenantId,
                artifact,
                CasObjectModel.ObjectKind.ACTION_RESULT,
                "application/vnd.elmos.portfolio-cache-artifact",
                "portfolio-scale",
                "1",
                CasObjectModel.Sensitivity.GENERATED_OUTPUT,
                policy.retentionClass(),
                policy.dataResidency(),
                policy.securityTier(),
                Optional.empty(),
                Map.of("producer", "portfolio-scale"),
                false,
                createdAt);
        CasCatalog.ReferenceRoot root = new CasCatalog.ReferenceRoot(
                tenantId,
                CasGarbageCollector.RootKind.ACTION_CACHE,
                rootId,
                artifact,
                createdAt);
        // Catalogue metadata and the GC reference are one publication boundary. Publishing them
        // separately lets a concurrent collector observe an unrooted durable object.
        long generation = catalog.recordAndPublishDurableReferenceRoots(
                entry, List.of(root), () -> store.putDurable(artifact, bytes));
        return new ArtifactRef(
                tenantId, trustDomain, cacheKey, digest(artifact), bytes.length, generation);
    }

    /**
     * Resolves the complete input identity through the durable ACTION_CACHE root. Callers do not
     * need a process-local or writer-supplied reference; the returned reference is reconstructed
     * from the catalogue's active generation and is suitable for generation-bound invalidation.
     */
    public Optional<CacheHit> lookup(
            String tenantId,
            String trustDomain,
            InputManifest manifest
    ) {
        requireText(tenantId, "cache tenant");
        requireText(trustDomain, "cache trust domain");
        Objects.requireNonNull(manifest, "manifest");
        String cacheKey = cacheKey(tenantId, trustDomain, manifest);
        String rootId = rootId(tenantId, trustDomain, cacheKey);
        Optional<IndexedArtifact> indexed = findIndexedArtifact(tenantId, rootId);
        if (indexed.isEmpty()) {
            return Optional.empty();
        }
        IndexedArtifact mapping = indexed.orElseThrow();
        int sizeBytes;
        try {
            sizeBytes = Math.toIntExact(mapping.digest().sizeBytes());
        } catch (ArithmeticException oversized) {
            throw new IllegalStateException("cached artifact is too large for this API", oversized);
        }
        ArtifactRef ref = new ArtifactRef(
                tenantId,
                trustDomain,
                cacheKey,
                digest(mapping.digest()),
                sizeBytes,
                mapping.generation());
        return readMapped(tenantId, trustDomain, ref, rootId, mapping)
                .map(bytes -> new CacheHit(ref, bytes));
    }

    public Optional<byte[]> get(String tenantId, String trustDomain, ArtifactRef ref) {
        requireText(tenantId, "cache tenant");
        requireText(trustDomain, "cache trust domain");
        Objects.requireNonNull(ref, "ref");
        if (!ref.tenantId().equals(tenantId) || !ref.trustDomain().equals(trustDomain)) {
            return Optional.empty();
        }
        String rootId = rootId(tenantId, trustDomain, ref.cacheKey());
        Optional<IndexedArtifact> indexed = findIndexedArtifact(tenantId, rootId);
        if (indexed.isEmpty()) {
            return Optional.empty();
        }
        return readMapped(tenantId, trustDomain, ref, rootId, indexed.orElseThrow());
    }

    /**
     * Releases exactly the generation named by {@code ref}. A delayed invalidation from an old
     * generation returns {@code false}; the catalogue's generation guard prevents it from
     * releasing a newer rebuild. Compatibility references with an unknown generation are never
     * accepted for lifecycle mutation.
     */
    public boolean invalidate(String tenantId, String trustDomain, ArtifactRef ref) {
        requireText(tenantId, "cache tenant");
        requireText(trustDomain, "cache trust domain");
        Objects.requireNonNull(ref, "ref");
        if (!ref.tenantId().equals(tenantId) || !ref.trustDomain().equals(trustDomain)) {
            return false;
        }
        if (!ref.hasKnownGeneration()) {
            throw new IllegalArgumentException(
                    "an artifact reference with unknown generation cannot invalidate a root");
        }
        String rootId = rootId(tenantId, trustDomain, ref.cacheKey());
        Optional<IndexedArtifact> indexed = findIndexedArtifact(tenantId, rootId);
        if (indexed.isEmpty() || !matches(ref, indexed.orElseThrow(), true)) {
            return false;
        }
        requireCatalogIdentity(tenantId, indexed.orElseThrow().digest());
        long releasedAt = Math.max(now(), ref.generation());
        return catalog.releaseReferenceRootGeneration(
                tenantId,
                CasGarbageCollector.RootKind.ACTION_CACHE,
                rootId,
                ref.generation(),
                releasedAt);
    }

    private Optional<byte[]> readMapped(
            String tenantId,
            String trustDomain,
            ArtifactRef ref,
            String rootId,
            IndexedArtifact indexed
    ) {
        if (!ref.tenantId().equals(tenantId) || !ref.trustDomain().equals(trustDomain)) {
            return Optional.empty();
        }
        CasDigest artifact = indexed.digest();
        if (!digest(artifact).equals(ref.artifactDigest())) {
            throw new IllegalStateException("cached artifact identity does not match the reference");
        }
        if (artifact.sizeBytes() != ref.sizeBytes()) {
            throw new IllegalStateException("cached artifact size does not match the reference");
        }
        if (ref.hasKnownGeneration() && ref.generation() != indexed.generation()) {
            return Optional.empty();
        }
        requireCatalogIdentity(tenantId, artifact);
        try {
            byte[] bytes = store.get(artifact);
            Optional<IndexedArtifact> current = findIndexedArtifact(tenantId, rootId);
            if (current.isEmpty() || !matches(ref, current.orElseThrow(), ref.hasKnownGeneration())) {
                return Optional.empty();
            }
            return Optional.of(bytes);
        } catch (CasExceptions.CasNotFoundException collected) {
            // One reader may lag the authoritative tier or see a transient outage. A local miss
            // therefore cannot revoke a global durable index entry. Explicit, generation-bound
            // reconciliation or invalidation owns lifecycle mutation.
            return Optional.empty();
        } catch (CasExceptions.CasCorruptionException poisoned) {
            // The store has already quarantined the bytes. Surfacing it keeps the historical
            // contract of this class, which callers treat as an unrecoverable cache fault.
            throw new IllegalStateException("cached artifact corruption detected", poisoned);
        }
    }

    private static boolean matches(
            ArtifactRef ref,
            IndexedArtifact indexed,
            boolean requireGeneration
    ) {
        return digest(indexed.digest()).equals(ref.artifactDigest())
                && indexed.digest().sizeBytes() == ref.sizeBytes()
                && (!requireGeneration || indexed.generation() == ref.generation());
    }

    /** Kept for source compatibility: callers pass the result straight back into {@link #put}. */
    public static String digest(byte[] bytes) {
        return "sha256:" + CasDigest.of(bytes).hex();
    }

    private static String digest(CasDigest digest) {
        return "sha256:" + digest.hex();
    }

    /**
     * Length-prefixed so no field can impersonate a separator. Two input sets that differ produce
     * two keys, whatever characters the digests contain.
     */
    private static String cacheKey(String tenantId, String trustDomain, InputManifest manifest) {
        StringBuilder canonical = new StringBuilder("elmos-portfolio-cache-key/1\n");
        for (String field : concat(tenantId, trustDomain, manifest.fields())) {
            byte[] encoded = field.getBytes(StandardCharsets.UTF_8);
            canonical.append(encoded.length).append(':').append(field).append('\n');
        }
        return CasDigest.ofUtf8(canonical.toString()).hex();
    }

    private static List<String> concat(String tenantId, String trustDomain, List<String> fields) {
        String[] all = new String[fields.size() + 2];
        all[0] = tenantId;
        all[1] = trustDomain;
        for (int index = 0; index < fields.size(); index++) {
            all[index + 2] = fields.get(index);
        }
        return Arrays.asList(all);
    }

    /**
     * The lookup identity is separately bound to the caller's tenant and trust domain. The cache
     * key already contains both, but hashing them again here prevents a caller from relabelling a
     * stolen {@link ArtifactRef} with another trust domain and addressing the original root.
     */
    private static String rootId(String tenantId, String trustDomain, String cacheKey) {
        StringBuilder canonical = new StringBuilder("elmos-portfolio-cache-index/1\n");
        for (String field : List.of(tenantId, trustDomain, cacheKey)) {
            byte[] encoded = field.getBytes(StandardCharsets.UTF_8);
            canonical.append(encoded.length).append(':').append(field).append('\n');
        }
        return ROOT_ID_PREFIX + CasDigest.ofUtf8(canonical.toString()).hex();
    }

    private Optional<IndexedArtifact> findIndexedArtifact(String tenantId, String rootId) {
        List<CasCatalog.ReferenceRoot> matches = catalog.activeReferenceRoots(
                tenantId, CasGarbageCollector.RootKind.ACTION_CACHE, rootId);
        if (matches.stream().anyMatch(root -> !root.tenantId().equals(tenantId)
                || root.kind() != CasGarbageCollector.RootKind.ACTION_CACHE
                || !root.rootId().equals(rootId))) {
            throw new IllegalStateException("durable cache index returned an out-of-scope root");
        }
        if (matches.size() > 1) {
            // A valid catalogue serializes publication of one digest per logical root. Multiple
            // active digests therefore mean tampered or legacy state and can never be a cache hit.
            throw new IllegalStateException("durable cache index contains an ambiguous mapping");
        }
        return matches.stream()
                .findFirst()
                .map(root -> new IndexedArtifact(root.digest(), root.createdAtEpochMillis()));
    }

    private void requireCatalogIdentity(String tenantId, CasDigest artifact) {
        CasCatalog.CatalogEntry entry = catalog.find(tenantId, artifact)
                .orElseThrow(() -> new IllegalStateException(
                        "durable cache index points at an uncatalogued object"));
        if (entry.kind() != CasObjectModel.ObjectKind.ACTION_RESULT
                || entry.sensitivity() != CasObjectModel.Sensitivity.GENERATED_OUTPUT
                || !entry.mediaType().equals("application/vnd.elmos.portfolio-cache-artifact")
                || !entry.sourceSystem().equals("portfolio-scale")
                || !entry.schemaVersion().equals("1")
                || !entry.dataResidency().equals(policy.dataResidency())
                || entry.securityTier() != policy.securityTier()
                || retentionStrength(entry.retentionClass())
                    < retentionStrength(policy.retentionClass())) {
            throw new SecurityException("cached artifact catalogue metadata conflicts with policy");
        }
    }

    private static int retentionStrength(CasObjectModel.RetentionClass retentionClass) {
        return switch (retentionClass) {
            case EPHEMERAL -> 0;
            case STANDARD -> 1;
            case EVIDENCE -> 2;
            case REGULATORY -> 3;
        };
    }

    private long now() {
        long now = clock.getAsLong();
        if (now < 0) {
            throw new IllegalStateException("cache clock returned a negative epoch");
        }
        return now;
    }

    private record IndexedArtifact(CasDigest digest, long generation) {}
}
