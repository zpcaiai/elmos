package io.elmos.securitycompliance;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class SecurityModels {
    private SecurityModels() {}

    public enum SecurityProfile { BASELINE, STANDARD, HIGH_ASSURANCE, REGULATED, CRITICAL_SYSTEM }
    public enum ExternalStatus { PASS, FAIL, NOT_RUN, PARTIALLY_RUN, INCONCLUSIVE, TOOL_ERROR, COVERAGE_INSUFFICIENT, HUMAN_REVIEW_REQUIRED }
    public enum AdapterType { ESTATE, IDENTITY, SECRET, CRYPTO, SAST, SCA, IAC, CONTAINER, DAST, API_SECURITY, CLOUD, RUNTIME, DLP, SBOM, PROVENANCE, VEX, OSCAL, SIEM }
    public enum AdapterStatus { NOT_CONFIGURED, READY, LICENSE_BLOCKED }
    public enum AuthorizationDecision { AUTHORIZED, AUTHORIZED_WITH_CONDITIONS, LIMITED_AUTHORIZATION, REASSESSMENT_REQUIRED, SUSPENDED, DENIED, EXPIRED }
    public enum ControlEffectiveness { EFFECTIVE, PARTIALLY_EFFECTIVE, INEFFECTIVE, NOT_IMPLEMENTED, NOT_ASSESSED, STALE }
    public enum MigrationState {
        SECURITY_DISCOVERY, THREAT_MODELING, CONTROL_BASELINING, REQUIREMENT_GENERATING,
        CONTROL_IMPLEMENTING, STATIC_VALIDATING, DYNAMIC_VALIDATING, RISK_EVALUATING,
        REMEDIATING, CONTROL_ASSESSING, AUTHORIZATION_REVIEW, AUTHORIZED, CONTINUOUS_MONITORING
    }
    public enum ExceptionState {
        SECURITY_ESTATE_INCOMPLETE, THREAT_MODEL_INCOMPLETE, CONTROL_NOT_IMPLEMENTED,
        SECURITY_TEST_FAILED, SECURITY_COVERAGE_INSUFFICIENT, CRITICAL_VULNERABILITY_OPEN,
        EXCEPTION_REQUIRED, EXCEPTION_EXPIRED, EVIDENCE_STALE, AUTHORIZATION_DENIED,
        AUTHORIZATION_EXPIRED, REASSESSMENT_REQUIRED, INCIDENT_REVIEW_REQUIRED
    }
    public enum EvidenceType {
        SECURITY_ESTATE, TRUST_BOUNDARY, IDENTITY_POSTURE, ZERO_TRUST_POLICY, SECRET_INVENTORY,
        CRYPTO_INVENTORY, SECURITY_REQUIREMENTS, THREAT_MODEL, SBOM, PROVENANCE, ATTESTATION, VEX,
        SAST_RESULT, SCA_RESULT, DAST_RESULT, API_SECURITY_RESULT, CLOUD_SECURITY_RESULT,
        RUNTIME_SECURITY_RESULT, VULNERABILITY_RISK, DATA_PROTECTION_RESULT, CONTROL_IMPLEMENTATION,
        CONTROL_ASSESSMENT, OSCAL_PACKAGE, AUTHORIZATION_DECISION
    }
    public enum CostUnit {
        SECURITY_DISCOVERY_UNIT, SAST_ANALYSIS, SCA_ANALYSIS, DAST_REQUEST, SBOM_GENERATION,
        PROVENANCE_VERIFICATION, THREAT_MODEL, CLOUD_POSTURE_ASSESSMENT, RUNTIME_MONITORING,
        CONTROL_ASSESSMENT, OSCAL_PACKAGE, AUTHORIZATION_REVIEW
    }

    public record ToolAdapter(
            AdapterType type,
            String tool,
            String version,
            AdapterStatus status,
            Set<String> targets,
            Set<String> permissions,
            boolean activeTest,
            String defaultNetwork,
            String license,
            String dataHandling,
            String outputFormat,
            String falsePositivePolicy,
            String coveragePolicy) {
        public ToolAdapter {
            Objects.requireNonNull(type); require(tool, "tool"); require(version, "version");
            Objects.requireNonNull(status); targets = Set.copyOf(targets); permissions = Set.copyOf(permissions);
            require(defaultNetwork, "defaultNetwork"); require(license, "license");
            require(dataHandling, "dataHandling"); require(outputFormat, "outputFormat");
            require(falsePositivePolicy, "falsePositivePolicy"); require(coveragePolicy, "coveragePolicy");
            if (!defaultNetwork.equals("DENY")) throw new IllegalArgumentException("security adapter network must default deny");
            if (permissions.stream().anyMatch(SecurityModels::prohibited)) {
                throw new IllegalArgumentException("security adapter requests a prohibited permission");
            }
        }
    }

    public record AuthorizationRequest(
            @NotBlank String organizationId,
            @NotBlank String authorizationBoundaryId,
            @NotBlank String profile,
            @NotBlank String sourceCommit,
            @NotBlank String artifactDigest,
            @NotBlank String deploymentRevision,
            @NotBlank String evidenceManifestHash,
            @NotEmpty List<String> evidenceRefs,
            boolean controlAssessmentSatisfied,
            boolean coverageSufficient,
            boolean criticalRiskOpen,
            boolean expiredExceptionOpen,
            boolean activeIncident,
            boolean independentAssessment,
            String humanRiskApprover,
            Instant validUntil,
            Map<String, String> conditions) {
        public AuthorizationRequest {
            evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs);
            conditions = conditions == null ? Map.of() : Map.copyOf(conditions);
        }
    }

    public record AuthorizationResult(
            String schemaVersion,
            String engine,
            AuthorizationDecision decision,
            boolean internalDecisionOnly,
            boolean externalCertificationGranted,
            List<String> reasonCodes,
            Map<String, String> conditions,
            Instant validFrom,
            Instant validUntil,
            String evidenceManifestHash,
            List<String> evidenceRefs) {}

    static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }

    private static boolean prohibited(String permission) {
        String normalized = permission.toUpperCase(java.util.Locale.ROOT);
        return normalized.contains("MODIFY_PRODUCTION") || normalized.contains("DUMP_SECRET")
                || normalized.contains("DISABLE_CONTROL") || normalized.contains("DELETE_EVIDENCE")
                || normalized.contains("ACCEPT_RISK");
    }
}
