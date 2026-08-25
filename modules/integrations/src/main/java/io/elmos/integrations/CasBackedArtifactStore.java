package io.elmos.integrations;

import io.elmos.cas.CasAccessPolicy;
import io.elmos.cas.CasCatalog;
import io.elmos.cas.CasDigest;
import io.elmos.cas.CasExceptions;
import io.elmos.cas.CasGarbageCollector;
import io.elmos.cas.CasObjectModel;
import io.elmos.cas.CasStore;
import io.elmos.cas.TenantCasStore;
import io.elmos.snapshot.SnapshotPorts;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.function.LongSupplier;

/**
 * Puts snapshot artifacts into {@code modules/cas} instead of a bare directory.
 *
 * <p>This is the seam that gives the CAS a caller. {@link LocalContentAddressedArtifactStore}
 * already stores by digest, but it stores only bytes: no tenant, no sensitivity, no residency, no
 * retention class, and therefore nothing the collector or the read path can reason about. Every
 * artifact written through here arrives in the catalogue with the facts that later decide whether
 * it may be read, replicated, or deleted.
 *
 * <p>The reference format is {@code cas://sha256/<hex>/<size>} rather than a filesystem path.
 * A consumer that receives it can verify the content it gets back without asking anyone: the
 * identity is in the reference.
 *
 * <p>Reads verify. {@link SnapshotPorts.ArtifactReader} hands the bytes straight to a
 * materialiser that will unpack them into a workspace, so a silent corruption here becomes a
 * corrupt build tree, and the digest check is the last place it can be caught.
 */
public final class CasBackedArtifactStore implements SnapshotPorts.ArtifactStore, SnapshotPorts.ArtifactReader {

    public static final String SCHEME = "cas://";
    public static final String ROOT_GENERATION = "cas.reference-root-created-at";

    private final TenantCasStore tenantStore;
    private final CasCatalog catalog;
    private final CasAccessPolicy accessPolicy;
    private final String dataResidency;
    private final CasAccessPolicy.SecurityTier classification;
    private final long maximumArtifactBytes;
    private final LongSupplier clock;

    public CasBackedArtifactStore(CasStore store, CasCatalog catalog,
                                  String dataResidency, CasAccessPolicy.SecurityTier classification,
                                  long maximumArtifactBytes, LongSupplier clock) {
        this(TenantCasStore.global(store), catalog, dataResidency, classification,
                maximumArtifactBytes, clock);
    }

    public CasBackedArtifactStore(TenantCasStore tenantStore, CasCatalog catalog,
                                  String dataResidency, CasAccessPolicy.SecurityTier classification,
                                  long maximumArtifactBytes, LongSupplier clock) {
        this.tenantStore = Objects.requireNonNull(tenantStore, "tenantStore");
        this.catalog = Objects.requireNonNull(catalog, "catalog");
        this.accessPolicy = new CasAccessPolicy();
        this.dataResidency = require(dataResidency, "dataResidency");
        this.classification = Objects.requireNonNull(classification, "classification");
        if (maximumArtifactBytes < 1 || maximumArtifactBytes > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("artifact limit must be between 1 and "
                    + Integer.MAX_VALUE + " bytes");
        }
        this.maximumArtifactBytes = maximumArtifactBytes;
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    @Override
    public String putIfAbsent(SnapshotPorts.ArtifactResourceContext resource,
                              String sha256, long size, InputStream content, String mediaType) {
        Objects.requireNonNull(resource, "resource");
        if (sha256 == null || !sha256.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("artifact identity is invalid");
        }
        if (size < 0 || size > maximumArtifactBytes) {
            throw new IllegalArgumentException("artifact size is outside policy: " + size);
        }
        Objects.requireNonNull(content, "content");
        CasCatalog.ResourceLifecycle lifecycle = catalog.ensureActiveResource(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId());
        CasStore store = tenantStore.forTenant(resource.organizationId());
        CasDigest declared = new CasDigest(CasDigest.ALGORITHM, sha256, size);
        CasCatalog.CatalogEntry intended = entry(resource, declared, mediaType);
        Optional<CasCatalog.CatalogEntry> bound = catalog.findBound(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId(), declared);

        if (bound.isPresent()) {
            requireWriteCompatible(intended, bound.orElseThrow());
            byte[] verified;
            if (store.contains(declared)) {
                // contains() is only a cheap size probe. Verify the already-published bytes before
                // trusting the catalogue binding and promoting them to the authoritative tier.
                verified = store.get(declared);
            } else {
                verified = readAndVerify(content, declared);
            }
            CasCatalog.ResourceBinding binding = new CasCatalog.ResourceBinding(
                    resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                    resource.repositoryId(), declared, clock.getAsLong());
            byte[] durableBytes = verified;
            // Revalidate the exact resource incarnation around the durable callback.  A
            // repository retirement that linearized after findBound must win here.
            catalog.recordAndBindDurableResource(
                    intended, binding, lifecycle,
                    () -> store.putDurable(declared, durableBytes));
            CasCatalog.CatalogEntry recorded = catalog.findBound(
                            resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                            resource.repositoryId(), declared)
                    .orElseThrow(() -> new IllegalStateException(
                            "CAS catalogue lost an existing artifact resource binding"));
            requireWriteCompatible(intended, recorded);
            requireSnapshotRetention(recorded);
            return reference(declared);
        }

        Optional<CasCatalog.CatalogEntry> existing =
                catalog.find(resource.organizationId(), declared);
        existing.ifPresent(entry -> requireWriteCompatible(intended, entry));

        // A global blob or tenant object may already exist because another tenant or repository
        // wrote identical bytes. A digest alone is not proof that this repository produced those
        // bytes: require and verify the complete content before minting its resource binding.
        byte[] bytes = readAndVerify(content, declared);
        byte[] verified = bytes;
        if (store.contains(declared)) {
            verified = store.get(declared);
        }
        CasCatalog.ResourceBinding binding = new CasCatalog.ResourceBinding(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId(), declared, clock.getAsLong());
        // A durable binding must never name bytes that exist only in a write-back L1. The
        // tombstone-aware catalogue boundary also makes a retry repairable if a collector raced
        // this first publication after the caller's initial content verification.
        byte[] durableBytes = verified;
        catalog.recordAndBindDurableResource(
                intended, binding, lifecycle,
                () -> store.putDurable(declared, durableBytes));
        CasCatalog.CatalogEntry recorded = catalog.findBound(
                        resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                        resource.repositoryId(), declared)
                .orElseThrow(() -> new IllegalStateException(
                        "CAS catalogue did not persist the artifact resource binding"));
        requireWriteCompatible(intended, recorded);
        requireSnapshotRetention(recorded);
        return reference(declared);
    }

    @Override
    public InputStream open(SnapshotPorts.ArtifactResourceContext resource, String reference) {
        Objects.requireNonNull(resource, "resource");
        CasDigest digest = parse(reference);
        CasStore store = tenantStore.forTenant(resource.organizationId());
        CasCatalog.CatalogEntry entry = catalog.findBound(
                        resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                        resource.repositoryId(), digest)
                .orElseThrow(CasBackedArtifactStore::unavailable);
        authorizeRead(resource, digest, entry);
        // get() verifies; a poisoned artifact throws here rather than being unpacked into a
        // workspace and compiled.
        return new ByteArrayInputStream(store.get(digest));
    }

    @Override
    public void retainSnapshot(SnapshotPorts.ArtifactResourceContext resource,
                               String snapshotId,
                               List<String> references) {
        retainSnapshotGeneration(resource, snapshotId, references);
    }

    @Override
    public SnapshotPorts.ArtifactRetention retainSnapshotGeneration(
            SnapshotPorts.ArtifactResourceContext resource,
            String snapshotId,
            List<String> references
    ) {
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        Objects.requireNonNull(references, "references");
        if (references.isEmpty()) {
            throw new IllegalArgumentException("snapshot references must not be empty");
        }
        CasCatalog.ResourceLifecycle lifecycle = catalog.ensureActiveResource(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId());

        // Complete all authorization and integrity checks before publishing the first root.
        // addReferenceRoots is one catalogue transaction, so a later database failure cannot
        // leave an archive-only or manifest-only logical snapshot root.
        List<CasDigest> digests = List.copyOf(references).stream()
                .map(CasBackedArtifactStore::parse)
                .distinct()
                .toList();
        CasStore store = tenantStore.forTenant(resource.organizationId());
        Map<CasDigest, byte[]> verifiedBytes = new java.util.LinkedHashMap<>();
        for (CasDigest digest : digests) {
            CasCatalog.CatalogEntry entry = catalog.findBound(
                            resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                            resource.repositoryId(), digest)
                    .orElseThrow(CasBackedArtifactStore::unavailable);
            authorizeRead(resource, digest, entry);
            byte[] verified = store.get(digest);
            verifiedBytes.put(digest, verified);
        }

        long retainedAt = clock.getAsLong();
        if (retainedAt < 0) {
            throw new IllegalStateException("CAS root generation clock is invalid");
        }
        String rootOwner = snapshotRootOwner(resource, snapshotId);
        List<CasCatalog.ReferenceRoot> requestedRoots = digests.stream()
                .map(digest -> new CasCatalog.ReferenceRoot(
                        resource.organizationId(), CasGarbageCollector.RootKind.SNAPSHOT,
                        rootOwner, digest, retainedAt))
                .toList();
        long authoritativeGeneration = catalog.publishDurableResourceReferenceRoots(
                lifecycle, requestedRoots,
                () -> verifiedBytes.forEach(store::putDurable));

        List<CasCatalog.ReferenceRoot> active = catalog.activeReferenceRoots(
                resource.organizationId(), CasGarbageCollector.RootKind.SNAPSHOT, rootOwner);
        Set<CasDigest> observed = active.stream().map(CasCatalog.ReferenceRoot::digest)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        Set<CasDigest> expected = Set.copyOf(digests);
        Set<Long> generations = active.stream()
                .map(CasCatalog.ReferenceRoot::createdAtEpochMillis)
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
        if (!observed.equals(expected)
                || !generations.equals(Set.of(authoritativeGeneration))) {
            throw new IllegalStateException(
                    "CAS catalogue did not expose one complete snapshot root generation");
        }
        return new SnapshotPorts.ArtifactRetention(
                snapshotId, Map.of(ROOT_GENERATION,
                authoritativeGeneration));
    }

    /**
     * Unconditional release is deliberately unavailable for a collector-aware store.
     *
     * @deprecated callers must retain the token returned by {@link #retainSnapshotGeneration}
     * and call {@link #releaseSnapshotGeneration}; a wall-clock release can retire a newer root
     * generation after a delayed acknowledgement.
     */
    @Override
    @Deprecated(forRemoval = false)
    public void releaseSnapshot(SnapshotPorts.ArtifactResourceContext resource, String snapshotId) {
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        throw new UnsupportedOperationException(
                "collector-aware snapshot release requires an exact generation token");
    }

    @Override
    public void releaseSnapshotGeneration(
            SnapshotPorts.ArtifactResourceContext resource,
            SnapshotPorts.ArtifactRetention retention
    ) {
        Objects.requireNonNull(resource, "resource");
        Objects.requireNonNull(retention, "retention");
        requireSnapshotId(retention.snapshotId());
        long generation = retention.requireGeneration(ROOT_GENERATION);
        String rootOwner = snapshotRootOwner(resource, retention.snapshotId());
        long releasedAt = Math.max(clock.getAsLong(), generation);
        if (catalog.releaseReferenceRootGeneration(
                resource.organizationId(), CasGarbageCollector.RootKind.SNAPSHOT,
                rootOwner, generation, releasedAt)) {
            return;
        }
        // An absent or later generation is deliberately idempotent for an old reconciliation
        // token. An older/mixed generation is inconsistent catalogue state and must fail closed.
        List<CasCatalog.ReferenceRoot> active = catalog.activeReferenceRoots(
                resource.organizationId(), CasGarbageCollector.RootKind.SNAPSHOT, rootOwner);
        if (active.isEmpty()
                || active.stream().allMatch(root ->
                root.createdAtEpochMillis() > generation)) {
            return;
        }
        throw new IllegalStateException(
                "snapshot root generation changed without a comparable lifecycle token");
    }

    /** Begins repository deletion and permanently fences this incarnation against new writes. */
    public CasCatalog.ResourceLifecycle beginRepositoryRetirement(
            SnapshotPorts.ArtifactResourceContext resource) {
        Objects.requireNonNull(resource, "resource");
        return catalog.beginResourceRetirement(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId(), clock.getAsLong());
    }

    /**
     * Completes deletion only after every snapshot root generation for the incarnation has been
     * reconciled.  Repository bindings are released as one catalogue transaction, never once per
     * snapshot.
     */
    public CasCatalog.ResourceLifecycle finalizeRepositoryRetirement(
            CasCatalog.ResourceLifecycle retiring) {
        requireRepositoryLifecycle(retiring);
        return catalog.finalizeResourceRetirement(retiring, clock.getAsLong());
    }

    /** Explicit repository-ID reuse.  A stale retirement token cannot affect the new epoch. */
    public CasCatalog.ResourceLifecycle reactivateRepository(
            CasCatalog.ResourceLifecycle retired) {
        requireRepositoryLifecycle(retired);
        return catalog.reactivateResource(retired, clock.getAsLong());
    }

    public static String reference(CasDigest digest) {
        return SCHEME + digest.algorithm() + "/" + digest.hex() + "/" + digest.sizeBytes();
    }

    public static CasDigest parse(String reference) {
        if (reference == null || !reference.startsWith(SCHEME)) {
            throw new IllegalArgumentException("not a CAS reference: " + reference);
        }
        String[] parts = reference.substring(SCHEME.length()).split("/", -1);
        if (parts.length != 3 || !CasDigest.ALGORITHM.equals(parts[0])
                || !parts[2].matches("0|[1-9][0-9]*")) {
            throw new IllegalArgumentException("malformed CAS reference: " + reference);
        }
        try {
            return new CasDigest(CasDigest.ALGORITHM, parts[1], Long.parseLong(parts[2]));
        } catch (NumberFormatException invalidSize) {
            throw new IllegalArgumentException("malformed CAS reference: " + reference,
                    invalidSize);
        }
    }

    private CasCatalog.CatalogEntry entry(SnapshotPorts.ArtifactResourceContext resource,
                                          CasDigest digest, String mediaType) {
        return new CasCatalog.CatalogEntry(resource.organizationId(), digest,
                CasObjectModel.ObjectKind.BLOB,
                mediaType == null || mediaType.isBlank() ? "application/octet-stream" : mediaType,
                "snapshot", "1.0",
                // Snapshot artifacts are derived from customer source, so they are never
                // cross-tenant shareable regardless of how reproducible they look.
                CasObjectModel.Sensitivity.PRIVATE_SOURCE,
                CasObjectModel.RetentionClass.STANDARD, dataResidency, classification,
                Optional.empty(), Map.of(), false, clock.getAsLong());
    }

    private void authorizeRead(SnapshotPorts.ArtifactResourceContext resource,
                               CasDigest digest, CasCatalog.CatalogEntry entry) {
        if (!entry.digest().equals(digest)
                || !entry.tenantId().equals(resource.organizationId())
                || entry.kind() != CasObjectModel.ObjectKind.BLOB
                || !"snapshot".equals(entry.sourceSystem())
                || !"1.0".equals(entry.schemaVersion())
                || entry.sensitivity() != CasObjectModel.Sensitivity.PRIVATE_SOURCE
                || retentionStrength(entry.retentionClass())
                    < retentionStrength(CasObjectModel.RetentionClass.STANDARD)) {
            throw unavailable();
        }
        CasAccessPolicy.Decision decision = accessPolicy.evaluateRead(
                new CasAccessPolicy.ReaderContext(resource.organizationId(), Set.of(),
                        dataResidency, classification, false),
                new CasAccessPolicy.ProducerContext(entry.tenantId(), resource.repositoryId(), Set.of(),
                        entry.dataResidency(), entry.securityTier(), entry.sensitivity(),
                        "snapshot-artifact-v1@sha256:" + digest.hex(), entry.provenanceDigest()));
        if (!decision.allowed()) {
            // Do not turn an authorization failure into an existence or metadata oracle.
            throw unavailable();
        }
    }

    private static void requireSnapshotRetention(CasCatalog.CatalogEntry entry) {
        if (retentionStrength(entry.retentionClass())
                < retentionStrength(CasObjectModel.RetentionClass.STANDARD)) {
            throw new IllegalStateException(
                    "snapshot artifact metadata did not reach STANDARD retention");
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

    private static void requireWriteCompatible(
            CasCatalog.CatalogEntry intended,
            CasCatalog.CatalogEntry existing
    ) {
        if (!existing.tenantId().equals(intended.tenantId())
                || !existing.digest().equals(intended.digest())
                || existing.kind() != intended.kind()
                || !existing.mediaType().equals(intended.mediaType())
                || !existing.sourceSystem().equals(intended.sourceSystem())
                || !existing.schemaVersion().equals(intended.schemaVersion())
                || existing.sensitivity() != intended.sensitivity()
                || !existing.dataResidency().equals(intended.dataResidency())
                || existing.securityTier() != intended.securityTier()) {
            throw new SecurityException(
                    "artifact identity is already bound to another resource context");
        }
    }

    private byte[] readAndVerify(InputStream content, CasDigest declared) {
        byte[] bytes = readAtMost(content, declared.sizeBytes());
        CasDigest actual = CasDigest.of(bytes);
        if (!actual.equals(declared)) {
            throw new CasExceptions.CasCorruptionException(
                    "snapshot-artifact-store", declared, actual);
        }
        return bytes;
    }

    private static SecurityException unavailable() {
        return new SecurityException("snapshot artifact is unavailable for resource context");
    }

    private static void requireRepositoryLifecycle(CasCatalog.ResourceLifecycle lifecycle) {
        Objects.requireNonNull(lifecycle, "lifecycle");
        if (lifecycle.resourceKind() != CasCatalog.ResourceKind.REPOSITORY) {
            throw new IllegalArgumentException("snapshot artifact lifecycle must be REPOSITORY");
        }
    }

    /**
     * Reads at most {@code size} bytes and refuses a stream that has more. A declared size that
     * undercounts is how a hostile or broken producer turns a bounded read into an unbounded one.
     */
    private byte[] readAtMost(InputStream content, long size) {
        try {
            byte[] bytes = content.readNBytes((int) Math.min(size, maximumArtifactBytes));
            if (bytes.length != size) {
                throw new IllegalArgumentException("artifact stream ended after " + bytes.length
                        + " bytes but declared " + size);
            }
            if (content.read() != -1) {
                throw new IllegalArgumentException("artifact stream is longer than its declared size");
            }
            return bytes;
        } catch (IOException error) {
            throw new UncheckedIOException("cannot read artifact content", error);
        }
    }

    private static String require(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return value;
    }

    private static void requireSnapshotId(String snapshotId) {
        if (snapshotId == null
                || !snapshotId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")) {
            throw new IllegalArgumentException("snapshotId must be a safe identifier");
        }
    }

    /** Deterministic owner used by lifecycle reconciliation as well as capture/release. */
    public static String snapshotRootOwner(SnapshotPorts.ArtifactResourceContext resource,
                                           String snapshotId) {
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        // The catalogue owner is bounded and repository-scoped even when an imported snapshot ID
        // is long or contains separators. The versioned preimage makes this deterministic without
        // exposing raw tenant/resource identifiers in operational root listings.
        return "snapshot-" + CasDigest.ofUtf8("elmos-snapshot-root-owner/1\n"
                + resource.organizationId() + "\n" + resource.repositoryId() + "\n"
                + snapshotId).hex();
    }
}
