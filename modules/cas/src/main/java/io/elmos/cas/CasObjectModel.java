package io.elmos.cas;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;

/**
 * ELMOS-CAS-002 and ELMOS-CAS-005. Immutable object identities plus the mutable-by-design
 * metadata that must live <em>outside</em> the content.
 *
 * <p>The split matters: two tenants can legitimately produce byte-identical content, and the
 * content digest must be the same for both or deduplication stops working. Everything that
 * differs between those two tenants - ownership, sensitivity, residency, provenance - is
 * therefore recorded next to the object rather than folded into its identity.
 */
public final class CasObjectModel {

    private CasObjectModel() {
    }

    /**
     * Drives cross-tenant reuse (ELMOS-CAS-019/029). Only {@link #PUBLIC_DEPENDENCY} content is
     * shareable by default, because it is reproducible from a public coordinate and carries no
     * customer source. Everything derived from customer source stays inside the tenant.
     */
    public enum Sensitivity {
        PUBLIC_DEPENDENCY(true),
        PRIVATE_SOURCE(false),
        GENERATED_OUTPUT(false),
        EVIDENCE(false);

        private final boolean crossTenantShareableByDefault;

        Sensitivity(boolean crossTenantShareableByDefault) {
            this.crossTenantShareableByDefault = crossTenantShareableByDefault;
        }

        public boolean crossTenantShareableByDefault() {
            return crossTenantShareableByDefault;
        }
    }

    /** Consumed by the collector (ELMOS-CAS-035); never by the identity of an object. */
    public enum RetentionClass {
        EPHEMERAL,
        STANDARD,
        EVIDENCE,
        REGULATORY
    }

    public enum ObjectKind {
        BLOB,
        TREE,
        MANIFEST,
        ACTION_RESULT
    }

    /**
     * Tenant-scoped object policy metadata that can be inspected without opening the object.
     * It is deliberately insufficient to authorize a resource read: callers also need an active
     * {@link CasCatalog.ResourceBinding}, resolved atomically through {@link CasCatalog#findBound}.
     *
     * @param provenanceDigest digest of the provenance record that explains where this object came
     *                         from. Absent only for objects ingested before provenance existed;
     *                         {@link CasAccessPolicy} refuses cross-tenant reads without it.
     */
    public record ObjectMetadata(String tenantId,
                                 ObjectKind kind,
                                 String mediaType,
                                 String sourceSystem,
                                 String schemaVersion,
                                 Sensitivity sensitivity,
                                 RetentionClass retentionClass,
                                 String dataResidency,
                                 Optional<CasDigest> provenanceDigest,
                                 long createdAtEpochMillis,
                                 Map<String, String> labels,
                                 boolean legalHold) {

        public ObjectMetadata {
            tenantId = CasText.required(tenantId, "tenantId");
            Objects.requireNonNull(kind, "kind");
            mediaType = CasText.required(mediaType, "mediaType");
            sourceSystem = CasText.required(sourceSystem, "sourceSystem");
            schemaVersion = CasText.required(schemaVersion, "schemaVersion");
            Objects.requireNonNull(sensitivity, "sensitivity");
            Objects.requireNonNull(retentionClass, "retentionClass");
            dataResidency = CasText.required(dataResidency, "dataResidency");
            Objects.requireNonNull(provenanceDigest, "provenanceDigest");
            if (createdAtEpochMillis < 0) {
                throw new IllegalArgumentException("createdAtEpochMillis must not be negative");
            }
            Objects.requireNonNull(labels, "labels").forEach((key, value) -> {
                CasText.withoutNul(key, "label key");
                CasText.withoutNul(value, "label value");
            });
            labels = Map.copyOf(new TreeMap<>(labels));
        }

        /**
         * Compatibility constructor for metadata producers that cannot set lifecycle policy.
         * Catalogue read paths must use the canonical constructor and carry the authoritative
         * legal-hold bit; silently defaulting a loaded hold is a destructive GC bug.
         */
        public ObjectMetadata(String tenantId,
                              ObjectKind kind,
                              String mediaType,
                              String sourceSystem,
                              String schemaVersion,
                              Sensitivity sensitivity,
                              RetentionClass retentionClass,
                              String dataResidency,
                              Optional<CasDigest> provenanceDigest,
                              long createdAtEpochMillis,
                              Map<String, String> labels) {
            this(tenantId, kind, mediaType, sourceSystem, schemaVersion, sensitivity,
                    retentionClass, dataResidency, provenanceDigest, createdAtEpochMillis,
                    labels, false);
        }

        public static ObjectMetadata blob(String tenantId,
                                          String mediaType,
                                          Sensitivity sensitivity,
                                          String dataResidency,
                                          long createdAtEpochMillis) {
            return new ObjectMetadata(tenantId, ObjectKind.BLOB, mediaType, "elmos", "1.0",
                    sensitivity, RetentionClass.STANDARD, dataResidency, Optional.empty(),
                    createdAtEpochMillis, Map.of());
        }

        /**
         * Compatibility bridge for callers written before repository ownership moved to
         * {@link CasCatalog.ResourceBinding}. The project value is validated but deliberately not
         * retained: treating it as object identity prevents two repositories in the same tenant
         * from binding the same bytes.
         */
        @Deprecated(forRemoval = false)
        public static ObjectMetadata blob(String tenantId,
                                          String projectId,
                                          String mediaType,
                                          Sensitivity sensitivity,
                                          String dataResidency,
                                          long createdAtEpochMillis) {
            CasText.required(projectId, "projectId");
            return blob(tenantId, mediaType, sensitivity, dataResidency, createdAtEpochMillis);
        }

        /** Compatibility constructor; see {@link #blob(String, String, String, Sensitivity, String, long)}. */
        @Deprecated(forRemoval = false)
        public ObjectMetadata(String tenantId,
                              String projectId,
                              ObjectKind kind,
                              String mediaType,
                              String sourceSystem,
                              String schemaVersion,
                              Sensitivity sensitivity,
                              RetentionClass retentionClass,
                              String dataResidency,
                              Optional<CasDigest> provenanceDigest,
                              long createdAtEpochMillis,
                              Map<String, String> labels) {
            this(tenantId, kind, mediaType, sourceSystem, schemaVersion, sensitivity, retentionClass,
                    dataResidency, provenanceDigest, createdAtEpochMillis, labels, false);
            CasText.required(projectId, "projectId");
        }

        public ObjectMetadata withProvenance(CasDigest provenance) {
            return new ObjectMetadata(tenantId, kind, mediaType, sourceSystem, schemaVersion,
                    sensitivity, retentionClass, dataResidency, Optional.of(provenance),
                    createdAtEpochMillis, labels, legalHold);
        }

        public ObjectMetadata withRetention(RetentionClass retention) {
            return new ObjectMetadata(tenantId, kind, mediaType, sourceSystem, schemaVersion,
                    sensitivity, retention, dataResidency, provenanceDigest, createdAtEpochMillis,
                    labels, legalHold);
        }
    }

    /** An object as the store sees it: an immutable identity bound to replaceable metadata. */
    public record StoredObject(CasDigest digest, ObjectMetadata metadata) {
        public StoredObject {
            Objects.requireNonNull(digest, "digest");
            Objects.requireNonNull(metadata, "metadata");
        }
    }
}
