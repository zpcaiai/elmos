package io.elmos.testquality;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public final class QualityDomainModels {
    private QualityDomainModels() {}

    public record TestCaseIdentity(String testCaseId, String repositoryId, String module, String framework,
                                   String suite, String classOrFile, String logicalName,
                                   List<String> parameters, String environmentProfile) {
        public TestCaseIdentity {
            required(testCaseId, "testCaseId"); required(repositoryId, "repositoryId"); required(module, "module");
            required(framework, "framework"); required(suite, "suite"); required(logicalName, "logicalName");
            required(environmentProfile, "environmentProfile"); parameters = List.copyOf(parameters);
        }
    }
    public record TestCountReconciliation(int source, int discovered, int executed, int reported, List<String> findings) {
        public TestCountReconciliation { findings = List.copyOf(findings); }
        public boolean reconciled() { return source == discovered && discovered == executed && executed == reported; }
    }
    public record QualityRisk(String riskId, String subjectId, String inherentRisk, String residualRisk,
                              String coverageStatus, String riskModelVersion, List<String> evidenceRefs) {
        public QualityRisk { evidenceRefs = List.copyOf(evidenceRefs); required(riskModelVersion, "riskModelVersion"); }
    }
    public record CoverageEdge(String testCaseId, String subjectId, String relationship,
                               String strength, List<String> evidenceRefs) {
        public CoverageEdge { evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record TestPortfolio(String portfolioId, int version, List<String> criticalRiskRefs,
                                List<String> layers, String costModelRef, List<String> evidenceRefs) {
        public TestPortfolio { criticalRiskRefs = List.copyOf(criticalRiskRefs); layers = List.copyOf(layers); evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record CharacterizationScenario(String scenarioId, String inputFixtureRef, List<String> observations,
                                           List<String> normalizations, List<String> knownDefects) {
        public CharacterizationScenario { observations = List.copyOf(observations); normalizations = List.copyOf(normalizations); knownDefects = List.copyOf(knownDefects); }
    }
    public record GoldenMaster(String goldenMasterId, String type, String artifactHash,
                               boolean humanApproved, String approvedBy, Instant approvedAt) {}
    public record ContractVerification(String contractId, String consumerVersion, String providerVersion,
                                       String status, boolean providerStateIsolated, List<String> evidenceRefs) {
        public ContractVerification { evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record PropertyRun(String propertyId, long seed, String minimalFailingExample,
                              String minimalFailingSequence, String status, List<String> evidenceRefs) {
        public PropertyRun { evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record MutationRun(String runId, int total, int covered, int killed, int survived,
                              double mutationCoverage, double testStrength, double mutationScore,
                              List<String> equivalentCandidateRefs, List<String> evidenceRefs) {
        public MutationRun { equivalentCandidateRefs = List.copyOf(equivalentCandidateRefs); evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record TestDataLease(String leaseId, String fixtureVersion, String classification,
                                Instant expiresAt, boolean destroyed, List<String> auditRefs) {
        public TestDataLease { auditRefs = List.copyOf(auditRefs); }
    }
    public record EnvironmentLease(String leaseId, String templateId, String namespace, String networkPolicy,
                                   Instant expiresAt, boolean cleanupVerified, List<String> evidenceRefs) {
        public EnvironmentLease {
            evidenceRefs = List.copyOf(evidenceRefs);
            if (!"DENY_BY_DEFAULT".equals(networkPolicy)) throw new IllegalArgumentException("environment network must default deny");
        }
    }
    public record AiTestCandidate(String candidateId, String source, String target, String contextHash,
                                  QualityModels.AiStatus status, List<String> generatedFiles, List<String> evidenceRefs) {
        public AiTestCandidate { generatedFiles = List.copyOf(generatedFiles); evidenceRefs = List.copyOf(evidenceRefs); }
    }
    public record FlakyProfile(String testCaseId, String status, int observations, double failureRate,
                               String cause, List<String> attemptEvidenceRefs) {
        public FlakyProfile { attemptEvidenceRefs = List.copyOf(attemptEvidenceRefs); }
    }
    public record TestSelection(String selectionId, String graphVersion, String riskVersion,
                                List<String> selected, List<String> unselected, List<String> unknowns,
                                Map<String, String> reasons) {
        public TestSelection { selected = List.copyOf(selected); unselected = List.copyOf(unselected); unknowns = List.copyOf(unknowns); reasons = Map.copyOf(reasons); }
    }
    public record QualityDecision(String scopeId, QualityModels.GateStatus decision,
                                  QualityModels.Confidence confidence, String evidenceManifestHash,
                                  List<String> conditions, List<String> blockers, boolean workerModifiedGate) {
        public QualityDecision {
            conditions = List.copyOf(conditions); blockers = List.copyOf(blockers);
            if (workerModifiedGate) throw new IllegalArgumentException("worker cannot modify quality gate");
        }
    }
    public record ContinuousValidationPlan(String planId, List<String> triggers, List<String> frequencies,
                                           List<String> safeProductionModes, List<String> evidenceInvalidators) {
        public ContinuousValidationPlan { triggers = List.copyOf(triggers); frequencies = List.copyOf(frequencies); safeProductionModes = List.copyOf(safeProductionModes); evidenceInvalidators = List.copyOf(evidenceInvalidators); }
    }
    public record ProductionDefectLearning(String defectId, String failureFingerprint,
                                           String regressionTestRef, boolean failBeforeFixProven,
                                           List<String> riskUpdates, List<String> evidenceRefs) {
        public ProductionDefectLearning { riskUpdates = List.copyOf(riskUpdates); evidenceRefs = List.copyOf(evidenceRefs); }
    }

    private static void required(String value, String name) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required");
    }
}
