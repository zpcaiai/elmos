package io.elmos.cas;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

/**
 * The authoritative, transactional record of what the store holds — the schema created by
 * {@code V65__content_addressed_store_and_action_cache.sql} plus the resource-binding,
 * complete-metadata, durable-index, and atomic-deletion migrations through V76.
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

    /**
     * Repairs or verifies the authoritative bytes while the catalogue owns the per-object
     * publication protocol. Implementations must reject {@code PENDING} or
     * {@code OUTCOME_UNKNOWN} before invoking this callback; they invoke it while a new deletion
     * is excluded and may clear only a terminal repairable tombstone afterwards. A failure must
     * leave every deletion tombstone and root unchanged.
     */
    @FunctionalInterface
    interface DurableObjectEnsurer {
        void ensureDurable();
    }

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

    enum ResourceLifecycleState {
        ACTIVE,
        RETIRING,
        RETIRED
    }

    /**
     * Durable incarnation of one trusted resource.  The two epochs are authorization data, not
     * counters for display: a delayed operation carrying an earlier incarnation must never bind
     * bytes or publish roots after a tenant or repository identifier has been reused.
     */
    record ResourceLifecycle(String tenantId,
                             ResourceKind resourceKind,
                             String resourceId,
                             long tenantEpoch,
                             long resourceEpoch,
                             ResourceLifecycleState state,
                             long transitionedAtEpochMillis,
                             long releasedBindingCount) {
        public ResourceLifecycle {
            tenantId = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(resourceKind, "resourceKind");
            resourceId = CasText.required(resourceId, "resourceId");
            if (tenantEpoch < 1 || resourceEpoch < 1) {
                throw new IllegalArgumentException("resource lifecycle epochs must be positive");
            }
            Objects.requireNonNull(state, "state");
            if (transitionedAtEpochMillis < 0 || releasedBindingCount < 0) {
                throw new IllegalArgumentException("resource lifecycle counters must not be negative");
            }
        }

        public void requireActive() {
            if (state != ResourceLifecycleState.ACTIVE) {
                throw new IllegalStateException("CAS resource is not ACTIVE");
            }
        }
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

    /**
     * Atomically records immutable object metadata and publishes its logical root set when no
     * deletion tombstone exists.
     * A collector must never observe the catalogue row without the root that protects it, so every
     * implementation is required to provide one real atomic operation rather than inheriting a
     * sequential compatibility fallback. This compatibility method cannot repair a tombstoned
     * object; production byte publication uses {@link #recordAndPublishDurableReferenceRoots}.
     */
    long recordAndAddReferenceRoots(CatalogEntry entry, List<ReferenceRoot> roots);

    /**
     * Production publication boundary for a newly catalogued object. The implementation locks
     * every referenced digest, invokes {@code durableObjectEnsurer}, clears any prior deletion
     * tombstone, then records metadata and publishes the complete logical root set atomically.
     * Bytes written by the callback may remain after a later catalogue rollback, but a root may
     * never become active unless the callback succeeded.
     */
    long recordAndPublishDurableReferenceRoots(
            CatalogEntry entry,
            List<ReferenceRoot> roots,
            DurableObjectEnsurer durableObjectEnsurer
    );

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

    /** Returns the current ACTIVE incarnation, creating epoch 1 for a new resource. */
    ResourceLifecycle ensureActiveResource(
            String tenantId, ResourceKind resourceKind, String resourceId);

    /**
     * Production first-publication boundary for a resource-bound object. Durable bytes, metadata,
     * and the active binding become one tombstone-aware operation, so a retry can recover after a
     * delete raced the caller between its initial write and catalogue publication.
     */
    void recordAndBindDurableResource(
            CatalogEntry entry,
            ResourceBinding binding,
            DurableObjectEnsurer durableObjectEnsurer
    );

    /**
     * Epoch-bound first publication.  Implementations hold the tenant and resource lifecycle
     * fences through the durable callback and binding insert, then lock objects in digest order.
     */
    void recordAndBindDurableResource(
            CatalogEntry entry,
            ResourceBinding binding,
            ResourceLifecycle resource,
            DurableObjectEnsurer durableObjectEnsurer
    );

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
     *
     * <p>This method fails while any requested digest is tombstoned and therefore cannot repair a
     * deletion. Production callers that can re-establish authoritative bytes use
     * {@link #publishDurableReferenceRoots}.
     *
     * <p>When a previously released logical root is reactivated, the catalogue must allocate a
     * generation strictly greater than every historical generation for that tenant/kind/root ID,
     * even if the caller restarted or its wall clock moved backwards. Implementations backed by
     * shared storage perform that comparison under the same logical-root transaction lock used
     * for publication.
     */
    long addReferenceRoots(List<ReferenceRoot> roots);

    /**
     * Production publication boundary for already-catalogued objects. This is the only supported
     * way to repair a digest after a deletion tombstone: durable bytes are re-established under
     * the same protocol that clears the tombstone and activates the complete root set.
     */
    long publishDurableReferenceRoots(
            List<ReferenceRoot> roots,
            DurableObjectEnsurer durableObjectEnsurer
    );

    /**
     * Publishes an exact logical root set and its authoritative root-to-resource edge in the same
     * transaction.  Snapshot stores must use this overload; a hashed root ID is deliberately not
     * reversible and therefore cannot substitute for the edge.
     */
    long publishDurableResourceReferenceRoots(
            ResourceLifecycle resource,
            List<ReferenceRoot> roots,
            DurableObjectEnsurer durableObjectEnsurer
    );

    /** Permanently fences the current incarnation against new bindings and roots. */
    ResourceLifecycle beginResourceRetirement(
            String tenantId, ResourceKind resourceKind, String resourceId,
            long transitionedAtEpochMillis);

    /**
     * Releases all bindings only after every mapped root generation has been reconciled.  The
     * exact RETIRING token prevents an acknowledgement for an old incarnation retiring a newer
     * resource with the same external ID.
     */
    ResourceLifecycle finalizeResourceRetirement(
            ResourceLifecycle retiring, long transitionedAtEpochMillis);

    /** Explicit identifier reuse; never performed implicitly by a write or a root publication. */
    ResourceLifecycle reactivateResource(
            ResourceLifecycle retired, long transitionedAtEpochMillis);

    /**
     * Creates the durable tombstone before touching bytes, then deletes only after authoritative
     * legal-hold and active-root checks under the same per-object protocol used by publication.
     * A tombstone is intentionally retained for deleted, missing, failed, or ambiguous outcomes;
     * only a later durable publication may clear it.
     */
    CasGarbageCollector.AtomicDeletionOutcome deleteIfUnreferenced(
            CasGarbageCollector.Candidate candidate,
            TenantCasStore store
    );

    void releaseReferenceRoot(String tenantId, CasGarbageCollector.RootKind kind, String rootId,
                              long releasedAtEpochMillis);

    /** Compare-and-release for lifecycle tokens; a different active generation is untouched. */
    boolean releaseReferenceRootGeneration(
            String tenantId,
            CasGarbageCollector.RootKind kind,
            String rootId,
            long expectedGeneration,
            long releasedAtEpochMillis
    );

    List<ReferenceRoot> activeReferenceRoots(String tenantId);

    /**
     * Resolves one logical root through its complete tenant/kind/root identity.
     *
     * <p>Online indexes must use this exact lookup instead of loading every active root for a
     * tenant and filtering in process. The V65 primary key begins with these three columns, so a
     * durable implementation can keep lookup cost proportional to the selected root set rather
     * than to every snapshot, workflow, evidence and cache root owned by the tenant.
     */
    default List<ReferenceRoot> activeReferenceRoots(
            String tenantId, CasGarbageCollector.RootKind kind, String rootId) {
        Objects.requireNonNull(kind, "kind");
        CasText.required(rootId, "rootId");
        return activeReferenceRoots(tenantId).stream()
                .filter(root -> root.kind() == kind && root.rootId().equals(rootId))
                .toList();
    }

    void setLegalHold(String tenantId, CasDigest digest, boolean legalHold);

    /** Records a completed collection batch. Append only: an edited manifest proves nothing. */
    void recordDeletionManifest(String tenantId, CasGarbageCollector.DeletionManifest manifest, String executedBy);

    List<String> deletionBatchIds(String tenantId);

    void recordQuarantine(String tenantId, String quarantineId, String subjectKind, String subject,
                          Optional<CasDigest> declared, Optional<CasDigest> observed, String detail,
                          long detectedAtEpochMillis);

    int quarantineCount(String tenantId);
}
