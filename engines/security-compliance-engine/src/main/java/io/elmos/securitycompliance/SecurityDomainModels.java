package io.elmos.securitycompliance;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import static io.elmos.securitycompliance.SecurityModels.ExternalStatus;

public final class SecurityDomainModels {
    private SecurityDomainModels() {}

    public enum Severity { INFO, LOW, MEDIUM, HIGH, CRITICAL }
    public enum Reachability { REACHABLE, POTENTIALLY_REACHABLE, NOT_REACHABLE_EVIDENCED, NOT_LOADED, UNKNOWN }
    public enum RiskDecision { REMEDIATE, MITIGATE, ACCEPTANCE_REQUIRED, NOT_AFFECTED, FALSE_POSITIVE, INVESTIGATE }
    public enum VexStatus { AFFECTED, NOT_AFFECTED, FIXED, UNDER_INVESTIGATION }
    public enum AssessmentResult { SATISFIED, OTHER_THAN_SATISFIED, NOT_APPLICABLE, NOT_ASSESSED, INCONCLUSIVE }

    public record EvidenceBinding(
            String sourceCommit, String artifactDigest, String deploymentRevision,
            String infrastructureStateVersion, String policyVersion, String identityConfigurationVersion,
            String dataClassificationVersion, String threatModelVersion) {
        public EvidenceBinding {
            require(sourceCommit, "sourceCommit"); require(artifactDigest, "artifactDigest");
            require(deploymentRevision, "deploymentRevision"); require(infrastructureStateVersion, "infrastructureStateVersion");
            require(policyVersion, "policyVersion"); require(identityConfigurationVersion, "identityConfigurationVersion");
            require(dataClassificationVersion, "dataClassificationVersion"); require(threatModelVersion, "threatModelVersion");
        }
    }

    public record SecurityEstate(String organizationId, String estateId, long version,
                                 List<String> assetRefs, List<String> trustBoundaryRefs,
                                 List<String> unknowns, List<String> evidenceRefs) {
        public SecurityEstate {
            require(organizationId, "organizationId"); require(estateId, "estateId");
            if (version < 1) throw new IllegalArgumentException("estate version must be positive");
            assetRefs = List.copyOf(assetRefs); trustBoundaryRefs = List.copyOf(trustBoundaryRefs);
            unknowns = List.copyOf(unknowns); evidenceRefs = requiredEvidence(evidenceRefs);
        }
    }

    public record SecurityFinding(String findingId, String assetId, String category, Severity severity,
                                  double confidence, String status, String sourceTool, String sourceRule,
                                  List<String> evidenceRefs) {
        public SecurityFinding {
            require(findingId, "findingId"); require(assetId, "assetId"); require(category, "category");
            Objects.requireNonNull(severity); require(status, "status"); require(sourceTool, "sourceTool"); require(sourceRule, "sourceRule");
            if (confidence < 0 || confidence > 1) throw new IllegalArgumentException("confidence must be between zero and one");
            evidenceRefs = requiredEvidence(evidenceRefs);
        }
    }

    public record Vulnerability(String vulnerabilityId, List<String> aliases, String affectedComponentRef) {
        public Vulnerability { require(vulnerabilityId, "vulnerabilityId"); aliases = List.copyOf(aliases); require(affectedComponentRef, "affectedComponentRef"); }
    }
    public record Exposure(String exposureId, String vulnerabilityId, String assetId, Reachability reachability,
                           boolean internetExposed, boolean runtimeLoaded, List<String> evidenceRefs) {
        public Exposure {
            require(exposureId, "exposureId"); require(vulnerabilityId, "vulnerabilityId"); require(assetId, "assetId");
            Objects.requireNonNull(reachability); evidenceRefs = requiredEvidence(evidenceRefs);
        }
    }
    public record VulnerabilityRisk(String vulnerabilityId, String assetId, String riskLevel, int priority,
                                    List<String> reasonCodes, RiskDecision decision, Reachability reachability,
                                    List<String> evidenceRefs) {
        public VulnerabilityRisk {
            require(vulnerabilityId, "vulnerabilityId"); require(assetId, "assetId"); require(riskLevel, "riskLevel");
            if (priority < 0) throw new IllegalArgumentException("priority cannot be negative");
            reasonCodes = List.copyOf(reasonCodes); Objects.requireNonNull(decision); Objects.requireNonNull(reachability);
            evidenceRefs = requiredEvidence(evidenceRefs);
        }
    }

    public record ScanCoverage(long targetCount, long scannedCount, long excludedCount, long parseErrorCount,
                               long timeoutCount, Map<String, String> exclusions) {
        public ScanCoverage {
            if (targetCount < 0 || scannedCount < 0 || excludedCount < 0 || parseErrorCount < 0 || timeoutCount < 0) {
                throw new IllegalArgumentException("coverage counts cannot be negative");
            }
            exclusions = Map.copyOf(exclusions);
        }
        public ExternalStatus status(int findings) {
            if (parseErrorCount > 0 || timeoutCount > 0 || scannedCount + excludedCount < targetCount) return ExternalStatus.COVERAGE_INSUFFICIENT;
            return findings == 0 ? ExternalStatus.PASS : ExternalStatus.FAIL;
        }
    }

    public record VexStatement(String productRef, String componentRef, String vulnerabilityId, VexStatus status,
                               String justification, String analysis, String author, Instant expiresAt,
                               String reassessmentTrigger, List<String> evidenceRefs) {
        public VexStatement {
            require(productRef, "productRef"); require(componentRef, "componentRef"); require(vulnerabilityId, "vulnerabilityId");
            Objects.requireNonNull(status); require(author, "author"); Objects.requireNonNull(expiresAt); require(reassessmentTrigger, "reassessmentTrigger");
            evidenceRefs = evidenceRefs == null ? List.of() : List.copyOf(evidenceRefs);
            if (status == VexStatus.NOT_AFFECTED) {
                require(justification, "not affected justification"); require(analysis, "not affected analysis");
                if (evidenceRefs.isEmpty()) throw new IllegalArgumentException("not affected VEX requires evidence");
            }
        }
    }

    public record ControlAssessment(String controlId, String implementationId, AssessmentResult result,
                                    List<String> methods, List<String> evidenceRefs, String assessor) {
        public ControlAssessment {
            require(controlId, "controlId"); require(implementationId, "implementationId"); Objects.requireNonNull(result);
            methods = List.copyOf(methods); evidenceRefs = requiredEvidence(evidenceRefs); require(assessor, "assessor");
        }
    }

    public record RiskException(String exceptionId, String owner, String scope, String reason,
                                String businessJustification, String compensatingControlRef, String impact,
                                Instant startsAt, Instant expiresAt, String artifactDigest, String sourceCommit,
                                String environment, String approver, List<String> evidenceRefs) {
        public RiskException {
            require(exceptionId, "exceptionId"); require(owner, "owner"); require(scope, "scope"); require(reason, "reason");
            require(businessJustification, "businessJustification"); require(compensatingControlRef, "compensatingControlRef");
            require(impact, "impact"); Objects.requireNonNull(startsAt); Objects.requireNonNull(expiresAt);
            if (!expiresAt.isAfter(startsAt)) throw new IllegalArgumentException("risk exception must expire after it starts");
            require(artifactDigest, "artifactDigest"); require(sourceCommit, "sourceCommit"); require(environment, "environment");
            require(approver, "approver"); evidenceRefs = requiredEvidence(evidenceRefs);
        }
    }

    private static List<String> requiredEvidence(List<String> evidenceRefs) {
        var copy = List.copyOf(Objects.requireNonNull(evidenceRefs));
        if (copy.isEmpty()) throw new IllegalArgumentException("evidenceRefs must not be empty");
        return copy;
    }
    private static void require(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
