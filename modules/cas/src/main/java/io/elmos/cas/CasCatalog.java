package io.elmos.cas;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * The authoritative, transactional record of what the store holds — the schema created by
 * {@code V65__content_addressed_store_and_action_cache.sql} plus the resource-binding and
 * complete-metadata migration in V66.
 *
 * <p>Separated from {@link CasStore} on purpose. The store answers "do these bytes exist"; the
 * catalogue answers "who owns them, where may they live, what keeps them alive, and what happened
 * to them". Only the second one needs transactions, and only the second one is what the collector
 * is allowed to delete on the strength of.
 *
 * <p>Every method takes the tenant explicitly. The database enforces the same boundary through row
 * level security, so a bug here fails closed rather than leaking; passing it explicitly means the
 * intended tenant is visible at every call site rather than buried in a thread local.
 */
public interface CasCatalog {

    record CatalogEntry(String tenantId,
                        CasDigest digest,
                        CasObjectModel.ObjectKind kind,
                        String mediaType,
                        String sourceSystem,
                        String schemaVersion,
                        CasObjectModel.Sensitivity sensitivity,
                        CasObjectModel.RetentionClass retentionClass,
                        String dataResidency,
                        CasAccessPolicy.SecurityTier securityTier,
                        Optional<CasDigest> provenanceDigest,
                        Map<String, String> labels,
                        boolean legalHold,
                        long createdAtEpochMillis) {

        public CatalogEntry {
            tenantId = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(digest, "digest");
            Objects.requireNonNull(kind, "kind");
            mediaType = CasText.required(mediaType, "mediaType");
            sourceSystem = CasText.required(sourceSystem, "sourceSystem");
            schemaVersion = CasText.required(schemaVersion, "schemaVersion");
            Objects.requireNonNull(sensitivity, "sensitivity");
            Objects.requireNonNull(retentionClass, "retentionClass");
            dataResidency = CasText.required(dataResidency, "dataResidency");
            Objects.requireNonNull(securityTier, "securityTier");
            Objects.requireNonNull(provenanceDigest, "provenanceDigest");
            Objects.requireNonNull(labels, "labels").forEach((key, value) -> {
                CasText.withoutNul(key, "label key");
                CasText.withoutNul(value, "label value");
            });
            labels = Map.copyOf(labels);
            if (createdAtEpochMillis < 0) {
                throw new IllegalArgumentException("createdAtEpochMillis must not be negative");
            }
            // Mirrors cas_object_catalog_shared_needs_provenance: content that may cross a tenant
            // boundary has to be attributable, or a poisoning incident has no blast radius.
            if (sensitivity == CasObjectModel.Sensitivity.PUBLIC_DEPENDENCY && provenanceDigest.isEmpty()) {
                throw new IllegalArgumentException("shareable content requires a provenance digest");
            }
        }

        /**
         * Compatibility bridge for the V65 shape. {@code projectId} is deliberately discarded;
         * callers must create a {@link ResourceBinding} before resource-scoped reads can succeed.
         */
        @Deprecated(forRemoval = false)
        public CatalogEntry(String tenantId,
                            CasDigest digest,
                            String projectId,
                            CasObjectModel.ObjectKind kind,
                            String mediaType,
                            String sourceSystem,
                            String schemaVersion,
                            CasObjectModel.Sensitivity sensitivity,
                            CasObjectModel.RetentionClass retentionClass,
                            String dataResidency,
                            CasAccessPolicy.SecurityTier securityTier,
                            Optional<CasDigest> provenanceDigest,
                            Map<String, String> labels,
                            boolean legalHold,
                            long createdAtEpochMillis) {
            this(tenantId, digest, kind, mediaType, sourceSystem, schemaVersion, sensitivity,
                    retentionClass, dataResidency, securityTier, provenanceDigest, labels, legalHold,
                    createdAtEpochMillis);
            CasText.required(projectId, "projectId");
        }

        public CasObjectModel.ObjectMetadata metadata() {
            return new CasObjectModel.ObjectMetadata(tenantId, kind, mediaType, sourceSystem,
                    schemaVersion, sensitivity, retentionClass, dataResidency, provenanceDigest,
                    createdAtEpochMillis, labels, legalHold);
        }
    }

    /** The trusted resource type whose authorization grants access to an object. */
    enum ResourceKind {
        REPOSITORY,
        PROJECT
    }

    /**
     * Tenant-local access edge kept outside immutable object metadata. A binding may be released
     * without deleting the object because another repository, project, or GC root can still retain
     * the same bytes.
     */
    record ResourceBinding(String tenantId,
                           ResourceKind resourceKind,
                           String resourceId,
                           CasDigest digest,
                           long boundAtEpochMillis) {
        public ResourceBinding {
            tenantId = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(resourceKind, "resourceKind");
            resourceId = CasText.required(resourceId, "resourceId");
            Objects.requireNonNull(digest, "digest");
            if (boundAtEpochMillis < 0) {
                throw new IllegalArgumentException("boundAtEpochMillis must not be negative");
            }
        }
    }

    enum PlacementRole {
        PRIMARY,
        REPLICA
    }

    record Placement(String tenantId, CasDigest digest, String region, PlacementRole role, String storageTier) {
    }

    record ReferenceRoot(String tenantId, CasGarbageCollector.RootKind kind, String rootId,
                         CasDigest digest, long createdAtEpochMillis) {
        public ReferenceRoot {
            tenantId = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(kind, "kind");
            rootId = CasText.required(rootId, "rootId");
            Objects.requireNonNull(digest, "digest");
            if (createdAtEpochMillis < 0) {
                throw new IllegalArgumentException("createdAtEpochMillis must not be negative");
            }
        }
    }

    void record(CatalogEntry entry);

    /** Tenant-level maintenance lookup; resource read paths must use {@link #findBound}. */
    Optional<CatalogEntry> find(String tenantId, CasDigest digest);

    /**
     * Atomically resolves an object through an active trusted-resource binding. Implementations
     * must not implement this as separate binding and object reads because release between those
     * operations would turn a revoked edge into an authorized read.
     */
    Optional<CatalogEntry> findBound(String tenantId, ResourceKind resourceKind, String resourceId,
                                     CasDigest digest);

    /** Binds a known object to a trusted resource; an unknown or size-mismatched digest fails. */
    void bindResource(ResourceBinding binding);

    void releaseResource(String tenantId, ResourceKind resourceKind, String resourceId,
                         CasDigest digest, long releasedAtEpochMillis);

    List<ResourceBinding> activeResourceBindings(String tenantId, ResourceKind resourceKind,
                                                 String resourceId);

    /**
     * Bulk load for the collector's sweep; absent digests are simply not in the result. The view
     * must include the authoritative legal-hold bit. Dropping it turns tenant deletion into a
     * legal-hold bypass.
     */
    Map<CasDigest, CasObjectModel.ObjectMetadata> load(String tenantId, Set<CasDigest> digests);

    void placeObject(Placement placement);

    List<Placement> placements(String tenantId, CasDigest digest);

    void addReferenceRoot(ReferenceRoot root);

    /**
     * Atomically publishes one logical root set. Every entry must have the same tenant, kind, and
     * root ID; either the complete set becomes active or none of it does. An existing active subset
     * may be repaired, but an unexpected active digest fails closed instead of widening the root.
     */
    void addReferenceRoots(List<ReferenceRoot> roots);

    void releaseReferenceRoot(String tenantId, CasGarbageCollector.RootKind kind, String rootId,
                              long releasedAtEpochMillis);

    List<ReferenceRoot> activeReferenceRoots(String tenantId);

    void setLegalHold(String tenantId, CasDigest digest, boolean legalHold);

    /** Records a completed collection batch. Append only: an edited manifest proves nothing. */
    void recordDeletionManifest(String tenantId, CasGarbageCollector.DeletionManifest manifest, String executedBy);

    List<String> deletionBatchIds(String tenantId);

    void recordQuarantine(String tenantId, String quarantineId, String subjectKind, String subject,
                          Optional<CasDigest> declared, Optional<CasDigest> observed, String detail,
                          long detectedAtEpochMillis);

    int quarantineCount(String tenantId);
}
