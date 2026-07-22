package io.elmos.hardening;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable Batch 10 Production Readiness Model and release-gate contracts. */
public final class ProductionHardeningModels {
    private ProductionHardeningModels() {}

    public enum RiskTier {
        TIER_0(0), TIER_1(1), TIER_2(2), TIER_3(3), TIER_4(4);
        private final int level;
        RiskTier(int level) { this.level = level; }
        public int level() { return level; }
    }
    public enum WorkloadKind { OPEN, CLOSED }
    public enum ScenarioKind { BASELINE, NORMAL, PEAK, BURST, STRESS, SPIKE, SOAK, RECOVERY,
        SECURITY, CHAOS, CRASH, RESTORE, PITR, DISASTER_RECOVERY, OBSERVABILITY,
        CANARY, ROLLBACK, COST }
    public enum EvidenceStatus { PASSED, FAILED, NOT_RUN, BLOCKED, INCONCLUSIVE, NOT_APPLICABLE }
    public enum Severity { INFO, LOW, MEDIUM, HIGH, CRITICAL }
    public enum Gate { BLOCKED, P_A, P_B, P_C, P_D, P_E, P_F }
    public enum RunStatus { INITIALIZED, PROFILING, PERFORMANCE_TESTING, SECURITY_TESTING,
        RESILIENCE_TESTING, RECOVERY_TESTING, OBSERVABILITY_TESTING, RELEASE_TESTING,
        READY_FOR_PROGRESSIVE_DELIVERY, READY_WITH_RESTRICTIONS, BLOCKED, FAILED_SAFELY }

    public record Request(Path artifactWorkspace, Path targetRepositoryPath, String hardeningRunId,
                          String migrationId, String targetSnapshotId, String targetArtifactId,
                          boolean batch9Eligible, ArtifactBinding artifact,
                          List<DeploymentUnit> deploymentUnits, List<RiskProfile> riskProfiles,
                          List<WorkloadModel> workloadModels, List<HardeningScenario> scenarios,
                          List<OpenRisk> openRisks, Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace"); required(targetRepositoryPath, "targetRepositoryPath");
            text(hardeningRunId, "hardeningRunId"); text(migrationId, "migrationId");
            text(targetSnapshotId, "targetSnapshotId"); text(targetArtifactId, "targetArtifactId");
            required(artifact, "artifact"); deploymentUnits = copy(deploymentUnits); riskProfiles = copy(riskProfiles);
            workloadModels = copy(workloadModels); scenarios = copy(scenarios); openRisks = copy(openRisks);
            required(policy, "policy"); required(observedAt, "observedAt");
            if (deploymentUnits.isEmpty()) throw new IllegalArgumentException("deployment units are required");
            if (!artifact.artifactId().equals(targetArtifactId) || !artifact.targetSnapshotId().equals(targetSnapshotId))
                throw new IllegalArgumentException("artifact binding does not match the hardening run");
            Path workspace = artifactWorkspace.toAbsolutePath().normalize();
            if (workspace.startsWith(targetRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("artifact workspace must be outside target repository");
        }
    }

    public record ArtifactBinding(String artifactId, String artifactDigest, String sourceSnapshotId,
                                  String targetSnapshotId, String buildEnvironmentHash, String dependencyLockHash,
                                  boolean immutable, boolean batch8Passed, boolean batch9Passed,
                                  String sbomRef, String provenanceRef, List<String> evidenceRefs) {
        public ArtifactBinding {
            text(artifactId, "artifactId"); digest(artifactDigest, "artifactDigest");
            text(sourceSnapshotId, "sourceSnapshotId"); text(targetSnapshotId, "targetSnapshotId");
            digest(buildEnvironmentHash, "buildEnvironmentHash"); digest(dependencyLockHash, "dependencyLockHash");
            text(sbomRef, "sbomRef"); text(provenanceRef, "provenanceRef"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record DeploymentUnit(String serviceId, String moduleId, boolean publicService,
                                 boolean payment, boolean authorization, boolean tenantAware,
                                 boolean transactionCritical, boolean regulated,
                                 int criticalEndpointCount, List<String> businessCapabilities) {
        public DeploymentUnit {
            text(serviceId, "serviceId"); text(moduleId, "moduleId"); businessCapabilities = copy(businessCapabilities);
            if (criticalEndpointCount < 0) throw new IllegalArgumentException("criticalEndpointCount cannot be negative");
        }
        public boolean highRisk() { return payment || authorization || tenantAware || transactionCritical || regulated; }
    }

    public record RiskProfile(String profileId, String serviceId, RiskTier tier,
                              double minimumHeadroomPercent, boolean requireSoak,
                              boolean requirePenetration, boolean requireBackupRestore,
                              boolean requirePitr, boolean requireDisasterRecovery,
                              boolean requireCanaryDrill, boolean requireRollbackDrill,
                              boolean approved, String approver, String approvalEvidenceRef) {
        public RiskProfile {
            text(profileId, "profileId"); text(serviceId, "serviceId"); required(tier, "tier");
            if (minimumHeadroomPercent < 0 || minimumHeadroomPercent > 100)
                throw new IllegalArgumentException("minimumHeadroomPercent is invalid");
            if (approved) { text(approver, "approver"); text(approvalEvidenceRef, "approvalEvidenceRef"); }
        }
    }

    public record WorkloadModel(String workloadId, String serviceId, WorkloadKind kind,
                                double normalRequestsPerSecond, double peakRequestsPerSecond,
                                double burstRequestsPerSecond, int burstDurationSeconds,
                                String endpointDistributionHash, String payloadDistributionHash,
                                String tenantDistributionHash, String sourceBaselineRef,
                                double confidence, boolean sanitized, boolean credentialsRemoved,
                                String version, List<String> evidenceRefs) {
        public WorkloadModel {
            text(workloadId, "workloadId"); text(serviceId, "serviceId"); required(kind, "kind");
            if (normalRequestsPerSecond <= 0 || peakRequestsPerSecond < normalRequestsPerSecond
                    || burstRequestsPerSecond < peakRequestsPerSecond || burstDurationSeconds < 1)
                throw new IllegalArgumentException("workload rates are invalid");
            digest(endpointDistributionHash, "endpointDistributionHash"); digest(payloadDistributionHash, "payloadDistributionHash");
            digest(tenantDistributionHash, "tenantDistributionHash"); text(sourceBaselineRef, "sourceBaselineRef");
            rate(confidence, "confidence"); text(version, "version"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record HardeningScenario(String scenarioId, String serviceId, String artifactId,
                                    ScenarioKind kind, boolean critical, boolean nonProduction,
                                    boolean usesProductionDependency, boolean destructive,
                                    boolean abortConditionsDefined, boolean killSwitchDefined,
                                    int timeoutSeconds, List<String> expectedEvidence) {
        public HardeningScenario {
            text(scenarioId, "scenarioId"); text(serviceId, "serviceId"); text(artifactId, "artifactId");
            required(kind, "kind"); expectedEvidence = copy(expectedEvidence);
            if (timeoutSeconds < 1) throw new IllegalArgumentException("scenario timeout must be positive");
            if (expectedEvidence.isEmpty()) throw new IllegalArgumentException("expected evidence is required");
        }
    }

    public record OpenRisk(String riskId, String serviceId, Severity severity, boolean releaseBlocking,
                           boolean approved, Instant expiresAt, String owner, String mitigation,
                           String fallback, String approvalEvidenceRef) {
        public OpenRisk {
            text(riskId, "riskId"); text(serviceId, "serviceId"); required(severity, "severity");
            required(expiresAt, "expiresAt"); text(owner, "owner"); text(mitigation, "mitigation"); text(fallback, "fallback");
            if (approved) text(approvalEvidenceRef, "approvalEvidenceRef");
        }
    }

    public record Policy(double maximumEnvironmentVariance, double requiredPerformancePassRate,
                         double requiredCriticalSecurityPassRate, double requiredCriticalChaosPassRate,
                         double requiredCriticalSliCoverage, double requiredAlertCoverage,
                         double requiredRunbookCoverage, double requiredTraceCoverage,
                         double highConfidencePerformancePassRate, double highConfidenceTraceCoverage,
                         double highConfidenceMinimumHeadroom, int maximumScenarios) {
        public Policy {
            rate(maximumEnvironmentVariance, "maximumEnvironmentVariance");
            rate(requiredPerformancePassRate, "requiredPerformancePassRate");
            rate(requiredCriticalSecurityPassRate, "requiredCriticalSecurityPassRate");
            rate(requiredCriticalChaosPassRate, "requiredCriticalChaosPassRate");
            rate(requiredCriticalSliCoverage, "requiredCriticalSliCoverage");
            rate(requiredAlertCoverage, "requiredAlertCoverage"); rate(requiredRunbookCoverage, "requiredRunbookCoverage");
            rate(requiredTraceCoverage, "requiredTraceCoverage"); rate(highConfidencePerformancePassRate, "highConfidencePerformancePassRate");
            rate(highConfidenceTraceCoverage, "highConfidenceTraceCoverage");
            if (highConfidenceMinimumHeadroom < 0 || highConfidenceMinimumHeadroom > 100 || maximumScenarios < 1)
                throw new IllegalArgumentException("hardening policy limits are invalid");
        }
    }

    public record ServiceCalibration(String serviceId, String artifactId, String environmentHash,
                                     boolean valid, double repeatedRunVariance, boolean warmupExcluded,
                                     boolean autoscalingDisabled, boolean generatorSaturated,
                                     boolean sourceResourcesComparable, boolean dataVolumeComparable,
                                     boolean productionResourceAccessed, boolean secretMaterialObserved,
                                     List<String> noiseSignals, List<String> evidenceRefs) {
        public ServiceCalibration {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); digest(environmentHash, "environmentHash");
            rate(repeatedRunVariance, "repeatedRunVariance"); noiseSignals = copy(noiseSignals); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record PerformanceEvidence(String serviceId, String artifactId, EvidenceStatus status,
                                      boolean normalLoadPassed, boolean peakLoadPassed, boolean stressComplete,
                                      boolean soakPassed, boolean p95SloPassed, boolean p99SloPassed,
                                      boolean errorRateSloPassed, boolean saturationControlled,
                                      boolean recoveredAfterOverload, double requiredScenarioPassRate,
                                      double headroomPercent, int criticalRegressions, int unexplainedLeaks,
                                      boolean unboundedResourceGrowth, boolean productionResourceAccessed,
                                      boolean secretMaterialObserved, String authorityId, List<String> evidenceRefs) {
        public PerformanceEvidence {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); required(status, "status");
            rate(requiredScenarioPassRate, "requiredScenarioPassRate");
            if (headroomPercent < 0 || headroomPercent > 100 || criticalRegressions < 0 || unexplainedLeaks < 0)
                throw new IllegalArgumentException("performance evidence values are invalid");
            text(authorityId, "authorityId"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record SecurityEvidence(String serviceId, String artifactId, EvidenceStatus status,
                                   int criticalVulnerabilities, int exploitableHighVulnerabilities,
                                   int criticalSastFindings, int criticalDastFindings, int secretLeaks,
                                   int authenticationRegressions, int authorizationRegressions,
                                   int tenantIsolationRegressions, int weakCryptographyFindings,
                                   int criticalConfigurationFindings, int unknownOriginBinaries,
                                   int unapprovedSecurityWaivers, double criticalScenarioPassRate,
                                   boolean penetrationPassed,
                                   boolean sbomComplete, boolean sbomMatchesArtifact, boolean fixedImageDigest,
                                   boolean nonRootLeastPrivilege, boolean productionResourceAccessed,
                                   boolean secretMaterialObserved, String authorityId, List<String> evidenceRefs) {
        public SecurityEvidence {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); required(status, "status");
            rate(criticalScenarioPassRate, "criticalScenarioPassRate");
            if (List.of(criticalVulnerabilities, exploitableHighVulnerabilities, criticalSastFindings,
                    criticalDastFindings, secretLeaks, authenticationRegressions, authorizationRegressions,
                    tenantIsolationRegressions, weakCryptographyFindings, criticalConfigurationFindings,
                    unknownOriginBinaries, unapprovedSecurityWaivers).stream().anyMatch(value -> value < 0))
                throw new IllegalArgumentException("security counts cannot be negative");
            text(authorityId, "authorityId"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ReliabilityEvidence(String serviceId, String artifactId, EvidenceStatus status,
                                      double criticalChaosPassRate, double recoveryScenarioPassRate,
                                      int dataCorruptionEvents, int unboundedRetries, int unboundedQueues,
                                      int retryStorms, boolean crashConsistencyPassed,
                                      boolean dependencyRecoveryPassed, boolean backupRestorePassed,
                                      boolean pitrPassed, boolean rpoPassed, boolean rtoPassed,
                                      boolean failoverAndFailbackPassed, boolean abortAndKillSwitchesVerified,
                                      boolean productionResourceAccessed, boolean destructiveProductionChaos,
                                      boolean secretMaterialObserved, String authorityId, List<String> evidenceRefs) {
        public ReliabilityEvidence {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); required(status, "status");
            rate(criticalChaosPassRate, "criticalChaosPassRate"); rate(recoveryScenarioPassRate, "recoveryScenarioPassRate");
            if (dataCorruptionEvents < 0 || unboundedRetries < 0 || unboundedQueues < 0 || retryStorms < 0)
                throw new IllegalArgumentException("reliability counts cannot be negative");
            text(authorityId, "authorityId"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ObservabilityEvidence(String serviceId, String artifactId, EvidenceStatus status,
                                        double criticalSliCoverage, double alertCoverage,
                                        double runbookCoverage, double traceCoverage,
                                        boolean sloCalculable, boolean criticalAlertsTested,
                                        boolean criticalRunbooksValidated, boolean correlationPassed,
                                        boolean telemetryOverheadWithinBudget, int sensitiveTelemetryLeaks,
                                        int unboundedMetricLabels, boolean productionResourceAccessed,
                                        boolean secretMaterialObserved, String authorityId, List<String> evidenceRefs) {
        public ObservabilityEvidence {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); required(status, "status");
            rate(criticalSliCoverage, "criticalSliCoverage"); rate(alertCoverage, "alertCoverage");
            rate(runbookCoverage, "runbookCoverage"); rate(traceCoverage, "traceCoverage");
            if (sensitiveTelemetryLeaks < 0 || unboundedMetricLabels < 0)
                throw new IllegalArgumentException("observability counts cannot be negative");
            text(authorityId, "authorityId"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ReleaseEvidence(String serviceId, String artifactId, EvidenceStatus status,
                                  boolean artifactImmutable, boolean artifactSigned,
                                  boolean signatureVerified, boolean provenanceComplete,
                                  boolean reproducibleBuildPassed, boolean sbomComplete,
                                  boolean canaryPlanValidated, boolean canaryDrillPassed,
                                  boolean rollbackPlanValidated, boolean rollbackDrillPassed,
                                  boolean schemaCompatibilityPassed, boolean forwardFixRunbookValidated,
                                  int openCriticalRisks, int unapprovedRisks,
                                  boolean progressiveDeliveryOnly, boolean productionDeploymentExecuted,
                                  boolean productionResourceAccessed, boolean secretMaterialObserved,
                                  String authorityId, List<String> evidenceRefs) {
        public ReleaseEvidence {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); required(status, "status");
            if (openCriticalRisks < 0 || unapprovedRisks < 0) throw new IllegalArgumentException("risk counts cannot be negative");
            text(authorityId, "authorityId"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record CostEvidence(String serviceId, String artifactId, EvidenceStatus status,
                               BigDecimal normalCost, BigDecimal peakCost, BigDecimal unitCost,
                               boolean sourceComparable, boolean assumptionsVersioned,
                               boolean headroomAndDrIncluded, boolean sloPreserved,
                               String currency, String authorityId, List<String> evidenceRefs) {
        public CostEvidence {
            text(serviceId, "serviceId"); text(artifactId, "artifactId"); required(status, "status");
            required(normalCost, "normalCost"); required(peakCost, "peakCost"); required(unitCost, "unitCost");
            if (normalCost.signum() < 0 || peakCost.signum() < 0 || unitCost.signum() < 0)
                throw new IllegalArgumentException("cost cannot be negative");
            text(currency, "currency"); text(authorityId, "authorityId"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record Metrics(double requiredPerformanceScenarioPassRate, double criticalSecurityScenarioPassRate,
                          double criticalChaosScenarioPassRate, double recoveryScenarioPassRate,
                          double criticalSliCoverage, double alertCoverage, double runbookCoverage,
                          double traceCoverage, double headroomPercent, int criticalVulnerabilities,
                          int exploitableHighVulnerabilities, int securityRegressions,
                          int dataCorruptionEvents, int unexplainedLeaks, int openCriticalRisks) {
        public Metrics {
            rate(requiredPerformanceScenarioPassRate, "requiredPerformanceScenarioPassRate");
            rate(criticalSecurityScenarioPassRate, "criticalSecurityScenarioPassRate");
            rate(criticalChaosScenarioPassRate, "criticalChaosScenarioPassRate");
            rate(recoveryScenarioPassRate, "recoveryScenarioPassRate"); rate(criticalSliCoverage, "criticalSliCoverage");
            rate(alertCoverage, "alertCoverage"); rate(runbookCoverage, "runbookCoverage"); rate(traceCoverage, "traceCoverage");
        }
    }

    public record ServiceGate(String serviceId, Gate gate, boolean eligibleForProgressiveDelivery,
                              boolean productionReady, boolean eligibleForCutover,
                              List<String> blockers, List<String> restrictions, Metrics metrics,
                              List<String> evidenceRefs) {
        public ServiceGate {
            text(serviceId, "serviceId"); required(gate, "gate"); blockers = copy(blockers);
            restrictions = copy(restrictions); required(metrics, "metrics"); evidenceRefs = copy(evidenceRefs);
            if (productionReady || eligibleForCutover)
                throw new IllegalArgumentException("Batch 10 never declares production completion or cutover eligibility");
        }
    }

    public record ConformanceReport(int batch, String hardeningRunId, String artifactId,
                                    RunStatus status, List<ServiceGate> services,
                                    List<String> blockers, boolean eligibleForProgressiveDelivery,
                                    boolean productionReady, boolean eligibleForCutover,
                                    Instant evaluatedAt) {
        public ConformanceReport {
            if (batch != 10) throw new IllegalArgumentException("batch must be 10");
            text(hardeningRunId, "hardeningRunId"); text(artifactId, "artifactId"); required(status, "status");
            services = copy(services); blockers = copy(blockers); required(evaluatedAt, "evaluatedAt");
            if (productionReady || eligibleForCutover)
                throw new IllegalArgumentException("Batch 10 only admits progressive delivery");
        }
    }

    public record Outcome(Request request, Map<String,ServiceCalibration> calibrations,
                          Map<String,PerformanceEvidence> performance,
                          Map<String,SecurityEvidence> security,
                          Map<String,ReliabilityEvidence> reliability,
                          Map<String,ObservabilityEvidence> observability,
                          Map<String,ReleaseEvidence> release,
                          Map<String,CostEvidence> costs, ConformanceReport report) {
        public Outcome {
            calibrations = map(calibrations); performance = map(performance); security = map(security);
            reliability = map(reliability); observability = map(observability); release = map(release);
            costs = map(costs); required(report, "report");
        }
    }

    static <T> List<T> copy(Collection<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static <K,V> Map<K,V> map(Map<K,V> values) { return values == null ? Map.of() : Map.copyOf(values); }
    static void text(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    static void required(Object value, String name) { if (value == null) throw new IllegalArgumentException(name + " is required"); }
    static void digest(String value, String name) { text(value, name); if (!value.matches("[A-Fa-f0-9]{64}")) throw new IllegalArgumentException(name + " must be sha-256"); }
    static void rate(double value, String name) { if (Double.isNaN(value) || value < 0 || value > 1) throw new IllegalArgumentException(name + " must be between 0 and 1"); }
}
