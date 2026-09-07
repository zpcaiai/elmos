package io.elmos.migrationpack;

import java.time.Instant;
import java.util.*;

/** Admission contracts for Migration Pack Certification M29-M34. */
public final class MigrationPackModels {
    private MigrationPackModels() {}

    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, INCONCLUSIVE, BLOCKED }
    public enum AdmissionDecision { BLOCKED, READY_FOR_PACK_GATE }

    public record PackDefinition(int pack, String domain, String contractVersion, String gateCommand,
                                 int skillCount, int schemaCount, List<String> requiredPhases,
                                 List<String> typedArtifacts, List<String> invariants) {
        public PackDefinition {
            if (pack < 29 || pack > 34) throw new IllegalArgumentException("migration pack must be M29-M34");
            text(domain, "domain"); text(contractVersion, "contractVersion"); text(gateCommand, "gateCommand");
            if (skillCount <= 0 || schemaCount <= 0) throw new IllegalArgumentException("pack counts must be positive");
            requiredPhases = nonempty(requiredPhases, "requiredPhases");
            typedArtifacts = nonempty(typedArtifacts, "typedArtifacts"); invariants = nonempty(invariants, "invariants");
        }
        public String id() { return "M" + pack; }
    }

    public record PhaseEvidence(String phase, EvidenceStatus status, String organizationId,
                                String assessmentId, String sourceSnapshotDigest, String targetSnapshotDigest,
                                String packVersion, String authorityId, boolean independentJudge,
                                boolean realEnvironment, boolean defaultDenyNetworkPassed,
                                boolean idempotencyPassed, boolean semanticIntegrityPassed,
                                int unsupportedCount, int criticalOpenRisks, Instant observedAt,
                                List<String> evidenceRefs, boolean productionMutationExecuted) {
        public PhaseEvidence {
            text(phase, "phase"); required(status, "status"); text(organizationId, "organizationId");
            text(assessmentId, "assessmentId"); digest(sourceSnapshotDigest, "sourceSnapshotDigest");
            digest(targetSnapshotDigest, "targetSnapshotDigest"); text(packVersion, "packVersion");
            text(authorityId, "authorityId"); required(observedAt, "observedAt");
            if (unsupportedCount < 0 || criticalOpenRisks < 0) throw new IllegalArgumentException("counts must be non-negative");
            evidenceRefs = copy(evidenceRefs);
            if (productionMutationExecuted)
                throw new IllegalArgumentException("migration-pack admission cannot execute a production mutation");
        }
    }

    public record AdmissionRequest(int pack, String organizationId, String assessmentId,
                                   String sourceSnapshotDigest, String targetSnapshotDigest,
                                   String packVersion, String requestedBy, Instant evaluatedAt,
                                   List<PhaseEvidence> evidence) {
        public AdmissionRequest {
            if (pack < 29 || pack > 34) throw new IllegalArgumentException("migration pack must be M29-M34");
            text(organizationId, "organizationId"); text(assessmentId, "assessmentId");
            digest(sourceSnapshotDigest, "sourceSnapshotDigest"); digest(targetSnapshotDigest, "targetSnapshotDigest");
            text(packVersion, "packVersion"); text(requestedBy, "requestedBy"); required(evaluatedAt, "evaluatedAt");
            evidence = copy(evidence);
        }
    }

    public record AdmissionResult(PackDefinition definition, AdmissionRequest request,
                                  AdmissionDecision decision, boolean evidenceComplete,
                                  List<String> blockers, List<String> restrictions,
                                  String soleCertificationAuthority, boolean certified,
                                  boolean productionMutationExecuted) {
        public AdmissionResult {
            required(definition, "definition"); required(request, "request"); required(decision, "decision");
            blockers = copy(blockers); restrictions = nonempty(restrictions, "restrictions");
            text(soleCertificationAuthority, "soleCertificationAuthority");
            if (certified || productionMutationExecuted)
                throw new IllegalArgumentException("admission result cannot certify or mutate production");
            if (decision == AdmissionDecision.READY_FOR_PACK_GATE && (!evidenceComplete || !blockers.isEmpty()))
                throw new IllegalArgumentException("pack-gate readiness requires complete evidence");
        }
    }

    static void text(String value, String field) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(field + " is required");
    }
    static void digest(String value, String field) {
        text(value, field);
        if (!value.matches("[a-f0-9]{64}")) throw new IllegalArgumentException(field + " must be a lowercase SHA-256 digest");
    }
    static <T> T required(T value, String field) {
        if (value == null) throw new IllegalArgumentException(field + " is required"); return value;
    }
    static <T> List<T> copy(List<T> value) { return value == null ? List.of() : List.copyOf(value); }
    static <T> List<T> nonempty(List<T> value, String field) {
        if (value == null || value.isEmpty() || value.stream().anyMatch(Objects::isNull))
            throw new IllegalArgumentException(field + " must not be empty");
        return List.copyOf(value);
    }
}
