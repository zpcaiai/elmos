package io.elmos.equivalence;

import java.math.BigDecimal;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

/** Immutable Batch 9 observable-behavior, differential-comparison and gate contracts. */
public final class BehaviorEquivalenceModels {
    private BehaviorEquivalenceModels() {}

    public enum SystemRole { SOURCE, TARGET }
    public enum RunStatus { INITIALIZED, BASELINE_ALIGNED, CAPTURING, COMPARING, TRIAGING,
        EQUIVALENT, EQUIVALENT_WITH_APPROVED_DIFFERENCES, PARTIALLY_EQUIVALENT,
        REGRESSION_DETECTED, NOT_COMPARABLE, BLOCKED }
    public enum ScenarioCategory { HTTP, MESSAGE, DATABASE, FILE, FUNCTION, JOB,
        PROPERTY, METAMORPHIC, CONCURRENCY, TIME_BOUNDARY, FAILURE_PATH }
    public enum Criticality { LOW, MEDIUM, HIGH, CRITICAL }
    public enum ObservationType { RETURN_VALUE, HTTP_RESPONSE, DATABASE_STATE, DATABASE_WRITE_TRACE,
        MESSAGE_EVENT, FILE_OUTPUT, OBJECT_STORAGE_OUTPUT, CACHE_STATE, EXTERNAL_CALL, EXCEPTION,
        LOG, AUDIT, METRIC, RESOURCE_LIFECYCLE, CONCURRENCY }
    public enum CollectorStatus { COMPLETE, FAILED, INCOMPLETE }
    public enum ComparisonStatus { EQUIVALENT, EQUIVALENT_AFTER_NORMALIZATION, WITHIN_TOLERANCE,
        APPROVED_CHANGE, REGRESSION, UNKNOWN, NOT_COMPARABLE }
    public enum OracleStatus { PASSED, FAILED, UNKNOWN, NOT_RUN }
    public enum Severity { INFO, LOW, MEDIUM, HIGH, CRITICAL }
    public enum RootCause { TYPE_MAPPING, NUMERIC_SEMANTICS, NULLABILITY, COLLECTION_ORDER,
        EVALUATION_ORDER, EXCEPTION_MAPPING, ASYNC_SCHEDULER, TRANSACTION, ORM, SERIALIZATION,
        DEPENDENCY_API, FRAMEWORK_BINDING, SECURITY, CONFIGURATION, MESSAGE_SEMANTICS, CACHE,
        SCHEDULER, TIME, RANDOMNESS, EXTERNAL_SERVICE, TEST_DATA, COLLECTOR, SOURCE_BUG, UNKNOWN }
    public enum DecisionOrigin { DETERMINISTIC_ORACLE, HUMAN_REVIEW, AGENT }
    public enum GoldenStatus { CANDIDATE, CAPTURED, REVIEWED, APPROVED, DEPRECATED,
        INVALIDATED, SUPERSEDED, REJECTED }
    public enum Gate { BLOCKED, E_A, E_B, E_C, E_D, E_E }

    public record Request(Path artifactWorkspace, Path sourceRepositoryPath, Path targetRepositoryPath,
                          String equivalenceRunId, String migrationId, String sourceSnapshotId,
                          String targetSnapshotId, boolean batch8Eligible,
                          RuntimeProfile sourceRuntime, RuntimeProfile targetRuntime,
                          List<ModuleScope> modules, List<Scenario> scenarios,
                          List<ObservationPoint> observationPoints, List<SemanticObligation> obligations,
                          List<CanonicalizationRule> normalizationRules, List<Tolerance> tolerances,
                          List<ApprovedChange> approvedChanges, List<GoldenMaster> goldenMasters,
                          Policy policy, Instant observedAt) {
        public Request {
            required(artifactWorkspace, "artifactWorkspace");
            required(sourceRepositoryPath, "sourceRepositoryPath");
            required(targetRepositoryPath, "targetRepositoryPath");
            text(equivalenceRunId, "equivalenceRunId"); text(migrationId, "migrationId");
            text(sourceSnapshotId, "sourceSnapshotId"); text(targetSnapshotId, "targetSnapshotId");
            required(sourceRuntime, "sourceRuntime"); required(targetRuntime, "targetRuntime");
            required(policy, "policy"); required(observedAt, "observedAt");
            modules = copy(modules); scenarios = copy(scenarios); observationPoints = copy(observationPoints);
            obligations = copy(obligations); normalizationRules = copy(normalizationRules);
            tolerances = copy(tolerances); approvedChanges = copy(approvedChanges); goldenMasters = copy(goldenMasters);
            if (modules.isEmpty()) throw new IllegalArgumentException("modules are required");
            if (scenarios.isEmpty()) throw new IllegalArgumentException("scenarios are required");
            if (sourceRuntime.role() != SystemRole.SOURCE || targetRuntime.role() != SystemRole.TARGET)
                throw new IllegalArgumentException("runtime roles must be source and target");
            if (!sourceRuntime.snapshotId().equals(sourceSnapshotId) || !targetRuntime.snapshotId().equals(targetSnapshotId))
                throw new IllegalArgumentException("runtime snapshots must match the frozen run snapshots");
            Path artifacts = artifactWorkspace.toAbsolutePath().normalize();
            if (artifacts.startsWith(sourceRepositoryPath.toAbsolutePath().normalize())
                    || artifacts.startsWith(targetRepositoryPath.toAbsolutePath().normalize()))
                throw new IllegalArgumentException("artifact workspace must be outside source and target repositories");
        }
    }

    public record RuntimeProfile(SystemRole role, String snapshotId, String runtimeVersion,
                                 String environmentId, Map<String,String> mutableResources,
                                 boolean productionAccessAllowed, List<String> evidenceRefs) {
        public RuntimeProfile {
            required(role, "role"); text(snapshotId, "snapshotId"); text(runtimeVersion, "runtimeVersion");
            text(environmentId, "environmentId"); mutableResources = map(mutableResources);
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ModuleScope(String moduleId, int publicEndpointCount, int criticalEndpointCount,
                              boolean highRisk, List<String> businessCapabilities) {
        public ModuleScope {
            text(moduleId, "moduleId"); businessCapabilities = copy(businessCapabilities);
            if (publicEndpointCount < 0 || criticalEndpointCount < 0 || criticalEndpointCount > publicEndpointCount)
                throw new IllegalArgumentException("endpoint counts are invalid");
        }
    }

    public record Scenario(String scenarioId, String moduleId, ScenarioCategory category,
                           Criticality criticality, boolean required, boolean securitySensitive,
                           boolean moneySensitive, boolean transactionSensitive,
                           Set<ObservationType> expectedObservations, Set<String> requiredOracleIds,
                           List<String> obligationIds, String origin, String initialStateHash,
                           String externalRecordingId, String clockId, Long randomSeed,
                           String sourceTargetTraceRef) {
        public Scenario {
            text(scenarioId, "scenarioId"); text(moduleId, "moduleId"); BehaviorEquivalenceModels.required(category, "category");
            BehaviorEquivalenceModels.required(criticality, "criticality"); expectedObservations = set(expectedObservations);
            requiredOracleIds = set(requiredOracleIds); obligationIds = copy(obligationIds);
            text(origin, "origin"); digest(initialStateHash, "initialStateHash");
            text(externalRecordingId, "externalRecordingId"); text(clockId, "clockId");
            if (expectedObservations.isEmpty()) throw new IllegalArgumentException("expected observations are required");
            if (requiredOracleIds.isEmpty()) throw new IllegalArgumentException("required oracles are required");
        }
        public boolean critical() { return criticality == Criticality.CRITICAL; }
        public boolean highRisk() { return securitySensitive || moneySensitive || transactionSensitive; }
    }

    public record ObservationPoint(String pointId, String moduleId, ObservationType type,
                                   boolean required, String sensitivity, String collectorId) {
        public ObservationPoint {
            text(pointId, "pointId"); text(moduleId, "moduleId"); BehaviorEquivalenceModels.required(type, "type");
            text(sensitivity, "sensitivity"); text(collectorId, "collectorId");
        }
    }

    public record SemanticObligation(String obligationId, String moduleId, boolean blocking,
                                     boolean resolved, List<String> scenarioIds, String owner) {
        public SemanticObligation {
            text(obligationId, "obligationId"); text(moduleId, "moduleId"); scenarioIds = copy(scenarioIds);
        }
    }

    public record CanonicalizationRule(String ruleId, String version, ObservationType observationType,
                                       String fieldPath, String transformation, boolean semanticImpactNone,
                                       boolean conditional, String approvalEvidenceRef) {
        public CanonicalizationRule {
            text(ruleId, "ruleId"); text(version, "version"); required(observationType, "observationType");
            text(fieldPath, "fieldPath"); text(transformation, "transformation");
            if (conditional) text(approvalEvidenceRef, "approvalEvidenceRef");
        }
    }

    public record Tolerance(String toleranceId, String scenarioId, ObservationType observationType,
                            String fieldPath, String type, BigDecimal value, BigDecimal floor,
                            String rationale, Instant expiresAt, String approver,
                            String approvalEvidenceRef, boolean highRiskApproved) {
        public Tolerance {
            text(toleranceId, "toleranceId"); text(scenarioId, "scenarioId");
            required(observationType, "observationType"); text(fieldPath, "fieldPath"); text(type, "type");
            required(value, "value"); text(rationale, "rationale"); required(expiresAt, "expiresAt");
            text(approver, "approver"); text(approvalEvidenceRef, "approvalEvidenceRef");
            if (value.signum() < 0) throw new IllegalArgumentException("tolerance cannot be negative");
        }
    }

    public record ApprovedChange(String changeId, String scenarioId, ObservationType observationType,
                                 String businessReason, String versionStrategy, String approver,
                                 String approvalEvidenceRef, boolean highRiskApproved) {
        public ApprovedChange {
            text(changeId, "changeId"); text(scenarioId, "scenarioId"); required(observationType, "observationType");
            text(businessReason, "businessReason"); text(versionStrategy, "versionStrategy");
            text(approver, "approver"); text(approvalEvidenceRef, "approvalEvidenceRef");
        }
    }

    public record GoldenMaster(String goldenId, String scenarioId, String sourceSnapshotId,
                               String environmentHash, String inputHash, String initialStateHash,
                               String rawObservationRef, String canonicalObservationRef,
                               String normalizationProfileId, GoldenStatus status,
                               String reviewer, String approvalEvidenceRef) {
        public GoldenMaster {
            text(goldenId, "goldenId"); text(scenarioId, "scenarioId"); text(sourceSnapshotId, "sourceSnapshotId");
            digest(environmentHash, "environmentHash"); digest(inputHash, "inputHash");
            digest(initialStateHash, "initialStateHash"); text(rawObservationRef, "rawObservationRef");
            text(canonicalObservationRef, "canonicalObservationRef"); text(normalizationProfileId, "normalizationProfileId");
            required(status, "status");
        }
        public boolean trusted() { return status == GoldenStatus.REVIEWED || status == GoldenStatus.APPROVED; }
    }

    public record Policy(int requiredCleanRuns, double publicEndpointEquivalenceThreshold,
                         double requiredScenarioEquivalenceThreshold, double highConfidenceThreshold,
                         double propertyPassThreshold, double metamorphicPassThreshold,
                         double maximumFlakyDifferenceRate, double observationCoverageThreshold,
                         double traceCoverageThreshold, int maximumScenarios, int scenarioTimeoutSeconds) {
        public Policy {
            if (requiredCleanRuns < 2 || maximumScenarios < 1 || scenarioTimeoutSeconds < 1)
                throw new IllegalArgumentException("equivalence policy limits are invalid");
            rate(publicEndpointEquivalenceThreshold, "publicEndpointEquivalenceThreshold");
            rate(requiredScenarioEquivalenceThreshold, "requiredScenarioEquivalenceThreshold");
            rate(highConfidenceThreshold, "highConfidenceThreshold");
            rate(propertyPassThreshold, "propertyPassThreshold"); rate(metamorphicPassThreshold, "metamorphicPassThreshold");
            rate(maximumFlakyDifferenceRate, "maximumFlakyDifferenceRate");
            rate(observationCoverageThreshold, "observationCoverageThreshold"); rate(traceCoverageThreshold, "traceCoverageThreshold");
        }
    }

    public record EnvironmentAlignment(boolean sourceReady, boolean targetReady, boolean isolated,
                                       boolean businessConfigurationAligned, boolean featureFlagsAligned,
                                       boolean localeAligned, boolean timezoneAligned, boolean databaseAligned,
                                       boolean cacheAligned, boolean messageStateAligned,
                                       boolean externalResponsesAligned, boolean virtualClockControlled,
                                       boolean randomnessControlled, boolean cleanEnvironment,
                                       boolean productionResourceAccessed, boolean secretMaterialObserved,
                                       List<String> differences, List<String> evidenceRefs) {
        public EnvironmentAlignment { differences = copy(differences); evidenceRefs = copy(evidenceRefs); }
        public boolean comparable() {
            return sourceReady && targetReady && isolated && businessConfigurationAligned && featureFlagsAligned
                    && localeAligned && timezoneAligned && databaseAligned && cacheAligned && messageStateAligned
                    && externalResponsesAligned && virtualClockControlled && randomnessControlled && cleanEnvironment
                    && !productionResourceAccessed && !secretMaterialObserved;
        }
    }

    public record Observation(String observationId, String scenarioId, String moduleId, SystemRole systemRole,
                              ObservationType observationType, String rawRef, String rawHash,
                              String canonicalRef, String canonicalHash, Map<String,String> facts,
                              CollectorStatus collectorStatus, boolean sensitiveDataRedacted,
                              List<String> evidenceRefs) {
        public Observation {
            text(observationId, "observationId"); text(scenarioId, "scenarioId"); text(moduleId, "moduleId");
            required(systemRole, "systemRole"); required(observationType, "observationType");
            text(rawRef, "rawRef"); digest(rawHash, "rawHash"); text(canonicalRef, "canonicalRef");
            digest(canonicalHash, "canonicalHash"); facts = map(facts); required(collectorStatus, "collectorStatus");
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record ScenarioExecution(String scenarioId, List<Observation> sourceObservations,
                                    List<Observation> targetObservations, boolean cleanEnvironment,
                                    boolean productionSideEffect, boolean secretLeak, boolean crossContamination,
                                    List<String> collectorFailures, List<String> evidenceRefs) {
        public ScenarioExecution {
            text(scenarioId, "scenarioId"); sourceObservations = copy(sourceObservations);
            targetObservations = copy(targetObservations); collectorFailures = copy(collectorFailures);
            evidenceRefs = copy(evidenceRefs);
        }
    }

    public record CleanRun(int runIndex, List<ScenarioExecution> scenarios, List<String> evidenceRefs) {
        public CleanRun {
            if (runIndex < 1) throw new IllegalArgumentException("runIndex must be positive");
            scenarios = copy(scenarios); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record OracleResult(String oracleId, OracleStatus status, boolean required,
                               String detail, List<String> evidenceRefs) {
        public OracleResult {
            text(oracleId, "oracleId"); BehaviorEquivalenceModels.required(status, "status"); evidenceRefs = copy(evidenceRefs);
        }
    }

    public record Comparison(String comparisonId, String scenarioId, String moduleId,
                             String sourceObservationId, String targetObservationId,
                             ObservationType observationType, String rawDifferenceRef,
                             String canonicalDifferenceRef, List<OracleResult> oracleResults,
                             ComparisonStatus status, Severity severity, RootCause rootCause,
                             List<String> obligationIds, String evidenceId, String toleranceId,
                             String approvedChangeId, DecisionOrigin decisionOrigin,
                             boolean flaky, boolean sourceTargetTraceLinked) {
        public Comparison {
            text(comparisonId, "comparisonId"); text(scenarioId, "scenarioId"); text(moduleId, "moduleId");
            text(sourceObservationId, "sourceObservationId"); text(targetObservationId, "targetObservationId");
            required(observationType, "observationType"); text(rawDifferenceRef, "rawDifferenceRef");
            text(canonicalDifferenceRef, "canonicalDifferenceRef"); oracleResults = copy(oracleResults);
            required(status, "status"); required(severity, "severity"); required(rootCause, "rootCause");
            obligationIds = copy(obligationIds); text(evidenceId, "evidenceId"); required(decisionOrigin, "decisionOrigin");
        }
        public boolean acceptable() {
            return Set.of(ComparisonStatus.EQUIVALENT, ComparisonStatus.EQUIVALENT_AFTER_NORMALIZATION,
                    ComparisonStatus.WITHIN_TOLERANCE, ComparisonStatus.APPROVED_CHANGE).contains(status) && !flaky;
        }
        public boolean strictEquivalent() {
            return Set.of(ComparisonStatus.EQUIVALENT, ComparisonStatus.EQUIVALENT_AFTER_NORMALIZATION).contains(status) && !flaky;
        }
    }

    public record ComparisonRequest(Request request, Scenario scenario, Observation source,
                                    Observation target, int cleanRunIndex) {}

    public record RepairFeedback(String clusterId, String moduleId, RootCause rootCause,
                                 List<String> comparisonIds, List<String> evidenceRefs,
                                 boolean batch8RepairCandidate) {
        public RepairFeedback { text(clusterId, "clusterId"); text(moduleId, "moduleId"); comparisonIds = copy(comparisonIds); evidenceRefs = copy(evidenceRefs); }
    }

    public record Metrics(double criticalScenarioCoverage, double publicEndpointCoverage,
                          double databaseEffectCoverage, double transactionFailurePathCoverage,
                          double observationCoverage, double criticalScenarioEquivalence,
                          double requiredScenarioEquivalence, double propertyDifferentialPassRate,
                          double metamorphicRelationPassRate, double flakyDifferenceRate,
                          double sourceTargetTraceCoverage, long approvedChanges, long regressions,
                          long unknownDifferences, int stableCleanRuns) {
        public Metrics {
            rate(criticalScenarioCoverage, "criticalScenarioCoverage"); rate(publicEndpointCoverage, "publicEndpointCoverage");
            rate(databaseEffectCoverage, "databaseEffectCoverage"); rate(transactionFailurePathCoverage, "transactionFailurePathCoverage");
            rate(observationCoverage, "observationCoverage"); rate(criticalScenarioEquivalence, "criticalScenarioEquivalence");
            rate(requiredScenarioEquivalence, "requiredScenarioEquivalence"); rate(propertyDifferentialPassRate, "propertyDifferentialPassRate");
            rate(metamorphicRelationPassRate, "metamorphicRelationPassRate"); rate(flakyDifferenceRate, "flakyDifferenceRate");
            rate(sourceTargetTraceCoverage, "sourceTargetTraceCoverage");
        }
    }

    public record ModuleGate(String moduleId, Gate gate, boolean eligibleForProductionHardening,
                             boolean eligibleForCutover, List<String> blockers,
                             List<String> restrictions, Metrics metrics) {
        public ModuleGate { text(moduleId, "moduleId"); required(gate, "gate"); blockers = copy(blockers); restrictions = copy(restrictions); required(metrics, "metrics"); }
    }

    public record ConformanceReport(int batch, String equivalenceRunId, RunStatus status,
                                    List<ModuleGate> modules, List<String> blockers,
                                    List<String> openBlockingObligations,
                                    boolean eligibleForProductionHardening,
                                    boolean eligibleForCutover, Instant evaluatedAt) {
        public ConformanceReport {
            if (batch != 9) throw new IllegalArgumentException("batch must be 9");
            text(equivalenceRunId, "equivalenceRunId"); required(status, "status"); modules = copy(modules);
            blockers = copy(blockers); openBlockingObligations = copy(openBlockingObligations); required(evaluatedAt, "evaluatedAt");
            if (eligibleForCutover) throw new IllegalArgumentException("Batch 9 never authorizes cutover");
        }
    }

    public record Outcome(Request request, EnvironmentAlignment alignment, List<CleanRun> cleanRuns,
                          List<Comparison> comparisons, List<RepairFeedback> repairFeedback,
                          ConformanceReport report) {
        public Outcome { cleanRuns = copy(cleanRuns); comparisons = copy(comparisons); repairFeedback = copy(repairFeedback); }
    }

    static <T> List<T> copy(Collection<T> values) { return values == null ? List.of() : List.copyOf(values); }
    static <T> Set<T> set(Collection<T> values) { return values == null ? Set.of() : Set.copyOf(values); }
    static <K,V> Map<K,V> map(Map<K,V> values) { return values == null ? Map.of() : Map.copyOf(values); }
    static void text(String value, String name) { if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is required"); }
    static void digest(String value, String name) {
        text(value, name);
        if (!value.matches("[a-fA-F0-9]{64}")) throw new IllegalArgumentException(name + " must be a sha-256 digest");
    }
    static void required(Object value, String name) { if (value == null) throw new IllegalArgumentException(name + " is required"); }
    static void rate(double value, String name) { if (value < 0.0 || value > 1.0 || Double.isNaN(value)) throw new IllegalArgumentException(name + " must be between 0 and 1"); }
}
