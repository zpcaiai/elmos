package io.elmos.product.assurance;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import static io.elmos.product.assurance.EvidenceAssuranceModels.*;

/** Independent judge admission. Digest presence alone never establishes trust or authorization. */
public final class EvidenceAssuranceService {
    public AdmissionResult evaluate(AdmissionRequest request) {
        required(request, "request"); List<String> blockers = new ArrayList<>();
        if (request.producerId().equals(request.verifierId())) blockers.add("PRODUCER_VERIFIER_SEPARATION_REQUIRED");
        require(request.contentImmutable(), "CONTENT_IMMUTABILITY_REQUIRED", blockers);
        require(request.metadataVersioned(), "METADATA_VERSIONING_REQUIRED", blockers);
        require(request.attestationSigned(), "SIGNED_ATTESTATION_REQUIRED", blockers);
        require(request.attestationSchemaVerified(), "ATTESTATION_SCHEMA_VERIFICATION_REQUIRED", blockers);
        require(request.trustRootVerified(), "TRUST_ROOT_VERIFICATION_REQUIRED", blockers);
        require(request.offlineVerificationComplete(), "OFFLINE_VERIFICATION_NOT_RUN", blockers);
        if (request.crossTenantDedupEnabled()) blockers.add("CROSS_TENANT_DEDUP_DISABLED_BY_DEFAULT");
        if (request.retentionExpired() && request.deletionRequested()) blockers.add("RETENTION_EXPIRY_IS_NOT_DELETE_AUTHORIZATION");
        if (request.externalEvidence().isEmpty()) blockers.add("EXTERNAL_EVIDENCE_NOT_RUN");
        request.externalEvidence().forEach(value -> validateExternal(value, blockers));
        if (request.metrics().isEmpty()) blockers.add("ASSURANCE_METRICS_NOT_RUN");
        request.metrics().forEach(value -> validateMetric(value, blockers));
        require(request.lineageComplete(), "LINEAGE_INCOMPLETE", blockers);
        require(request.evidenceCompletenessMultidimensional(), "EVIDENCE_COMPLETENESS_DIMENSIONS_REQUIRED", blockers);
        if (request.criticalFailureOpen()) blockers.add("CRITICAL_FAILURE_CANNOT_BE_HIDDEN_BY_ROLLUP");
        if (request.controlPresenceOnly()) blockers.add("CONTROL_PRESENCE_IS_NOT_EFFECTIVENESS");
        require(request.independentAssessment(), "INDEPENDENT_ASSESSMENT_REQUIRED", blockers);
        require(request.auditClaimIndependentlyVerified(), "EXTERNAL_AUDIT_REPORT_REMAINS_A_CLAIM", blockers);
        require(request.cacheTenantAuthorizationVersionBound(), "QUERY_CACHE_SCOPE_BINDING_REQUIRED", blockers);
        require(request.narrativesEvidenceBound(), "NARRATIVE_MUST_MARK_INFERENCE_AND_DATA_GAPS", blockers);
        if (request.evidenceRefs().isEmpty()) blockers.add("IMMUTABLE_EVIDENCE_REFS_REQUIRED");
        List<String> result = blockers.stream().distinct().sorted().toList();
        return new AdmissionResult(result.isEmpty() ? Decision.READY_FOR_HUMAN_DECISION : Decision.BLOCKED,
                result, List.of("CONTENT_ARTIFACT_ATTESTATION_DECISION_GRAPH_AND_PACK_REMAIN_DISTINCT",
                "NATIVE_AND_NORMALIZED_EXTERNAL_EVIDENCE_REMAIN_SEPARATE",
                "UNKNOWN_INCONCLUSIVE_AND_NOT_RUN_NEVER_MEAN_PASS",
                "RATIOS_REAGGREGATE_NUMERATOR_AND_DENOMINATOR",
                "CONTROL_MAPPING_IS_NOT_CONTROL_EFFECTIVENESS",
                "HUMAN_ASSURANCE_DECISION_REMAINS_REQUIRED"), false, false, false);
    }

    private static void validateExternal(ExternalEvidence value, List<String> blockers) {
        String p = "EXTERNAL_" + value.stableId() + ":";
        require(value.webhookReceived() || value.pollingReconciled(), p + "INGESTION_NOT_OBSERVED", blockers);
        require(value.pollingReconciled(), p + "RECONCILIATION_REQUIRED", blockers);
        require(value.nativePreserved(), p + "NATIVE_EVIDENCE_NOT_PRESERVED", blockers);
        require(value.normalizedSeparatelyPreserved(), p + "NORMALIZED_EVIDENCE_NOT_SEPARATE", blockers);
        require(value.artifactDigestRecomputed(), p + "ARTIFACT_DIGEST_NOT_RECOMPUTED", blockers);
        require(value.firstFailurePreserved(), p + "FIRST_FAILURE_ERASED_BY_RERUN", blockers);
        if (value.state() != EvidenceState.VERIFIED) blockers.add(p + "STATUS_" + value.state());
    }

    private static void validateMetric(MetricObservation value, List<String> blockers) {
        String p = "METRIC_" + value.definitionVersion() + ":";
        if (value.applicable() && value.denominator().compareTo(BigDecimal.ZERO) == 0) blockers.add(p + "DENOMINATOR_REQUIRED");
        if (!value.ratioReaggregated()) blockers.add(p + "RATIO_AVERAGING_FORBIDDEN");
        if (value.dataQuality() != EvidenceState.VERIFIED) blockers.add(p + "QUALITY_" + value.dataQuality());
    }

    private static void require(boolean value, String blocker, List<String> blockers) { if (!value) blockers.add(blocker); }
}
