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
        CasStore store = tenantStore.forTenant(resource.organizationId());
        CasDigest declared = new CasDigest(CasDigest.ALGORITHM, sha256, size);
        CasCatalog.CatalogEntry intended = entry(resource, declared, mediaType);
        Optional<CasCatalog.CatalogEntry> bound = catalog.findBound(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId(), declared);

        if (bound.isPresent()) {
            requireWriteCompatible(intended, bound.orElseThrow());
            if (store.contains(declared)) {
                // contains() is only a cheap size probe. Verify the already-published bytes before
                // trusting the catalogue binding and returning a reusable reference.
                store.get(declared);
                return reference(declared);
            }

            byte[] recovered = readAndVerify(content, declared);
            store.put(declared, recovered);
            return reference(declared);
        }

        Optional<CasCatalog.CatalogEntry> existing =
                catalog.find(resource.organizationId(), declared);
        existing.ifPresent(entry -> requireWriteCompatible(intended, entry));

        // A global blob or tenant object may already exist because another tenant or repository
        // wrote identical bytes. A digest alone is not proof that this repository produced those
        // bytes: require and verify the complete content before minting its resource binding.
        byte[] bytes = readAndVerify(content, declared);
        if (store.contains(declared)) {
            store.get(declared);
        } else {
            store.put(declared, bytes);
        }
        if (existing.isEmpty()) {
            catalog.record(intended);
        }
        catalog.bindResource(new CasCatalog.ResourceBinding(
                resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                resource.repositoryId(), declared, clock.getAsLong()));
        CasCatalog.CatalogEntry recorded = catalog.findBound(
                        resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                        resource.repositoryId(), declared)
                .orElseThrow(() -> new IllegalStateException(
                        "CAS catalogue did not persist the artifact resource binding"));
        requireWriteCompatible(intended, recorded);
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
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        Objects.requireNonNull(references, "references");
        if (references.isEmpty()) {
            throw new IllegalArgumentException("snapshot references must not be empty");
        }

        // Complete all authorization and integrity checks before publishing the first root.
        // addReferenceRoots is one catalogue transaction, so a later database failure cannot
        // leave an archive-only or manifest-only logical snapshot root.
        List<CasDigest> digests = List.copyOf(references).stream()
                .map(CasBackedArtifactStore::parse)
                .distinct()
                .toList();
        CasStore store = tenantStore.forTenant(resource.organizationId());
        for (CasDigest digest : digests) {
            CasCatalog.CatalogEntry entry = catalog.findBound(
                            resource.organizationId(), CasCatalog.ResourceKind.REPOSITORY,
                            resource.repositoryId(), digest)
                    .orElseThrow(CasBackedArtifactStore::unavailable);
            authorizeRead(resource, digest, entry);
            store.get(digest);
        }

        long retainedAt = clock.getAsLong();
        String rootOwner = snapshotRootOwner(resource, snapshotId);
        catalog.addReferenceRoots(digests.stream()
                .map(digest -> new CasCatalog.ReferenceRoot(
                        resource.organizationId(), CasGarbageCollector.RootKind.SNAPSHOT,
                        rootOwner, digest, retainedAt))
                .toList());
    }

    @Override
    public void releaseSnapshot(SnapshotPorts.ArtifactResourceContext resource, String snapshotId) {
        Objects.requireNonNull(resource, "resource");
        requireSnapshotId(snapshotId);
        catalog.releaseReferenceRoot(resource.organizationId(),
                CasGarbageCollector.RootKind.SNAPSHOT, snapshotRootOwner(resource, snapshotId),
                clock.getAsLong());
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
                || entry.sensitivity() != CasObjectModel.Sensitivity.PRIVATE_SOURCE) {
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
                || !snapshotId.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")) {
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
