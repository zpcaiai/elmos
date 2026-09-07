package io.elmos.product.assurance;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

/** Product Batch 37 contracts spanning content, attestations, external producers and assurance semantics. */
public final class EvidenceAssuranceModels {
    private EvidenceAssuranceModels() {}

    public enum EvidenceState { VERIFIED, FAILED, NOT_RUN, INCONCLUSIVE, UNKNOWN }
    public enum Decision { BLOCKED, READY_FOR_HUMAN_DECISION }

    public record ExternalEvidence(String providerInstanceId, String nativeRunId,
                                   String nativeEvidenceDigest, String normalizedEvidenceDigest,
                                   boolean webhookReceived, boolean pollingReconciled,
                                   boolean nativePreserved, boolean normalizedSeparatelyPreserved,
                                   boolean artifactDigestRecomputed, boolean firstFailurePreserved,
                                   EvidenceState state) {
        public ExternalEvidence {
            text(providerInstanceId, "providerInstanceId"); text(nativeRunId, "nativeRunId");
            digest(nativeEvidenceDigest, "nativeEvidenceDigest"); digest(normalizedEvidenceDigest, "normalizedEvidenceDigest");
            required(state, "state");
        }
        public String stableId() { return providerInstanceId + ":" + nativeRunId; }
    }

    public record MetricObservation(String definitionVersion, String grain, BigDecimal numerator,
                                    BigDecimal denominator, boolean applicable, Instant asOf,
                                    String sourceCertificationRef, boolean ratioReaggregated,
                                    EvidenceState dataQuality) {
        public MetricObservation {
            text(definitionVersion, "definitionVersion"); text(grain, "grain");
            required(numerator, "numerator"); required(denominator, "denominator"); required(asOf, "asOf");
            text(sourceCertificationRef, "sourceCertificationRef"); required(dataQuality, "dataQuality");
            if (numerator.signum() < 0 || denominator.signum() < 0) throw new IllegalArgumentException("metric values must be non-negative");
        }
    }

    public record AdmissionRequest(
            String organizationId, String evidencePackId, String subjectDigest, String contextSnapshotDigest,
            String producerId, String verifierId, Instant evaluatedAt,
            boolean contentImmutable, boolean metadataVersioned, boolean attestationSigned,
            boolean attestationSchemaVerified, boolean trustRootVerified, boolean offlineVerificationComplete,
            boolean crossTenantDedupEnabled, boolean retentionExpired, boolean deletionRequested,
            List<ExternalEvidence> externalEvidence, List<MetricObservation> metrics,
            boolean lineageComplete, boolean evidenceCompletenessMultidimensional,
            boolean criticalFailureOpen, boolean controlPresenceOnly, boolean independentAssessment,
            boolean auditClaimIndependentlyVerified, boolean cacheTenantAuthorizationVersionBound,
            boolean narrativesEvidenceBound, List<String> evidenceRefs) {
        public AdmissionRequest {
            text(organizationId, "organizationId"); text(evidencePackId, "evidencePackId");
            digest(subjectDigest, "subjectDigest"); digest(contextSnapshotDigest, "contextSnapshotDigest");
            text(producerId, "producerId"); text(verifierId, "verifierId"); required(evaluatedAt, "evaluatedAt");
            externalEvidence = copy(externalEvidence); metrics = copy(metrics); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record AdmissionResult(Decision decision, List<String> blockers, List<String> restrictions,
                                  boolean approved, boolean certified, boolean externalOperationExecuted) {
        public AdmissionResult {
            required(decision, "decision"); blockers = copy(blockers); restrictions = nonempty(restrictions, "restrictions");
            if (approved || certified || externalOperationExecuted)
                throw new IllegalArgumentException("Product B37 assurance cannot approve, certify, or execute externally");
            if (decision == Decision.READY_FOR_HUMAN_DECISION && !blockers.isEmpty())
                throw new IllegalArgumentException("human-decision readiness requires no blockers");
        }
    }

    static void text(String value, String field) { if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required"); }
    static void digest(String value, String field) { text(value, field); if (!value.matches("[a-f0-9]{64}")) throw new IllegalArgumentException(field + " must be SHA-256"); }
    static <T> T required(T value, String field) { return Objects.requireNonNull(value, field + " is required"); }
    static <T> List<T> copy(List<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static <T> List<T> nonempty(List<T> values, String field) { if (values == null || values.isEmpty()) throw new IllegalArgumentException(field + " must not be empty"); return List.copyOf(values); }
}
