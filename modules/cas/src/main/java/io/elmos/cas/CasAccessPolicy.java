package io.elmos.cas;

import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.TreeSet;

/**
 * ELMOS-CAS-028/029. The read-side authorisation decision, in one place.
 *
 * <p>Cache reads are the quiet path to a data breach. Nobody audits a cache hit: it produces no
 * new work, no new log line worth reading, and the artifact it hands back looks exactly like one
 * the caller could have built. Every check that the execution path performs must therefore be
 * performed again here, on the way out of the cache, with the reader's own context.
 */
public final class CasAccessPolicy {

    /** Ordered by clearance. A reader may read at or below its own tier, never above. */
    public enum SecurityTier {
        PUBLIC,
        INTERNAL,
        CONFIDENTIAL,
        RESTRICTED
    }

    public record ReaderContext(String tenantId,
                                Set<String> permissionScope,
                                String dataResidency,
                                SecurityTier clearance,
                                boolean explicitCrossTenantSharing) {
        public ReaderContext {
            tenantId = CasText.required(tenantId, "tenantId");
            permissionScope = Set.copyOf(permissionScope);
            dataResidency = CasText.required(dataResidency, "dataResidency");
            Objects.requireNonNull(clearance, "clearance");
        }
    }

    public record ProducerContext(String tenantId,
                                  String projectId,
                                  Set<String> permissionScope,
                                  String dataResidency,
                                  SecurityTier classification,
                                  CasObjectModel.Sensitivity sensitivity,
                                  String toolchainImage,
                                  Optional<CasDigest> provenanceDigest) {
        public ProducerContext {
            tenantId = CasText.required(tenantId, "tenantId");
            projectId = CasText.required(projectId, "projectId");
            permissionScope = Set.copyOf(permissionScope);
            dataResidency = CasText.required(dataResidency, "dataResidency");
            Objects.requireNonNull(classification, "classification");
            Objects.requireNonNull(sensitivity, "sensitivity");
            toolchainImage = CasText.required(toolchainImage, "toolchainImage");
            Objects.requireNonNull(provenanceDigest, "provenanceDigest");
        }
    }

    public record Decision(boolean allowed, String reason, String detail) {
        public static Decision allow() {
            return new Decision(true, "ALLOWED", "");
        }

        public static Decision deny(String reason, String detail) {
            return new Decision(false, reason, detail);
        }
    }

    public Decision evaluateRead(ReaderContext reader, ProducerContext producer) {
        if (!reader.tenantId().equals(producer.tenantId())) {
            if (!producer.sensitivity().crossTenantShareableByDefault()) {
                return Decision.deny("CROSS_TENANT_REUSE_DISABLED",
                        producer.sensitivity() + " content is not shareable across tenants");
            }
            if (!reader.explicitCrossTenantSharing()) {
                return Decision.deny("CROSS_TENANT_SHARING_NOT_ENABLED",
                        reader.tenantId() + " has not opted into shared public content");
            }
            if (producer.provenanceDigest().isEmpty()) {
                // Shared content without provenance cannot be attributed if it later turns out to
                // be poisoned, so it is not shareable regardless of its sensitivity label.
                return Decision.deny("PROVENANCE_MISSING", "shared object carries no provenance digest");
            }
        }
        if (!reader.dataResidency().equals(producer.dataResidency())) {
            return Decision.deny("DATA_RESIDENCY_MISMATCH",
                    producer.dataResidency() + " content requested from " + reader.dataResidency());
        }
        if (reader.clearance().ordinal() < producer.classification().ordinal()) {
            return Decision.deny("SECURITY_TIER_TOO_LOW",
                    "reader clearance " + reader.clearance() + " below " + producer.classification());
        }
        Set<String> missing = new TreeSet<>(producer.permissionScope());
        missing.removeAll(reader.permissionScope());
        if (!missing.isEmpty()) {
            // The classic confused-deputy shape: the result was produced with permissions the
            // reader does not hold, so handing it back grants those permissions retroactively.
            return Decision.deny("PERMISSION_DOWNGRADE", "reader is missing scopes " + missing);
        }
        return Decision.allow();
    }
}
